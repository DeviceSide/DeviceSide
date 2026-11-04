#!/usr/bin/env -S uv run python
"""Run the rig tests against the live HA, behind a human approval gate.

The rig is the household's own Home Assistant and its in-use lights. Nothing changes state before the gate:
preflight reads the profile, the adapter registry and the deployed tree hash, prints what will run, then asks.
DEVICE_SIDE_RIG_APPROVED=1 answers the gate for a non-interactive caller that already has a human's yes.

Runs share the rig through locks in the git common dir, shared by every worktree (tests/rig/locks.py): each holds the
integrations it moves, so runs on different ones go side by side, and HA, shared, or exclusively for a deploy or a
suite with device_side options, which restart or reload device_side under every other run. The plan prints the run's
locks. Each run deploys and restarts HA onto its own checkout's tree when HA hasn't loaded it, so a run queued behind
another tests its own code; it reads the deploy state again once it holds its locks, and takes HA exclusively if it
must deploy after all. Once its deploy is done and HA is back, a run with no option suites steps HA down to shared.
Ctrl-C mid-deploy waits for the deploy and HA's restart to finish before releasing the locks.
The tests are the step files in tests/rig/steps, run by tests/rig/engine.py; a full pass of an adapter rewrites its
test record.

Ctrl-C, SIGTERM and SIGHUP stop a run, putting the devices back; a second one leaves them. What a run changes is
journaled first, in a journal of its own next to the locks (tests/rig/journal.py), so whatever a killed run leaves
changed, the next run whose locks cover it puts back before its gate, or --recover, holding every lock, does.

--hold runs a probe's command holding the named integrations and HA (--exclusive: exclusively), with the profile's
automations for them paused, passing signals on to it and returning its exit code; no case journal, and no gate but
the clear one below.

RIG_BLOCKER_ENTITY in .env.rig names an HA binary_sensor that is on while someone is near enough to see the lights;
unless the profile has `pre_authorized: true`, the rig is clear only while it is off. DEVICE_SIDE_RIG_APPROVED=1 is
refused otherwise, and so is a probe, though a human at the prompt may still say yes. A run or probe that started clear
reads it every 15 s and, on two reads in a row of on, unknown or unavailable, aborts as on a SIGTERM, putting the
devices back. Reads that fail, as during the deploy's restart, don't count. Without the key, or on a pre-authorized
profile, nothing gates on it.

Under cmux the run colors its workspace: green holding its locks, amber waiting for them.

A profile (tests/rig/profiles/<name>.yaml) names the entities a run may move and what it pauses; --profile picks
one, and may be left out when there is only one. A run pauses the profile's `all` list and those of the integrations it
holds, through a baseline runs side by side share (tests/rig/baseline.py): the last run out turns each back on. The
baseline also holds the log levels and Z2M device options a run changes, so a crashed run's come back with the next
run's prune, or --recover's.

The run starts with lanes: one per integration, side by side, each running that integration's cases on fixed entities
(engine.in_head). The rest run after, one at a time: cases with device_side options, whose save reloads the entry, and
those on roaming bulbs, rig-made groups and scenes, or powered entities and their supplies. --serial runs every case
one at a time, as before lanes.

A profile with `roam:` has bulbs the run moves between the networks it declares, of Hue, ZHA and Z2M
(tests/rig/roam.py): the lanes run with the bulbs at home, then the rest run in phases, the home's with the other
integrations', then each other declared network's in that order, each only if it has suites, with a direct move before
each and one straight home at the end. The run holds only the networks it visits. --recover, and the replay before the
next run's gate, move them home. --roam-check visits every declared network with no suites.

Before the gate, and alone with --check, the run checks every phase's devices at once: each fixed entity its cases
use is in HA and available, and each roaming bulb is on a network. Without that, a device left unpowered stops the run
only when its phase comes, after the bulbs have moved.

Every run captures Z2M's log (when it touches Z2M) and HA's next to its report, as <report>.z2m.log and .ha.log
(tests/rig/runlogs.py): deleted after a clean run, kept and printed after any other. --debug-logs also raises HA's
device_side and the run's integrations, and Z2M, to debug for the run, keeps the logs, and puts the levels back (the
baseline, so --recover too).

Usage: scripts/rig.py [--profile NAME] [--dry-run] [--no-deploy] [--unattended] [--serial] [--debug-logs]
                      [--integration KEY ...] [--action NAME ...] [-k TEXT]
       scripts/rig.py [--profile NAME] --check [--integration KEY ...] [--action NAME ...] [-k TEXT]
       scripts/rig.py [--profile NAME] --roam-check [--debug-logs]
       scripts/rig.py --recover
       scripts/rig.py --wait-free [--integration KEY ...]
       scripts/rig.py [--profile NAME] --hold KEY [--hold KEY ...] [--exclusive] -- COMMAND [ARGS ...]
"""

import argparse
import asyncio
import contextlib
import datetime
import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable, Coroutine, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from custom_components.device_side.core.registry import AdapterRegistry  # noqa: E402
from tests.rig import locks  # noqa: E402
from tests.rig.baseline import NAME as BASELINE_NAME  # noqa: E402
from tests.rig.baseline import Baseline  # noqa: E402
from tests.rig.bridge import BridgeError, HueBridge  # noqa: E402
from tests.rig.client import HAClient, HAError  # noqa: E402
from tests.rig.engine import (  # noqa: E402
    ADMIN_INTEGRATIONS,
    Case,
    EntryOptions,
    RunResult,
    Snapshot,
    StepFile,
    Suite,
    SuiteResult,
    adapters_for,
    cases,
    in_head,
    load_step_files,
    merge,
    run,
    write_records,
    write_report,
)
from tests.rig.home import HomeRecord  # noqa: E402
from tests.rig.journal import LEGACY_NAME, Journal, orphans  # noqa: E402
from tests.rig.locks import Claim, Held  # noqa: E402
from tests.rig.profile import (  # noqa: E402
    EXAMPLE,
    PAUSE_ALL,
    PROFILES_DIR,
    TOLERANCE_S,
    Profile,
    RoamBulb,
    load_env,
    profile_paths,
)
from tests.rig.roam import BLUETOOTH_RESET, NAMES, Bulb, GroupError, Roamer, RoamError  # noqa: E402
from tests.rig.roam import plan_lines as roam_plan_lines  # noqa: E402
from tests.rig.runlogs import DebugLevels, RunLogs, ha_domains  # noqa: E402

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
ABORT_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
CLEAR_POLL_S = 15
BLOCKED = ("on", "unknown", "unavailable")  # blocker states that revoke a run; an unread one doesn't
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
    """Whether the run moves the profile's bulbs: for --roam-check, or a suite on a network the profile lets them
    visit other than their home. The home's suites and the rest run with the bulbs at home, so a run of only those
    stays there."""
    return bool(profile.roam) and (roam_check or any(suite.integration in away(profile) for suite in suites))


def away(profile: Profile) -> list[str]:
    """The networks the profile's bulbs may visit other than their home, in CYCLE order."""
    return [network for network in profile.roam_networks if network != profile.roam_home]


def makes_groups(profile: Profile, suites: list[Suite], roam_check: bool = False) -> bool:
    """Whether the run makes the profile's ds-rig-* groups: on each visit when it roams, or at home for a suite
    there."""
    if not profile.roam_groups:
        return False
    return roams(profile, suites, roam_check) or any(suite.integration == profile.roam_home for suite in suites)


def phases(suites: list[Suite], profile: Profile, roaming: bool) -> list[tuple[str | None, list[Suite]]]:
    """The run's phases, each a network to move the bulbs to (None: no move) and the suites run there. Roaming: the
    home's suites with every other integration's, then those of each network the profile lets the bulbs visit, in
    CYCLE order, each in select's order, skipping a network with no suites; a run with none (--roam-check) visits
    every one."""
    if not roaming:
        return [(None, suites)]
    home, stops = profile.roam_home, away(profile)
    by_network = [
        (network, [suite for suite in suites if (suite.integration if suite.integration in stops else home) == network])
        for network in [home, *stops]
    ]
    return [(network, held) for network, held in by_network if network == home or held or not suites]


def plan_lines(
    suites: list[Suite],
    profile: Profile,
    registry: AdapterRegistry,
    keyword: str | None = None,
    only: Callable[[Case], bool] | None = None,
) -> list[str]:
    """Per adapter about to run: the household entities it will move, then each test case `only` accepts. A suite
    with none is left out: another part of the run has its cases."""
    lines = []
    for suite in suites:
        suite_cases = cases(suite, profile, keyword, adapters_for(suite, registry))
        if only is not None and not (suite_cases := [case for case in suite_cases if only(case)]):
            continue
        if registry.adapter(suite.action, suite.integration) is None:
            lines.append(f"{suite.integration} / {suite.action} (no adapter, will skip)")
            continue
        if only is None:
            entities = [entity for role in suite.file.roles if (entity := profile.entity(suite.integration, role))]
        else:
            entities = [entity for case in suite_cases for entity in case.entities.values()]
        targets = ", ".join(dict.fromkeys(entities)) or "no entity, will skip"
        lines.append(f"{suite.integration} / {suite.name} -> {targets}")
        for case in suite_cases:
            lines.append(f"    {case.id}: {case.skip or ', '.join(dict.fromkeys(case.entities.values()))}")
    return lines


def head(profile: Profile) -> Callable[[Case], bool]:
    """The cases the lanes run: in_head's."""
    return lambda case: in_head(case, profile)


def tail(profile: Profile) -> Callable[[Case], bool]:
    """The cases the phases run after the lanes."""
    return lambda case: not in_head(case, profile)


def lane_order(suites: list[Suite]) -> dict[str, list[Suite]]:
    """The suites by integration, one lane each, in the order select gives them."""
    lanes: dict[str, list[Suite]] = {}
    for suite in suites:
        lanes.setdefault(suite.integration, []).append(suite)
    return lanes


def estimate(
    suites: list[Suite],
    registry: AdapterRegistry,
    restarting: bool,
    roaming: bool = False,
    profile: Profile | None = None,
) -> int:
    """Each suite's rig_seconds, summed; with `profile`, the run is in lanes, so each suite's seconds are split by its
    share of cases in the lanes, which count as the longest lane, and the phases, which add up."""
    runnable = [suite for suite in suites if registry.adapter(suite.action, suite.integration)]
    if profile is None:
        seconds = float(sum(suite.file.rig_seconds for suite in runnable))
    else:
        lanes: dict[str, float] = {}
        seconds = 0.0
        for suite in runnable:
            suite_cases = cases(suite, profile, None, adapters_for(suite, registry))
            share = sum(in_head(case, profile) for case in suite_cases) / len(suite_cases) if suite_cases else 0.0
            lanes[suite.integration] = lanes.get(suite.integration, 0.0) + suite.file.rig_seconds * share
            seconds += suite.file.rig_seconds * (1 - share)
        seconds += max(lanes.values(), default=0.0)
    return round(seconds) + (RESTART_ESTIMATE_S if restarting else 0) + (ROAM_ESTIMATE_S if roaming else 0)


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


def gate(clear: tuple[bool, str] | None = None, prompt: Callable[[str], str] = input) -> bool:
    """A human's yes, or DEVICE_SIDE_RIG_APPROVED=1 while the rig is clear (`clear`: rig_clear's answer, None when the
    profile isn't gated). A rig not clear refuses the env var; at the prompt, a yes overrides it."""
    if os.environ.get("DEVICE_SIDE_RIG_APPROVED") == "1":
        if clear is not None and not clear[0]:
            print(f"Rig not clear ({clear[1]}); DEVICE_SIDE_RIG_APPROVED=1 doesn't override that.")
            return False
        print("Approved by DEVICE_SIDE_RIG_APPROVED=1.")
        return True
    return ask(f"Rig not clear ({clear[1]}). Proceed anyway?" if clear and not clear[0] else "Proceed?", prompt)


def ask(question: str, prompt: Callable[[str], str] = input) -> bool:
    """An explicit yes; no terminal (an agent's call) answers no."""
    try:
        return prompt(f"{question} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def _get(url: str, token: str) -> Any:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def gate_sensor(env: dict, profile: Profile) -> str | None:
    """The sensor that gates the profile's runs: RIG_BLOCKER_ENTITY, or None when it is unset or the profile is
    pre-authorized."""
    return None if profile.pre_authorized else env.get("RIG_BLOCKER_ENTITY") or None


def clearance(env: dict, blocker: str | None) -> tuple[bool, str] | None:
    """rig_clear's answer on `blocker`, or None when nothing gates the run."""
    return rig_clear(env, blocker) if blocker else None


def rig_clear(env: dict, blocker: str) -> tuple[bool, str]:
    """Whether the rig may run unattended: `blocker`, an HA binary_sensor the household defines, is off. Any other
    state, the entity missing or HA unreachable is not clear. The reason says which."""
    state, reason = read_blocker(env, blocker)
    return state == "off", reason


def read_blocker(env: dict, entity: str) -> tuple[str | None, str]:
    """The blocker's state, None when it can't be read, and a reason naming it. A state HA restored at startup, before
    the template has evaluated, counts as unread."""
    try:
        reply = _get(f"{env.get('HA_URL', '')}/api/states/{entity}", env.get("HA_TOKEN", ""))
        state, restored = reply["state"], reply.get("attributes", {}).get("restored")
    except urllib.error.HTTPError as err:
        return None, f"{entity} {'is not in HA' if err.code == 404 else f'read failed: HTTP {err.code}'}"
    except (urllib.error.URLError, OSError, ValueError, TypeError, KeyError, AttributeError) as err:
        return None, f"can't read {entity}: {err}"
    if restored:
        return None, f"{entity} is still being restored by HA"
    return state, f"{entity} is {state}"


@contextlib.contextmanager
def watching(env: dict, blocker: str | None, interval: float = CLEAR_POLL_S) -> Iterator[None]:
    """Read `blocker` (None: nothing to watch) every `interval` seconds and, on two reads in a row of a state in
    BLOCKED, stop the run with one SIGTERM, which the run's own handlers take from there: the deploy finishes, the
    tests put the devices back, a probe's command gets it. A read that fails neither counts nor breaks the run of
    two: HA is unreachable during a deploy's restart."""
    stop = threading.Event()

    def watch() -> None:
        misses = 0
        while not stop.wait(interval):
            state, reason = read_blocker(env, blocker)
            if state is None:
                continue
            misses = misses + 1 if state in BLOCKED else 0
            if misses == 2:
                print(f"\nRig authorization revoked ({reason}); aborting.", flush=True)
                os.kill(os.getpid(), signal.SIGTERM)
                return

    thread = threading.Thread(target=watch, name="rig-clear", daemon=True)
    if blocker:
        thread.start()
    try:
        yield
    finally:
        stop.set()
        if blocker:
            thread.join()


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


@dataclass(slots=True)
class Setup:
    """What a run reads before it takes its locks, none of which changes anything; take() reads `deploy` again once it
    holds them."""

    env: dict
    profile: Profile
    registry: AdapterRegistry
    suites: list[Suite]
    roaming: bool
    grouping: bool
    deploy: Deploy | None = None  # None for --check, which deploys nothing
    gated: str | None = None  # gate_sensor's answer: the sensor that gates the run, if the profile is gated

    def deploying(self, args: argparse.Namespace) -> bool:
        """--roam-check deploys nothing, as it runs none of our code."""
        return self.deploy is not None and self.deploy.needed and not args.no_deploy and not args.roam_check


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    command: list[str] = []
    if "--" in argv:
        argv, command = argv[: argv.index("--")], argv[argv.index("--") + 1 :]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", help="the profile to run (tests/rig/profiles/NAME.yaml); needed if there are two")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and stop before the gate")
    parser.add_argument(
        "--check",
        action="store_true",
        help="check the run's devices are in HA and available, and where its roaming bulbs are, then stop: no lock, "
        "no deploy, nothing changed",
    )
    parser.add_argument("--no-deploy", action="store_true", help="test whatever HA already runs")
    parser.add_argument(
        "--integration",
        action="append",
        choices=sorted(TOLERANCE_S),
        help="limit to an integration key (repeatable); with --wait-free, wait for it",
    )
    parser.add_argument("--action", action="append", help="limit to an action's step files (repeatable)")
    parser.add_argument("-k", dest="keyword", help="run only test cases whose id contains this text")
    parser.add_argument("--unattended", action="store_true", help="skip observed tests, reporting them not observed")
    parser.add_argument(
        "--serial",
        action="store_true",
        help="run every case one at a time, with no lanes: to tell a case that fails in a lane from one that fails",
    )
    parser.add_argument(
        "--debug-logs",
        action="store_true",
        help="run HA's device_side and the run's integrations, and Z2M, at debug, and keep the run's captured logs "
        "(they are kept after a failure whatever this says)",
    )
    parser.add_argument("--recover", action="store_true", help="put back what an aborted run left changed, then stop")
    parser.add_argument(
        "--roam-check", action="store_true", help="move the profile's roam bulbs to every network and home, no suites"
    )
    parser.add_argument(
        "--wait-free",
        action="store_true",
        help="wait until no rig run holds the locks (with --integration, those integrations' and HA exclusively), "
        "without taking them; another run may take them first",
    )
    parser.add_argument(
        "--hold",
        action="append",
        metavar="INTEGRATION",
        choices=sorted(TOLERANCE_S),
        help="hold this integration's lock (repeatable) and HA shared while running the command after --, for a probe",
    )
    parser.add_argument(
        "--exclusive",
        action="store_true",
        help="with a command after --: hold HA exclusively, for a probe that restarts HA or reloads device_side",
    )
    args = parser.parse_args(argv)
    args.command = command
    if args.check and (args.recover or args.roam_check or args.wait_free):
        parser.error("--check can't be combined with --recover, --roam-check or --wait-free")
    if args.debug_logs and (args.check or args.recover or args.wait_free or command):
        parser.error("--debug-logs is for a run or --roam-check")
    if bool(args.hold or args.exclusive) != bool(command):
        parser.error("--hold and --exclusive need a command after --, and a command after -- needs one of them")
    if command and (args.dry_run or args.check or args.recover or args.roam_check or args.wait_free):
        parser.error("a command after -- can't be combined with a run's modes")
    args.dry_run |= args.check  # like a dry run, it holds no lock and changes nothing
    colors = args.wait_free or not args.dry_run  # a dry run holds no lock and sets no color, so it clears none
    try:
        with handling_signals(leave):  # a run killed while it waits still clears its color
            return wait_or_run(args)
    finally:
        if colors:
            locks.workspace_color(None)


def leave(signum: int, _frame: object) -> None:
    """Stop a run that holds nothing yet, with the shell's exit code for the signal."""
    raise SystemExit(128 + signum)


def wait_or_run(args: argparse.Namespace) -> int:
    directory = common_dir()
    if args.wait_free:
        locks.wait_free(directory, args.integration)
        return 0
    if args.command:
        return hold_command(args, directory)
    if args.recover:
        return recover_all(args, directory)
    setup = prepare(args)
    held = None if args.dry_run else take(args, setup, directory)  # waits for the locks, then holds them until exit
    try:
        with end_on_signals():
            return run_held(args, setup, held, directory)
    except Aborted as err:
        print(err)
        return 1
    finally:
        if held is not None:
            held.close()


def prepare(args: argparse.Namespace) -> Setup:
    """The profile, the suites, and, but for --check, the deploy state; a run also checks .env.rig has its tokens."""
    env = load_env()
    try:
        profile = Profile.load(choose_profile(args.profile, env))
    except ValueError as err:
        raise SystemExit(f"Fix the profile: {err}") from err
    registry = AdapterRegistry.discover()
    suites = run_suites(args, profile, registry)
    setup = Setup(
        env,
        profile,
        registry,
        suites,
        roams(profile, suites, args.roam_check),
        makes_groups(profile, suites, args.roam_check),
    )
    if args.check:
        return setup
    setup.gated = gate_sensor(env, profile)
    if not args.dry_run:
        check_tokens(env, suites, registry, setup.roaming or setup.grouping)
    setup.deploy = deploy_state(env.get("RIG_STATUS_CMD", ""))
    return setup


def claim(args: argparse.Namespace, setup: Setup) -> Claim:
    """What the run must hold: each integration with a suite that has an adapter, the integrations their entities draw
    power through, and the networks its roaming bulbs visit, home included; HA exclusively when it deploys, which
    restarts HA, or runs a suite with device_side options, whose save reloads the entry; HA shared otherwise."""
    runnable = [suite for suite in setup.suites if setup.registry.adapter(suite.action, suite.integration)]
    integrations = {suite.integration for suite in runnable}
    integrations |= supplies(setup.profile, integrations)
    if setup.roaming:
        integrations |= {network for network, _ in phases(setup.suites, setup.profile, roaming=True) if network}
    if setup.grouping:
        integrations.add(setup.profile.roam_home)
    exclusive = setup.deploying(args) or reloads(setup)
    return Claim("exclusive" if exclusive else "shared", frozenset(integrations))


def reloads(setup: Setup) -> bool:
    """Whether a suite the run can run has device_side options, whose save reloads the entry under every other run."""
    return any(suite.file.options for suite in setup.suites if setup.registry.adapter(suite.action, suite.integration))


def supplies(profile: Profile, integrations: set[str]) -> set[str]:
    """The integrations whose switches power an entity of `integrations`: a case cuts or needs that power."""
    where = {entity.entity_id: key for key, entities in profile.integrations.items() for entity in entities}
    return {
        where[entity.powered_by]
        for integration in integrations
        for entity in profile.integrations.get(integration, ())
        if entity.powered_by in where
    }


def take(args: argparse.Namespace, setup: Setup, directory: Path) -> Held:
    """Wait for the run's claim and hold it. Another run may have deployed meanwhile, so the deploy state is read again;
    if the run now needs more (it must deploy after all), it lets go and waits for that, once: HA held exclusively,
    nothing can change it again."""
    holder = git("rev-parse", "--abbrev-ref", "HEAD")
    held = locks.hold(claim(args, setup), holder, directory)
    setup.deploy = deploy_state(setup.env.get("RIG_STATUS_CMD", ""))
    if not held.claim.covers(needed := claim(args, setup)):
        held.close()
        print(f"HA changed while this run waited; it now needs {needed}.")
        held = locks.hold(held.claim | needed, holder, directory)
        setup.deploy = deploy_state(setup.env.get("RIG_STATUS_CMD", ""))
    return held


def run_held(args: argparse.Namespace, setup: Setup, held: Held | None, directory: Path) -> int:
    """The run, once its locks are held (none for a dry run or --check)."""
    env, profile, registry, suites = setup.env, setup.profile, setup.registry, setup.suites
    gated = setup.gated
    homes = replay(env, held, directory)
    if args.check:
        return check_only(setup, args.keyword, homes, claim(args, setup), directory)
    deploy = setup.deploy
    deploying = setup.deploying(args)
    lanes = not args.serial
    print_plan(profile, suites, registry, args.keyword, deploy, deploying, setup.roaming, setup.grouping, lanes)
    print(f"Locks: {held.claim if held else claim(args, setup)}")
    if args.debug_logs:
        print_debug_logs(env, suites, setup.roaming)

    if deploying:
        check_deploy(env, deploy)
    if not args.roam_check:
        print()
        ready = not asyncio.run(check_devices(env, suites, profile, registry, args.keyword, setup.roaming, homes))
        if not (ready or args.dry_run):
            raise SystemExit("Power or fix the devices above, then run again.")
    clear = clearance(env, gated)
    if clear is not None:
        print(f"Rig {'clear' if clear[0] else 'not clear'}: {clear[1]}.")
    if args.dry_run:
        return 0
    if not gate(clear):
        print("Not approved; nothing changed.")
        return 1

    journal = Journal.start(directory)
    try:
        with watching(env, gated if clear and clear[0] else None):
            return run_approved(args, setup, held, journal, deploying, lanes)
    finally:
        journal.release()


def print_debug_logs(env: dict, suites: list[Suite], roaming: bool) -> None:
    """The brief's note that --debug-logs raises the run's logs to debug, which may shift timing cases, and, for a
    run that touches Z2M, a warning when Z2M won't send its debug lines to MQTT."""
    z2m = touches_z2m(suites, roaming)
    print(
        f"Debug logs: {', '.join(ha_domains({s.integration for s in suites}, roaming))} in HA"
        f"{' and Z2M' if z2m else ''} at debug for the run. Debug logging costs CPU, so timing cases may read "
        "differently."
    )
    if z2m and env.get("HA_ADMIN_TOKEN"):
        try:
            asyncio.run(with_admin(env, warn_z2m_debug))
        except Exception as err:  # noqa: BLE001 - the warning is a courtesy: the run goes on without it
            print(f"Couldn't read Z2M's settings to check its debug lines reach MQTT: {err}")


def touches_z2m(suites: list[Suite], roaming: bool) -> bool:
    """Whether the run's logs include Z2M's: a Z2M suite, or roaming."""
    return roaming or any(suite.integration == "zigbee2mqtt" for suite in suites)


async def warn_z2m_debug(admin: HAClient) -> None:
    config = (await admin.z2m_info()).get("config") or {}
    if not (config.get("advanced") or {}).get("log_debug_to_mqtt_frontend"):
        print(
            "Warning: Z2M's advanced.log_debug_to_mqtt_frontend is off, so its debug lines won't reach the captured "
            "log. Turn it on and restart Z2M; the rig never sets it."
        )


async def with_admin(env: dict, call: Callable[[HAClient], Awaitable[None]]) -> None:
    """`call` on an admin connection to HA, closed after."""
    admin = HAClient(env["HA_URL"], env["HA_ADMIN_TOKEN"])
    await admin.connect()
    try:
        await call(admin)
    finally:
        await admin.close()


def run_approved(
    args: argparse.Namespace, setup: Setup, held: Held, journal: Journal, deploying: bool, lanes: bool
) -> int:
    """The deploy and the tests, once the run is approved."""
    env, deploy = setup.env, setup.deploy
    deploy_and_wait(env, deploy.branch if deploying else None)
    if deploying and not reloads(setup):  # HA is back, and nothing left restarts or reloads it under other runs
        held.share_ha()
    commit = tested_commit(env.get("RIG_STATUS_CMD", ""), deploy, deploying)
    return run_tests(
        run_rig(
            env,
            setup.suites,
            setup.profile,
            setup.registry,
            args.keyword,
            args.unattended,
            commit,
            journal,
            roaming=setup.roaming,
            grouping=setup.grouping,
            lanes=lanes,
            claim=held.claim,
            debug_logs=args.debug_logs,
        )
    )


def check_only(setup: Setup, keyword: str | None, homes: set[str], wanted: Claim, directory: Path) -> int:
    """--check: the device check alone, naming the runs that hold locks this run would claim, whose moves and pauses
    it would see."""
    if held := locks.holders(directory, wanted):
        print("Runs hold locks this run needs; what they have moved or paused shows below as it is now:")
        for line in held:
            print(f"  {line}")
    problems = asyncio.run(
        check_devices(setup.env, setup.suites, setup.profile, setup.registry, keyword, setup.roaming, homes)
    )
    return 1 if problems else 0


def hold_command(args: argparse.Namespace, directory: Path) -> int:
    """A command after --: run a probe holding the integrations --hold names and HA, shared or with --exclusive
    exclusively, with the profile's automations for them paused, and return its exit code. No case journal: the
    probe puts back what it changes. Its only gate is the clear one (probe_approved), checked before and after the
    wait for the locks. A journal is started all the same, never written, as the name the baseline knows the probe
    by, alive while it runs: a crashed probe's pauses are pruned like a run's."""
    wanted = Claim("exclusive" if args.exclusive else "shared", frozenset(args.hold or ()))
    env = load_env()
    try:
        profile = Profile.load(choose_profile(args.profile, env))
    except ValueError as err:
        raise SystemExit(f"Fix the profile: {err}") from err
    pausing, gated = profile.paused_by(wanted.integrations), gate_sensor(env, profile)
    if pausing and not (env.get("HA_URL") and env.get("HA_TOKEN")):
        raise SystemExit("HA_URL and HA_TOKEN must be set in .env.rig to pause the profile's automations")
    holder = f"{git('rev-parse', '--abbrev-ref', 'HEAD')} (probe: {shlex.join(args.command)})"
    if not probe_approved(clear := clearance(env, gated)):
        return 1
    with locks.hold(wanted, holder, directory):
        # a probe may wait long for its locks; a human who let it past a rig not clear isn't asked again
        if clear and clear[0] and not probe_approved(clear := clearance(env, gated)):
            return 1
        journal = Journal.start(directory)
        try:
            with watching(env, gated if clear and clear[0] else None):
                if pausing:
                    asyncio.run(with_ha(env, lambda ha: Baseline.of(ha, journal, "pause").pause(pausing)))
                return run_command(args.command)
        finally:
            if pausing:
                asyncio.run(with_ha(env, lambda ha: Baseline.of(ha, journal, "pause").release()))
            journal.release()


def probe_approved(clear: tuple[bool, str] | None, prompt: Callable[[str], str] = input) -> bool:
    """A probe's gate, its only one: through while the rig is clear or nothing gates on it (`clear` None), else only
    on a human's yes; an agent's call, which has no terminal, is refused."""
    if clear is None or clear[0] or ask(f"Rig not clear ({clear[1]}). Proceed anyway?", prompt):
        return True
    print("Not approved; nothing changed.")
    return False


async def with_ha(env: dict, call: Callable[[HAClient], Awaitable[None]]) -> None:
    """`call` on a connection to HA, the admin one where .env.rig has it (the baseline's prune may set Z2M's level
    or options, which only an admin may), closed after."""
    ha, admin = await connect(env)
    try:
        await call(admin or ha)
    finally:
        await ha.close()
        if admin:
            await admin.close()


def run_command(command: list[str]) -> int:
    """Run `command` in its own session, passing on Ctrl-C, SIGTERM and SIGHUP, so it gets each once, through here;
    its exit code, or 128 plus the number of the signal that ended it."""
    try:
        process = subprocess.Popen(command, start_new_session=True)
    except OSError as err:
        raise SystemExit(f"Can't run {command[0]}: {err}") from None
    with handling_signals(lambda signum, _frame: process.send_signal(signum)):
        code = process.wait()
    return 128 - code if code < 0 else code


def recover_all(args: argparse.Namespace, directory: Path) -> int:
    """--recover: hold everything, so no run is going, and put back what every aborted run left, the journal from
    before per-run journals included, then what the baseline holds for no live run. Nonzero while something is left."""
    env = load_env()
    held = None if args.dry_run else locks.hold(Claim.everything(), git("rev-parse", "--abbrev-ref", "HEAD"), directory)
    try:
        with end_on_signals():
            # The journal from before per-run journals is older than any of them; orphans come oldest first.
            journals = [*filter(None, [Journal(directory / LEGACY_NAME)]), *orphans(directory)]
            if not journals:
                print("No aborted run left anything to put back.")
            for journal in journals:
                try:
                    if args.dry_run:
                        print(f"An aborted run left changes in {journal.path}; --recover puts them back.")
                    else:
                        asyncio.run(recover_rig(env, journal))
                finally:
                    journal.release()
            if not args.dry_run and (directory / BASELINE_NAME).exists():
                asyncio.run(prune_baseline(env, directory))
            return 1 if any(journals) or (directory / BASELINE_NAME).exists() else 0
    except Aborted as err:
        print(err)
        return 1
    finally:
        if held is not None:
            held.close()


def run_suites(args: argparse.Namespace, profile: Profile, registry: AdapterRegistry) -> list[Suite]:
    """The suites the arguments select: none for --roam-check, which needs a profile that roams."""
    if args.roam_check:
        if not profile.roam:
            raise SystemExit(f"--roam-check needs a profile with roam:, and {profile.name} has none")
        return []
    suites = select(load_step_files(), profile, args.integration, args.action)
    if not any(registry.adapter(suite.action, suite.integration) for suite in suites):
        raise SystemExit("No rig test matches the profile's integrations.")
    return suites


def choose_profile(
    name: str | None,
    env: dict,
    directory: Path = PROFILES_DIR,
    example: Path = EXAMPLE,
) -> Path:
    """The profile --profile names, else the only one. Refuses while .env.rig still has the RIG_PAUSE that profiles
    replaced, so nothing runs against half a migration."""
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


def common_dir() -> Path:
    """The git common dir, shared by every worktree, where the locks and the journals live."""
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


def replay(env: dict, held: Held | None, directory: Path) -> set[str]:
    """Put back what aborted runs left changed, each whose claim the run holds (needs); say how to put back the rest.
    A dry run holds nothing, so it only says what is there. Returns the roaming bulbs whose Hue home the home record
    or a journal from before it still holds, which a run puts back."""
    homes: set[str] = set()
    for orphan in orphans(directory):
        try:
            needed = needs(orphan)
            if held is not None and held.claim.covers(needed):
                asyncio.run(recover_rig(env, orphan))
            elif held is None:
                print(f"An aborted run left changes in {orphan.path}; a run holding {needed} puts them back first.")
            else:
                print(
                    f"An aborted run left changes in {orphan.path} that need {needed}, more than this run holds; "
                    "a run holding that, or --recover, puts them back."
                )
            # What is left in a journal from before the home record: a recovery that brought the bulbs home cleared it.
            homes |= set((orphan.get("roam") or {}).get("home", {}))
        finally:
            orphan.release()
    if legacy := Journal(directory / LEGACY_NAME):
        print(f"A run from before per-run journals left changes in {legacy.path}; --recover puts them back.")
        homes |= set((legacy.get("roam") or {}).get("home", {}))
    return homes | {entry["entity_id"] for entry in HomeRecord(directory).all().values() if entry.get("hue")}


def needs(journal: Journal) -> Claim:
    """What a run must hold to put back an orphan: the integrations its run held, and HA exclusively when it left
    device_side's options changed, as setting them reloads the entry."""
    held = Claim.of(journal.get("claim"))
    return Claim("exclusive" if journal.get("options") is not None else "shared", held.integrations)


def check_tokens(env: dict, suites: list[Suite], registry: AdapterRegistry, roaming: bool = False) -> None:
    """Stop before the gate when .env.rig lacks a token the run needs: ADMIN_INTEGRATIONS and any adapter with
    options (they are set through device_side's options flow) need HA_ADMIN_TOKEN; a Hue file with a bridge step
    needs the bridge's host and key; roaming, or making the lab's groups, needs both, for the registries, MQTT and
    the bridge."""
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
    grouping: bool = False,
    lanes: bool = False,
) -> None:
    print_profile(profile)
    print_phases(profile, suites, registry, keyword, roaming, grouping, lanes)
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
    seconds = estimate(suites, registry, deploying, roaming, profile if lanes else None)
    print(f"Estimated duration: {seconds} s. These are in-use household devices; they will visibly change state.")


def print_profile(profile: Profile) -> None:
    """The profile's entities by integration, its roaming bulbs once each, and its pause list."""
    print(f"Profile {profile.name}:")
    roaming_ids = {bulb.entity_id for bulb in profile.roam}  # the groups print below, and the bulbs once
    for integration, entities in profile.integrations.items():
        for entity in entities:
            if entity.entity_id not in roaming_ids:
                print(f"  {integration:8} {entity.entity_id:40} {', '.join(sorted(entity.roles))}")
    for bulb in profile.roam:
        print(f"  {'roams':8} {bulb.entity_id:40} {', '.join(sorted(bulb.roles))}")
    for group in profile.roam_groups:
        print(f"  {'ds-rig':8} {group.entity_id:40} {', '.join(sorted(group.roles))}")
        if group.scene:
            print(f"  {'ds-rig':8} {group.scene:40} scene")
    for key, entity_ids in profile.pause.items():
        if entity_ids:
            whose = "every run" if key == PAUSE_ALL else f"a run holding {key}"
            print(f"Paused for {whose}: {', '.join(entity_ids)}")


def print_phases(
    profile: Profile,
    suites: list[Suite],
    registry: AdapterRegistry,
    keyword: str | None,
    roaming: bool,
    grouping: bool = False,
    lanes: bool = False,
) -> None:
    """The moves, if the run roams, and the groups it makes, then the lanes' cases, then each phase's adapters and
    the cases left for it."""
    if not roaming and profile.roam:
        where = " or ".join(NAMES[network] for network in away(profile)) or "another network"
        print(f"Roaming: none, as no {where} suite runs; the bulbs stay on {NAMES[profile.roam_home]}.")
    if roaming or grouping:
        print(
            "\n".join(
                roam_plan_lines(
                    profile.roam,
                    profile.roam_groups if grouping else (),
                    roaming,
                    [network for network, _ in phases(suites, profile, roaming) if network],
                )
            )
        )
    if lanes and suites:
        print("In parallel, one lane per integration:")
        for integration, lane in lane_order(suites).items():
            lines = plan_lines(lane, profile, registry, keyword, head(profile))
            print(f"  {integration}:" + ("" if lines else " none"))
            for line in lines:
                print(f"    {line}")
    only = tail(profile) if lanes else None
    for network, phase_suites in phases(suites, profile, roaming):
        print(f"Adapters on {NAMES[network]}:" if network else "Adapters:")
        for line in plan_lines(phase_suites, profile, registry, keyword, only) or ["none"]:
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
    grouping: bool = False,
    lanes: bool = False,
    claim: Claim | None = None,
    debug_logs: bool = False,
    logs_dir: Path | None = None,
) -> int:
    """Run the step files, in lanes first when `lanes` (run_phases), then phase by phase, moving the roaming bulbs
    before each and home after the last, and making the ds-rig-* groups in each phase when `grouping`, then write a
    test record for each adapter whose every test passed, citing `commit`; with no commit, none: a record nobody can
    trace to a commit proves nothing. Roaming and groups need the admin connection and the bridge (check_tokens).

    Z2M's log (for a run that touches it) and HA's go next to the report as `<report>.z2m.log` and `.ha.log`: deleted
    after a clean run, kept and printed after any other, or with `debug_logs`, which also runs HA's device_side and the
    run's integrations, and Z2M, at debug until the run ends (RunLogs, DebugLevels)."""
    lab = roaming or grouping
    if lab and not (env.get("HA_ADMIN_TOKEN") and env.get("HUE_BRIDGE_HOST") and env.get("HUE_APP_KEY")):
        raise SystemExit("Roaming needs HA_ADMIN_TOKEN, HUE_BRIDGE_HOST and HUE_APP_KEY in .env.rig")
    cancel_on_signals()
    ha, admin = await connect(env)
    bridge = None
    if env.get("HUE_BRIDGE_HOST") and env.get("HUE_APP_KEY"):
        bridge = HueBridge(env["HUE_BRIDGE_HOST"], env["HUE_APP_KEY"])
    groups = profile.roam_groups if grouping else ()
    roamer = Roamer(admin, bridge, map(Bulb.of, profile.roam), journal, groups=groups) if lab else None
    # The pauses are the run's, by its journal's name: a run with no journal (a test's) pauses nothing.
    pauses = Baseline.of(admin or ha, journal, "pause") if journal is not None else None
    pausing = profile.paused_by(claim.integrations if claim else None)
    stopped: Roamer | None = None  # the roamer, once a RoamError stopped the run
    home = True  # whether the roaming bulbs ended at home, with no rig-made group left
    if journal is not None:  # the claim says what a run must hold to put back what this one leaves
        journal.update(profile=profile.name, **({"claim": claim.as_json()} if claim else {}))
    results: list[SuiteResult] = []  # each phase's, as it finishes: a failed move keeps the phases before it
    started = datetime.datetime.now()
    stamp = started.strftime("%Y-%m-%d %H:%M:%S")
    logs = RunLogs(logs_dir or REPORT_DIR, f"rig run {stamp}", started, keep=debug_logs)
    levels = DebugLevels(Baseline.of(admin or ha, journal, "debug")) if debug_logs else None
    code = 1  # only a run that returns 0 is clean; any other end keeps the logs
    try:
        try:
            await begin_logging(logs, levels, admin, suites, roaming)
            result = await run_phases(
                ha,
                admin,
                bridge,
                roamer,
                roaming,
                suites,
                profile,
                registry,
                keyword,
                unattended,
                (lambda: pauses.pause(pausing)) if pauses and pausing else None,
                journal,
                results,
                lanes,
                reloads=claim is None or claim.ha == "exclusive",  # holding HA shared, it may not reload the entry
            )
            if suites:
                await report(result, ha, registry, commit, profile, keyword, stamp)
        except RoamError as err:
            # A move that failed isn't retried here; the journal keeps where the bulbs are, for --recover. The groups
            # made so far still go, and after a group that couldn't be made, the bulbs still go home. The phases that
            # ran still get their report and records.
            if not isinstance(err, GroupError):
                stopped, roamer = roamer, None
            await report_ran(results, ha, registry, commit, profile, keyword, stamp)
            raise SystemExit(f"Roaming stopped: {err}") from None
        finally:
            home = await leave_lab(roamer, stopped)
            await end_logging(logs, levels, admin)
            if pauses is not None:
                await pauses.release()
            drop_profile(journal)
            if bridge:
                await bridge.close()
            await ha.close()
            if admin:
                await admin.close()
        code = 1 if result.failed or not home else 0
    finally:
        logs.settle(code == 0)
    return code


async def begin_logging(
    logs: RunLogs, levels: DebugLevels | None, admin: HAClient | None, suites: list[Suite], roaming: bool
) -> None:
    """Start Z2M's capture, when the run touches Z2M, then raise the debug levels, when asked: the raise's own lines
    are captured."""
    z2m = touches_z2m(suites, roaming)
    if z2m:
        await logs.start_z2m(admin)
    if levels is not None:
        await levels.raise_levels(ha_domains({suite.integration for suite in suites}, roaming), z2m)


async def end_logging(logs: RunLogs, levels: DebugLevels | None, admin: HAClient | None) -> None:
    """Put the levels back, then stop Z2M's capture and save HA's log."""
    if levels is not None:
        await levels.restore()
    await logs.stop_z2m()
    await logs.save_ha(admin)


async def run_phases(
    ha: HAClient,
    admin: HAClient | None,
    bridge: HueBridge | None,
    roamer: Roamer | None,
    roaming: bool,
    suites: list[Suite],
    profile: Profile,
    registry: AdapterRegistry,
    keyword: str | None,
    unattended: bool,
    pause: Callable[[], Awaitable[None]] | None,
    journal: Journal | None,
    results: list[SuiteResult] | None = None,
    lanes: bool = False,
    reloads: bool = True,
) -> RunResult:
    """Each phase: move the bulbs there and make its groups, wait for its targets, then run its cases, automated then
    observed. `pause` pauses the automations, once, after the first phase's targets are all there. A run with no suites
    is --roam-check, which makes and removes the groups on every visit as a probe. Each phase's results go into
    `results` as it finishes, so a caller keeps them when a later move raises.

    With `lanes`, the first phase starts with every suite's in_head cases, one lane per integration side by side,
    with the bulbs at home; the phases then run only the rest (see merge)."""
    results = [] if results is None else results
    lanes = lanes and bool(suites)
    ask = None if unattended else input
    # One busy map for every run: the phases go on from the lanes, on some of the same lights.
    common = {
        "admin": admin,
        "keyword": keyword,
        "ask": ask,
        "bridge": bridge,
        "journal": journal,
        "busy": {},
        "reloads": reloads,
    }
    only = tail(profile) if lanes else None
    for number, (network, phase_suites) in enumerate(phases(suites, profile, roaming)):
        if roamer is not None:
            await roamer.go(network or roamer.home_network)  # removes the last phase's groups first
            if phase_suites or not suites:
                await roamer.make_groups(network or roamer.home_network)
        if number == 0 and lanes:
            await wait_for_targets(ha, suites, profile, registry, keyword, only=head(profile))
        if phase_suites:
            await wait_for_targets(ha, phase_suites, profile, registry, keyword, only=only)
        if number == 0 and pause is not None:
            await pause()
        if number == 0 and lanes:
            results += (await run(suites, profile, registry, ha, only=head(profile), lanes=True, **common)).suites
        if phase_suites:
            results += (await run(phase_suites, profile, registry, ha, only=only, **common)).suites
    if roamer is not None:
        await roamer.go(roamer.home_network)
    return RunResult(results)


async def report_ran(
    results: list[SuiteResult],
    ha: HAClient,
    registry: AdapterRegistry,
    commit: str | None,
    profile: Profile,
    keyword: str | None = None,
    stamp: str | None = None,
) -> None:
    """After a failed move, report the phases that ran before it. A report that fails is printed, never raised: the
    move's error, with its recovery steps, must still show."""
    if not results:
        return
    try:
        await report(RunResult(results), ha, registry, commit, profile, keyword, stamp)
    except Exception as err:  # noqa: BLE001
        print(f"The phases that ran couldn't be reported: {err}")


async def report(
    result: RunResult,
    ha: HAClient,
    registry: AdapterRegistry,
    commit: str | None,
    profile: Profile,
    keyword: str | None = None,
    stamp: str | None = None,
):
    """The run's report, and a test record per fully passed suite when a commit names the tree HA ran. A suite whose
    cases ran in parts (lanes, then phases) is joined first; one missing a part writes no record."""
    result = merge(result.suites, profile, registry, keyword)
    stamp = stamp or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\nReport: {write_report(result, REPORT_DIR, f'rig run {stamp}')}")
    if commit is None:
        print("No test records: no commit names the tree HA ran (--no-deploy, or origin moved before the deploy).")
        return
    source = f"rig run (`scripts/rig.py`), commit `{git('rev-parse', '--short', commit)}`"
    today = datetime.date.today().isoformat()
    for path in await write_records(result, registry, TEST_RECORDS_DIR, today, source, profile.name):
        print(f"Wrote {path.relative_to(REPO)}; review the diff before committing it.")


async def leave_lab(roamer: Roamer | None, stopped: Roamer | None) -> bool:
    """After the run: the bulbs home and the groups removed (go_home), or, after a RoamError, only the groups removed:
    a move that failed isn't retried here. Whether the bulbs are home with no group left."""
    if roamer is not None:
        return await go_home(roamer)
    if stopped is not None:
        await stopped.remove_groups()
    return True


async def go_home(roamer: Roamer) -> bool:
    """Remove the rig-made groups and move the roaming bulbs home after a run that stopped part way (a no-op after
    one that finished); whether that is all done, their homes put back included. A failure is printed: the journal
    keeps where they are, and --recover tries again."""
    try:
        await roamer.go(roamer.home_network)
    except Exception as err:  # noqa: BLE001 - as resume: say so, and go on putting the rest back
        print(f"Could not move the roaming bulbs home: {err}. scripts/rig.py --recover tries again.")
        return False
    return roamer.done


async def wait_for_targets(
    ha: HAClient,
    suites: list[Suite],
    profile: Profile,
    registry: AdapterRegistry,
    keyword: str | None,
    timeout: float = TARGETS_TIMEOUT_S,
    only: Callable[[Case], bool] | None = None,
) -> None:
    """Until every entity a case `only` accepts will move, a group's listed members included, is available; exits the
    runner, naming the rest, after `timeout`, or at once for one HA doesn't have."""
    entities = targets(suites, profile, registry, keyword, only)
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


def available(state: dict | None) -> bool:
    return state is not None and state["state"] != "unavailable"


def targets(
    suites: list[Suite],
    profile: Profile,
    registry: AdapterRegistry,
    keyword: str | None,
    only: Callable[[Case], bool] | None = None,
) -> list[str]:
    """Every entity a case `only` accepts will move, a group's listed members included."""
    return sorted(
        {
            entity
            for suite in suites
            if registry.adapter(suite.action, suite.integration)
            for case in cases(suite, profile, keyword, adapters_for(suite, registry))
            if not case.skip and (only is None or only(case))
            for entity in (*case.entities.values(), *case.members)
        }
    )


async def check_devices(
    env: dict,
    suites: list[Suite],
    profile: Profile,
    registry: AdapterRegistry,
    keyword: str | None,
    roaming: bool,
    homes: set[str] = frozenset(),
) -> list[str]:
    """Before anything changes, for every phase at once: each fixed entity the selected cases use is in HA and
    available, and, when the run roams, each roaming bulb is on a network with its light available. Prints what it
    found; returns the problems, which would otherwise stop the run part way, after moves. Rig-made groups and scenes
    don't exist yet, and a roaming bulb's light may still be under another ID, so neither is looked up as an entity.
    `homes` are the bulbs whose Hue home the home record holds, which a run puts back."""
    fixed = [entity for entity in targets(suites, profile, registry, keyword) if entity not in profile.made_entities]
    bulbs = list(profile.roam) if roaming else []
    print(f"Checking profile {profile.name}: {len(fixed)} entities" + (f", {len(bulbs)} roaming." if bulbs else "."))
    if not (env.get("HA_URL") and env.get("HA_TOKEN")):
        return ["Can't check the devices: HA_URL and HA_TOKEN must be set in .env.rig"]
    problems: list[str] = []
    try:
        ha, admin = await connect(env)
    except (OSError, aiohttp.ClientError, RuntimeError) as err:
        return [f"Can't reach HA at {env.get('HA_URL')}: {err or type(err).__name__}"]
    try:
        for entity, state in zip(fixed, await asyncio.gather(*map(ha.get_state, fixed)), strict=True):
            if state is None:
                problems.append(f"{entity}: not in HA; check profile {profile.name}")
            elif not available(state):
                problems.append(f"{entity}: unavailable; check it is powered")
        if bulbs:
            problems += await check_roaming(env, admin, bulbs, ha, homes)
    finally:
        await ha.close()
        if admin:
            await admin.close()
    for problem in problems:
        print(f"  {problem}")
    print(f"{len(problems)} problem(s): nothing was changed." if problems else "Every device is ready.")
    return problems


async def check_roaming(
    env: dict, admin: HAClient | None, bulbs: list[RoamBulb], ha: HAClient, homes: set[str] = frozenset()
) -> list[str]:
    """Where each roaming bulb is, printed, and the problems: one on no network, or whose light is unavailable, or
    one the networks couldn't be asked about."""
    if admin is None or not (env.get("HUE_BRIDGE_HOST") and env.get("HUE_APP_KEY")):
        return ["Can't find the roaming bulbs: that needs HA_ADMIN_TOKEN, HUE_BRIDGE_HOST and HUE_APP_KEY in .env.rig"]
    bridge = HueBridge(env["HUE_BRIDGE_HOST"], env["HUE_APP_KEY"])
    problems = []
    try:
        finder = Roamer(admin, bridge, map(Bulb.of, bulbs), out=lambda _: None)
        home = finder.home_network
        for bulb in finder.bulbs:
            try:
                network = await finder.locate(bulb)
            except (BridgeError, HAError, OSError, aiohttp.ClientError, TimeoutError) as err:
                problems.append(f"{bulb.entity_id}: can't tell which network it is on: {err or type(err).__name__}")
                continue
            state = await ha.get_state(bulb.entity_id)
            if network is None:
                problems.append(f"{bulb.entity_id}: not on any Zigbee network. {BLUETOOTH_RESET}")
            elif state is not None and not available(state):
                problems.append(f"{bulb.entity_id}: on {NAMES[network]}, unavailable; check it is powered")
            elif network != home and bulb.entity_id in homes:
                print(f"  {bulb.entity_id}: on {NAMES[network]}; the home record has its Hue home for a run to restore")
            elif network != home:
                print(
                    f"  {bulb.entity_id}: on {NAMES[network]}. The run moves it from there; it has no saved Hue home, "
                    "so put its rooms and scenes back by hand after its first visit."
                )
            else:
                print(f"  {bulb.entity_id}: on {NAMES[network]}")
    finally:
        await bridge.close()
    return problems


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
        try:
            await admin.connect()
        except BaseException:
            await ha.close()
            raise
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
    device_side's options, the roaming bulbs (the ds-rig-* groups removed, the bulbs moved home, their Hue rooms and
    scenes put back), what it holds in the baseline (its pauses, log levels and Z2M options) and the automations a
    journal from before the baseline paused.
    A step that fails is printed and dropped from the journal, except an entity that couldn't be put back, which stays
    for the next try; options stay in it while there is no admin connection to set them. The bulbs can't be left half
    done, so a failure there stops recovery, keeping the rest journaled."""
    run_of = f" (profile {name})" if (name := journal.get("profile")) else ""
    out(f"An aborted rig run{run_of} left changes in {journal.path}; putting them back.")
    for key, entry in dict(journal.get("cases") or {}).items():
        await recover_case(ha, entry, out, journal=journal, journal_key=key).restore()
    if taken := journal.get("taken"):  # a journal from before lanes, with one case at the top level
        entry = {"taken": taken, "stored": journal.get("stored", {}), "power": journal.get("power", {})}
        await recover_case(ha, entry, out).restore()
        journal.clear("taken", "stored", "power")
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
    await Baseline(admin or ha, journal.path.parent, journal.name, out).release()
    if paused := journal.get("paused"):  # a run from before the pause ledger kept its pauses here
        for entity_id in paused:
            try:
                await ha.call_service(entity_id.partition(".")[0], "turn_on", {"entity_id": entity_id})
                out(f"Resumed {entity_id}.")
            except Exception as err:  # noqa: BLE001 - try every one, and say which stayed off
                out(f"Could not turn {entity_id} back on: {err}. Turn it on by hand.")
        journal.clear("paused")
    drop_profile(journal)


async def prune_baseline(env: dict, directory: Path) -> None:
    """Put back what the baseline holds for no live run, on the admin connection where there is one: Z2M's level
    and options need it."""
    if not (env.get("HA_URL") and env.get("HA_TOKEN")):
        raise SystemExit("HA_URL and HA_TOKEN must be set in .env.rig to put back what the baseline holds")
    ha, admin = await connect(env)
    try:
        await Baseline(admin or ha, directory, "recover").prune()
    finally:
        await ha.close()
        if admin:
            await admin.close()


def recover_case(ha: HAClient, entry: dict, out: Callable[[str], None], **journaled: Any) -> Snapshot:
    """The snapshot that puts back one case's entities from its journal entry, saying which go back how; `journaled`
    (journal, journal_key) has its restore drop the entry."""
    for entity_id, state in entry["taken"].items():
        if state is not None and state["state"] in ("on", "off"):
            out(f"Putting {entity_id} back {state['state']}.")
    return Snapshot(ha, entry.get("power", {}), taken=entry["taken"], stored=entry.get("stored", {}), **journaled)


async def recover_roam(
    admin: HAClient | None, bridge: HueBridge | None, journal: Journal, out: Callable[[str], None]
) -> None:
    """Remove the journal's ds-rig-* groups, move its roaming bulbs straight home and put back their Hue rooms and
    scenes; stop on a failure."""
    if admin is None or bridge is None:
        raise SystemExit(
            "Moving the roaming bulbs home needs HA_ADMIN_TOKEN, HUE_BRIDGE_HOST and HUE_APP_KEY in .env.rig; "
            f"the journal ({journal.path}) keeps where they are."
        )
    roamer = Roamer.from_journal(admin, bridge, journal, out)
    out(f"Moving the roaming bulbs home to {NAMES[roamer.home_network]}.")
    try:
        # A group that can't be removed is printed and stays journaled; the rest of recovery goes on.
        await roamer.go(roamer.home_network)
    except RoamError as err:
        raise SystemExit(f"Recovery stopped: {err}") from None


def drop_profile(journal: Journal | None) -> None:
    """Clear the journal's `profile` and `claim` once nothing they describe a run for is left, so an empty journal is
    deleted; while a change is left, they stay, saying which profile's run left it and what putting it back needs."""
    if journal is not None and set(journal.sections) <= {"profile", "claim"}:
        journal.clear("profile", "claim")


if __name__ == "__main__":
    # Line by line even when stdout is a file, so a background caller sees "waiting for the lock" and each result
    # as they happen rather than when the buffer fills.
    sys.stdout.reconfigure(line_buffering=True)
    sys.exit(main())
