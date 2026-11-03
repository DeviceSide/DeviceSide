"""The pause ledger (tests/rig/ledger.py): runs side by side share what they pause, and the last one out resumes it.

A run's liveness is its journal lock; flock tells handles apart within a process, so Journal.start stands in for a live
run, and a holder with no lock file, or an unlocked one, for a dead run."""

import json

import pytest

from tests.rig import journal
from tests.rig.journal import Journal
from tests.rig.ledger import NAME, Ledger


@pytest.fixture(autouse=True)
def quick_probes(monkeypatch):
    monkeypatch.setattr(journal, "PROBE_GAP_S", 0)


class PauseHA:
    """States and turn_on/turn_off calls; a call changes the state, as HA would."""

    def __init__(self, states: dict[str, str], failing: str | None = None):
        self.states, self.failing, self.calls = states, failing, []

    async def get_state(self, entity_id):
        return {"state": self.states[entity_id]} if entity_id in self.states else None

    async def call_service(self, domain, service, data):
        self.calls.append((service, data["entity_id"]))
        if service == "turn_on" and data["entity_id"] == self.failing:
            raise RuntimeError("refused")
        self.states[data["entity_id"]] = "on" if service == "turn_on" else "off"


def run(tmp_path, printed: list | None = None) -> tuple[Journal, Ledger]:
    """A live run: its journal, whose lock is held while the test keeps it, and its ledger."""
    journal = Journal.start(tmp_path)
    return journal, Ledger(tmp_path, journal.name, (printed if printed is not None else []).append)


def ledger(tmp_path) -> dict:
    path = tmp_path / NAME
    return json.loads(path.read_text()) if path.exists() else {}


async def test_pause_turns_off_only_what_is_on_and_resumes_it(tmp_path):
    states = {"switch.al_office": "on", "automation.motion_hall": "off", "automation.motion_den": "on"}
    ha = PauseHA(states, failing="automation.motion_den")
    printed: list[str] = []
    alive_a, a = run(tmp_path, printed)

    await a.pause(ha, list(states))
    assert ledger(tmp_path)["automation.motion_hall"] == {"was_on": False, "holders": [a.holder]}
    await a.resume(ha)

    assert ha.calls == [
        ("turn_off", "switch.al_office"),
        ("turn_off", "automation.motion_den"),
        ("turn_on", "automation.motion_den"),
        ("turn_on", "switch.al_office"),
    ]
    assert any("Could not turn automation.motion_den back on" in line for line in printed)
    assert ledger(tmp_path) == {}


async def test_pause_stops_on_an_unknown_entity_keeping_what_it_paused(tmp_path):
    ha = PauseHA({"switch.al_office": "on"})
    alive_a, a = run(tmp_path)

    with pytest.raises(SystemExit, match="switch.typo in the profile's pause list"):
        await a.pause(ha, ["switch.al_office", "switch.typo"])

    assert list(ledger(tmp_path)) == ["switch.al_office"]


async def test_pause_writes_the_ledger_before_turning_an_entity_off(tmp_path):
    ha = PauseHA({"switch.al_office": "on"})
    seen = []
    call_service = ha.call_service

    async def recorded(domain, service, data):
        seen.append((service, ledger(tmp_path)))
        await call_service(domain, service, data)

    ha.call_service = recorded
    alive_a, a = run(tmp_path)
    await a.pause(ha, ["switch.al_office"])

    assert seen == [("turn_off", {"switch.al_office": {"was_on": True, "holders": [a.holder]}})]


async def test_with_two_holders_the_last_one_out_resumes(tmp_path):
    ha = PauseHA({"automation.motion": "on"})
    alive_a, a = run(tmp_path)
    alive_b, b = run(tmp_path)

    await a.pause(ha, ["automation.motion"])
    await b.pause(ha, ["automation.motion"])  # finds it off, but paused by a: it joins rather than records it off
    await a.resume(ha)
    assert ha.states["automation.motion"] == "off"
    assert ledger(tmp_path)["automation.motion"] == {"was_on": True, "holders": [b.holder]}
    await b.resume(ha)

    assert ha.states["automation.motion"] == "on"
    assert ha.calls == [("turn_off", "automation.motion"), ("turn_on", "automation.motion")]
    assert ledger(tmp_path) == {}


async def test_a_dead_holder_is_pruned_and_its_pause_resumed_by_the_last_live_one(tmp_path):
    ha = PauseHA({"automation.motion": "on", "switch.al": "on"})
    dead_journal, dead = run(tmp_path)
    await dead.pause(ha, ["automation.motion", "switch.al"])
    alive, live = run(tmp_path)
    await live.pause(ha, ["automation.motion"])
    dead_journal.lock.close()  # the run dies: its lock file stays, unlocked

    await live.resume(ha)

    assert ha.states == {"automation.motion": "on", "switch.al": "on"}
    assert ledger(tmp_path) == {}


async def test_a_pausing_run_takes_over_a_dead_runs_entry_and_resumes_the_rest(tmp_path):
    ha = PauseHA({"automation.motion": "on", "switch.al": "on"})
    dead_journal, dead = run(tmp_path)
    await dead.pause(ha, ["automation.motion", "switch.al"])
    dead_journal.release()  # no journal written: the lock file goes too
    alive, live = run(tmp_path)

    await live.pause(ha, ["automation.motion"])

    # Taken over as it is, still off, was_on kept; the dead run's other pause goes back on.
    assert ledger(tmp_path) == {"automation.motion": {"was_on": True, "holders": [live.holder]}}
    assert ha.states == {"automation.motion": "off", "switch.al": "on"}
    assert ha.calls == [("turn_off", "automation.motion"), ("turn_off", "switch.al"), ("turn_on", "switch.al")]
    await live.resume(ha)
    assert ha.states["automation.motion"] == "on"


async def test_a_live_holders_pause_survives_another_runs_resume(tmp_path):
    ha = PauseHA({"automation.motion": "on", "switch.al": "on"})
    alive_a, a = run(tmp_path)
    alive_b, b = run(tmp_path)
    await a.pause(ha, ["automation.motion"])
    await b.pause(ha, ["switch.al"])

    await b.resume(ha)

    assert ha.states == {"automation.motion": "off", "switch.al": "on"}
    assert list(ledger(tmp_path)) == ["automation.motion"]


async def test_recovery_resumes_an_orphans_pauses_as_its_holder(tmp_path):
    # --recover holds the orphan's lock while it puts it back, so the orphan reads as alive; it resumes as the orphan.
    ha = PauseHA({"automation.motion": "on"})
    orphan, dead = run(tmp_path)
    await dead.pause(ha, ["automation.motion"])

    await Ledger(tmp_path, orphan.name, lambda _: None).resume(ha)

    assert ha.states["automation.motion"] == "on"
    assert ledger(tmp_path) == {}
