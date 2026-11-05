"""The baseline (tests/rig/baseline.py): runs side by side share what they change beyond the devices, and the last one
out puts it back.

A run's liveness is its journal lock; flock tells handles apart within a process, so Journal.start stands in for a live
run, and a holder with no lock file, or an unlocked one, for a dead run."""

import json
import logging

import pytest

from tests.rig import journal
from tests.rig.baseline import LEDGER_NAME, NAME, Baseline
from tests.rig.journal import Journal


@pytest.fixture(autouse=True)
def quick_probes(monkeypatch):
    monkeypatch.setattr(journal, "PROBE_GAP_S", 0)


class BaselineHA:
    """Entity states, HA's log levels, and Z2M's log level and device options; each change is recorded in `calls`."""

    def __init__(self, states: dict[str, str] | None = None, failing: str | None = None):
        self.states, self.failing, self.calls = dict(states or {}), failing, []
        self.ha_levels = {"deviceside": logging.WARNING, "mqtt": logging.WARNING}
        self.z2m_level = "warning"
        self.z2m_options: dict[str, dict] = {"0xa": {"hue_native_control": True}}

    async def get_state(self, entity_id):
        return {"state": self.states[entity_id]} if entity_id in self.states else None

    async def call_service(self, domain, service, data):
        self.calls.append((service, data["entity_id"]))
        if service == "turn_on" and data["entity_id"] == self.failing:
            raise RuntimeError("refused")
        self.states[data["entity_id"]] = "on" if service == "turn_on" else "off"

    async def log_levels(self):
        return dict(self.ha_levels)

    async def set_log_level(self, domain, level):
        self.calls.append(("log_level", domain, level))
        self.ha_levels[domain] = logging.getLevelName(level)

    async def z2m_log_level(self):
        return self.z2m_level

    async def z2m_set_log_level(self, level):
        self.calls.append(("z2m_log_level", level))
        self.z2m_level = level

    async def z2m_device(self, ieee):
        return {"ieee_address": ieee} if ieee in self.z2m_options else None

    async def z2m_device_options(self, ieee):
        return dict(self.z2m_options.get(ieee, {}))

    async def set_z2m_device_options(self, ieee, options):
        self.calls.append(("z2m_option", ieee, options))
        self.z2m_options[ieee].update(options)


def run(tmp_path, ha, role="pause", printed: list | None = None) -> tuple[Journal, Baseline]:
    """A live run: its journal, whose lock is held while the test keeps it, and its baseline as `role`."""
    started = Journal.start(tmp_path)
    return started, Baseline.of(ha, started, role, (printed if printed is not None else []).append)


def baseline(tmp_path) -> dict:
    path = tmp_path / NAME
    return json.loads(path.read_text()) if path.exists() else {}


def debug(ha):
    return ("ha_log_level", "deviceside", lambda _: ha.set_log_level("deviceside", "DEBUG"))


def z2m_level(ha, level):
    return ("z2m_log_level", "", lambda _: ha.z2m_set_log_level(level))


def native(ha, on: bool):
    key = "0xa:hue_native_control"
    return ("z2m_option", key, lambda _: ha.set_z2m_device_options("0xa", {"hue_native_control": on}))


def current(ha) -> tuple:
    return (
        ha.states.get("automation.motion"),
        ha.ha_levels["deviceside"],
        ha.z2m_level,
        ha.z2m_options["0xa"]["hue_native_control"],
    )


BEFORE = ("on", logging.WARNING, "warning", True)
CHANGED = ("off", logging.DEBUG, "debug", False)


async def hold_every_kind(base: Baseline, ha) -> None:
    await base.pause(["automation.motion"])
    await base.hold(debug(ha), z2m_level(ha, "debug"), native(ha, False))


# --- each kind: overlapping runs, a crash, the last one out -----------------------------------------------------------


async def test_two_runs_overlap_then_one_crashes_and_the_other_ending_puts_every_kind_back(tmp_path):
    ha = BaselineHA({"automation.motion": "on"})
    crashed_journal, crashed = run(tmp_path, ha)
    _, live = run(tmp_path, ha)

    await hold_every_kind(crashed, ha)
    await hold_every_kind(live, ha)  # finds each changed, but held: it joins rather than records the change
    assert current(ha) == CHANGED
    held = baseline(tmp_path)
    assert held["ha_log_level:deviceside"] == {"original": "WARNING", "holders": [crashed.holder, live.holder]}
    assert held["z2m_option:0xa:hue_native_control"]["original"] is True

    crashed_journal.lock.close()  # the run dies: its lock file stays, unlocked
    await live.release()

    assert current(ha) == BEFORE
    assert baseline(tmp_path) == {}


async def test_while_another_run_holds_them_a_release_puts_nothing_back(tmp_path):
    ha = BaselineHA({"automation.motion": "on"})
    _, a = run(tmp_path, ha)
    _, b = run(tmp_path, ha)
    await hold_every_kind(a, ha)
    await hold_every_kind(b, ha)

    await a.release()
    assert current(ha) == CHANGED
    await b.release()
    assert current(ha) == BEFORE


async def test_a_run_holding_puts_back_what_a_dead_run_left_and_takes_over_what_it_holds(tmp_path):
    ha = BaselineHA({"automation.motion": "on"})
    dead_journal, dead = run(tmp_path, ha)
    await hold_every_kind(dead, ha)
    dead_journal.release()  # no journal written: the lock file goes too
    _, live = run(tmp_path, ha)

    await live.hold(z2m_level(ha, "debug"))

    # Taken over as it is, the original kept; the dead run's other holds go back.
    assert baseline(tmp_path) == {"z2m_log_level": {"original": "warning", "holders": [live.holder]}}
    assert current(ha) == ("on", logging.WARNING, "debug", True)
    await live.release()
    assert ha.z2m_level == "warning"


async def test_one_runs_roles_let_go_separately(tmp_path):
    ha = BaselineHA()
    started = Journal.start(tmp_path)
    debugging, joining = Baseline.of(ha, started, "debug"), Baseline.of(ha, started, "join")
    await debugging.hold(z2m_level(ha, "debug"))
    await joining.hold(z2m_level(ha, "info"))

    await joining.release()
    assert ha.z2m_level == "info"  # the run's debug hold still has it
    await debugging.release()
    assert ha.z2m_level == "warning"


async def test_a_z2m_option_is_held_again_by_each_step_of_a_case(tmp_path):
    ha = BaselineHA()
    _, case = run(tmp_path, ha, "case:zigbee2mqtt")
    await case.hold(native(ha, False))
    await case.hold(native(ha, True))
    await case.hold(native(ha, False))

    await case.release()

    assert ha.z2m_options["0xa"] == {"hue_native_control": True}
    assert baseline(tmp_path) == {}


async def test_an_option_of_a_device_z2m_no_longer_lists_is_dropped(tmp_path):
    ha = BaselineHA()
    _, case = run(tmp_path, ha, "case:zigbee2mqtt")
    await case.hold(native(ha, False))
    del ha.z2m_options["0xa"]

    await case.release()

    assert baseline(tmp_path) == {}


async def test_a_level_ha_no_longer_reports_is_dropped(tmp_path):
    ha = BaselineHA()
    _, a = run(tmp_path, ha, "debug")
    await a.hold(debug(ha))
    del ha.ha_levels["deviceside"]  # HA restarted: its levels are its own again

    await a.release()

    assert ("log_level", "deviceside", "WARNING") not in ha.calls
    assert baseline(tmp_path) == {}


# --- probes and recovery ----------------------------------------------------------------------------------------------


async def test_a_crashed_probes_pauses_are_put_back_by_the_next_prune(tmp_path):
    ha = BaselineHA({"automation.motion": "on"})
    probe, paused = run(tmp_path, ha)
    await paused.pause(["automation.motion"])
    probe.lock.close()

    await Baseline(ha, tmp_path, "recover").prune()

    assert ha.states["automation.motion"] == "on"
    assert baseline(tmp_path) == {}


async def test_recovery_lets_go_of_every_role_as_the_dead_run(tmp_path):
    # --recover holds the orphan's lock while it puts it back, so the orphan reads as alive; it releases as the orphan.
    ha = BaselineHA({"automation.motion": "on"})
    orphan = Journal.start(tmp_path)
    await Baseline.of(ha, orphan, "pause").pause(["automation.motion"])
    await Baseline.of(ha, orphan, "debug").hold(debug(ha), z2m_level(ha, "debug"))
    await Baseline.of(ha, orphan, "case:zigbee2mqtt").hold(native(ha, False))

    await Baseline(ha, tmp_path, orphan.name).release()

    assert current(ha) == BEFORE
    assert baseline(tmp_path) == {}


async def test_a_put_back_that_fails_stays_for_the_next_try(tmp_path):
    ha = BaselineHA({"automation.motion": "on", "switch.al": "on"}, failing="automation.motion")
    printed: list[str] = []
    _, a = run(tmp_path, ha, printed=printed)
    await a.pause(["automation.motion", "switch.al"])

    await a.release()

    assert ha.states == {"automation.motion": "off", "switch.al": "on"}
    assert any(line.startswith("Could not put automation:automation.motion back to on") for line in printed)
    assert baseline(tmp_path) == {"automation:automation.motion": {"original": "on", "holders": []}}
    ha.failing = None
    await Baseline(ha, tmp_path, "recover").prune()
    assert ha.states["automation.motion"] == "on"
    assert baseline(tmp_path) == {}


# --- pauses -----------------------------------------------------------------------------------------------------------


async def test_pause_turns_off_only_what_is_on_and_resumes_it(tmp_path):
    ha = BaselineHA({"switch.al_office": "on", "automation.motion_hall": "off"})
    _, a = run(tmp_path, ha)

    await a.pause(["switch.al_office", "automation.motion_hall"])
    assert baseline(tmp_path)["automation:automation.motion_hall"] == {"original": "off", "holders": [a.holder]}
    await a.release()

    assert ha.calls == [("turn_off", "switch.al_office"), ("turn_on", "switch.al_office")]
    assert baseline(tmp_path) == {}


async def test_pause_stops_on_an_unknown_entity_keeping_what_it_paused(tmp_path):
    ha = BaselineHA({"switch.al_office": "on"})
    _, a = run(tmp_path, ha)

    with pytest.raises(SystemExit, match="switch.typo in the profile's pause list"):
        await a.pause(["switch.al_office", "switch.typo"])

    assert list(baseline(tmp_path)) == ["switch:switch.al_office"]


async def test_the_original_is_written_before_the_change(tmp_path):
    ha = BaselineHA({"switch.al_office": "on"})
    seen = []
    call_service = ha.call_service

    async def recorded(domain, service, data):
        seen.append((service, baseline(tmp_path)))
        await call_service(domain, service, data)

    ha.call_service = recorded
    _, a = run(tmp_path, ha)
    await a.pause(["switch.al_office"])

    assert seen == [("turn_off", {"switch:switch.al_office": {"original": "on", "holders": [a.holder]}})]


# --- the old ledger; a level left raised ------------------------------------------------------------------------------


async def test_the_pause_ledger_is_read_in_once(tmp_path):
    ha = BaselineHA({"automation.motion": "off"})
    dead = Journal.start(tmp_path)
    (tmp_path / LEDGER_NAME).write_text(json.dumps({"automation.motion": {"was_on": True, "holders": [dead.name]}}))
    _, live = run(tmp_path, ha)
    await live.pause(["automation.motion"])

    assert not (tmp_path / LEDGER_NAME).exists()
    assert baseline(tmp_path) == {
        "automation:automation.motion": {"original": "on", "holders": [dead.name, live.holder]}
    }
    dead.lock.close()
    await live.release()
    assert ha.states["automation.motion"] == "on"


async def test_a_z2m_level_left_at_debug_with_no_holder_goes_back_to_info(tmp_path):
    ha = BaselineHA()
    ha.z2m_level = "debug"
    printed: list[str] = []
    _, a = run(tmp_path, ha, "join", printed)

    await a.hold(z2m_level(ha, "debug"))
    await a.release()

    assert ha.z2m_level == "info"
    assert "Z2M's log level is debug with no run holding it; it goes back to info." in printed


async def test_in_memory_with_no_journal(tmp_path):
    ha = BaselineHA({"automation.motion": "on"})
    base = Baseline.of(ha, None, "pause")
    await hold_every_kind(base, ha)
    await base.release()
    assert current(ha) == BEFORE
    assert not list(tmp_path.iterdir())
