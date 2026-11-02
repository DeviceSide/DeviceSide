"""scripts/rig.py with a roaming profile: phases by the cycle, a move before each and home after the last, a crash in
each phase, --roam-check, and --recover bringing the bulbs home. Against the Lab fake; no rig is touched."""

import asyncio
import importlib.util
from pathlib import Path

import pytest

from custom_components.device_side.core.registry import AdapterRegistry
from tests.rig import engine, roam
from tests.rig.engine import load_step_file
from tests.rig.journal import Journal
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
    monkeypatch.setattr(roam, "ZHA_LEAVE_GAP_S", 0)
    monkeypatch.setattr(rig, "workspace_color", lambda color: None)


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


def lab_with_pause(tmp_path: Path) -> Profile:
    path = lab_profile(tmp_path)
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
    run = suites(tmp_path, "zigbee2mqtt", "shelly", "zha", "hue", "matter")
    assert [(network, [s.integration for s in group]) for network, group in rig.phases(run, True)] == [
        ("hue", ["shelly", "hue", "matter"]),
        ("zha", ["zha"]),
        ("zigbee2mqtt", ["zigbee2mqtt"]),
    ]
    assert rig.phases(run, False) == [(None, run)]


def test_phases_skip_a_network_with_no_suites_and_the_check_visits_every_one(tmp_path):
    run = suites(tmp_path, "zigbee2mqtt", "shelly")
    assert [network for network, _ in rig.phases(run, True)] == ["hue", "zigbee2mqtt"]  # straight past ZHA
    assert [network for network, _ in rig.phases([], True)] == ["hue", "zha", "zigbee2mqtt"]
    lines = roam.plan_lines(lab_with_pause(tmp_path).roam, route=["hue", "zigbee2mqtt"])
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
    asyncio.run(aborted_on_zha(lab, tmp_path / rig.JOURNAL_NAME))
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
