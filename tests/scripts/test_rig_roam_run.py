"""scripts/rig.py with a roaming profile: phases by the cycle, a move before each and home after the last, a crash in
each phase, --roam-check, and --recover bringing the bulbs home. Against the Lab fake; no rig is touched."""

import asyncio
import contextlib
import importlib.util
import io
import sys
from pathlib import Path

import pytest

from custom_components.device_side.core.registry import AdapterRegistry
from tests.rig import engine, roam
from tests.rig.engine import load_step_file
from tests.rig.journal import LEGACY_NAME, Journal
from tests.rig.profile import Profile
from tests.rig.roam import Roamer
from tests.scripts import rig_fakes as fakes

REPO = Path(__file__).parents[2]
_spec = importlib.util.spec_from_file_location("rig_for_roaming", REPO / "scripts" / "rig.py")
rig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rig)

A, B, BULBS, lab_profile = fakes.LAB_A, fakes.LAB_B, fakes.LAB_BULBS, fakes.lab_profile
ENV = {"HA_URL": "http://ha", "HA_TOKEN": "t", "HA_ADMIN_TOKEN": "a", "HUE_BRIDGE_HOST": "h", "HUE_APP_KEY": "k"}


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(roam, "POLL_S", 0)


class LabHA(fakes.FakeHA):
    async def close(self):
        pass


@pytest.fixture
def lab(monkeypatch) -> fakes.Lab:
    ha = LabHA({"automation.lab": {"state": "on"}})
    lab = fakes.Lab(ha, fakes.FakeBridge(), {A: "light.lab_a", B: "light.lab_b"})

    async def connect(env):
        return ha, ha

    monkeypatch.setattr(rig, "connect", connect)
    monkeypatch.setattr(rig, "HueBridge", lambda host, key: lab.bridge)
    return lab


def lab_with_pause(tmp_path: Path, networks: str = "hue, zha, zigbee2mqtt") -> Profile:
    path = lab_profile(tmp_path, networks=networks)
    path.write_text("pause: [automation.lab]\n" + path.read_text())
    return Profile.load(path)


def suites(tmp_path: Path, *integrations: str) -> list[rig.Suite]:
    path = tmp_path / "steps.yaml"
    path.write_text(fakes.RESTORED_MIDWAY)
    return [rig.Suite(load_step_file(path), integration) for integration in integrations]


async def where(lab: fakes.Lab) -> list[str | None]:
    found = Roamer(lab.ha, lab.bridge, BULBS, out=lambda _: None)
    return [await found.locate(bulb) for bulb in BULBS]


def fake_phases(monkeypatch, lab: fakes.Lab, fail_on: str | None = None) -> list[tuple[list[str], list]]:
    """engine.run and wait_for_targets as recorders: each phase's integrations and where the bulbs were."""
    ran: list[tuple[list[str], list]] = []

    async def run(phase_suites, *args, **kwargs):
        ran.append(([suite.integration for suite in phase_suites], await where(lab)))
        if fail_on in [suite.integration for suite in phase_suites]:
            raise RuntimeError(f"crash on {fail_on}")
        return engine.RunResult([])

    async def wait_for_targets(*args, **kwargs):
        pass

    monkeypatch.setattr(rig, "run", run)
    monkeypatch.setattr(rig, "wait_for_targets", wait_for_targets)
    monkeypatch.setattr(rig, "write_report", lambda result, directory, title: directory / "report.md")
    return ran


def test_a_profile_roams_only_for_a_zha_or_z2m_suite_or_the_check(tmp_path):
    profile = lab_with_pause(tmp_path)
    assert not rig.roams(profile, suites(tmp_path, "shelly", "hue"))
    assert rig.roams(profile, suites(tmp_path, "zigbee2mqtt"))
    assert rig.roams(profile, [], roam_check=True)
    assert not rig.roams(fakes.profile("zha"), suites(tmp_path, "zha"))


def test_phases_follow_the_cycle_with_the_fixed_integrations_on_hue(tmp_path):
    profile = lab_with_pause(tmp_path)
    run = suites(tmp_path, "zigbee2mqtt", "shelly", "zha", "hue", "matter")
    assert [(network, [s.integration for s in group]) for network, group in rig.phases(run, profile, True)] == [
        ("hue", ["shelly", "hue", "matter"]),
        ("zha", ["zha"]),
        ("zigbee2mqtt", ["zigbee2mqtt"]),
    ]
    assert rig.phases(run, profile, False) == [(None, run)]


def test_a_suite_on_an_undeclared_network_runs_at_home_and_never_moves_the_bulbs(tmp_path):
    profile = lab_with_pause(tmp_path, networks="hue, zha")
    run = suites(tmp_path, "zigbee2mqtt", "zha")
    assert [(network, [s.integration for s in group]) for network, group in rig.phases(run, profile, True)] == [
        ("hue", ["zigbee2mqtt"]),
        ("zha", ["zha"]),
    ]
    assert not rig.roams(profile, suites(tmp_path, "zigbee2mqtt"))
    assert [network for network, _ in rig.phases([], profile, True)] == ["hue", "zha"]  # the check: declared only


def test_phases_skip_a_network_with_no_suites_and_the_check_visits_every_one(tmp_path):
    profile = lab_with_pause(tmp_path)
    run = suites(tmp_path, "zigbee2mqtt", "shelly")
    assert [network for network, _ in rig.phases(run, profile, True)] == ["hue", "zigbee2mqtt"]  # straight past ZHA
    assert [network for network, _ in rig.phases([], profile, True)] == ["hue", "zha", "zigbee2mqtt"]
    lines = roam.plan_lines(profile.roam, route=["hue", "zigbee2mqtt"])
    assert lines[0] == "Roams light.lab_a, light.lab_b together: Hue -> Z2M -> Hue."


async def test_a_roaming_run_moves_before_each_phase_and_ends_home(tmp_path, monkeypatch, lab):
    ran = fake_phases(monkeypatch, lab)
    journal = Journal(tmp_path / "journal.json")
    run = suites(tmp_path, "zigbee2mqtt", "shelly", "zha")

    assert await rig.run_rig(ENV, run, lab_with_pause(tmp_path), None, None, True, None, journal, roaming=True) == 0

    assert ran == [(["shelly"], ["hue", "hue"]), (["zha"], ["zha", "zha"]), (["zigbee2mqtt"], ["zigbee2mqtt"] * 2)]
    assert await where(lab) == ["hue", "hue"]
    assert lab.ha.states["automation.lab"]["state"] == "on"
    assert not journal.path.exists()


@pytest.mark.parametrize("phase", ["shelly", "zha", "zigbee2mqtt"])
async def test_a_crash_in_any_phase_still_moves_the_bulbs_home(tmp_path, monkeypatch, lab, phase):
    fake_phases(monkeypatch, lab, fail_on=phase)
    journal = Journal(tmp_path / "journal.json")
    run = suites(tmp_path, "shelly", "zha", "zigbee2mqtt")

    with pytest.raises(RuntimeError, match=f"crash on {phase}"):
        await rig.run_rig(ENV, run, lab_with_pause(tmp_path), None, None, True, None, journal, roaming=True)

    assert await where(lab) == ["hue", "hue"]
    assert len(lab.bridge.resources["room"]["r1"]["children"]) == 3
    assert not journal.path.exists()


async def test_a_failed_move_stops_the_run_and_leaves_the_bulbs_for_recover(tmp_path, monkeypatch, lab):
    fake_phases(monkeypatch, lab)
    monkeypatch.setattr(roam, "JOIN_S", 0.02)
    lab.stuck.add(B[2:])
    journal = Journal(tmp_path / "journal.json")

    with pytest.raises(SystemExit, match="Roaming stopped: light.lab_b did not join ZHA"):
        await rig.run_rig(
            ENV, suites(tmp_path, "zha"), lab_with_pause(tmp_path), None, None, True, None, journal, roaming=True
        )

    assert await where(lab) == ["zha", None]
    assert lab.ha.states["automation.lab"]["state"] == "on"
    assert set(Journal(journal.path).sections) == {"profile", "roam"}


async def test_a_failed_move_still_reports_the_phases_before_it(tmp_path, monkeypatch, lab):
    fake_phases(monkeypatch, lab)
    passed = object()  # the Hue phase's suite result, as the 3 Nov run's Hue suites passed before the move to Z2M

    async def run(phase_suites, *args, **kwargs):
        return engine.RunResult([passed] if phase_suites[0].integration == "shelly" else [])

    reported = []

    async def report(result, *args):
        reported.append(result.suites)

    monkeypatch.setattr(rig, "run", run)
    monkeypatch.setattr(rig, "report", report)
    monkeypatch.setattr(roam, "JOIN_S", 0.02)
    lab.stuck.add(B[2:])
    journal = Journal(tmp_path / "journal.json")

    with pytest.raises(SystemExit, match="Roaming stopped: light.lab_b did not join ZHA"):
        await rig.run_rig(
            ENV,
            suites(tmp_path, "shelly", "zha"),
            lab_with_pause(tmp_path),
            None,
            None,
            True,
            None,
            journal,
            roaming=True,
        )

    assert reported == [[passed]]


async def test_a_move_home_that_fails_after_the_last_phase_stops_the_run(tmp_path, monkeypatch, lab):
    fake_phases(monkeypatch, lab)
    joins = lab.opened

    def opened(network):
        if network == "hue":
            lab.stuck.add(A[2:])
        joins(network)

    lab.opened = opened
    lab.ha.on_open = opened
    monkeypatch.setattr(roam, "JOIN_S", 0.02)

    journal = Journal(tmp_path / "journal.json")
    with pytest.raises(SystemExit, match="did not join Hue"):
        await rig.run_rig(
            ENV, suites(tmp_path, "zha"), lab_with_pause(tmp_path), None, None, True, None, journal, roaming=True
        )
    assert "light.lab_a" in Journal(journal.path).get("roam")["home"]


async def test_roam_check_runs_the_cycle_with_no_suites(monkeypatch, lab, tmp_path):
    ran = fake_phases(monkeypatch, lab)
    assert await rig.run_rig(ENV, [], lab_with_pause(tmp_path), None, None, True, None, None, roaming=True) == 0
    assert ran == []
    assert lab.searches == 1
    assert await where(lab) == ["hue", "hue"]


def test_main_refuses_roam_check_on_a_profile_with_no_roam(tmp_path, monkeypatch):
    path = tmp_path / "house.yaml"
    path.write_text("shelly:\n  - entity_id: switch.plug\n    roles: [switch_plug]\n")
    monkeypatch.setattr(rig, "choose_profile", lambda name, env: path)
    monkeypatch.setattr(rig, "load_env", lambda: {})
    monkeypatch.setattr(rig, "git", lambda *args, check=True: str(tmp_path) if "--git-common-dir" in args else "wt")
    with pytest.raises(SystemExit, match="--roam-check needs a profile with roam:, and house has none"):
        rig.main(["--roam-check", "--dry-run"])


def test_main_dry_runs_roam_check_with_the_moves_and_no_deploy(tmp_path, monkeypatch, capsys):
    path = lab_profile(tmp_path)
    monkeypatch.setattr(rig, "choose_profile", lambda name, env: path)
    monkeypatch.setattr(rig, "load_env", lambda: {})
    monkeypatch.setattr(rig, "git", lambda *args, check=True: str(tmp_path) if "--git-common-dir" in args else "wt")
    deploy = rig.Deploy("c1", "tree", "old", "old", "wt")
    monkeypatch.setattr(rig, "deploy_state", lambda status_cmd: deploy)

    assert rig.main(["--roam-check", "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert "  roams    light.lab_a" in out
    assert "Roams light.lab_a, light.lab_b together: Hue -> ZHA -> Z2M -> Hue." in out
    assert "Adapters on ZHA:\n  none\n" in out
    assert "Deploy: not needed, no restart" in out
    assert f"Estimated duration: {rig.ROAM_ESTIMATE_S} s." in out


def test_the_plan_lists_each_phase_and_the_moves(tmp_path, capsys):
    profile = lab_with_pause(tmp_path)
    registry = AdapterRegistry.discover()
    run = rig.select(rig.load_step_files(), profile, None, ["turn_on_for"])
    rig.print_phases(profile, run, registry, None, rig.roams(profile, run))
    out = capsys.readouterr().out
    assert out.index("Adapters on Hue:") < out.index("Adapters on ZHA:") < out.index("Adapters on Z2M:")
    assert "zha / turn_on_for -> light.lab_b, light.lab_a" in out
    assert rig.estimate(run, registry, False, True) == rig.estimate(run, registry, False) + rig.ROAM_ESTIMATE_S


def test_roaming_needs_the_admin_token_and_the_bridge():
    for missing in ("HA_ADMIN_TOKEN", "HUE_APP_KEY"):
        env = {key: value for key, value in ENV.items() if key != missing}
        with pytest.raises(SystemExit, match="Roaming needs HA_ADMIN_TOKEN, HUE_BRIDGE_HOST and HUE_APP_KEY"):
            rig.check_tokens(env, [], AdapterRegistry.discover(), roaming=True)
    rig.check_tokens(ENV, [], AdapterRegistry.discover(), roaming=True)


async def aborted_on_zha(lab: fakes.Lab, path: Path) -> Journal:
    """What a run killed on ZHA leaves: the bulbs there, their home saved, the automation paused."""
    journal = Journal(path)
    journal.update(profile="lab", paused=["automation.lab"])
    lab.ha.states["automation.lab"]["state"] = "off"
    await Roamer(lab.ha, lab.bridge, BULBS, journal, out=lambda _: None).go("zha")
    return journal


async def test_recover_moves_the_bulbs_home_then_resumes_the_automations(tmp_path, lab):
    journal = await aborted_on_zha(lab, tmp_path / "journal.json")
    printed = []

    await rig.recover(lab.ha, lab.ha, Journal(journal.path), printed.append, bridge=lab.bridge)

    assert await where(lab) == ["hue", "hue"]
    assert "Moving the roaming bulbs home to Hue." in printed
    assert lab.ha.states["automation.lab"]["state"] == "on"
    assert lab.ha.calls[-1][:2] == ("automation", "turn_on")
    assert not journal.path.exists()


def test_main_recover_builds_the_bridge_and_brings_the_bulbs_home(tmp_path, monkeypatch, lab):
    asyncio.run(aborted_on_zha(lab, tmp_path / LEGACY_NAME))
    monkeypatch.setattr(rig, "git", lambda *args, check=True: str(tmp_path) if "--git-common-dir" in args else "wt")
    monkeypatch.setattr(rig, "load_env", lambda: ENV)

    assert rig.main(["--recover"]) == 0
    assert asyncio.run(where(lab)) == ["hue", "hue"]


async def test_recover_stops_on_a_bulb_on_no_network_keeping_the_journal(tmp_path, lab):
    journal = await aborted_on_zha(lab, tmp_path / "journal.json")
    await lab.ha.zha_remove("00:17:88:01:0a:bc:de:f1")

    with pytest.raises(SystemExit, match=r"Recovery stopped: Not on any Zigbee network: light.lab_b\. Reset it"):
        await rig.recover(lab.ha, lab.ha, Journal(journal.path), lambda _: None, bridge=lab.bridge)

    assert set(Journal(journal.path).sections) == {"profile", "paused", "roam"}
    assert lab.ha.states["automation.lab"]["state"] == "off"


async def test_recover_without_the_bridge_keeps_the_bulbs_in_the_journal(tmp_path, lab):
    journal = await aborted_on_zha(lab, tmp_path / "journal.json")
    with pytest.raises(SystemExit, match="needs HA_ADMIN_TOKEN, HUE_BRIDGE_HOST and HUE_APP_KEY"):
        await rig.recover(lab.ha, lab.ha, Journal(journal.path), lambda _: None)
    assert await where(lab) == ["zha", "zha"]
    assert "roam" in Journal(journal.path).sections


GROUPS_YAML = (
    "  groups:\n"
    "    - entity_id: light.test_group\n      roles: [group]\n      members: all\n      scene: scene.test_relax\n"
)


def lab_with_groups(tmp_path: Path) -> Profile:
    path = lab_profile(tmp_path, GROUPS_YAML)
    path.write_text("pause: [automation.lab]\n" + path.read_text())
    return Profile.load(path)


def record_groups(monkeypatch, lab: fakes.Lab, fail_on: str | None = None) -> list[tuple[list[str], list, list]]:
    """fake_phases, also noting which rig-made entities HA had during each phase."""
    ran = fake_phases(monkeypatch, lab, fail_on)
    recorded: list[tuple[list[str], list, list]] = []
    run = rig.run

    async def run_noting(phase_suites, *args, **kwargs):
        made = sorted(e for e in lab.ha.entity_meta if e in ("light.test_group", "scene.test_relax"))
        try:
            return await run(phase_suites, *args, **kwargs)
        finally:
            recorded.append((*ran[-1], made))

    monkeypatch.setattr(rig, "run", run_noting)
    return recorded


def test_groups_are_made_when_the_run_roams_or_runs_a_hue_suite(tmp_path):
    profile = lab_with_groups(tmp_path)
    assert rig.makes_groups(profile, suites(tmp_path, "hue"))
    assert rig.makes_groups(profile, suites(tmp_path, "zha"))
    assert rig.makes_groups(profile, [], roam_check=True)
    assert not rig.makes_groups(profile, suites(tmp_path, "shelly"))
    assert not rig.makes_groups(lab_with_pause(tmp_path), suites(tmp_path, "hue"))


async def test_a_roaming_run_makes_the_groups_in_each_phase_and_removes_them(tmp_path, monkeypatch, lab):
    monkeypatch.setattr(roam, "GONE_S", 0)
    recorded = record_groups(monkeypatch, lab)
    journal = Journal(tmp_path / "journal.json")
    run = suites(tmp_path, "hue", "zha", "zigbee2mqtt")

    code = await rig.run_rig(
        ENV, run, lab_with_groups(tmp_path), None, None, True, None, journal, roaming=True, grouping=True
    )

    assert code == 0
    assert [(phase[0], phase[2]) for phase in recorded] == [
        (["hue"], ["light.test_group", "scene.test_relax"]),
        (["zha"], ["light.test_group"]),
        (["zigbee2mqtt"], ["light.test_group"]),
    ]
    assert "light.test_group" not in lab.ha.entity_meta
    assert lab.ha.zha_group_names == {} and lab.ha.z2m_groups == {}
    assert not journal.path.exists()


async def test_a_hue_run_makes_the_groups_on_hue_without_moving_the_bulbs(tmp_path, monkeypatch, lab):
    monkeypatch.setattr(roam, "GONE_S", 0)
    recorded = record_groups(monkeypatch, lab)
    joins = lab.joins

    code = await rig.run_rig(
        ENV, suites(tmp_path, "hue"), lab_with_groups(tmp_path), None, None, True, None, None, grouping=True
    )

    assert code == 0
    assert recorded == [(["hue"], ["hue", "hue"], ["light.test_group", "scene.test_relax"])]
    assert lab.joins == joins
    assert "light.test_group" not in lab.ha.entity_meta


async def test_roam_check_makes_and_removes_the_groups_on_every_visit(tmp_path, monkeypatch, lab):
    monkeypatch.setattr(roam, "GONE_S", 0)
    made = []
    make = Roamer.make_groups

    async def noting(self, network):
        await make(self, network)
        made.append((network, sorted(e for e in lab.ha.entity_meta if e.startswith(("light.test_group", "scene.")))))

    monkeypatch.setattr(Roamer, "make_groups", noting)
    code = await rig.run_rig(ENV, [], lab_with_groups(tmp_path), None, None, True, None, None, True, True)
    assert code == 0
    assert made == [
        ("hue", ["light.test_group", "scene.test_relax"]),
        ("zha", ["light.test_group"]),
        ("zigbee2mqtt", ["light.test_group"]),
    ]
    assert "light.test_group" not in lab.ha.entity_meta


async def test_a_group_that_cant_be_made_stops_the_run_and_removes_the_ones_made(tmp_path, monkeypatch, lab):
    monkeypatch.setattr(roam, "GONE_S", 0)
    fake_phases(monkeypatch, lab)
    lab.ha.register("scene.test_relax", None, "template", "someone-elses")
    journal = Journal(tmp_path / "journal.json")

    with pytest.raises(SystemExit, match="Roaming stopped: scene.test_relax is already in HA's entity registry"):
        await rig.run_rig(
            ENV, suites(tmp_path, "hue"), lab_with_groups(tmp_path), None, None, True, None, journal, grouping=True
        )

    assert "light.test_group" not in lab.ha.entity_meta
    assert {item["metadata"]["name"] for item in lab.bridge.resources["zone"].values() if "metadata" in item} == set()
    assert lab.ha.states["automation.lab"]["state"] == "on"


async def test_recover_removes_the_groups_a_crash_left_on_z2m_and_brings_the_bulbs_home(tmp_path, monkeypatch, lab):
    monkeypatch.setattr(roam, "GONE_S", 0)
    journal = Journal(tmp_path / "journal.json")
    groups = lab_with_groups(tmp_path).roam_groups
    moving = Roamer(lab.ha, lab.bridge, BULBS, journal, out=lambda _: None, groups=groups)
    await moving.go("zigbee2mqtt")
    await moving.make_groups("zigbee2mqtt")

    await rig.recover(lab.ha, lab.ha, Journal(journal.path), lambda _: None, bridge=lab.bridge)

    assert lab.ha.z2m_groups == {} and "light.test_group" not in lab.ha.entity_meta
    assert await where(lab) == ["hue", "hue"]
    assert not journal.path.exists()


def test_the_plan_lists_the_groups_and_whether_the_bulbs_move(tmp_path, capsys):
    profile = lab_with_groups(tmp_path)
    run = rig.select(rig.load_step_files(), profile, ["hue"], ["set_scene"])
    rig.print_phases(profile, run, AdapterRegistry.discover(), None, False, True)
    out = capsys.readouterr().out
    assert "Roaming: none, as no ZHA or Z2M suite runs; the bulbs stay on Hue." in out
    assert "Makes ds-rig-test-group on Hue as light.test_group (light.lab_a, light.lab_b), with scene" in out
    assert "hue / set_scene -> scene.test_relax" in out
    rig.print_profile(profile)
    assert "  ds-rig   scene.test_relax" in capsys.readouterr().out


async def test_a_group_that_cant_be_made_away_from_home_still_brings_the_bulbs_home(tmp_path, monkeypatch, lab):
    monkeypatch.setattr(roam, "GONE_S", 0)
    fake_phases(monkeypatch, lab)
    journal = Journal(tmp_path / "journal.json")
    await lab.ha.zha_group_add("ds-rig-test-group")  # a leftover no run journaled

    with pytest.raises(SystemExit, match="Roaming stopped: ZHA already has a group named ds-rig-test-group"):
        await rig.run_rig(
            ENV, suites(tmp_path, "zha"), lab_with_groups(tmp_path), None, None, True, None, journal, True, True
        )

    assert await where(lab) == ["hue", "hue"]
    assert not journal.path.exists()


async def test_a_leftover_rig_zone_isnt_saved_as_a_bulbs_home(lab):
    lab.bridge.resources["zone"]["z9"] = {
        "id": "z9",
        "metadata": {"name": "ds-rig-test-group"},
        "children": [{"rid": lab.ha.entity_meta["light.lab_a"]["unique_id"], "rtype": "light"}],
    }
    moving = Roamer(lab.ha, lab.bridge, BULBS, out=lambda _: None)
    await moving.go("zha")
    assert moving.home["light.lab_a"]["zones"] == ["z1"]


# --- the device check: every phase's devices before the gate, and --check -------------------------------------------

PLUG_AND_BULB = """
action: turn_on_for
rig_seconds: 5
tests:
  - name: t
    roles: [switch_plug, light_ct]
    steps:
      - set: {state: off}
"""


def leave_hue(lab: fakes.Lab, device_id: str) -> None:
    """The bridge deletes the bulb, which then searches for a network."""
    lab.bridge._delete("device", lab.bridge.resources["device"], device_id)


def check_suites(tmp_path: Path) -> list[rig.Suite]:
    path = tmp_path / "check.yaml"
    path.write_text(PLUG_AND_BULB)
    return [rig.Suite(load_step_file(path), integration) for integration in ("shelly", "zigbee2mqtt")]


async def check(tmp_path: Path, roaming: bool = True) -> list[str]:
    return await rig.check_devices(
        ENV, check_suites(tmp_path), Profile.load(lab_profile(tmp_path)), AdapterRegistry.discover(), None, roaming
    )


async def test_the_check_passes_with_every_fixed_entity_up_and_the_bulbs_home(tmp_path, lab, capsys):
    lab.ha.states["switch.plug"] = {"entity_id": "switch.plug", "state": "on", "attributes": {}}

    assert await check(tmp_path) == []

    out = capsys.readouterr().out
    assert "Checking profile lab: 1 entities, 2 roaming." in out  # a roaming bulb is no fixed entity
    assert "  light.lab_a: on Hue\n" in out
    assert "Every device is ready." in out


async def test_the_check_names_an_unavailable_or_missing_entity_and_a_bulb_on_no_network(tmp_path, lab, capsys):
    lab.ha.states["switch.plug"] = {"entity_id": "switch.plug", "state": "unavailable", "attributes": {}}
    leave_hue(lab, "hue-device-2")  # lab_b leaves Hue and joins nothing

    problems = await check(tmp_path)

    assert problems[0] == "switch.plug: unavailable; check it is powered"
    assert problems[1].startswith("light.lab_b: not on any Zigbee network.")
    assert "2 problem(s): nothing was changed." in capsys.readouterr().out
    assert lab.ha.calls == []

    del lab.ha.states["switch.plug"]
    assert (await check(tmp_path))[0] == "switch.plug: not in HA; check profile lab"


async def test_the_check_says_a_bulb_away_from_hue_will_be_moved_and_finds_one_unpowered(tmp_path, lab, capsys):
    lab.ha.states["switch.plug"] = {"entity_id": "switch.plug", "state": "on", "attributes": {}}
    leave_hue(lab, "hue-device-2")
    lab.opened("zha")  # lab_b joins ZHA, under an entity ID of ZHA's own

    assert await check(tmp_path) == []
    assert "light.lab_b: on ZHA. The run moves it from there" in capsys.readouterr().out

    lab.ha.states["light.lab_a"] = {"entity_id": "light.lab_a", "state": "unavailable", "attributes": {}}
    assert await check(tmp_path) == ["light.lab_a: on Hue, unavailable; check it is powered"]


async def test_the_check_says_a_run_puts_back_a_home_the_journal_holds(tmp_path, lab, capsys):
    lab.ha.states["switch.plug"] = {"entity_id": "switch.plug", "state": "on", "attributes": {}}
    leave_hue(lab, "hue-device-2")
    lab.opened("zha")
    profile = Profile.load(lab_profile(tmp_path))

    assert (
        await rig.check_devices(
            ENV, check_suites(tmp_path), profile, AdapterRegistry.discover(), None, True, {"light.lab_b"}
        )
        == []
    )
    assert "light.lab_b: on ZHA; the journal holds its Hue home, which a run puts back" in capsys.readouterr().out


async def test_the_check_reports_a_network_it_cannot_ask(tmp_path, lab):
    lab.ha.states["switch.plug"] = {"entity_id": "switch.plug", "state": "on", "attributes": {}}

    async def unreachable(ieee):
        raise fakes.BridgeError("bridge unreachable")

    lab.bridge.device_id_by_ieee = unreachable
    problems = await check(tmp_path)
    assert problems == [
        "light.lab_a: can't tell which network it is on: bridge unreachable",
        "light.lab_b: can't tell which network it is on: bridge unreachable",
    ]


async def test_the_check_looks_for_no_bulb_when_the_run_does_not_roam(tmp_path, lab, capsys):
    lab.ha.states["switch.plug"] = {"entity_id": "switch.plug", "state": "on", "attributes": {}}
    leave_hue(lab, "hue-device-2")
    assert await check(tmp_path, roaming=False) == []
    assert "Checking profile lab: 1 entities." in capsys.readouterr().out


async def test_the_check_needs_the_admin_token_and_bridge_to_find_the_bulbs():
    problems = await rig.check_roaming({}, None, [], fakes.FakeHA({}))
    assert problems == [
        "Can't find the roaming bulbs: that needs HA_ADMIN_TOKEN, HUE_BRIDGE_HOST and HUE_APP_KEY in .env.rig"
    ]


async def test_the_check_needs_ha_in_the_env(tmp_path):
    problems = await rig.check_devices({}, [], Profile(name="house"), AdapterRegistry.discover(), None, False)
    assert problems == ["Can't check the devices: HA_URL and HA_TOKEN must be set in .env.rig"]


async def test_the_check_reports_an_unreachable_ha(tmp_path, monkeypatch):
    async def refused(env):
        raise OSError("connection refused")

    monkeypatch.setattr(rig, "connect", refused)
    assert await check(tmp_path) == ["Can't reach HA at http://ha: connection refused"]


def main_with(tmp_path: Path, monkeypatch, problems: list[str]) -> list:
    """main's preflight against lab_profile, with check_devices answering `problems`; returns what it was asked."""
    path = lab_profile(tmp_path)
    asked = []

    async def check_devices(env, suites, profile, registry, keyword, roaming, homes=frozenset()):
        asked.append(([suite.integration for suite in suites], roaming))
        return problems

    monkeypatch.setattr(rig, "choose_profile", lambda name, env: path)
    monkeypatch.setattr(rig, "load_env", lambda: dict(ENV))
    monkeypatch.setattr(rig, "git", lambda *args, check=True: str(tmp_path) if "--git-common-dir" in args else "wt")
    monkeypatch.setattr(rig, "check_devices", check_devices)
    monkeypatch.setattr(rig, "deploy_state", lambda status_cmd: rig.Deploy("c1", "tree", "tree", "tree", "wt"))
    return asked


def test_check_alone_takes_no_lock_and_deploys_nothing(tmp_path, monkeypatch, capsys):
    asked = main_with(tmp_path, monkeypatch, ["switch.plug: unavailable; check it is powered"])
    monkeypatch.setattr(rig, "deploy_state", lambda status_cmd: pytest.fail("--check read the deploy"))
    monkeypatch.setattr(rig.locks, "hold", lambda *args, **kwargs: pytest.fail("--check took a lock"))

    assert rig.main(["--check", "--integration", "zigbee2mqtt"]) == 1
    assert [(set(integrations), roaming) for integrations, roaming in asked] == [({"zigbee2mqtt"}, True)]
    assert "Proceed?" not in capsys.readouterr().out


def test_check_names_a_run_holding_a_lock_it_would_claim(tmp_path, monkeypatch, capsys):
    main_with(tmp_path, monkeypatch, [])
    with rig.locks.hold(rig.Claim(integrations=frozenset({"zha"})), "wt/other", tmp_path, out=lambda _: None):
        assert rig.main(["--check"]) == 0
    assert "  zha: wt/other (pid" in capsys.readouterr().out
    assert rig.locks.held_by(tmp_path / rig.locks.integration_lock("zha")) is None


def test_check_refuses_another_mode(capsys):
    with pytest.raises(SystemExit):
        rig.main(["--check", "--recover"])
    assert "--check can't be combined with --recover" in capsys.readouterr().err


def test_a_run_stops_before_the_gate_on_a_device_problem(tmp_path, monkeypatch):
    main_with(tmp_path, monkeypatch, ["switch.plug: unavailable; check it is powered"])
    monkeypatch.setattr(rig, "gate", lambda: pytest.fail("asked to proceed"))

    with pytest.raises(SystemExit, match="Power or fix the devices above, then run again."):
        rig.main([])


def test_a_dry_run_shows_the_check_and_still_passes(tmp_path, monkeypatch, capsys):
    asked = main_with(tmp_path, monkeypatch, ["switch.plug: unavailable; check it is powered"])
    assert rig.main(["--dry-run"]) == 0
    assert asked and asked[0][1] is True  # the lab's bulbs roam for its ZHA and Z2M suites


def clear_run(tmp_path, monkeypatch, state: str) -> list:
    """main_with, with RIG_BLOCKER_ENTITY reading `state` and the approved run stubbed; returns the watcher's arming."""
    main_with(tmp_path, monkeypatch, [])
    monkeypatch.setattr(rig, "load_env", lambda: {**ENV, "RIG_BLOCKER_ENTITY": "binary_sensor.rig_blocker"})
    monkeypatch.setattr(rig, "_get", lambda url, token: {"state": state})
    seen = []
    monkeypatch.setattr(rig, "watching", lambda env, armed: seen.append(armed) or contextlib.nullcontext())
    monkeypatch.setattr(rig, "run_approved", lambda *args: 0)
    return seen


def test_a_dry_run_says_whether_the_rig_is_clear(tmp_path, monkeypatch, capsys):
    clear_run(tmp_path, monkeypatch, "on")
    assert rig.main(["--dry-run"]) == 0
    assert "Rig not clear: binary_sensor.rig_blocker is on." in capsys.readouterr().out


def test_an_env_approved_run_is_refused_while_the_rig_is_not_clear(tmp_path, monkeypatch, capsys):
    armed = clear_run(tmp_path, monkeypatch, "unavailable")
    monkeypatch.setenv("DEVICE_SIDE_RIG_APPROVED", "1")
    assert rig.main([]) == 1
    assert "Not approved; nothing changed." in capsys.readouterr().out
    assert armed == []


def test_an_env_approved_run_while_clear_is_watched(tmp_path, monkeypatch):
    armed = clear_run(tmp_path, monkeypatch, "off")
    monkeypatch.setenv("DEVICE_SIDE_RIG_APPROVED", "1")
    assert rig.main([]) == 0
    assert armed == [True]


def test_a_run_a_human_let_past_a_rig_not_clear_is_not_watched(tmp_path, monkeypatch):
    armed = clear_run(tmp_path, monkeypatch, "on")
    monkeypatch.delenv("DEVICE_SIDE_RIG_APPROVED", raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO("y\n"))
    assert rig.main([]) == 0
    assert armed == [False]


def test_a_run_plans_lanes_unless_serial(tmp_path, monkeypatch, capsys):
    main_with(tmp_path, monkeypatch, [])
    assert rig.main(["--dry-run"]) == 0
    assert "In parallel, one lane per integration:" in capsys.readouterr().out
    assert rig.main(["--dry-run", "--serial"]) == 0
    assert "In parallel" not in capsys.readouterr().out


def test_roam_check_skips_the_device_check(tmp_path, monkeypatch):
    asked = main_with(tmp_path, monkeypatch, [])
    assert rig.main(["--roam-check", "--dry-run"]) == 0
    assert asked == []


async def test_connect_closes_the_first_session_when_the_admin_one_fails(monkeypatch):
    closed = []

    class Client:
        def __init__(self, url, token):
            self.token = token

        async def connect(self):
            if self.token == "a":
                raise RuntimeError("WebSocket auth failed")

        async def close(self):
            closed.append(self.token)

    monkeypatch.setattr(rig, "HAClient", Client)
    with pytest.raises(RuntimeError, match="auth failed"):
        await rig.connect(ENV)
    assert closed == ["t"]
