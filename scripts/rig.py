#!/usr/bin/env -S uv run python
"""Run the rig tests against the live HA, behind a human approval gate.

The rig is the household's own Home Assistant and its in-use lights. Nothing changes state before the gate:
preflight reads the profile, the adapter registry and the deployed tree hash, prints what will run, then asks.
DEVICE_SIDE_RIG_APPROVED=1 answers the gate for a non-interactive caller that already has a human's yes.

One run at a time: a lock in the git common dir, shared by every worktree; a second run waits for it. Each run deploys
and restarts HA onto its own checkout's tree when HA hasn't loaded it, so a run queued behind another tests its own
code. Ctrl-C mid-deploy waits for the deploy and HA's restart to finish before releasing the lock. The tests are the
step files in tests/rig/steps, run by tests/rig/engine.py; a full pass of an adapter rewrites its test record.

Ctrl-C, SIGTERM and SIGHUP stop a run, putting the devices back; a second one leaves them. What a run changes is
journaled first (next to the lock), so whatever a killed run leaves changed, the next run puts back before its gate, or
--recover alone does.

Under cmux the run colors its workspace: green holding the lock, amber waiting for it.

A profile (tests/rig/profiles/<name>.yaml) names the entities a run may move and what it pauses; --profile picks
one, and may be left out when there is only one.

A profile with `roam:` has bulbs the run moves round Hue -> ZHA -> Z2M -> Hue (tests/rig/roam.py): the suites run in
phases, Hue's with the fixed integrations', then ZHA's, then Z2M's, with a move before each and one home at the end.
--recover, and the replay before the next run's gate, move them home. --roam-check runs the cycle with no suites.

Usage: scripts/rig.py [--profile NAME] [--dry-run] [--no-deploy] [--unattended] [--integration KEY ...]
                      [--action NAME ...] [-k TEXT]
       scripts/rig.py [--profile NAME] --roam-check
       scripts/rig.py --recover
       scripts/rig.py --wait-free
"""

import argparse
import asyncio
import contextlib
import datetime
import fcntl
import getpass
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Coroutine, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from custom_components.device_side.core.registry import AdapterRegistry  # noqa: E402
from tests.rig.bridge import HueBridge  # noqa: E402
from tests.rig.client import HAClient  # noqa: E402
from tests.rig.engine import (  # noqa: E402
    ADMIN_INTEGRATIONS,
    EntryOptions,
    RunResult,
    Snapshot,
    StepFile,
    Suite,
    SuiteResult,
    cases,
    load_step_files,
    run,
    write_records,
    write_report,
)
from tests.rig.journal import Journal  # noqa: E402
from tests.rig.profile import (  # noqa: E402
    CYCLE,
    EXAMPLE,
    LEGACY_INVENTORY,
    PROFILES_DIR,
    Profile,
    load_env,
    profile_paths,
)
from tests.rig.roam import HOME, NAMES, Bulb, Roamer, RoamError  # noqa: E402
from tests.rig.roam import plan_lines as roam_plan_lines  # noqa: E402

COMPONENT = "custom_components/device_side"
TEST_RECORDS_DIR = REPO / "docs" / "test-records"
SERVICE = ("device_side", "turn_on_for")
# HA's bootstrap stage-1 (120 s) and stage-2 (300 s) timeouts, after which a stuck dependency is let go, plus the
# container's start. A restart behind a hung ZHA took about 350 s.
READY_TIMEOUT_S = 450
# A target still unavailable this long after HA is ready is most likely unpowered, so the run stops rather than fail
# every case; the grace covers an integration whose entities come back just after the restart.
TARGETS_TIMEOUT_S = 60
RESTART_ESTIMATE_S = 90
ROAM_ESTIMATE_S = 180  # the three moves: the probe's joins took about 10 s each, plus releases, renames and HA
LOCK_NAME = "device_side-rig.lock"
LOCK_POLL_S = 2.0  # how often a waiting run retries the lock
WORKSPACE_HELD = "Green"  # a cmux workspace's color while its run holds the lock
WORKSPACE_QUEUED = "Amber"  # ...while its run waits for the lock
JOURNAL_NAME = "device_side-rig.journal.json"
ABORT_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
# Run reports go where the OS clears old files: they are for reviewing a run, not for keeping.
REPORT_DIR = Path(tempfile.gettempdir()) / "device_side-rig"


class Aborted(Exception):
    """A signal before the tests start; the run ends on its message."""


@dataclass(slots=True)
class Deploy:
    commit: str  # HEAD at the plan, whose tree local_tree is
    local_tree: str
    synced_tree: str | None  # on disk in HA's config
    loaded_tree: str | None  # what HA last restarted onto
    branch: str
    blocker: str | None = None

    @property
    def needed(self) -> bool:
        """Also when only the loaded tree differs: a failed restart leaves the synced tree unloaded."""
        return not self.local_tree == self.synced_tree == self.loaded_tree


def git(*args: str, check: bool = True) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], check=check, capture_output=True, text=True).stdout.strip()


def select(
    step_files: list[StepFile], profile: Profile, integrations: list[str] | None, actions: list[str] | None = None
) -> list[Suite]:
    """Every step file on every integration in the profile, narrowed to --integration and --action. An action takes
    every step file for it (lower_brightness and lower_brightness-predicted_state), whole, so each still writes its
    record."""
    return [
        Suite(step_file, integration)
        for step_file in step_files
        if not actions or step_file.action in actions
        for integration in profile.integrations
        if not integrations or integration in integrations
    ]


def roams(profile: Profile, suites: list[Suite], roam_check: bool = False) -> bool:
    """Whether the run moves the profile's bulbs: for --roam-check, or a ZHA or Z2M suite. Hue's suites and the fixed
    integrations' run with the bulbs at home, so a run of only those stays there."""
    return bool(profile.roam) and (roam_check or any(suite.integration in CYCLE[1:] for suite in suites))


def phases(suites: list[Suite], roaming: bool) -> list[tuple[str | None, list[Suite]]]:
    """The run's phases, each a network to move the bulbs to (None: no move) and the suites run there. Roaming, the
    cycle's: Hue's suites with the fixed integrations', then ZHA's, then Z2M's, each in select's order."""
    if not roaming:
        return [(None, suites)]
    return [
        (network, [suite for suite in suites if (suite.integration if suite.integration in CYCLE else HOME) == network])
        for network in CYCLE
    ]


def plan_lines(
    suites: list[Suite],
    profile: Profile,
    registry: AdapterRegistry,
    keyword: str | None = None,
) -> list[str]:
    """Per adapter about to run: the household entities it will move, then each test case."""
    lines = []
    for suite in suites:
        if registry.adapter(suite.action, suite.integration) is None:
            lines.append(f"{suite.integration} / {suite.action} (no adapter, will skip)")
            continue
        roles = suite.file.roles
        entities = [entity for role in roles if (entity := profile.entity(suite.integration, role))]
        targets = ", ".join(dict.fromkeys(entities)) or "no entity, will skip"
        lines.append(f"{suite.integration} / {suite.name} -> {targets}")
        for case in cases(suite, profile, keyword):
            lines.append(f"    {case.id}: {case.skip or ', '.join(dict.fromkeys(case.entities.values()))}")
    return lines


def estimate(suites: list[Suite], registry: AdapterRegistry, restarting: bool, roaming: bool = False) -> int:
    seconds = sum(suite.file.rig_seconds for suite in suites if registry.adapter(suite.action, suite.integration))
    return seconds + (RESTART_ESTIMATE_S if restarting else 0) + (ROAM_ESTIMATE_S if roaming else 0)


def deployed_trees(status_cmd: str) -> tuple[str | None, str | None]:
    """The synced and loaded tree hashes, each None if unknown: RIG_STATUS_CMD unset, never synced (exit 91), or a
    line missing. It prints `synced <tree>` and `loaded <tree>` lines; a bare hash, from older tooling, counts as both.
    """
    if not status_cmd:
        return None, None
    result = subprocess.run(status_cmd.split(), capture_output=True, text=True)
    if result.returncode == 91:
        return None, None
    if result.returncode != 0:
        raise SystemExit(f"{status_cmd} failed ({result.returncode}): {result.stderr.strip()}")
    output = result.stdout.strip()
    if output and " " not in output:
        return output, output
    trees = dict(line.split(maxsplit=1) for line in output.splitlines() if " " in line.strip())
    return trees.get("synced"), trees.get("loaded")


def deploy_state(status_cmd: str) -> Deploy:
    """Whether HA runs this checkout's integration, and if not, whether origin has it to deploy.

    The deploy sync command installs a branch tip from GitHub, never the working tree, so a
    deploy needs the change pushed.
    """
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    commit = git("rev-parse", "HEAD")
    synced, loaded = deployed_trees(status_cmd)
    state = Deploy(
        commit=commit,
        local_tree=git("rev-parse", f"{commit}:{COMPONENT}"),
        synced_tree=synced,
        loaded_tree=loaded,
        branch=branch,
    )
    if git("status", "--porcelain", "--", COMPONENT):
        state.blocker = f"uncommitted changes under {COMPONENT}; commit and push them first"
        return state
    if not state.needed:
        return state
    remote = git("ls-remote", "origin", f"refs/heads/{branch}").split()
    if not remote:
        state.blocker = f"{branch} is not on origin; push it first"
    elif git("rev-parse", "--quiet", "--verify", f"{remote[0]}:{COMPONENT}", check=False) != state.local_tree:
        state.blocker = f"origin/{branch} does not match HEAD under {COMPONENT}; push first"
    return state


def check_deploy(env: dict, deploy: Deploy) -> None:
    """Raise SystemExit if the deploy cannot proceed: missing commands or a git blocker."""
    if not env.get("RIG_SYNC_CMD"):
        raise SystemExit("RIG_SYNC_CMD must be set in .env.rig to deploy (see tests/rig/env.example)")
    if not env.get("RIG_RESTART_CMD"):
        raise SystemExit("RIG_RESTART_CMD must be set in .env.rig to restart (see tests/rig/env.example)")
    if deploy.blocker:
        raise SystemExit(f"Cannot deploy: {deploy.blocker}.")


def workspace_color(color: str | None) -> None:
    """Color the cmux workspace this run belongs to (`color` None clears it), so the sidebar shows who holds the lock
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
    """What a run writes into the lock: `holder` and its pid, then how to reach whoever started it.

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
    """Describe the lock's holder from its `lock_entry`, naming the Claude Code session that holds it, if any.

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


def wait_for_lock(handle: TextIO, operation: int, out: Callable[[str], None]) -> bool:
    """Take `operation` (LOCK_EX or LOCK_SH) on `handle`, polling while a run holds the lock and saying who holds it,
    and again whenever that changes. Returns whether it had to wait."""
    waiting_on = None
    while True:
        try:
            fcntl.flock(handle, operation | fcntl.LOCK_NB)
            return waiting_on is not None
        except BlockingIOError:
            handle.seek(0)
            held_by = lock_holder(handle.read())
            if held_by != waiting_on:
                if waiting_on is None:
                    workspace_color(WORKSPACE_QUEUED)
                out(f"Another rig run holds the lock: {held_by}. Waiting for it to finish (Ctrl-C to give up)...")
                waiting_on = held_by
            time.sleep(LOCK_POLL_S)


def lock_rig(path: Path, holder: str, out: Callable[[str], None] = print) -> TextIO:
    """Hold an exclusive lock on `path` for the process's life, waiting while another run has it.

    One lock in the git common dir covers every worktree. flock drops when the process dies, so nothing goes stale.
    A waiting run says who holds the lock (with its Claude Code session, so a waiting agent can message it), and again
    whenever that changes. Waiting runs poll rather than queue, so when several wait, whichever polls first after a
    release goes next.
    """
    handle = path.open("a+")
    if wait_for_lock(handle, fcntl.LOCK_EX, out):
        out("Rig lock acquired.")
    handle.truncate(0)
    handle.write(lock_entry(holder))
    handle.flush()
    workspace_color(WORKSPACE_HELD)
    return handle


def wait_free(path: Path, out: Callable[[str], None] = print) -> None:
    """Return once no run holds the lock on `path`, without taking it: a shared lock, dropped at once.

    It says only that the rig was free at that moment; another run may take the lock before the caller's own run does.
    """
    with path.open("a+") as handle:
        wait_for_lock(handle, fcntl.LOCK_SH, out)
        fcntl.flock(handle, fcntl.LOCK_UN)
    out("The rig lock is free.")


def gate(prompt: Callable[[str], str] = input) -> bool:
    if os.environ.get("DEVICE_SIDE_RIG_APPROVED") == "1":
        print("Approved by DEVICE_SIDE_RIG_APPROVED=1.")
        return True
    try:
        return prompt("Proceed? [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def _get(url: str, token: str) -> Any:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def wait_until_ready(
    url: str,
    token: str,
    admin_token: str | None = None,
    timeout: float = READY_TIMEOUT_S,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Until HA reports RUNNING and lists device_side.turn_on_for; exits the runner on timeout, saying why when HA
    answers without it, still starting or running."""
    deadline = time.monotonic() + timeout
    state = None
    while time.monotonic() < deadline:
        state = None  # only the last poll counts: HA that was RUNNING may have crashed since
        try:
            state = _get(f"{url}/api/config", token).get("state")
            if state == "RUNNING":
                services = {entry["domain"]: entry["services"] for entry in _get(f"{url}/api/services", token)}
                if SERVICE[1] in services.get(SERVICE[0], {}):
                    return
        except urllib.error.URLError, OSError, ValueError, TypeError, KeyError, AttributeError:
            pass
        sleep(3)
    if state == "RUNNING":
        raise SystemExit(f"HA is running but has no {'.'.join(SERVICE)}. {diagnose(url, admin_token)}")
    if state is not None:
        raise SystemExit(f"HA is still starting after {timeout:.0f}s ({state}). {diagnose(url, admin_token)}")
    raise SystemExit(f"HA did not report RUNNING within {timeout:.0f}s; check HA logs for errors.")


def diagnose(url: str, admin_token: str | None) -> str:
    """Why device_side's actions are missing, from HA's config entries, which only an admin may read."""
    manifest = json.loads((REPO / COMPONENT / "manifest.json").read_text())
    waits_for = manifest.get("after_dependencies", [])
    if not admin_token:
        return (
            "Without HA_ADMIN_TOKEN in .env.rig the runner can't read config entries to say why; check device_side "
            f"and the integrations it waits for ({', '.join(waits_for)}) in Settings > Devices & services."
        )
    try:
        entries = asyncio.run(config_entries(url, admin_token))
    except Exception as err:  # noqa: BLE001 - the diagnosis is a hint; the run is already stopping
        return f"Could not read config entries to say why: {err!r}."
    return explain(entries, waits_for)


async def config_entries(url: str, admin_token: str) -> list[dict]:
    admin = HAClient(url, admin_token)
    try:
        await admin.connect()
        return await admin.command({"type": "config_entries/get"})
    finally:
        await admin.close()


def explain(entries: list[dict], waits_for: list[str]) -> str:
    """device_side's entry state and each integration it waits for whose enabled entry isn't loaded: HA sets up
    device_side only after their entries finish setting up, so one stuck in setup holds it back."""
    own = [entry["state"] for entry in entries if entry["domain"] == SERVICE[0]]
    if not own:
        return (
            "On a first load, add the integration (Settings > Devices & services > Add integration > Device Side), "
            "then rerun."
        )
    stuck = [
        f"{entry['domain']} ({entry['state']})"
        for entry in entries
        if entry["domain"] in waits_for and entry["state"] != "loaded" and not entry.get("disabled_by")
    ]
    why = (
        f"it waits for {', '.join(stuck)}"
        if stuck
        else f"none of the integrations it waits for ({', '.join(waits_for)}) is stuck; check HA's logs"
    )
    return (
        f"device_side's entry is {', '.join(own)}; {why}. "
        "device_side actions are unavailable in the house until this is fixed."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", help="the profile to run (tests/rig/profiles/NAME.yaml); needed if there are two")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and stop before the gate")
    parser.add_argument("--no-deploy", action="store_true", help="test whatever HA already runs")
    parser.add_argument("--integration", action="append", help="limit to an integration key (repeatable)")
    parser.add_argument("--action", action="append", help="limit to an action's step files (repeatable)")
    parser.add_argument("-k", dest="keyword", help="run only test cases whose id contains this text")
    parser.add_argument("--unattended", action="store_true", help="skip observed tests, reporting them not observed")
    parser.add_argument("--recover", action="store_true", help="put back what an aborted run left changed, then stop")
    parser.add_argument(
        "--roam-check", action="store_true", help="move the profile's roam bulbs round the cycle and home, no suites"
    )
    parser.add_argument(
        "--wait-free",
        action="store_true",
        help="wait until no rig run holds the lock, without taking it; another run may take it first",
    )
    args = parser.parse_args(argv)
    colors = args.wait_free or not args.dry_run  # a dry run holds no lock and sets no color, so it clears none
    try:
        with handling_signals(leave):  # a run killed while it waits still clears its color
            return wait_or_run(args)
    finally:
        if colors:
            workspace_color(None)


def leave(signum: int, _frame: object) -> None:
    """Stop a run that holds nothing yet, with the shell's exit code for the signal."""
    raise SystemExit(128 + signum)


def wait_or_run(args: argparse.Namespace) -> int:
    if args.wait_free:
        wait_free(common_dir() / LOCK_NAME)
        return 0

    _held, journal = hold_rig(args.dry_run)  # the lock is held until exit
    try:
        with end_on_signals():
            return run_held(args, journal)
    except Aborted as err:
        print(err)
        return 1


def run_held(args: argparse.Namespace, journal: Journal) -> int:
    """The run, once the lock is held."""
    env = load_env()
    replay(env, journal, args.dry_run, args.recover)
    if args.recover:
        return 1 if journal else 0
    try:
        profile = Profile.load(choose_profile(args.profile, env))
    except ValueError as err:
        raise SystemExit(f"Fix the profile: {err}") from err
    registry = AdapterRegistry.discover()
    if args.roam_check:
        if not profile.roam:
            raise SystemExit(f"--roam-check needs a profile with roam:, and {profile.name} has none")
        suites = []
    else:
        suites = select(load_step_files(), profile, args.integration, args.action)
        if not any(registry.adapter(suite.action, suite.integration) for suite in suites):
            raise SystemExit("No rig test matches the profile's integrations.")
    roaming = roams(profile, suites, args.roam_check)
    if not args.dry_run:
        check_tokens(env, suites, registry, roaming)
    deploy = deploy_state(env.get("RIG_STATUS_CMD", ""))
    deploying = deploy.needed and not args.no_deploy and not args.roam_check  # the check runs none of our code
    print_plan(profile, suites, registry, args.keyword, deploy, deploying, roaming)

    if deploying:
        check_deploy(env, deploy)
    if args.dry_run:
        return 0
    if not gate():
        print("Not approved; nothing changed.")
        return 1

    deploy_and_wait(env, deploy.branch if deploying else None)
    commit = tested_commit(env.get("RIG_STATUS_CMD", ""), deploy, deploying)
    return run_tests(
        run_rig(env, suites, profile, registry, args.keyword, args.unattended, commit, journal, roaming=roaming)
    )


def choose_profile(
    name: str | None,
    env: dict,
    directory: Path = PROFILES_DIR,
    legacy: Path = LEGACY_INVENTORY,
    example: Path = EXAMPLE,
) -> Path:
    """The profile --profile names, else the only one. Refuses while the setup still has the single inventory.yaml or
    RIG_PAUSE that profiles replaced, so nothing runs against half a migration."""
    if legacy.exists():
        raise SystemExit(
            f"{legacy} is now a profile: move it to {directory}/<name>.yaml (see {example}), and its RIG_PAUSE with it"
        )
    if env.get("RIG_PAUSE"):
        raise SystemExit("RIG_PAUSE has moved from .env.rig into the profile, as `pause:` (see tests/rig/profiles)")
    paths = {path.stem: path for path in profile_paths(directory)}
    if name is not None:
        if name not in paths:
            raise SystemExit(f"No profile {name!r} in {directory}; there are: {', '.join(paths) or 'none'}")
        return paths[name]
    if not paths:
        raise SystemExit(f"No profile in {directory}; copy {example} to <name>.yaml there and fill it in")
    if len(paths) > 1:
        raise SystemExit(f"Choose a profile with --profile: {', '.join(paths)}")
    return next(iter(paths.values()))


def tested_commit(status_cmd: str, deploy: Deploy, deploying: bool) -> str | None:
    """The commit whose integration tree HA loaded for the tests, or None if none can be named: under --no-deploy HA
    runs whatever it last loaded, and a deploy may install a different tip if origin moved past the plan (trusted when
    HA can't say what it loaded). Read before the tests, since HEAD moves when the session commits mid-run."""
    if not deploying:
        return None if deploy.needed else deploy.commit
    loaded = deployed_trees(status_cmd)[1]
    return deploy.commit if loaded in (None, deploy.local_tree) else None


def deploy_and_wait(env: dict, branch: str | None) -> None:
    """Deploy `branch` (None: don't), then wait for HA; a deploy holds off a signal until HA is back."""
    with finish_first() if branch is not None else contextlib.nullcontext():
        if branch is not None:
            deploy_env = {**os.environ, "RIG_SYNC_CMD": env["RIG_SYNC_CMD"], "RIG_RESTART_CMD": env["RIG_RESTART_CMD"]}
            try:
                # Its own session, so a Ctrl-C at the terminal reaches only the runner, which holds it.
                subprocess.run(
                    ["sh", str(REPO / "scripts" / "deploy.sh"), branch],
                    check=True,
                    env=deploy_env,
                    start_new_session=True,
                )
            except subprocess.CalledProcessError as err:
                raise SystemExit(
                    f"Deploy failed (exit {err.returncode}); HA may be mid-restart, so check it before the next run."
                ) from None
        timeout = READY_TIMEOUT_S if branch is not None else 15
        wait_until_ready(env["HA_URL"].rstrip("/"), env["HA_TOKEN"], env.get("HA_ADMIN_TOKEN"), timeout)


@contextlib.contextmanager
def end_on_signals() -> Iterator[None]:
    """Until the tests take over (cancel_on_signals), have Ctrl-C, SIGTERM and SIGHUP end the run on one line rather
    than a traceback. What a recovery had yet to put back stays in the journal."""

    def abort(_signum: int, _frame: object) -> None:
        raise Aborted("Aborted.")

    with handling_signals(abort):
        yield


@contextlib.contextmanager
def finish_first() -> Iterator[None]:
    """Hold off a signal until the block ends, then stop: the deploy and HA's restart finish under the lock, so the next
    run doesn't sync into a booting HA. A second signal stops at once."""
    held: list[int] = []

    def hold(signum: int, _frame: object) -> None:
        if held:
            raise Aborted("Aborted mid-deploy; HA may be mid-restart, so check it before the next run.")
        held.append(signum)
        print("\nStopping once the deploy and HA's restart finish; again to stop now.")

    with handling_signals(hold):
        yield
    if held:
        raise Aborted("Aborted after the deploy.")


@contextlib.contextmanager
def handling_signals(handler: Callable[[int, object], None]) -> Iterator[None]:
    previous = {signum: signal.signal(signum, handler) for signum in ABORT_SIGNALS}
    try:
        yield
    finally:
        for signum, before in previous.items():
            signal.signal(signum, before)


def hold_rig(dry_run: bool) -> tuple[TextIO | None, Journal]:
    """The rig lock, unless it is a dry run, and the journal, read once the lock is held: whoever last held it has
    exited, so the journal is what it left."""
    shared = common_dir()
    lock = None if dry_run else lock_rig(shared / LOCK_NAME, git("rev-parse", "--abbrev-ref", "HEAD"))
    return lock, Journal(shared / JOURNAL_NAME)


def common_dir() -> Path:
    """The git common dir, shared by every worktree, where the lock and the journal live."""
    return Path(git("rev-parse", "--path-format=absolute", "--git-common-dir"))


def run_tests(rig_run: Coroutine[Any, Any, int]) -> int:
    """Run run_rig, ending on one line rather than a traceback when a signal stops it (cancel_on_signals)."""
    try:
        return asyncio.run(rig_run)
    except asyncio.CancelledError:
        print("Aborted.")
    except KeyboardInterrupt:  # a second Ctrl-C, mid-cleanup
        print("Aborted before putting everything back; the next run puts back the rest.")
    return 1


def replay(env: dict, journal: Journal, dry_run: bool, asked: bool) -> None:
    """Put back what an aborted run left changed. A dry run holds no lock, so the run may still be going: it only says
    the journal is there."""
    if not journal:
        if asked:
            print("No aborted run left anything to put back.")
    elif dry_run:
        print(f"An aborted run left changes in {journal.path}; the next run puts them back before its gate.")
    else:
        asyncio.run(recover_rig(env, journal))


def check_tokens(env: dict, suites: list[Suite], registry: AdapterRegistry, roaming: bool = False) -> None:
    """Stop before the gate when .env.rig lacks a token the run needs: ADMIN_INTEGRATIONS and any adapter with
    options (they are set through device_side's options flow) need HA_ADMIN_TOKEN; a Hue file with a bridge step
    needs the bridge's host and key; roaming needs both, for the registries, MQTT and the bridge."""
    if not (env.get("HA_URL") and env.get("HA_TOKEN")):
        raise SystemExit("HA_URL and HA_TOKEN must be set in .env.rig (see tests/rig/env.example)")
    bridge = env.get("HUE_BRIDGE_HOST") and env.get("HUE_APP_KEY")
    if any(suite.integration == "hue" and suite.file.uses_bridge for suite in suites) and not bridge:
        raise SystemExit("HUE_BRIDGE_HOST and HUE_APP_KEY must be set in .env.rig for the bridge step")
    if roaming and not (bridge and env.get("HA_ADMIN_TOKEN")):
        raise SystemExit("Roaming needs HA_ADMIN_TOKEN, HUE_BRIDGE_HOST and HUE_APP_KEY in .env.rig")
    if env.get("HA_ADMIN_TOKEN"):
        return
    with_options = {
        suite.integration
        for suite in suites
        if (adapter := registry.adapter(suite.action, suite.integration)) is not None and adapter.scope.options
    }
    if admin_only := sorted(({suite.integration for suite in suites} & ADMIN_INTEGRATIONS) | with_options):
        raise SystemExit(
            f"{', '.join(admin_only)} needs HA_ADMIN_TOKEN in .env.rig (an admin user's token), "
            "or leave it out with --integration"
        )


def print_plan(
    profile: Profile,
    suites: list[Suite],
    registry: AdapterRegistry,
    keyword: str | None,
    deploy: Deploy,
    deploying: bool,
    roaming: bool = False,
) -> None:
    print_profile(profile)
    print_phases(profile, suites, registry, keyword, roaming)
    print(
        f"Integration: local {deploy.local_tree[:12]}, synced {(deploy.synced_tree or 'unknown')[:12]}, "
        f"loaded {(deploy.loaded_tree or 'unknown')[:12]}"
    )
    if deploying:
        print(f"Deploy: sync {deploy.branch}, then restart Home Assistant")
    elif deploy.needed and suites:
        print("Deploy: skipped (--no-deploy); tests run the deployed tree, not this checkout, and write no record")
    else:
        print("Deploy: not needed, no restart")
    seconds = estimate(suites, registry, deploying, roaming)
    print(f"Estimated duration: {seconds} s. These are in-use household devices; they will visibly change state.")


def print_profile(profile: Profile) -> None:
    """The profile's entities by integration, its roaming bulbs once each, and its pause list."""
    print(f"Profile {profile.name}:")
    roaming_ids = {bulb.entity_id for bulb in profile.roam}
    for integration, entities in profile.integrations.items():
        for entity in entities:
            if entity.entity_id not in roaming_ids:
                print(f"  {integration:8} {entity.entity_id:40} {', '.join(sorted(entity.roles))}")
    for bulb in profile.roam:
        print(f"  {'roams':8} {bulb.entity_id:40} {', '.join(sorted(bulb.roles))}")
    if profile.pause:
        print(f"Paused while it runs: {', '.join(profile.pause)}")


def print_phases(
    profile: Profile, suites: list[Suite], registry: AdapterRegistry, keyword: str | None, roaming: bool
) -> None:
    """The moves, if the run roams, then each phase's adapters and cases."""
    if roaming:
        print("\n".join(roam_plan_lines(profile.roam)))
    elif profile.roam:
        print("Roaming: none, as no ZHA or Z2M suite runs; the bulbs stay on Hue.")
    for network, phase_suites in phases(suites, roaming):
        print(f"Adapters on {NAMES[network]}:" if network else "Adapters:")
        for line in plan_lines(phase_suites, profile, registry, keyword) or ["none"]:
            print(f"  {line}")


async def run_rig(
    env: dict,
    suites: list[Suite],
    profile: Profile,
    registry: AdapterRegistry,
    keyword: str | None,
    unattended: bool,
    commit: str | None,
    journal: Journal | None = None,
    roaming: bool = False,
) -> int:
    """Run the step files phase by phase, moving the roaming bulbs before each and home after the last, then write a
    test record for each adapter whose every test passed, citing `commit`; with no commit, none: a record nobody can
    trace to a commit proves nothing. Roaming needs the admin connection and the bridge (check_tokens)."""
    if roaming and not (env.get("HA_ADMIN_TOKEN") and env.get("HUE_BRIDGE_HOST") and env.get("HUE_APP_KEY")):
        raise SystemExit("Roaming needs HA_ADMIN_TOKEN, HUE_BRIDGE_HOST and HUE_APP_KEY in .env.rig")
    cancel_on_signals()
    ha, admin = await connect(env)
    bridge = None
    if env.get("HUE_BRIDGE_HOST") and env.get("HUE_APP_KEY"):
        bridge = HueBridge(env["HUE_BRIDGE_HOST"], env["HUE_APP_KEY"])
    roamer = Roamer(admin, bridge, map(Bulb.of, profile.roam), journal) if roaming else None
    paused: list[str] = []
    home = True  # whether the roaming bulbs ended at home
    if journal is not None:
        journal.update(profile=profile.name)
    try:
        result = await run_phases(
            ha, admin, bridge, roamer, suites, profile, registry, keyword, unattended, paused, journal
        )
        if suites:
            await report(result, ha, registry, commit, profile)
    except RoamError as err:
        roamer = None  # a move that failed isn't retried here; the journal keeps where the bulbs are, for --recover
        raise SystemExit(f"Roaming stopped: {err}") from None
    finally:
        if roamer is not None:
            home = await go_home(roamer)
        await resume(ha, paused, journal)
        drop_profile(journal)
        if bridge:
            await bridge.close()
        await ha.close()
        if admin:
            await admin.close()
    return 1 if result.failed or not home else 0


async def run_phases(
    ha: HAClient,
    admin: HAClient | None,
    bridge: HueBridge | None,
    roamer: Roamer | None,
    suites: list[Suite],
    profile: Profile,
    registry: AdapterRegistry,
    keyword: str | None,
    unattended: bool,
    paused: list[str],
    journal: Journal | None,
) -> RunResult:
    """Each phase: move the bulbs there, wait for its targets, then run its cases, automated then observed. The
    automations are paused once, after the first phase's targets are all there."""
    results: list[SuiteResult] = []
    for number, (network, phase_suites) in enumerate(phases(suites, roamer is not None)):
        if roamer is not None:
            await roamer.go(network)
        if phase_suites:
            await wait_for_targets(ha, phase_suites, profile, registry, keyword)
        if number == 0:
            await pause(ha, list(profile.pause), paused, journal)
        if phase_suites:
            ask = None if unattended else input
            phase = await run(
                phase_suites,
                profile,
                registry,
                ha,
                admin=admin,
                keyword=keyword,
                ask=ask,
                bridge=bridge,
                journal=journal,
            )
            results += phase.suites
    if roamer is not None:
        await roamer.go(HOME)
    return RunResult(results)


async def report(result: RunResult, ha: HAClient, registry: AdapterRegistry, commit: str | None, profile: Profile):
    """The run's report, and a test record per fully passed suite when a commit names the tree HA ran."""
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\nReport: {write_report(result, REPORT_DIR, f'rig run {stamp}')}")
    if commit is None:
        print("No test records: no commit names the tree HA ran (--no-deploy, or origin moved before the deploy).")
        return
    source = f"rig run (`scripts/rig.py`), commit `{git('rev-parse', '--short', commit)}`"
    today = datetime.date.today().isoformat()
    for path in await write_records(result, ha, registry, TEST_RECORDS_DIR, today, source, profile.name):
        print(f"Wrote {path.relative_to(REPO)}; review the diff before committing it.")


async def go_home(roamer: Roamer) -> bool:
    """Move the roaming bulbs home after a run that stopped part way (a no-op after one that finished). A failure is
    printed: the journal keeps where they are, and --recover tries again."""
    try:
        await roamer.go(HOME)
    except Exception as err:  # noqa: BLE001 - as resume: say so, and go on putting the rest back
        print(f"Could not move the roaming bulbs home: {err}. scripts/rig.py --recover tries again.")
        return False
    return True


async def wait_for_targets(
    ha: HAClient,
    suites: list[Suite],
    profile: Profile,
    registry: AdapterRegistry,
    keyword: str | None,
    timeout: float = TARGETS_TIMEOUT_S,
) -> None:
    """Until every entity a case will move, a group's listed members included, is available; exits the runner, naming
    the rest, after `timeout`, or at once for one HA doesn't have."""

    def available(state: dict | None) -> bool:
        return state is not None and state["state"] != "unavailable"

    entities = sorted(
        {
            entity
            for suite in suites
            if registry.adapter(suite.action, suite.integration)
            for case in cases(suite, profile, keyword)
            if not case.skip
            for entity in (*case.entities.values(), *case.members)
        }
    )
    states = dict(zip(entities, await asyncio.gather(*map(ha.get_state, entities)), strict=True))
    if missing := [entity for entity, state in states.items() if state is None]:
        raise SystemExit(f"Not in HA: {', '.join(missing)}. Check profile {profile.name}; nothing was changed.")
    waiting = [entity for entity, state in states.items() if not available(state)]
    if not waiting:
        return
    print(f"Waiting up to {timeout:.0f} s for {', '.join(waiting)} to become available.")
    results = await asyncio.gather(
        *(ha.wait_for(entity, available, timeout) for entity in waiting), return_exceptions=True
    )
    for result in results:
        if isinstance(result, BaseException) and not isinstance(result, TimeoutError):
            raise result
    if still := [entity for entity, result in zip(waiting, results, strict=True) if isinstance(result, TimeoutError)]:
        raise SystemExit(
            f"Still unavailable after {timeout:.0f} s: {', '.join(still)}. Check it is powered; nothing was changed."
        )


def cancel_on_signals() -> None:
    """Have Ctrl-C, SIGTERM and SIGHUP cancel the running task, so its finally blocks put the devices back. The first
    one restores the default handlers: a second kills the process (Ctrl-C: interrupts it), leaving the journal."""
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()

    def abort() -> None:
        for signum in ABORT_SIGNALS:
            loop.remove_signal_handler(signum)
        print("\nAborting: putting devices back.")
        task.cancel()

    for signum in ABORT_SIGNALS:
        loop.add_signal_handler(signum, abort)


async def connect(env: dict) -> tuple[HAClient, HAClient | None]:
    """The HA connection, and the admin one when .env.rig has HA_ADMIN_TOKEN."""
    ha = HAClient(env["HA_URL"], env["HA_TOKEN"])
    admin = HAClient(env["HA_URL"], env["HA_ADMIN_TOKEN"]) if env.get("HA_ADMIN_TOKEN") else None
    await ha.connect()
    if admin:
        await admin.connect()
    return ha, admin


async def recover_rig(env: dict, journal: Journal) -> None:
    if not (env.get("HA_URL") and env.get("HA_TOKEN")):
        raise SystemExit("HA_URL and HA_TOKEN must be set in .env.rig to put back what an aborted run left changed")
    ha, admin = await connect(env)
    bridge = None
    if env.get("HUE_BRIDGE_HOST") and env.get("HUE_APP_KEY"):
        bridge = HueBridge(env["HUE_BRIDGE_HOST"], env["HUE_APP_KEY"])
    try:
        await recover(ha, admin, journal, bridge=bridge)
    finally:
        if bridge:
            await bridge.close()
        await ha.close()
        if admin:
            await admin.close()


async def recover(
    ha: HAClient,
    admin: HAClient | None,
    journal: Journal,
    out: Callable[[str], None] = print,
    bridge: HueBridge | None = None,
) -> None:
    """Put back what an aborted run left changed, in the order its finally blocks would have: the case's entities,
    device_side's options, the roaming bulbs (moved home, their Hue rooms and scenes put back), the paused automations.
    A step that fails is printed and dropped from the journal; options stay in it while there is no admin connection
    to set them. The bulbs can't be left half done, so a failure there stops recovery, keeping the rest journaled."""
    run_of = f" (profile {name})" if (name := journal.get("profile")) else ""
    out(f"An aborted rig run{run_of} left changes in {journal.path}; putting them back.")
    if taken := journal.get("taken"):
        for entity_id, state in taken.items():
            if state is not None and state["state"] in ("on", "off"):
                out(f"Putting {entity_id} back {state['state']}.")
        power, stored = journal.get("power", {}), journal.get("stored", {})
        await Snapshot(ha, power, taken=taken, stored=stored, journal=journal).restore()
    if (options := journal.get("options")) is not None:
        if admin is None:
            out("Putting device_side's options back needs HA_ADMIN_TOKEN in .env.rig; they stay in the journal.")
        else:
            try:
                await EntryOptions(admin).apply(options)
                out("Put device_side's options back.")
            except Exception as err:  # noqa: BLE001 - as resume: say so, and go on to the automations
                out(f"Could not put device_side's options back; set them in HA: {err}")
            journal.clear("options")
    if journal.get("roam") is not None:
        await recover_roam(admin, bridge, journal, out)
    if paused := journal.get("paused"):
        await resume(ha, paused, journal)
    drop_profile(journal)


async def recover_roam(
    admin: HAClient | None, bridge: HueBridge | None, journal: Journal, out: Callable[[str], None]
) -> None:
    """Move the journal's roaming bulbs forward round the cycle to Hue and put back their home; stop on a failure."""
    if admin is None or bridge is None:
        raise SystemExit(
            "Moving the roaming bulbs home needs HA_ADMIN_TOKEN, HUE_BRIDGE_HOST and HUE_APP_KEY in .env.rig; "
            f"the journal ({journal.path}) keeps where they are."
        )
    out("Moving the roaming bulbs home to Hue.")
    try:
        await Roamer.from_journal(admin, bridge, journal, out).go(HOME)
    except RoamError as err:
        raise SystemExit(f"Recovery stopped: {err}") from None


def drop_profile(journal: Journal | None) -> None:
    """Clear the journal's `profile` once nothing it names a run for is left, so an empty journal is deleted; while a
    change is left, it stays, saying which profile's run left it."""
    if journal is not None and set(journal.sections) == {"profile"}:
        journal.clear("profile")


async def pause(ha: HAClient, entity_ids: list[str], paused: list[str], journal: Journal | None = None) -> None:
    """Turn off each listed automation or switch that is on, appending it to `paused` (and the journal, first) as it
    goes.

    For automations that would fight the tests: motion lighting turning a light on as someone walks past, or an
    Adaptive Lighting instance resetting a light's color temperature whenever it turns on. One that is already off
    stays off and is left alone after the run. One HA doesn't know stops the run before any test.
    """
    for entity_id in entity_ids:
        if (state := await ha.get_state(entity_id)) is None:
            raise SystemExit(f"{entity_id} in the profile's pause list has no state in Home Assistant")
        if state["state"] == "on":
            if journal is not None:
                journal.update(paused=[*paused, entity_id])
            await ha.call_service(entity_id.partition(".")[0], "turn_off", {"entity_id": entity_id})
            paused.append(entity_id)
            print(f"Paused {entity_id} for the run.")


async def resume(ha: HAClient, paused: list[str], journal: Journal | None = None) -> None:
    """Turn back on what pause turned off; a failure is printed, so it can be turned on by hand."""
    for entity_id in paused:
        try:
            await ha.call_service(entity_id.partition(".")[0], "turn_on", {"entity_id": entity_id})
            print(f"Resumed {entity_id}.")
        except Exception as err:  # noqa: BLE001 - try every one, and say which stayed off
            print(f"Could not turn {entity_id} back on: {err}. Turn it on by hand.")
    if journal is not None:
        journal.clear("paused")


if __name__ == "__main__":
    # Line by line even when stdout is a file, so a background caller sees "waiting for the lock" and each result
    # as they happen rather than when the buffer fills.
    sys.stdout.reconfigure(line_buffering=True)
    sys.exit(main())
