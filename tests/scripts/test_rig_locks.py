"""The rig's locks, claims, per-run journals and --hold. flock locks belong to the open file handle, so two handles in
one process conflict as two runs would; no rig is touched."""

import argparse
import asyncio
import contextlib
import fcntl
import importlib.util
import io
import os
import signal
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.rig import baseline, locks
from tests.rig.engine import load_step_file
from tests.rig.journal import LEGACY_NAME, Journal, orphans
from tests.rig.locks import Claim
from tests.rig.profile import Profile
from tests.scripts import rig_fakes as fakes
from tests.scripts.conftest import REAL_WORKSPACE_COLOR

REPO = Path(__file__).parents[2]
_spec = importlib.util.spec_from_file_location("rig_for_locks", REPO / "scripts" / "rig.py")
rig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rig)

SHARED = Claim()
EXCLUSIVE = Claim("exclusive")


def claim(*integrations: str, ha: str = "shared") -> Claim:
    return Claim(ha, frozenset(integrations))


def quiet(lines: list[str] | None = None):
    return (lines if lines is not None else []).append


def blocked(directory: Path, wanted: Claim) -> bool:
    """Whether `wanted` would wait: a hold that may not poll fails at its first wait. Patched within, as callers may
    already have patched the sleep it replaces."""

    def refuse(_seconds):
        raise TimeoutError

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(locks.time, "sleep", refuse)
        try:
            locks.hold(wanted, "probe", directory, out=quiet()).close()
        except TimeoutError:
            return True
    return False


# --- Holder entries -------------------------------------------------------------------------------------------


def claude_session(tmp_path, monkeypatch, name):
    """Run as if under a Claude Code session called `name`, with its registry file under a fake config dir."""
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "4242.json").write_text(f'{{"pid": 4242, "name": "{name}"}}')
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PID", "4242")
    return tmp_path / "sessions" / "4242.json"


def test_the_holder_is_named_as_its_session_is_called_now(tmp_path, monkeypatch):
    session_file = claude_session(tmp_path, monkeypatch, "rig-agent-1a")
    entry = locks.lock_entry("wt/first")
    session_file.write_text('{"name": "renamed"}')
    assert locks.lock_holder(entry).endswith('Claude Code session "renamed" (SendMessage reaches it)')


def test_a_holder_whose_session_file_is_gone_or_unreadable_is_named_by_its_line_alone(tmp_path, monkeypatch):
    session_file = claude_session(tmp_path, monkeypatch, "rig-agent-1a")
    entry = locks.lock_entry("wt/first")
    line = f"wt/first (pid {os.getpid()})"
    for contents in ("not json", '{"pid": 4242}', "[]"):
        session_file.write_text(contents)
        assert locks.lock_holder(entry) == line
    session_file.unlink()
    assert locks.lock_holder(entry) == line
    assert locks.lock_holder("") == "an unnamed process"


def test_a_terminal_run_is_named_by_user_and_tty(monkeypatch):
    monkeypatch.delenv("CLAUDE_PID", raising=False)
    monkeypatch.setattr(locks.getpass, "getuser", lambda: "tester")
    monkeypatch.setattr(locks.os, "ttyname", lambda _fd: "/dev/ttys003")
    assert locks.lock_holder(locks.lock_entry("wt/first")) == f"wt/first (pid {os.getpid()}, user tester on ttys003)"

    def no_tty(_fd):
        raise OSError

    monkeypatch.setattr(locks.os, "ttyname", no_tty)
    assert locks.lock_entry("wt/first") == f"wt/first (pid {os.getpid()}, user tester)\n"


# --- Holding --------------------------------------------------------------------------------------------------


def test_shared_holders_on_different_integrations_both_proceed(tmp_path):
    with locks.hold(claim("hue"), "wt/hue", tmp_path, out=quiet()):
        assert not blocked(tmp_path, claim("zha"))
        assert not blocked(tmp_path, SHARED)


def test_two_holders_of_one_integration_block_each_other(tmp_path):
    with locks.hold(claim("hue", "zha"), "wt/first", tmp_path, out=quiet()):
        assert blocked(tmp_path, claim("zha"))
        assert blocked(tmp_path, claim("shelly", "zha"))


def test_a_waiting_run_names_the_holder_once_and_says_when_it_has_its_locks(tmp_path, monkeypatch):
    claude_session(tmp_path, monkeypatch, "rig-agent-1a")
    held = locks.hold(claim("hue"), "wt/first", tmp_path, out=quiet())
    printed: list[str] = []
    polls: list[float] = []

    def release_on_second_poll(seconds):
        if len(polls) == 1:
            held.close()
        polls.append(seconds)

    monkeypatch.setattr(locks.time, "sleep", release_on_second_poll)
    locks.hold(claim("hue"), "wt/second", tmp_path, out=printed.append).close()

    assert len(polls) == 2
    assert printed == [
        f'Another rig run holds the hue lock: wt/first (pid {os.getpid()}), Claude Code session "rig-agent-1a" '
        "(SendMessage reaches it). Waiting for it to finish (Ctrl-C to give up)...",
        "Rig locks acquired: HA shared, hue.",
    ]
    assert (tmp_path / locks.integration_lock("hue")).read_text().startswith("wt/second ")


def test_a_waiting_run_names_each_new_holder_once(tmp_path, monkeypatch):
    held = [locks.hold(claim("zha"), "wt/first", tmp_path, out=quiet())]
    printed: list[str] = []

    def hand_over(_seconds):
        if len(printed) == 1:  # the first holder finishes and a third run takes the lock before us
            held[0].close()
            held[0] = locks.hold(claim("zha"), "wt/third", tmp_path, out=quiet())
        elif len(printed) == 2:
            held[0].close()

    monkeypatch.setattr(locks.time, "sleep", hand_over)
    locks.hold(claim("zha"), "wt/second", tmp_path, out=printed.append).close()

    assert [line.split(" (pid")[0] for line in printed[:2]] == [
        "Another rig run holds the zha lock: wt/first",
        "Another rig run holds the zha lock: wt/third",
    ]
    assert printed[2] == "Rig locks acquired: HA shared, zha."


def test_an_uncontested_hold_says_nothing_and_colors_the_workspace_green(tmp_path, workspace_colors):
    printed: list[str] = []
    locks.hold(claim("hue"), "wt/first", tmp_path, out=printed.append).close()
    assert printed == []
    assert workspace_colors == [locks.WORKSPACE_HELD]


def test_a_run_colors_its_workspace_amber_while_it_waits(tmp_path, monkeypatch, workspace_colors):
    held = locks.hold(claim("hue"), "wt/first", tmp_path, out=quiet())
    workspace_colors.clear()

    def release(_seconds):
        assert workspace_colors == [locks.WORKSPACE_QUEUED]
        held.close()

    monkeypatch.setattr(locks.time, "sleep", release)
    locks.hold(claim("hue"), "wt/second", tmp_path, out=quiet()).close()
    assert workspace_colors == [locks.WORKSPACE_QUEUED, locks.WORKSPACE_HELD]


def test_an_exclusive_claim_waits_out_the_shared_holders_naming_them(tmp_path, monkeypatch):
    first = locks.hold(claim("hue"), "wt/hue", tmp_path, out=quiet())
    second = locks.hold(claim("zha"), "wt/zha", tmp_path, out=quiet())
    printed: list[str] = []

    def drain(_seconds):
        (first if first.handles else second).close()

    monkeypatch.setattr(locks.time, "sleep", drain)
    locks.hold(EXCLUSIVE, "wt/deploy", tmp_path, out=printed.append).close()

    assert [line.split(" (pid")[0] for line in printed[:1]] == ["Another rig run holds HA: shared by hue: wt/hue"]
    assert "zha: wt/zha" in printed[0]
    assert printed[-1] == "Rig locks acquired: HA exclusive."
    assert (tmp_path / locks.LOCK_NAME).read_text().startswith("wt/deploy ")


def test_shared_claims_wait_for_an_exclusive_holder(tmp_path):
    with locks.hold(EXCLUSIVE, "wt/deploy", tmp_path, out=quiet()):
        assert blocked(tmp_path, claim("hue"))
        assert blocked(tmp_path, SHARED)


def test_a_waiting_exclusive_claim_holds_off_new_shared_ones(tmp_path, monkeypatch):
    """The turnstile: once a deploy waits for HA, a new shared claim queues behind it rather than starve it."""
    sharing = locks.hold(claim("hue"), "wt/hue", tmp_path, out=quiet())
    seen: list[bool] = []

    def meanwhile(_seconds):
        if not seen:
            seen.append(blocked(tmp_path, claim("zha")))
        sharing.close()

    monkeypatch.setattr(locks.time, "sleep", meanwhile)
    locks.hold(EXCLUSIVE, "wt/deploy", tmp_path, out=quiet()).close()
    assert seen == [True]


def test_the_waits_name_the_turnstile_holder(tmp_path, monkeypatch):
    with (tmp_path / locks.TURNSTILE_NAME).open("a+") as turnstile:
        fcntl.flock(turnstile, fcntl.LOCK_EX)
        locks.write_holder(turnstile, "wt/deploy, waiting for HA")
        printed: list[str] = []
        monkeypatch.setattr(locks.time, "sleep", lambda _s: fcntl.flock(turnstile, fcntl.LOCK_UN))
        locks.hold(claim("hue"), "wt/hue", tmp_path, out=printed.append).close()
    assert printed[0].startswith("Another rig run holds the turn for HA: wt/deploy, waiting for HA (pid")


def test_an_exclusive_wait_leaves_its_own_integrations_out_of_the_holders(tmp_path, monkeypatch):
    sharing = locks.hold(claim("zha"), "wt/zha", tmp_path, out=quiet())
    printed: list[str] = []
    monkeypatch.setattr(locks.time, "sleep", lambda _s: sharing.close())
    locks.hold(claim("hue", ha="exclusive"), "wt/deploy", tmp_path, out=printed.append).close()
    assert printed[0].startswith("Another rig run holds HA: shared by zha: wt/zha (pid")
    assert "hue:" not in printed[0]


def test_claims_take_their_integrations_in_sorted_order(tmp_path, monkeypatch):
    """Two claims over the same integrations, listed in either order, take them in one order, which is what keeps two
    runs from each holding what the other waits for: the second waits on the first's first lock, holding nothing."""
    first = locks.hold(Claim("shared", frozenset(["zha", "hue"])), "wt/first", tmp_path, out=quiet())
    printed: list[str] = []

    def release(_seconds):
        first.close()

    monkeypatch.setattr(locks.time, "sleep", release)
    second = locks.hold(Claim("exclusive", frozenset(["hue", "zha"])), "wt/second", tmp_path, out=printed.append)
    assert printed[0].startswith("Another rig run holds the hue lock: wt/first")
    assert len(second.handles) == 3
    second.close()


def test_a_failed_wait_lets_go_of_what_it_took(tmp_path):
    def give_up(_seconds):
        raise KeyboardInterrupt

    with locks.hold(claim("zha"), "wt/zha", tmp_path, out=quiet()), pytest.MonkeyPatch.context() as patch:
        patch.setattr(locks.time, "sleep", give_up)
        with pytest.raises(KeyboardInterrupt):
            locks.hold(claim("hue", "zha"), "wt/both", tmp_path, out=quiet())
    assert not blocked(tmp_path, claim("hue"))


def test_the_legacy_lock_path_still_excludes_new_runs(tmp_path):
    """A run from an older checkout takes device_side-rig.lock exclusively; new runs wait for it, and it for them."""
    assert locks.LOCK_NAME == "device_side-rig.lock"
    with (tmp_path / "device_side-rig.lock").open("a+") as old:
        fcntl.flock(old, fcntl.LOCK_EX)
        old.write("release/v0.0.1 (pid 1)\n")
        old.flush()
        assert blocked(tmp_path, claim("hue"))
        assert locks.holders(tmp_path, claim("hue")) == ["HA: release/v0.0.1 (pid 1), exclusively"]
    with locks.hold(claim("hue"), "wt/new", tmp_path, out=quiet()), (tmp_path / "device_side-rig.lock").open() as old:
        with pytest.raises(BlockingIOError):
            fcntl.flock(old, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_holders_lists_what_a_claim_would_wait_for(tmp_path):
    assert locks.holders(tmp_path, claim("hue", ha="exclusive")) == []
    with locks.hold(claim("zha"), "wt/zha", tmp_path, out=quiet()):
        assert locks.holders(tmp_path, claim("hue")) == []
        assert locks.holders(tmp_path, claim("hue", ha="exclusive")) == ["HA: shared by a run on no other integration"]
        lines = locks.holders(tmp_path, claim("zha", ha="exclusive"))
        assert [line.split(" (pid")[0] for line in lines] == ["zha: wt/zha", "HA: shared by the runs above"]


def test_share_ha_keeps_the_integrations_and_lets_a_shared_run_start(tmp_path):
    with locks.hold(claim("zigbee2mqtt", ha="exclusive"), "wt/deploy", tmp_path, out=quiet()) as held:
        assert blocked(tmp_path, claim("shelly"))
        held.share_ha(out=quiet())
        assert held.claim == claim("zigbee2mqtt")
        assert not blocked(tmp_path, claim("shelly"))
        assert blocked(tmp_path, claim("zigbee2mqtt"))
        assert blocked(tmp_path, EXCLUSIVE)
        assert locks.held_by(tmp_path / locks.LOCK_NAME) is None


def test_a_share_ha_that_waited_says_so_and_turns_the_workspace_green(tmp_path, monkeypatch, workspace_colors):
    """flock's conversion may drop HA first, so a queued deploy can slip in; the run then waits for HA shared."""
    printed: list[str] = []
    with locks.hold(claim("hue", ha="exclusive"), "wt/deploy", tmp_path, out=quiet()) as held:
        workspace_colors.clear()
        monkeypatch.setattr(
            locks, "wait_for_lock", lambda *_args: workspace_colors.append(locks.WORKSPACE_QUEUED) or True
        )
        held.share_ha(out=printed.append)
    assert printed == ["Rig locks acquired: HA shared, hue."]
    assert workspace_colors == [locks.WORKSPACE_QUEUED, locks.WORKSPACE_HELD]


def test_share_ha_on_a_shared_hold_does_nothing(tmp_path):
    with locks.hold(claim("hue"), "wt/hue", tmp_path, out=quiet()) as held:
        held.share_ha(out=quiet())
        assert held.claim == claim("hue")
        assert not blocked(tmp_path, claim("zha"))


# --- Claims ---------------------------------------------------------------------------------------------------


def test_claims_cover_and_combine():
    assert claim("hue", "zha").covers(claim("hue"))
    assert not claim("hue").covers(claim("hue", ha="exclusive"))
    assert EXCLUSIVE.covers(SHARED)
    assert claim("hue") | claim("zha", ha="exclusive") == claim("hue", "zha", ha="exclusive")
    assert Claim.of(claim("zha").as_json()) == claim("zha")
    assert Claim.of(None) == Claim.everything()
    assert str(claim("zha", "hue")) == "HA shared, hue, zha"


def run_args(*argv: str) -> argparse.Namespace:
    return argparse.Namespace(no_deploy="--no-deploy" in argv, roam_check="--roam-check" in argv)


def setup(tmp_path, profile, suites, deploy_needed=False, roaming=False, grouping=False, registry=None) -> rig.Setup:
    tree = "old" if deploy_needed else "tree"
    deploy = rig.Deploy("c1", "tree", tree, tree, "wt")
    return rig.Setup({}, profile, registry or fakes.OPTION_REGISTRY, suites, roaming, grouping, deploy)


def step_suites(tmp_path: Path, text: str, *integrations: str) -> list:
    path = tmp_path / f"steps-{len(list(tmp_path.iterdir()))}.yaml"
    path.write_text(text)
    return [rig.Suite(load_step_file(path), integration) for integration in integrations]


def test_a_plain_run_claims_its_integrations_and_ha_shared(tmp_path):
    profile = fakes.profile("shelly", light_ct="light.a")
    run = setup(tmp_path, profile, step_suites(tmp_path, fakes.RESTORED_MIDWAY, "shelly"))
    assert rig.claim(run_args(), run) == claim("shelly")


def test_a_deploy_takes_ha_exclusive_unless_no_deploy(tmp_path):
    profile = fakes.profile("shelly", light_ct="light.a")
    run = setup(tmp_path, profile, step_suites(tmp_path, fakes.RESTORED_MIDWAY, "shelly"), deploy_needed=True)
    assert rig.claim(run_args(), run) == claim("shelly", ha="exclusive")
    assert rig.claim(run_args("--no-deploy"), run) == claim("shelly")


def test_an_option_suite_takes_ha_exclusive(tmp_path):
    profile = fakes.profile("shelly", light_ct="light.a")
    options = fakes.RESTORED_MIDWAY.replace("tests:", "options: [opt]\ntests:", 1)
    run = setup(tmp_path, profile, step_suites(tmp_path, options, "shelly"), registry=fakes.OPTION_REGISTRY)
    assert rig.claim(run_args(), run) == claim("shelly", ha="exclusive")


def test_a_suite_with_no_adapter_claims_nothing(tmp_path):
    profile = fakes.profile("shelly", light_ct="light.a")
    run = setup(
        tmp_path,
        profile,
        step_suites(tmp_path, fakes.RESTORED_MIDWAY, "shelly"),
        registry=SimpleNamespace(adapter=lambda action, integration: None),
    )
    assert rig.claim(run_args(), run) == SHARED


def test_a_zha_only_roam_claims_hue_and_zha_not_z2m(tmp_path):
    profile = Profile.load(fakes.lab_profile(tmp_path, networks="hue, zha"))
    run = setup(tmp_path, profile, step_suites(tmp_path, fakes.RESTORED_MIDWAY, "zha"), roaming=True)
    assert rig.claim(run_args(), run) == claim("hue", "zha")


def test_a_run_on_an_undeclared_network_claims_it_but_not_the_bulbs_networks(tmp_path):
    profile = Profile.load(fakes.lab_profile(tmp_path, networks="hue, zha"))
    run_suites = step_suites(tmp_path, fakes.RESTORED_MIDWAY, "zigbee2mqtt")
    assert not rig.roams(profile, run_suites)
    assert rig.claim(run_args(), setup(tmp_path, profile, run_suites)) == claim("zigbee2mqtt")


def test_roam_check_claims_every_declared_network(tmp_path):
    profile = Profile.load(fakes.lab_profile(tmp_path))
    run = setup(tmp_path, profile, [], deploy_needed=True, roaming=True, grouping=True)
    assert rig.claim(run_args("--roam-check"), run) == claim("hue", "zha", "zigbee2mqtt")
    profile = Profile.load(fakes.lab_profile(tmp_path, networks="hue, zigbee2mqtt"))
    run = setup(tmp_path, profile, [], deploy_needed=True, roaming=True, grouping=True)
    assert rig.claim(run_args("--roam-check"), run) == claim("hue", "zigbee2mqtt")


def test_a_run_claims_the_integration_that_powers_its_entities(tmp_path):
    path = tmp_path / "powered.yaml"
    path.write_text(
        "shelly:\n  - entity_id: switch.supply\n    roles: [switch_plug]\n"
        "hue:\n  - entity_id: light.lamp\n    roles: [light_ct]\n    powered_by: switch.supply\n"
    )
    profile = Profile.load(path)
    assert rig.supplies(profile, {"hue"}) == {"shelly"}
    assert rig.supplies(profile, {"shelly"}) == set()


def test_a_run_upgrades_to_exclusive_when_it_finds_a_deploy_is_needed(tmp_path, monkeypatch, capsys):
    """It waited for HA shared while HA had its tree; meanwhile another run deployed its own, so this one must
    deploy after all: it lets go and takes HA exclusively."""
    profile = fakes.profile("shelly", light_ct="light.a")
    run = setup(tmp_path, profile, step_suites(tmp_path, fakes.RESTORED_MIDWAY, "shelly"))
    states = iter([rig.Deploy("c1", "tree", "other", "other", "wt"), rig.Deploy("c1", "tree", "other", "other", "wt")])
    monkeypatch.setattr(rig, "deploy_state", lambda _cmd: next(states))
    monkeypatch.setattr(rig, "git", lambda *args, check=True: "wt")
    taken: list[Claim] = []
    real_hold = locks.hold
    monkeypatch.setattr(
        rig.locks,
        "hold",
        lambda wanted, holder, directory, **kw: taken.append(wanted) or real_hold(wanted, holder, directory, **kw),
    )

    held = rig.take(run_args(), run, tmp_path)

    assert taken == [claim("shelly"), claim("shelly", ha="exclusive")]
    assert held.claim == claim("shelly", ha="exclusive")
    assert "it now needs HA exclusive, shelly" in capsys.readouterr().out
    held.close()


def test_a_run_that_still_matches_keeps_its_first_claim(tmp_path, monkeypatch):
    profile = fakes.profile("shelly", light_ct="light.a")
    run = setup(tmp_path, profile, step_suites(tmp_path, fakes.RESTORED_MIDWAY, "shelly"))
    monkeypatch.setattr(rig, "deploy_state", lambda _cmd: rig.Deploy("c1", "tree", "tree", "tree", "wt"))
    monkeypatch.setattr(rig, "git", lambda *args, check=True: "wt")
    with rig.take(run_args(), run, tmp_path) as held:
        assert held.claim == claim("shelly")


def approved(tmp_path, monkeypatch, run, deploying: bool) -> tuple[locks.Held, list[Claim]]:
    """run_approved with the deploy and the tests faked out: what the run holds after, and the claim run_rig got."""
    held = locks.hold(rig.claim(run_args(), run), "wt", tmp_path, out=quiet())
    given: list[Claim] = []
    monkeypatch.setattr(rig, "deploy_and_wait", lambda _env, _branch: None)
    monkeypatch.setattr(rig, "tested_commit", lambda *_args: "c1")
    monkeypatch.setattr(rig, "run_rig", lambda *_args, claim, **_kw: given.append(claim))
    monkeypatch.setattr(rig, "run_tests", lambda _run: 0)
    rig.run_approved(SimpleNamespace(keyword=None, unattended=True, debug_logs=False), run, held, None, deploying, True)
    return held, given


def test_a_deploying_run_without_options_steps_ha_down_to_shared(tmp_path, monkeypatch):
    profile = fakes.profile("shelly", light_ct="light.a")
    run = setup(tmp_path, profile, step_suites(tmp_path, fakes.RESTORED_MIDWAY, "shelly"), deploy_needed=True)
    held, given = approved(tmp_path, monkeypatch, run, deploying=True)
    with held:
        assert held.claim == given[0] == claim("shelly")
        assert not blocked(tmp_path, claim("zha"))


def test_a_run_that_does_not_deploy_keeps_its_claim(tmp_path, monkeypatch):
    profile = fakes.profile("shelly", light_ct="light.a")
    run = setup(tmp_path, profile, step_suites(tmp_path, fakes.RESTORED_MIDWAY, "shelly"))
    held, given = approved(tmp_path, monkeypatch, run, deploying=False)
    with held:
        assert held.claim == given[0] == claim("shelly")


def test_a_deploying_run_with_options_keeps_ha_exclusive(tmp_path, monkeypatch):
    profile = fakes.profile("shelly", light_ct="light.a")
    options = fakes.RESTORED_MIDWAY.replace("tests:", "options: [opt]\ntests:", 1)
    run = setup(tmp_path, profile, step_suites(tmp_path, options, "shelly"), deploy_needed=True)
    held, given = approved(tmp_path, monkeypatch, run, deploying=True)
    with held:
        assert held.claim == given[0] == claim("shelly", ha="exclusive")
        assert blocked(tmp_path, claim("zha"))


# --- Journals -------------------------------------------------------------------------------------------------


def test_a_run_journal_is_locked_and_leaves_nothing_once_empty(tmp_path):
    journal = Journal.start(tmp_path)
    assert journal.path.name.startswith(f"device_side-rig.journal.{os.getpid()}-")
    journal.update(paused=["automation.motion"])
    assert orphans(tmp_path) == []  # held, so not an orphan
    journal.clear("paused")
    journal.release()
    assert list(tmp_path.iterdir()) == []


def test_a_journal_its_run_left_is_an_orphan_until_put_back(tmp_path):
    journal = Journal.start(tmp_path)
    journal.update(claim=claim("hue").as_json(), cases={"hue": {}})
    journal.release()  # as when its run dies: the lock goes, the journal stays

    [orphan] = orphans(tmp_path)
    assert orphan.get("cases") == {"hue": {}}
    assert orphans(tmp_path) == []  # this process holds it while it puts it back
    orphan.clear("cases", "claim")
    orphan.release()
    assert list(tmp_path.iterdir()) == []


def test_orphans_sweeps_a_dead_runs_lock_with_no_journal(tmp_path):
    Journal.start(tmp_path).release()
    (tmp_path / "device_side-rig.journal.1-abc.lock").touch()
    assert orphans(tmp_path) == []
    assert list(tmp_path.iterdir()) == []


def orphan(directory: Path, wanted: Claim | None, **sections) -> Path:
    journal = Journal.start(directory)
    journal.update(profile="lab", **({"claim": wanted.as_json()} if wanted else {}), **sections)
    journal.release()
    return journal.path


CASE = {"hue": {"taken": {}, "stored": {}, "power": {}}}


def test_needs_is_the_orphans_integrations_and_ha_exclusive_for_options(tmp_path):
    orphan(tmp_path, claim("hue", ha="exclusive"), cases=CASE)
    orphan(tmp_path, claim("zha"), options={"opt": True})
    orphan(tmp_path, None, cases=CASE)
    needed = sorted((rig.needs(journal) for journal in orphans(tmp_path)), key=str)
    assert claim("zha", ha="exclusive") in needed
    assert claim("hue") in needed  # a deploy's exclusive HA isn't needed to put its cases back
    assert Claim("shared", Claim.everything().integrations) in needed


def replayed(tmp_path, monkeypatch, held: Claim | None) -> list[str]:
    """Run replay holding `held`; the journals recover_rig was asked to put back."""
    put_back: list[str] = []

    async def recover_rig(env, journal):
        put_back.append(journal.path.name)
        journal.clear(*journal.sections)

    monkeypatch.setattr(rig, "recover_rig", recover_rig)
    holding = locks.Held(held) if held is not None else None
    rig.replay({}, holding, tmp_path)
    return put_back


def test_an_orphan_is_replayed_only_when_the_claim_covers_it(tmp_path, monkeypatch, capsys):
    hue = orphan(tmp_path, claim("hue"), cases=CASE).name
    zha = orphan(tmp_path, claim("zha"), cases=CASE).name

    assert replayed(tmp_path, monkeypatch, claim("hue", "shelly")) == [hue]
    out = capsys.readouterr().out
    assert f"{zha} that need HA shared, zha, more than this run holds" in out
    assert replayed(tmp_path, monkeypatch, claim("zha")) == [zha]
    assert sorted(path.name for path in tmp_path.iterdir()) == []


def test_an_orphan_with_options_needs_ha_exclusive(tmp_path, monkeypatch):
    options = orphan(tmp_path, claim("hue"), options={"opt": True}).name
    assert replayed(tmp_path, monkeypatch, claim("hue")) == []
    assert replayed(tmp_path, monkeypatch, claim("hue", ha="exclusive")) == [options]


def test_a_dry_run_only_says_what_orphans_there_are(tmp_path, monkeypatch, capsys):
    path = orphan(tmp_path, claim("hue"), cases=CASE, roam={"home": {"light.lab_a": {}}})
    assert rig.replay({}, None, tmp_path) == {"light.lab_a"}
    assert f"left changes in {path}; a run holding HA shared, hue puts them back first" in capsys.readouterr().out
    assert path.exists()


def test_the_legacy_journal_is_replayed_only_by_recover(tmp_path, monkeypatch, capsys):
    legacy = Journal(tmp_path / LEGACY_NAME)
    legacy.update(profile="lab", cases=CASE)
    assert replayed(tmp_path, monkeypatch, Claim.everything()) == []
    assert "--recover puts them back" in capsys.readouterr().out

    put_back: list[str] = []

    async def recover_rig(env, journal):
        put_back.append(journal.path.name)
        journal.clear(*journal.sections)

    monkeypatch.setattr(rig, "recover_rig", recover_rig)
    monkeypatch.setattr(rig, "load_env", dict)
    monkeypatch.setattr(rig, "git", lambda *args, check=True: "wt")
    assert rig.recover_all(argparse.Namespace(dry_run=False), tmp_path) == 0
    assert put_back == [LEGACY_NAME]


def test_recover_holds_everything_and_puts_back_every_orphan(tmp_path, monkeypatch, capsys):
    names = sorted([orphan(tmp_path, claim("hue"), cases=CASE).name, orphan(tmp_path, None, options={}).name])
    put_back: list[str] = []

    async def recover_rig(env, journal):
        put_back.append(journal.path.name)
        assert locks.holders(tmp_path, Claim.everything())  # it holds every lock
        journal.clear(*journal.sections)

    monkeypatch.setattr(rig, "recover_rig", recover_rig)
    monkeypatch.setattr(rig, "load_env", dict)
    monkeypatch.setattr(rig, "git", lambda *args, check=True: "wt")
    args = argparse.Namespace(dry_run=True)
    assert rig.recover_all(args, tmp_path) == 1
    assert put_back == []
    args.dry_run = False
    assert rig.recover_all(args, tmp_path) == 0
    assert sorted(put_back) == names
    assert rig.recover_all(args, tmp_path) == 0
    assert "No aborted run left anything to put back." in capsys.readouterr().out


# --- main -----------------------------------------------------------------------------------------------------


@pytest.fixture
def no_run(monkeypatch, tmp_path):
    """main with nothing to read or run: prepare, take and run_held stubbed."""
    monkeypatch.setattr(rig, "common_dir", lambda: tmp_path)
    monkeypatch.setattr(rig, "prepare", lambda args: None)
    monkeypatch.setattr(rig, "take", lambda args, setup, directory: locks.Held(SHARED))
    monkeypatch.setattr(rig, "run_held", lambda *_args: 0)


def test_main_clears_the_workspace_color_when_the_run_ends_but_not_after_a_dry_run(no_run, workspace_colors):
    rig.main(["--dry-run"])
    assert workspace_colors == []
    rig.main([])
    assert workspace_colors == [None]


def test_main_clears_the_workspace_color_when_a_wait_is_given_up(no_run, monkeypatch, workspace_colors):
    def interrupted(*_args):
        raise KeyboardInterrupt

    monkeypatch.setattr(rig, "take", interrupted)
    with pytest.raises(KeyboardInterrupt):
        rig.main([])
    assert workspace_colors == [None]


def test_a_sigterm_while_queued_for_the_locks_still_clears_the_workspace_color(no_run, monkeypatch, workspace_colors):
    monkeypatch.setattr(rig, "take", lambda *_args: os.kill(os.getpid(), signal.SIGTERM))
    with pytest.raises(SystemExit) as stopped:
        rig.main([])
    assert stopped.value.code == 128 + signal.SIGTERM
    assert workspace_colors == [None]


def test_workspace_color_calls_cmux_only_inside_a_cmux_workspace(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(locks.subprocess, "run", lambda command, **_kw: calls.append(command))
    monkeypatch.setattr(locks.shutil, "which", lambda _name: "/bin/cmux")
    monkeypatch.delenv("CMUX_WORKSPACE_ID", raising=False)
    REAL_WORKSPACE_COLOR("Green")
    assert calls == []

    monkeypatch.setenv("CMUX_WORKSPACE_ID", "workspace:7")
    REAL_WORKSPACE_COLOR("Green")
    REAL_WORKSPACE_COLOR(None)
    assert calls == [
        ["cmux", "workspace-action", "--workspace", "workspace:7", "--action", "set-color", "--color", "Green"],
        ["cmux", "workspace-action", "--workspace", "workspace:7", "--action", "clear-color"],
    ]

    monkeypatch.setattr(locks.shutil, "which", lambda _name: None)
    calls.clear()
    REAL_WORKSPACE_COLOR("Green")
    assert calls == []


def test_workspace_color_swallows_a_cmux_failure(monkeypatch):
    def fail(*_args, **_kwargs):
        raise locks.subprocess.TimeoutExpired("cmux", 5)

    monkeypatch.setattr(locks.subprocess, "run", fail)
    monkeypatch.setattr(locks.shutil, "which", lambda _name: "/bin/cmux")
    monkeypatch.setenv("CMUX_WORKSPACE_ID", "workspace:7")
    REAL_WORKSPACE_COLOR("Amber")


# --- --wait-free ----------------------------------------------------------------------------------------------


def test_wait_free_returns_at_once_when_nothing_is_held(tmp_path, monkeypatch):
    def no_sleep(_seconds):
        raise AssertionError("wait_free polled a free lock")

    monkeypatch.setattr(locks.time, "sleep", no_sleep)
    printed: list[str] = []
    locks.wait_free(tmp_path, out=printed.append)
    locks.wait_free(tmp_path, ["zha"], out=printed.append)
    locks.wait_free(tmp_path, ["hue", "zha"], out=printed.append)
    assert printed == ["Every rig lock is free.", "Zha is free.", "Hue, zha are free."]


def test_wait_free_waits_for_the_named_integrations_and_an_exclusive_ha_only(tmp_path, monkeypatch):
    printed: list[str] = []
    with locks.hold(claim("hue"), "wt/hue", tmp_path, out=quiet()) as held:
        monkeypatch.setattr(locks.time, "sleep", lambda _s: pytest.fail("waited for hue"))
        locks.wait_free(tmp_path, ["zha"], out=printed.append)  # HA shared doesn't count
        monkeypatch.setattr(locks.time, "sleep", lambda _s: held.close())
        locks.wait_free(tmp_path, ["hue"], out=printed.append)
    assert [line.split(" (pid")[0] for line in printed] == [
        "Zha is free.",
        "Another rig run holds the hue lock: wt/hue",
        "Hue is free.",
    ]


def test_wait_free_with_no_filter_waits_for_every_holder_without_taking_anything(tmp_path, monkeypatch):
    printed: list[str] = []
    held = locks.hold(SHARED, "wt/probe", tmp_path, out=quiet())  # a run on no integration still holds HA
    monkeypatch.setattr(locks.time, "sleep", lambda _s: held.close())
    locks.wait_free(tmp_path, out=printed.append)
    assert printed[0].startswith("Another rig run holds HA: shared by a run on no integration")
    assert printed[-1] == "Every rig lock is free."
    assert not blocked(tmp_path, EXCLUSIVE)  # wait_free kept no hold


def test_wait_free_names_an_exclusive_ha_holder(tmp_path, monkeypatch):
    printed: list[str] = []
    held = locks.hold(EXCLUSIVE, "wt/deploy", tmp_path, out=quiet())
    monkeypatch.setattr(locks.time, "sleep", lambda _s: held.close())
    locks.wait_free(tmp_path, out=printed.append)
    assert printed[0].startswith("Another rig run holds HA: wt/deploy (pid")
    assert ", exclusively. Waiting" in printed[0]


def test_a_run_waits_out_a_dry_runs_probe_of_an_orphan(tmp_path, monkeypatch):
    """A dry run holds an orphan's lock only for a moment; a run scanning meanwhile still finds it an orphan."""
    path = orphan(tmp_path, claim("hue"), cases=CASE)
    probe = path.with_suffix(".lock").open("a+")
    fcntl.flock(probe, fcntl.LOCK_EX)
    monkeypatch.setattr("tests.rig.journal.time.sleep", lambda _s: probe.close())
    [found] = orphans(tmp_path)
    assert found.path == path
    found.release()


def test_main_wait_free_stops_before_the_journals_and_env(tmp_path, monkeypatch, workspace_colors):
    def untouched(*_args):
        raise AssertionError("--wait-free went past the locks")

    asked = []
    monkeypatch.setattr(rig, "common_dir", lambda: tmp_path)
    monkeypatch.setattr(rig, "prepare", untouched)
    monkeypatch.setattr(rig, "load_env", untouched)
    monkeypatch.setattr(rig.locks, "wait_free", lambda directory, integrations: asked.append(integrations))
    assert rig.main(["--wait-free", "--integration", "zha"]) == 0
    assert asked == [["zha"]]
    assert workspace_colors == [None]


# --- --hold ---------------------------------------------------------------------------------------------------


@pytest.fixture
def probe(tmp_path, monkeypatch):
    monkeypatch.setattr(rig, "common_dir", lambda: tmp_path)
    monkeypatch.setattr(rig, "git", lambda *args, check=True: "wt/probe")
    monkeypatch.setattr(rig, "load_env", lambda: {"HA_URL": "http://ha:8123", "HA_TOKEN": "tok"})
    profile = tmp_path / "lab.yaml"
    profile.write_text("pause:\n  all: [automation.motion]\n  hue: [switch.al]\nshelly:\n")
    monkeypatch.setattr(rig, "choose_profile", lambda name, env: profile)
    monkeypatch.setattr(ProbeHA, "states", {"automation.motion": "on", "switch.al": "on"})
    monkeypatch.setattr(ProbeHA, "calls", [])
    monkeypatch.setattr(rig, "HAClient", ProbeHA)
    return tmp_path


class ProbeHA:
    """The HA a probe's pauses go to: one state per entity, and the calls, shared by every connection."""

    states = {"automation.motion": "on", "switch.al": "on"}
    calls: list = []

    def __init__(self, url, token):
        pass

    async def connect(self):
        pass

    async def close(self):
        pass

    async def get_state(self, entity_id):
        return {"state": self.states[entity_id]}

    async def call_service(self, domain, service, data):
        self.calls.append((service, data["entity_id"]))
        self.states[data["entity_id"]] = "on" if service == "turn_on" else "off"


def test_hold_pauses_its_integrations_entries_while_the_command_runs(probe, monkeypatch):
    seen = []
    monkeypatch.setattr(rig, "run_command", lambda command: seen.append(dict(ProbeHA.states)) or 3)

    assert rig.main(["--hold", "zha", "--", "true"]) == 3  # zha pauses only the `all` list

    assert seen == [{"automation.motion": "off", "switch.al": "on"}]
    assert ProbeHA.calls == [("turn_off", "automation.motion"), ("turn_on", "automation.motion")]
    assert not list(probe.glob("device_side-rig.journal.*"))  # its liveness token is gone with it
    assert not (probe / baseline.NAME).exists()


def test_hold_pausing_nothing_needs_no_ha(probe, monkeypatch):
    (probe / "lab.yaml").write_text("shelly:\n")
    monkeypatch.setattr(rig, "load_env", dict)
    assert rig.main(["--hold", "hue", "--", "true"]) == 0


def test_recover_puts_back_a_crashed_probes_pauses_with_no_orphan_journal(probe, capsys):
    crashed = Journal.start(probe)  # a probe's journal is never written
    asyncio.run(baseline.Baseline.of(ProbeHA("", ""), crashed, "pause").pause(["automation.motion"]))
    crashed.release()
    assert ProbeHA.states["automation.motion"] == "off"

    assert rig.recover_all(argparse.Namespace(dry_run=False), probe) == 0

    assert "No aborted run left anything to put back." in capsys.readouterr().out
    assert ProbeHA.states["automation.motion"] == "on"
    assert not (probe / baseline.NAME).exists()


def test_hold_pausing_needs_ha_settings(probe, monkeypatch):
    monkeypatch.setattr(rig, "load_env", dict)
    with pytest.raises(SystemExit, match="HA_URL and HA_TOKEN must be set"):
        rig.main(["--hold", "hue", "--", "true"])


def test_hold_runs_the_command_holding_its_claim_and_returns_its_exit_code(probe):
    script = (
        "import fcntl, sys\n"
        f"handle = open({str(probe / locks.integration_lock('hue'))!r})\n"
        "try:\n    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)\nexcept BlockingIOError:\n    sys.exit(7)\n"
    )
    assert rig.main(["--hold", "hue", "--", sys.executable, "-c", script]) == 7  # it found hue held
    assert "wt/probe (probe: " in (probe / locks.integration_lock("hue")).read_text()
    assert not blocked(probe, claim("hue", ha="exclusive"))  # all let go


def test_hold_exclusive_holds_ha_exclusively(probe, monkeypatch):
    seen = []
    monkeypatch.setattr(rig, "run_command", lambda command: seen.append(blocked(probe, SHARED)) or 0)
    assert rig.main(["--exclusive", "--", "true"]) == 0
    assert seen == [True]


def test_hold_passes_a_signal_on_and_lets_go(probe):
    script = "import os, signal, time\nos.kill(os.getppid(), signal.SIGTERM)\ntime.sleep(30)\n"
    assert rig.main(["--hold", "zha", "--", sys.executable, "-c", script]) == 128 + signal.SIGTERM
    assert not blocked(probe, claim("zha", ha="exclusive"))


def clear_states(monkeypatch, *states):
    """The rig's clear sensor reads each state in turn; the probe's env names it."""
    env = {"HA_URL": "http://ha:8123", "HA_TOKEN": "tok", "RIG_BLOCKER_ENTITY": "binary_sensor.rig_blocker"}
    monkeypatch.setattr(rig, "load_env", lambda: env)
    replies = [{"state": state} for state in states]
    monkeypatch.setattr(rig, "_get", lambda url, token: replies.pop(0))
    seen = []
    monkeypatch.setattr(
        rig, "watching", lambda env, blocker: seen.append(blocker is not None) or contextlib.nullcontext()
    )
    return seen


def test_an_agents_probe_is_refused_while_the_rig_is_not_clear(probe, monkeypatch, capsys):
    clear_states(monkeypatch, "on")
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))  # an agent's call: no terminal
    monkeypatch.setattr(rig, "run_command", lambda command: pytest.fail("ran"))
    assert rig.main(["--hold", "hue", "--", "true"]) == 1
    assert "Rig not clear (binary_sensor.rig_blocker is on). Proceed anyway?" in capsys.readouterr().out
    assert ProbeHA.calls == []
    assert not blocked(probe, claim("hue", ha="exclusive"))


def test_a_probe_is_checked_again_once_it_holds_its_locks(probe, monkeypatch):
    clear_states(monkeypatch, "off", "on")
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    monkeypatch.setattr(rig, "run_command", lambda command: pytest.fail("ran"))
    assert rig.main(["--hold", "hue", "--", "true"]) == 1
    assert ProbeHA.calls == []


def test_a_clear_probe_runs_watched(probe, monkeypatch):
    armed = clear_states(monkeypatch, "off", "off")
    monkeypatch.setattr(rig, "run_command", lambda command: 0)
    assert rig.main(["--hold", "hue", "--", "true"]) == 0
    assert armed == [True]


def test_a_probe_a_human_let_past_is_not_watched_or_asked_again(probe, monkeypatch):
    armed = clear_states(monkeypatch, "on")
    monkeypatch.setattr(sys, "stdin", io.StringIO("y\n"))
    monkeypatch.setattr(rig, "run_command", lambda command: 0)
    assert rig.main(["--hold", "hue", "--", "true"]) == 0
    assert armed == [False]


def test_a_probe_without_the_key_is_not_watched(probe, monkeypatch):
    seen = []
    monkeypatch.setattr(
        rig, "watching", lambda env, blocker: seen.append(blocker is not None) or contextlib.nullcontext()
    )
    monkeypatch.setattr(rig, "run_command", lambda command: 0)
    assert rig.main(["--hold", "hue", "--", "true"]) == 0
    assert seen == [False]


def test_a_pre_authorized_probe_is_not_watched_or_asked(probe, monkeypatch):
    seen = clear_states(monkeypatch)  # no reply: reading the sensor would fail
    with (probe / "lab.yaml").open("a") as profile:
        profile.write("pre_authorized: true\n")
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    monkeypatch.setattr(rig, "run_command", lambda command: 0)
    assert rig.main(["--hold", "hue", "--", "true"]) == 0
    assert seen == [False]


def test_a_probe_aborts_when_the_rig_stops_being_clear(probe, monkeypatch, capsys):
    states = ["off", "off", "on", "on"]  # the gate's two reads, then the watcher's
    env = {"HA_URL": "http://ha:8123", "HA_TOKEN": "tok", "RIG_BLOCKER_ENTITY": "binary_sensor.rig_blocker"}
    monkeypatch.setattr(rig, "load_env", lambda: env)
    monkeypatch.setattr(rig, "_get", lambda url, token: {"state": states.pop(0) if states else "on"})
    watching = rig.watching
    monkeypatch.setattr(
        rig, "watching", lambda env, blocker: watching(env, blocker, interval=0.2)
    )  # time to start the command

    assert (
        rig.main(["--hold", "hue", "--", sys.executable, "-c", "import time; time.sleep(30)"]) == 128 + signal.SIGTERM
    )
    assert "Rig authorization revoked (binary_sensor.rig_blocker is on); aborting." in capsys.readouterr().out
    assert ProbeHA.states == {"automation.motion": "on", "switch.al": "on"}  # resumed
    assert not blocked(probe, claim("hue", ha="exclusive"))


def test_hold_reports_a_command_it_cannot_run(probe):
    with pytest.raises(SystemExit, match="Can't run /no/such/probe"):
        rig.main(["--hold", "hue", "--", "/no/such/probe"])


@pytest.mark.parametrize(
    "argv",
    [
        ["--hold", "hue"],
        ["--", "true"],
        ["--exclusive"],
        ["--hold", "hue", "--dry-run", "--", "true"],
        ["--hold", "nowhere", "--", "true"],
    ],
)
def test_hold_refuses_a_bad_command_line(argv, capsys):
    with pytest.raises(SystemExit):
        rig.main(argv)
    assert "error:" in capsys.readouterr().err
