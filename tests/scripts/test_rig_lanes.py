"""Lanes: every integration's fixed-bulb cases side by side, then the rest one at a time. Against the fakes; no rig."""

import asyncio
import importlib.util
from pathlib import Path

import pytest

from tests.rig import engine, roam
from tests.rig.engine import CaseResult, Device, Outcome, Suite, SuiteResult, cases, in_head, load_step_file, merge, run
from tests.rig.journal import Journal
from tests.rig.profile import Profile, RigEntity, RoamBulb, RoamGroup
from tests.scripts import rig_fakes as fakes

REPO = Path(__file__).parents[2]
_spec = importlib.util.spec_from_file_location("rig_for_lanes", REPO / "scripts" / "rig.py")
rig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rig)

TOLERANCE = dict.fromkeys(("shelly", "zha", "hue", "zigbee2mqtt"), 0.2)
STEPS = """
action: raise_brightness
rig_seconds: 60
tests:
  - name: t
    roles: [light_ct]
    steps:
      - set: {state: off}
      - call: {}
"""
ON = {"state": "on", "attributes": {"brightness": 200}}


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(engine, "OPTIONS_RELOAD_S", 0)


class Overlapping(fakes.FakeAdmin):
    """deviceside's calls take a while; it counts how many are in flight at once, and what the journal held then."""

    def __init__(self, states: dict, journal: Journal | None = None, call_s: float = 0.05):
        super().__init__(states, lambda ha, action, data: {data["entity_id"]: {"status": "sent"}})
        self.journal, self.call_s = journal, call_s
        self.active = self.most = 0
        self.lanes_journaled: set[str] = set()
        self.saves_seen: list[int] = []  # how many option saves there had been at each call

    async def call_service(self, domain, service, data=None, return_response=False):
        if domain == "deviceside" and service == "raise_brightness":
            self.saves_seen.append(len(self.saved))
            self.active += 1
            self.most = max(self.most, self.active)
            try:
                await asyncio.sleep(self.call_s)
                if self.journal is not None:
                    self.lanes_journaled |= set(self.journal.get("cases") or {})
            finally:
                self.active -= 1
        return await super().call_service(domain, service, data, return_response)


def two_lanes(tmp_path: Path, text: str = STEPS) -> tuple[list[Suite], Profile]:
    path = tmp_path / "steps.yaml"
    path.write_text(text)
    step_file = load_step_file(path)
    profile = Profile(
        {
            "shelly": [RigEntity("light.a", frozenset({"light_ct"}))],
            "zha": [RigEntity("light.b", frozenset({"light_ct"}))],
        }
    )
    return [Suite(step_file, "shelly"), Suite(step_file, "zha")], profile


async def run_two(ha, suites, profile, lines: list[str] | None = None, **kwargs):
    out = lines.append if lines is not None else lambda _: None
    return await run(
        suites, profile, fakes.OPTION_REGISTRY, ha, admin=ha, tolerance=TOLERANCE, ask=None, out=out, **kwargs
    )


@pytest.mark.parametrize(("lanes", "most"), [(True, 2), (False, 1)])
async def test_lanes_run_side_by_side_and_serial_one_at_a_time(tmp_path, lanes, most):
    journal = Journal(tmp_path / "journal.json")
    ha = Overlapping({"light.a": ON, "light.b": ON}, journal)
    suites, profile = two_lanes(tmp_path)
    lines: list[str] = []

    result = await run_two(ha, suites, profile, lines, journal=journal, lanes=lanes)

    assert not result.failed
    assert ha.most == most
    assert ha.lanes_journaled == ({"shelly", "zha"} if lanes else {"serial"})  # one entry per lane
    assert ha.states["light.a"]["state"] == ha.states["light.b"]["state"] == "on"
    assert not journal.path.exists()
    assert ("shelly / raise_brightness  t[light_ct]: pass" in lines) is lanes
    assert ("  t[light_ct]: pass" in lines) is not lanes


async def test_lanes_save_the_options_once_before_they_start(tmp_path):
    ha = Overlapping({"light.a": ON, "light.b": ON})
    suites, profile = two_lanes(tmp_path)

    await run_two(ha, suites, profile, lanes=True)

    assert ha.saved == [{"opt": False, "other": False}, {"opt": True, "other": False}]  # set, then put back
    assert ha.saves_seen == [1, 1]  # no reload while a lane runs


async def test_lanes_refuse_suites_that_want_different_options(tmp_path):
    ha = Overlapping({"light.a": ON, "light.b": ON})
    suites, profile = two_lanes(tmp_path)
    (tmp_path / "opt").mkdir()
    with_opt = tmp_path / "opt" / "steps.yaml"
    with_opt.write_text(STEPS.replace("tests:", "options: [opt]\ntests:"))
    suites[1] = Suite(load_step_file(with_opt), "zha")

    with pytest.raises(RuntimeError, match="same DeviceSide options"):
        await run_two(ha, suites, profile, lanes=True)


async def test_an_error_in_one_lane_cancels_the_other_and_both_put_back(tmp_path, monkeypatch):
    journal = Journal(tmp_path / "journal.json")
    ha = Overlapping({"light.a": ON, "light.b": ON}, journal, call_s=5)
    suites, profile = two_lanes(tmp_path)
    steps = engine._CaseRun.steps

    async def crash_on_zha(self, case_steps, relaxed=False):
        if self.integration == "zha":
            await self.touch("light.b")
            await self.ha.call_service("light", "turn_off", {"entity_id": "light.b"})
            await asyncio.sleep(0.05)  # the other lane is mid-call
            raise ConnectionResetError("HA went away")
        await steps(self, case_steps, relaxed)

    monkeypatch.setattr(engine._CaseRun, "steps", crash_on_zha)

    with pytest.raises(ConnectionResetError, match="HA went away"):
        await run_two(ha, suites, profile, journal=journal, lanes=True)

    assert ha.states["light.a"]["state"] == ha.states["light.b"]["state"] == "on"
    assert not journal.path.exists()


def test_the_head_leaves_out_option_files_roaming_and_made_entities_and_power(tmp_path):
    profile = Profile(
        {
            "zha": [
                RigEntity("light.fixed", frozenset({"light_ct"})),
                RigEntity("light.powered", frozenset({"light_dimmable"}), "switch.supply"),
                RigEntity("switch.supply", frozenset({"switch_plug"})),
                RigEntity("light.roam", frozenset({"light_color"})),
                RigEntity("light.rig_group", frozenset({"group"}), members=("light.roam",)),
                RigEntity("light.mixed", frozenset({"group_color"}), members=("light.fixed", "light.roam")),
            ]
        },
        roam=(RoamBulb("abc", "light.roam", frozenset({"light_color"})),),
        roam_groups=(RoamGroup("light.rig_group", frozenset({"group"}), ("light.roam",)),),
    )
    text = STEPS.replace("[light_ct]", "[light_ct, light_dimmable, switch_plug, light_color, group, group_color]")
    path = tmp_path / "steps.yaml"
    path.write_text(text)
    plain = load_step_file(path)
    with_options = engine.StepFile(path, plain.action, plain.rig_seconds, plain.tests, frozenset({"predicted_state"}))

    head = {case.role for case in cases(Suite(plain, "zha"), profile) if in_head(case, profile)}
    assert head == {"light_ct"}
    assert not any(in_head(case, profile) for case in cases(Suite(with_options, "zha"), profile))


def result(suite: Suite, *ids: str, outcome: Outcome = Outcome.PASS) -> SuiteResult:
    return SuiteResult(suite, [CaseResult(case_id, "light_ct", "light", outcome) for case_id in ids], complete=False)


def test_merge_joins_a_suite_split_between_lanes_and_phases_in_file_order(tmp_path):
    path = tmp_path / "steps.yaml"
    path.write_text(STEPS.replace("[light_ct]", "[light_ct, light_color]"))
    suite = Suite(load_step_file(path), "zha")
    profile = Profile(
        {"zha": [RigEntity("light.a", frozenset({"light_ct"})), RigEntity("light.c", frozenset({"light_color"}))]}
    )
    lanes, phases = result(suite, "t[light_color]"), result(suite, "t[light_ct]")

    (joined,) = merge([lanes, phases], profile, fakes.OPTION_REGISTRY).suites
    assert [case.id for case in joined.cases] == ["t[light_ct]", "t[light_color]"]
    assert joined.complete and joined.recordable

    (alone,) = merge([lanes], profile, fakes.OPTION_REGISTRY).suites  # a failed move cut the phases short
    assert not alone.complete and not alone.recordable
    (keyed,) = merge([lanes, phases], profile, fakes.OPTION_REGISTRY, keyword="t").suites
    assert not keyed.complete


def test_merge_unions_the_devices_of_a_suites_parts_in_order(tmp_path):
    path = tmp_path / "steps.yaml"
    path.write_text(STEPS)
    suite = Suite(load_step_file(path), "zha")
    profile = Profile({"zha": [RigEntity("light.a", frozenset({"light_ct"}))]})
    one, two, three = Device("A", None, "1"), Device("B", None, "1"), Device("C", None, "1")
    lanes, phases = result(suite, "t[light_ct]"), result(suite, "t[light_ct]")
    lanes.ha_version, lanes.devices = "2026.10.1", [one, two]
    phases.ha_version, phases.devices = "2026.10.2", [two, three]

    (joined,) = merge([lanes, phases], profile, fakes.OPTION_REGISTRY).suites
    assert joined.devices == [one, two, three]
    assert joined.ha_version == "2026.10.1"
    assert lanes.devices == [one, two]  # the part itself is left alone


LAB_STEPS = STEPS.replace("[light_ct]", "[switch_plug, light_ct]")


async def test_a_roaming_run_starts_with_the_lanes_at_home_then_runs_the_rest_by_phase(tmp_path, monkeypatch):
    ha = fakes.FakeHA({})
    lab = fakes.Lab(ha, fakes.FakeBridge(), {fakes.LAB_A: "light.lab_a", fakes.LAB_B: "light.lab_b"})
    monkeypatch.setattr(roam, "POLL_S", 0)
    profile = Profile.load(fakes.lab_profile(tmp_path))
    path = tmp_path / "steps.yaml"
    path.write_text(LAB_STEPS)
    suites = [Suite(load_step_file(path), integration) for integration in ("shelly", "zha", "zigbee2mqtt")]
    finder = roam.Roamer(ha, lab.bridge, fakes.LAB_BULBS, out=lambda _: None)
    ran = []

    busy_maps = set()

    async def recorded(run_suites, run_profile, *args, only=None, lanes=False, busy=None, **kwargs):
        busy_maps.add(id(busy))
        where = [await finder.locate(bulb) for bulb in fakes.LAB_BULBS]
        accepted = [
            f"{suite.integration} {case.id}"
            for suite in run_suites
            for case in cases(suite, run_profile)
            if only is None or only(case)
        ]
        ran.append((lanes, where, accepted))
        return engine.RunResult([])

    async def no_wait(*args, **kwargs):
        pass

    monkeypatch.setattr(rig, "run", recorded)
    monkeypatch.setattr(rig, "wait_for_targets", no_wait)
    roamer = roam.Roamer(ha, lab.bridge, fakes.LAB_BULBS)

    await rig.run_phases(ha, ha, lab.bridge, roamer, True, suites, profile, None, None, True, None, None, lanes=True)

    home = ["hue", "hue"]
    assert ran == [
        (
            True,
            home,
            ["shelly t[switch_plug]", "shelly t[light_ct]", "zha t[switch_plug]", "zigbee2mqtt t[switch_plug]"],
        ),
        (False, home, []),
        (False, ["zha", "zha"], ["zha t[light_ct]"]),
        (False, ["zigbee2mqtt"] * 2, ["zigbee2mqtt t[light_ct]"]),
    ]
    assert len(busy_maps) == 1 and id(None) not in busy_maps  # the phases wait out the lanes' predictions


async def test_a_run_waits_out_the_predictions_an_earlier_run_left(tmp_path):
    ha = Overlapping({"light.a": ON, "light.b": ON}, call_s=0)
    suites, profile = two_lanes(tmp_path)
    loop = asyncio.get_running_loop()
    started = loop.time()

    await run_two(ha, suites[:1], profile, busy={"light.a": started + 0.2})

    assert loop.time() - started >= 0.2


def test_the_plan_shows_the_lanes_then_the_phases_and_estimates_the_longest_lane(tmp_path, capsys):
    path = tmp_path / "steps.yaml"
    path.write_text(STEPS.replace("[light_ct]", "[light_ct, light_color]"))
    step_file = load_step_file(path)
    profile = Profile(
        {
            "hue": [RigEntity("light.a", frozenset({"light_ct"})), RigEntity("light.c", frozenset({"light_color"}))],
            "zha": [RigEntity("light.b", frozenset({"light_ct"})), RigEntity("light.r", frozenset({"light_color"}))],
        },
        roam=(RoamBulb("abc", "light.r", frozenset({"light_color"})),),
    )
    suites = [Suite(step_file, "hue"), Suite(step_file, "zha")]

    rig.print_phases(profile, suites, fakes.OPTION_REGISTRY, None, roaming=False, lanes=True)

    out = capsys.readouterr().out
    assert out.index("In parallel, one lane per integration:") < out.index("Adapters:")
    lanes, phases = out.split("Adapters:")
    assert "    hue / raise_brightness -> light.a, light.c" in lanes
    assert "    zha / raise_brightness -> light.b" in lanes
    assert "  zha / raise_brightness -> light.r" in phases
    assert "light.a" not in phases
    # hue's 60 s run whole in its lane, beside zha's 30; zha's other 30 s come after.
    assert rig.estimate(suites, fakes.OPTION_REGISTRY, False, profile=profile) == 90
    assert rig.estimate(suites, fakes.OPTION_REGISTRY, False) == 120
