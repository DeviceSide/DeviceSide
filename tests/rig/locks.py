"""The rig's locks, in the git common dir so every worktree shares them: one on HA, and one per integration.

A run holds HA shared, unless it restarts HA or reloads device_side's entry (a deploy, a suite with device_side
options, --recover), and then exclusively. A run that deploys but has no option suites steps HA down to shared once
HA is back (Held.share_ha). It holds each integration it moves exclusively. So runs on different integrations go side
by side, and a deploy waits for every run and holds off new ones meanwhile.

flock drops a lock when its process dies, so nothing goes stale. Locks are taken in one order (the integrations
sorted, then HA), so two runs never each hold what the other waits for. A waiting run polls, and says who holds what
it waits for, with their Claude Code session so a waiting agent can message them.
"""

import contextlib
import fcntl
import getpass
import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, TextIO

from .profile import TOLERANCE_S

# HA's lock keeps the path of the single lock it replaced, so a run from an older checkout, which takes it
# exclusively, still keeps out every new run, and they it.
LOCK_NAME = "device_side-rig.lock"
# A deploy waiting for HA holds this, so new shared holders queue behind it rather than starve it.
TURNSTILE_NAME = "device_side-rig.turnstile.lock"
LOCK_POLL_S = 2.0  # how often a waiting run retries a lock
WORKSPACE_HELD = "Green"  # a cmux workspace's color while its run holds its locks
WORKSPACE_QUEUED = "Amber"  # ...while its run waits for them

Out = Callable[[str], None]


def integration_lock(integration: str) -> str:
    return f"device_side-rig.{integration}.lock"


@dataclass(frozen=True, slots=True)
class Claim:
    """What a run holds: HA, shared or exclusive, and these integrations, exclusively."""

    ha: Literal["shared", "exclusive"] = "shared"
    integrations: frozenset[str] = frozenset()

    @classmethod
    def everything(cls) -> Claim:
        return cls("exclusive", frozenset(TOLERANCE_S))

    @classmethod
    def of(cls, raw: object) -> Claim:
        """A claim from its journal form (as_json); anything else, such as a journal from before claims, claims
        everything."""
        if not isinstance(raw, dict) or raw.get("ha") not in ("shared", "exclusive"):
            return cls.everything()
        return cls(raw["ha"], frozenset(raw.get("integrations") or ()))

    def as_json(self) -> dict:
        return {"ha": self.ha, "integrations": sorted(self.integrations)}

    def covers(self, other: Claim) -> bool:
        return other.integrations <= self.integrations and (self.ha == "exclusive" or other.ha == "shared")

    def __or__(self, other: Claim) -> Claim:
        ha = "exclusive" if "exclusive" in (self.ha, other.ha) else "shared"
        return Claim(ha, self.integrations | other.integrations)

    def __str__(self) -> str:
        return f"HA {self.ha}" + "".join(f", {integration}" for integration in sorted(self.integrations))


@dataclass(slots=True)
class Held:
    """The locks a run holds, released together on close (or when the process ends)."""

    claim: Claim
    handles: list[TextIO] = field(default_factory=list)
    ha: TextIO | None = None  # HA's lock, among `handles`

    def share_ha(self, out: Out = print) -> None:
        """Step HA down from exclusive to shared, keeping the integrations: once a deploy's restart is done, a run with
        no option suites needs HA shared only. Nothing changes for a claim that holds HA shared.

        flock's conversion need not be atomic (it may drop the lock before taking the new one), so a run waiting for HA
        exclusively may slip in between; this then waits for it, saying who holds HA, as any shared claim does. The
        turnstile isn't taken: a run waiting for HA exclusively holds it, waiting on this very lock."""
        if self.claim.ha != "exclusive" or self.ha is None:
            return
        self.ha.truncate(0)  # shared holders leave no entry; cleared while still exclusive, so no one else's is lost
        self.ha.flush()
        wait_for_lock(self.ha, fcntl.LOCK_SH, out, "HA")
        self.claim = Claim("shared", self.claim.integrations)

    def close(self) -> None:
        for handle in reversed(self.handles):
            handle.close()
        self.handles.clear()
        self.ha = None

    def __enter__(self) -> Held:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def workspace_color(color: str | None) -> None:
    """Color the cmux workspace this run belongs to (`color` None clears it), so the sidebar shows who holds the locks
    and who queues. Best effort: it does nothing outside cmux, and a failure never stops a run."""
    workspace = os.environ.get("CMUX_WORKSPACE_ID")
    if not workspace or not shutil.which("cmux"):
        return
    action = ["--action", "set-color", "--color", color] if color else ["--action", "clear-color"]
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        subprocess.run(
            ["cmux", "workspace-action", "--workspace", workspace, *action],
            capture_output=True,
            timeout=5,
            check=False,
        )


def lock_entry(holder: str) -> str:
    """What a run writes into a lock it holds alone: `holder` and its pid, then how to reach whoever started it.

    Under Claude Code that is the path of the session's registry file, which the reader resolves to the session's
    current name (sessions can be renamed mid-run). Run from a terminal, it is the user and tty instead.
    """
    claude_pid = os.environ.get("CLAUDE_PID")
    if claude_pid:
        config = Path(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude").expanduser()
        return f"{holder} (pid {os.getpid()})\n{config / 'sessions' / f'{claude_pid}.json'}\n"
    who = f"user {getpass.getuser()}"
    try:
        who += f" on {os.ttyname(0).removeprefix('/dev/')}"
    except OSError:  # stdin is not a tty
        pass
    return f"{holder} (pid {os.getpid()}, {who})\n"


def lock_holder(entry: str) -> str:
    """Describe a lock's holder from its `lock_entry`, naming the Claude Code session that holds it, if any.

    The registry file is Claude Code's own, undocumented: when it is gone or unreadable, the holder line stands alone.
    """
    line, _, session_file = entry.strip().partition("\n")
    held_by = line or "an unnamed process"
    if not session_file:
        return held_by
    try:
        name = json.loads(Path(session_file).read_text())["name"]
    except OSError, ValueError, KeyError, TypeError:
        return held_by
    return f'{held_by}, Claude Code session "{name}" (SendMessage reaches it)'


def read_holder(handle: TextIO) -> str:
    handle.seek(0)
    return lock_holder(handle.read())


def write_holder(handle: TextIO, holder: str) -> None:
    handle.truncate(0)
    handle.write(lock_entry(holder))
    handle.flush()


def wait_for_lock(
    handle: TextIO, operation: int, out: Out, name: str = "the rig lock", holders: Callable[[], str] | None = None
) -> bool:
    """Take `operation` (LOCK_EX or LOCK_SH) on `handle`, polling while it is held and saying who holds it (`holders`,
    else the entry in the file), and again whenever that changes. Returns whether it had to wait."""
    waiting_on = None
    while True:
        try:
            fcntl.flock(handle, operation | fcntl.LOCK_NB)
            return waiting_on is not None
        except BlockingIOError:
            held_by = holders() if holders else read_holder(handle)
            if held_by != waiting_on:
                if waiting_on is None:
                    workspace_color(WORKSPACE_QUEUED)
                out(f"Another rig run holds {name}: {held_by}. Waiting for it to finish (Ctrl-C to give up)...")
                waiting_on = held_by
            time.sleep(LOCK_POLL_S)


def free(path: Path, operation: int = fcntl.LOCK_EX) -> bool:
    """Whether `operation` on `path` could be taken now: it is taken and dropped at once, leaving nothing held."""
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle, operation | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True


def held_by(path: Path) -> str | None:
    """Who holds `path` exclusively now, or None when nobody does; takes nothing."""
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return read_holder(handle)
    return None


def integration_holders(directory: Path, integrations: Iterable[str] = TOLERANCE_S) -> list[str]:
    """`integration: holder` for each of `integrations` someone holds."""
    return [
        f"{integration}: {holder}"
        for integration in sorted(integrations)
        if (holder := held_by(directory / integration_lock(integration)))
    ]


def ha_holders(directory: Path, own: Iterable[str] = ()) -> str:
    """Who holds HA: its exclusive holder, or, as shared holders leave no name, whoever holds an integration but the
    caller's `own`."""
    if exclusive := held_by(directory / LOCK_NAME):
        return f"{exclusive}, exclusively"
    sharing = integration_holders(directory, set(TOLERANCE_S) - set(own))
    return "shared by " + ("; ".join(sharing) if sharing else "a run on no integration")


def holders(directory: Path, claim: Claim) -> list[str]:
    """Who holds what `claim` would wait for, one line each; takes nothing."""
    lines = integration_holders(directory, claim.integrations)
    if exclusive := held_by(directory / LOCK_NAME):
        lines.append(f"HA: {exclusive}, exclusively")
    elif claim.ha == "exclusive" and not free(directory / LOCK_NAME):
        lines.append("HA: shared by the runs above" if lines else "HA: shared by a run on no other integration")
    return lines


def hold(claim: Claim, holder: str, directory: Path, out: Out = print) -> Held:
    """Take `claim`'s locks, waiting for each in turn: the integrations sorted, then HA, so no two runs each hold what
    the other waits for. Every lock held alone gets `holder`'s entry, for whoever waits on it.

    HA is taken through the turnstile: a shared claim passes it at once, while an exclusive one keeps it until it has
    HA, so the shared holders drain and no new one starts meanwhile."""
    held = Held(claim)
    waited = False
    try:
        for integration in sorted(claim.integrations):
            handle = (directory / integration_lock(integration)).open("a+")
            held.handles.append(handle)
            waited |= wait_for_lock(handle, fcntl.LOCK_EX, out, f"the {integration} lock")
            write_holder(handle, holder)
        with (directory / TURNSTILE_NAME).open("a+") as turnstile:
            waited |= wait_for_lock(turnstile, fcntl.LOCK_EX, out, "the turn for HA")
            write_holder(turnstile, f"{holder}, waiting for HA" if claim.ha == "exclusive" else holder)
            ha = (directory / LOCK_NAME).open("a+")
            held.handles.append(ha)
            held.ha = ha
            if claim.ha == "exclusive":
                waited |= wait_for_lock(ha, fcntl.LOCK_EX, out, "HA", lambda: ha_holders(directory, claim.integrations))
                write_holder(ha, holder)
            else:
                waited |= wait_for_lock(ha, fcntl.LOCK_SH, out, "HA")
    except BaseException:
        held.close()
        raise
    if waited:
        out(f"Rig locks acquired: {claim}.")
    workspace_color(WORKSPACE_HELD)
    return held


def wait_free(directory: Path, integrations: Iterable[str] | None = None, out: Out = print) -> None:
    """Return once nobody holds `integrations` (None: every lock, HA's included) and nobody holds HA exclusively,
    without taking anything.

    It says only that they were free at that moment; another run may take them before the caller's own run does.
    """
    names = sorted(TOLERANCE_S if integrations is None else integrations)
    everything = integrations is None
    while True:
        waited = False
        for integration in names:
            with (directory / integration_lock(integration)).open("a+") as handle:
                waited |= wait_for_lock(handle, fcntl.LOCK_SH, out, f"the {integration} lock")
        with (directory / LOCK_NAME).open("a+") as handle:
            if everything:
                waited |= wait_for_lock(handle, fcntl.LOCK_EX, out, "HA", lambda: ha_holders(directory))
            else:
                waited |= wait_for_lock(handle, fcntl.LOCK_SH, out, "HA")
        if not waited:  # one pass found them all free at once
            break
    what = "every rig lock is" if everything else ", ".join(names) + (" are" if len(names) > 1 else " is")
    out(f"{what[0].upper()}{what[1:]} free.")
