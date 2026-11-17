"""The call transcript recorder (tests/transcripts.py), run on an inner pytest session over the fake integration.

Each inner session runs in a subprocess, as the recorder patches the dispatcher and HA's service registry for its
whole session.
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
GOLDEN = "tests/integrations/fake/calls/turn_on_for.json"

CONFTEST = """
from tests.conftest import *  # noqa: F403
"""

# A boundary a test may replace, declared in the fake integration's wire.py.
WIRE_MODULE = """
async def send(hass, payload, *, context=None):
    return {"ok": payload}
"""

WIRE = """
BOUNDARIES = [("inner_wire", "send", 0)]
"""

TEST = """
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import inner_wire
import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later

from tests.conftest import advance, call, wall_clock_now
from tests.fakes.fake_integration import FakeTurnOnFor
from tests.fakes.scripted import ScriptedAdapter
from tests.fixtures.fake import add_fake_entity, fake_config_entry

LEVEL = 1


async def execute(self, hass, request, targets):
    await inner_wire.send(hass, {"level": LEVEL}, context=request.context)
    await hass.services.async_call("probe", "ping", {"level": LEVEL, "context": request.context}, blocking=True)

    async def later(now):
        # A fade's tick: sent after the adapter returned, from a timer it started.
        await hass.services.async_call("probe", "ping", {"later": True}, blocking=True)

    async_call_later(hass, timedelta(seconds=1), later)
    return await ScriptedAdapter.execute(self, hass, request, targets)


async def run(hass):
    hass.services.async_register("probe", "ping", lambda call: None)
    add_fake_entity(hass, fake_config_entry(hass), "light.a")
    start = wall_clock_now()
    with patch.object(FakeTurnOnFor, "execute", execute):
        response = await call(hass, "turn_on_for", {"entity_id": "light.a", "duration": 5})
    await advance(hass, start, 2)
    return response


async def test_action(hass, setup_integration):
    await run(hass)


async def test_a_replaced_boundary_is_recorded(hass, setup_integration, monkeypatch):
    monkeypatch.setattr(inner_wire, "send", AsyncMock(side_effect=OSError))
    with pytest.raises(HomeAssistantError):
        await run(hass)
"""

FAILING = """
def test_fails():
    assert False
"""


@pytest.fixture
def inner(pytester: pytest.Pytester, monkeypatch) -> pytest.Pytester:
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    pytester.makepyprojecttoml('[tool.pytest.ini_options]\nasyncio_mode = "auto"\n')
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(inner_wire=WIRE_MODULE, test_inner=TEST)
    (pytester.path / "tests/integrations/fake").mkdir(parents=True)
    (pytester.path / "tests/integrations/fake/wire.py").write_text(WIRE)
    return pytester


def run(pytester: pytest.Pytester, *args: str) -> pytest.RunResult:
    return pytester.runpytest_subprocess("-p", "no:cacheprovider", *args)


def segments(pytester: pytest.Pytester) -> list[dict]:
    return json.loads((pytester.path / GOLDEN).read_text())


def test_write_then_check_passes_and_records_the_wire(inner):
    assert run(inner, "--transcripts=write").ret == 0
    assert run(inner, "--transcripts=check").ret == 0

    raised, sent = segments(inner)
    assert [raised["integration"], raised["action"]] == [sent["integration"], sent["action"]] == ["fake", "turn_on_for"]
    # The request's Context is dropped.
    assert "context" not in sent["request"]["request"]
    assert sent["request"]["targets"] == [["light.a", "light.a", False]]
    assert [r["status"] for r in raised["result"]] == ["rejected"]
    assert [r["status"] for r in sent["result"]] == ["sent"]
    # The raise of the mock the test put in place, and nothing after it.
    assert raised["wire"] == [[["inner_wire.send", [None, {"level": 1}], {}], {"raises": "OSError"}]]
    # HomeAssistant becomes None in args, and the Context leaves kwargs and service data; the timer's call, after
    # the adapter returned, is in the segment.
    assert sent["wire"] == [
        [["inner_wire.send", [None, {"level": 1}], {}], {"ok": {"level": 1}}],
        [["service", "probe.ping", {"level": 1}], None],
        [["service", "probe.ping", {"later": True}], None],
    ]


def test_a_changed_call_fails_check(inner):
    assert run(inner, "--transcripts=write").ret == 0
    test = inner.path / "test_inner.py"
    test.write_text(test.read_text().replace("LEVEL = 1", "LEVEL = 2"))

    result = run(inner, "--transcripts=check")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines([f"differs: {GOLDEN} (+2 -2 segments)"])


def test_a_missing_or_extra_file_fails_check_and_write_fixes_both(inner):
    calls = inner.path / "tests/integrations/fake/calls"
    calls.mkdir()
    (calls / "gone.json").write_text("[]\n")

    result = run(inner, "--transcripts=check")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines([f"missing: {GOLDEN}", "extra: tests/integrations/fake/calls/gone.json"])
    assert run(inner, "--transcripts=write").ret == 0
    assert sorted(p.name for p in calls.iterdir()) == ["turn_on_for.json"]


def test_a_failing_test_blocks_write(inner):
    inner.makepyfile(test_failing=FAILING)

    result = run(inner, "--transcripts=write")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["transcripts not written: the run failed"])
    assert not (inner.path / "tests/integrations/fake/calls").exists()


def test_transcripts_are_off_by_default(inner):
    assert run(inner).ret == 0
    assert not (inner.path / "tests/integrations/fake/calls").exists()


def test_xdist_workers_hand_their_segments_to_the_controller(inner):
    assert run(inner, "--transcripts=write").ret == 0
    serial = segments(inner)
    (inner.path / GOLDEN).unlink()

    assert run(inner, "-n", "2", "--transcripts=write").ret == 0
    assert segments(inner) == serial
    assert run(inner, "-n", "2", "--transcripts=check").ret == 0
