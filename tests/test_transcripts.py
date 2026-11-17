"""The call transcript recorder (tests/transcripts.py), run on an inner pytest session over the fake integrations.

Each inner session runs in a subprocess, as the recorder patches the dispatcher and HA's service registry for its
whole session.
"""

import enum
import json
from pathlib import Path

import pytest

from tests.transcripts import norm

ROOT = Path(__file__).parents[1]
CALLS = "tests/integrations/fake/calls"
GOLDEN = f"{CALLS}/turn_on_for.json"

CONFTEST = """
from tests.conftest import *  # noqa: F403
"""

# A boundary a test may replace, declared in the fake integration's wire.py.
WIRE_MODULE = """
async def send(hass, payload, *, context=None):
    return {"ok": payload}


class Client:
    async def send(self, payload):
        return {"client": payload}

    @staticmethod
    def static():
        pass
"""

WIRE = """
BOUNDARIES = [("inner_wire", "send", 0)]
"""

# Shared by the inner test modules: an execute that sends through the boundary and HA's services, with a timer.
HELPERS = """
from datetime import timedelta
from unittest.mock import patch

import inner_wire
from homeassistant.helpers.event import async_call_later

from tests.conftest import advance, call, wall_clock_now
from tests.fakes.fake_integration import FakeTurnOnFor
from tests.fakes.scripted import ScriptedAdapter
from tests.fixtures.fake import add_fake_entity, fake_config_entry

LEVEL = 1


async def execute(self, hass, request, targets):
    await inner_wire.send(hass, {"level": LEVEL}, context=request.context)
    await hass.services.async_call("probe", "ping", {"level": LEVEL, "context": request.context}, blocking=True)
    await hass.services.async_call("probe", "ping", {}, blocking=True, target={"entity_id": "light.a"})
    # DeviceSide's own services are no wire call.
    await hass.services.async_call("deviceside", "probe", {}, blocking=True)

    async def later(now):
        # A fade's tick: sent after the adapter returned, from a timer it started.
        await hass.services.async_call("probe", "ping", {"later": True}, blocking=True)

    async_call_later(hass, timedelta(seconds=1), later)
    return await ScriptedAdapter.execute(self, hass, request, targets)


def register(hass):
    hass.services.async_register("probe", "ping", lambda call: None)
    hass.services.async_register("deviceside", "probe", lambda call: None)


async def run(hass):
    register(hass)
    add_fake_entity(hass, fake_config_entry(hass), "light.a")
    start = wall_clock_now()
    with patch.object(FakeTurnOnFor, "execute", execute):
        response = await call(hass, "turn_on_for", {"entity_id": "light.a", "duration": 5})
    await advance(hass, start, 2)
    return response
"""

TEST = """
from unittest.mock import AsyncMock

import inner_wire
import pytest
from homeassistant.exceptions import HomeAssistantError

from inner_helpers import run


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
    # A test that edits an inner module and reruns within the second would otherwise import the stale .pyc.
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    pytester.makepyprojecttoml('[tool.pytest.ini_options]\nasyncio_mode = "auto"\n')
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(inner_wire=WIRE_MODULE, inner_helpers=HELPERS, test_inner=TEST)
    for integration in ("fake", "fake_special"):
        (pytester.path / "tests/integrations" / integration).mkdir(parents=True)
    (pytester.path / "tests/integrations/fake/wire.py").write_text(WIRE)
    return pytester


def only(pytester: pytest.Pytester, test: str) -> None:
    """The inner session's tests: just `test`, as test_inner.py."""
    (pytester.path / "test_inner.py").write_text(test)


def run(pytester: pytest.Pytester, *args: str) -> pytest.RunResult:
    return pytester.runpytest_subprocess("-p", "no:cacheprovider", *args)


def segments(pytester: pytest.Pytester, path: str = GOLDEN) -> list[dict]:
    return json.loads((pytester.path / path).read_text())


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
    # HomeAssistant becomes None in args, and the Context leaves kwargs and service data; a service call's target is
    # kept; DeviceSide's own service isn't there; the timer's call, after the adapter returned, is in the segment.
    assert sent["wire"] == [
        [["inner_wire.send", [None, {"level": 1}], {}], {"ok": {"level": 1}}],
        [["service", "probe.ping", {"level": 1}], None],
        [["service", "probe.ping", {}, {"target": {"entity_id": "light.a"}}], None],
        [["service", "probe.ping", {"later": True}], None],
    ]


def test_a_changed_call_fails_check(inner):
    assert run(inner, "--transcripts=write").ret == 0
    helpers = inner.path / "inner_helpers.py"
    helpers.write_text(helpers.read_text().replace("LEVEL = 1", "LEVEL = 2"))

    result = run(inner, "--transcripts=check")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines([f"differs: {GOLDEN} (+2 -2 segments)"])


def test_a_missing_or_extra_file_fails_check_and_write_fixes_both(inner):
    calls = inner.path / CALLS
    calls.mkdir()
    (calls / "gone.json").write_text("[]\n")

    result = run(inner, "--transcripts=check")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines([f"missing: {GOLDEN}", f"extra: {CALLS}/gone.json"])
    assert run(inner, "--transcripts=write").ret == 0
    assert sorted(p.name for p in calls.iterdir()) == ["turn_on_for.json"]


def test_a_failing_test_blocks_write(inner):
    inner.makepyfile(test_failing=FAILING)

    result = run(inner, "--transcripts=write")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["transcripts not written: the run failed"])
    assert not (inner.path / CALLS).exists()


def test_transcripts_are_off_by_default(inner):
    assert run(inner).ret == 0
    assert not (inner.path / CALLS).exists()


@pytest.mark.parametrize(
    ("args", "reason"),
    [
        pytest.param(["-k", "test_action"], "it runs with -k", id="k"),
        pytest.param(["-m", "slow"], "it runs with -m", id="m"),
        pytest.param(["--deselect", "test_inner.py::test_action"], "it runs with --deselect", id="deselect"),
        pytest.param(["test_inner.py"], "it runs test_inner.py, not the testpaths", id="path"),
        pytest.param(["--collect-only"], "it runs with --collect-only", id="collect-only"),
    ],
)
def test_a_narrowed_run_is_refused(inner, args, reason):
    for mode in ("write", "check"):
        result = run(inner, f"--transcripts={mode}", *args)

        assert result.ret == pytest.ExitCode.USAGE_ERROR
        result.stderr.fnmatch_lines([f"ERROR: --transcripts={mode} needs the whole suite: {reason}"])
    assert not (inner.path / CALLS).exists()


def test_a_run_deselected_by_a_plugin_is_refused(inner):
    inner.makeconftest(
        CONFTEST
        + """
def pytest_collection_modifyitems(config, items):
    config.hook.pytest_deselected(items=items[:1])
    items[:] = items[1:]
"""
    )

    result = run(inner, "--transcripts=write")

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(["ERROR: --transcripts=write needs the whole suite: this run deselects tests"])
    # Under xdist each worker deselects; the controller refuses once they're done.
    result = run(inner, "-n", "2", "--transcripts=write")

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stdout.fnmatch_lines(["--transcripts=write needs the whole suite: this run deselects tests"])
    assert not (inner.path / CALLS).exists()


def test_a_run_from_a_subdirectory_is_refused(inner, monkeypatch):
    sub = inner.mkpydir("sub")
    (sub / "test_sub.py").write_text("def test_sub():\n    pass\n")
    monkeypatch.chdir(sub)

    result = run(inner, "--transcripts=write")

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(["ERROR: --transcripts=write needs the whole suite: it runs */sub, not the testpaths"])


def test_a_run_where_no_test_ran_keeps_the_golden_files(inner):
    assert run(inner, "--transcripts=write").ret == 0
    only(inner, "")

    for mode in ("write", "check"):
        result = run(inner, f"--transcripts={mode}")

        assert result.ret == pytest.ExitCode.USAGE_ERROR
        result.stdout.fnmatch_lines([f"transcripts not {'written' if mode == 'write' else 'checked'}: no test ran"])
    assert (inner.path / GOLDEN).is_file()


def test_the_whole_suite_named_explicitly_is_not_narrowed(inner):
    assert run(inner, "--transcripts=write", str(inner.path)).ret == 0


def test_xdist_workers_hand_their_segments_to_the_controller(inner):
    assert run(inner, "--transcripts=write").ret == 0
    serial = segments(inner)
    (inner.path / GOLDEN).unlink()

    assert run(inner, "-n", "2", "--transcripts=write").ret == 0
    assert segments(inner) == serial
    assert run(inner, "-n", "2", "--transcripts=check").ret == 0


def test_a_wrapper_forwards_attributes_and_is_gone_after_its_test(inner):
    only(
        inner,
        """
import types
from unittest.mock import AsyncMock

import inner_wire

from inner_helpers import run


async def test_a_sets_its_mock_after_a_call(hass, setup_integration, monkeypatch):
    mock = AsyncMock(return_value=1)
    monkeypatch.setattr(inner_wire, "send", mock)
    await run(hass)
    # The recorder's wrapper stands there now; this configures the mock.
    inner_wire.send.return_value = 2
    assert mock.return_value == 2
    await run(hass)


async def test_b_finds_the_real_function(hass, setup_integration):
    await run(hass)
    assert type(inner_wire.send) is not types.FunctionType


async def test_c_finds_the_real_function_again():
    assert type(inner_wire.send) is types.FunctionType
""",
    )

    assert run(inner, "-p", "no:randomly", "--transcripts=write").ret == 0
    assert sorted(str(segment["wire"][0][1]) for segment in segments(inner)) == ["1", "2", "{'ok': {'level': 1}}"]


def test_a_mock_calling_through_to_the_real_boundary_records_once(inner):
    only(
        inner,
        """
from unittest.mock import AsyncMock

import inner_wire

from inner_helpers import run


async def test_through(hass, setup_integration, monkeypatch):
    await run(hass)
    through = inner_wire.send  # the recorder's wrapper of the real one, by now

    async def via_mock(hass, payload, **kw):
        return await through(hass, {"via": "mock"}, **kw)

    monkeypatch.setattr(inner_wire, "send", AsyncMock(side_effect=via_mock))
    await run(hass)
""",
    )

    assert run(inner, "--transcripts=write").ret == 0
    sends = [entry for segment in segments(inner) for entry in segment["wire"] if entry[0][0] == "inner_wire.send"]
    assert sorted(sends, key=str) == [
        [["inner_wire.send", [None, {"level": 1}], {}], {"ok": {"level": 1}}],
        [["inner_wire.send", [None, {"level": 1}], {}], {"ok": {"via": "mock"}}],
    ]


def test_concurrent_runs_each_hold_only_their_own_calls(inner):
    only(
        inner,
        """
import asyncio
from unittest.mock import patch

import inner_wire

from tests.conftest import call
from tests.fakes.scripted import ScriptedAdapter
from tests.fixtures.fake import add_fake_entity, fake_config_entry

execute = ScriptedAdapter.execute


async def interleaved(self, hass, request, targets):
    for step in range(3):
        await inner_wire.send(hass, {"by": self.integration, "step": step})
        await asyncio.sleep(0)
    return await execute(self, hass, request, targets)


async def test_two_runs(hass, setup_integration):
    fake = fake_config_entry(hass)
    add_fake_entity(hass, fake, "light.a")
    add_fake_entity(hass, fake, "light.lamp", identifier="special_1")
    with patch.object(ScriptedAdapter, "execute", interleaved):
        await call(hass, "turn_on_for", {"entity_id": ["light.a", "light.lamp"], "duration": 5})
""",
    )

    assert run(inner, "--transcripts=write").ret == 0
    for integration in ("fake", "fake_special"):
        (segment,) = segments(inner, f"tests/integrations/{integration}/calls/turn_on_for.json")
        assert [entry[0][1][1] for entry in segment["wire"]] == [{"by": integration, "step": s} for s in range(3)]


def test_a_run_that_never_finished_is_left_out(inner):
    only(
        inner,
        """
import asyncio
from contextlib import suppress
from unittest.mock import patch

from tests.conftest import call
from tests.fakes.fake_integration import FakeTurnOnFor
from tests.fixtures.fake import add_fake_entity, fake_config_entry

from inner_helpers import register


async def test_cancelled(hass, setup_integration):
    started = asyncio.Event()

    async def stuck(self, hass, request, targets):
        await hass.services.async_call("probe", "ping", {}, blocking=True)
        started.set()
        await asyncio.Event().wait()

    register(hass)
    add_fake_entity(hass, fake_config_entry(hass), "light.a")
    with patch.object(FakeTurnOnFor, "execute", stuck):
        task = hass.async_create_task(call(hass, "turn_on_for", {"entity_id": "light.a", "duration": 5}))
        await started.wait()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
""",
    )

    assert run(inner, "--transcripts=write").ret == 0
    assert not (inner.path / CALLS).exists()


def test_a_class_method_boundary_records_its_call_mocked_or_not(inner):
    (inner.path / "tests/integrations/fake/wire.py").write_text('BOUNDARIES = [("inner_wire", "Client.send", 1)]\n')
    only(
        inner,
        """
from unittest.mock import AsyncMock, patch

import inner_wire

from tests.conftest import call
from tests.fakes.fake_integration import FakeTurnOnFor
from tests.fakes.scripted import ScriptedAdapter
from tests.fixtures.fake import add_fake_entity, fake_config_entry


async def sends(self, hass, request, targets):
    await inner_wire.Client().send({"level": 1})
    return await ScriptedAdapter.execute(self, hass, request, targets)


async def turn_on(hass):
    add_fake_entity(hass, fake_config_entry(hass), "light.a")
    with patch.object(FakeTurnOnFor, "execute", sends):
        await call(hass, "turn_on_for", {"entity_id": "light.a", "duration": 5})


async def test_real(hass, setup_integration):
    await turn_on(hass)


async def test_mocked_on_the_class(hass, setup_integration, monkeypatch):
    mock = AsyncMock(return_value={"mocked": True})
    monkeypatch.setattr(inner_wire.Client, "send", mock)
    await turn_on(hass)
    # Called without the instance, as a mock on a class is; reached through the wrapper, which forwards to it.
    mock.assert_awaited_once_with({"level": 1})
    inner_wire.Client().send.assert_awaited_once_with({"level": 1})
""",
    )

    assert run(inner, "--transcripts=write").ret == 0
    assert sorted((segment["wire"] for segment in segments(inner)), key=str) == [
        [[["inner_wire.Client.send", [{"level": 1}], {}], {"client": {"level": 1}}]],
        [[["inner_wire.Client.send", [{"level": 1}], {}], {"mocked": True}]],
    ]


def test_dict_keys_are_normalized():
    class Color(enum.Enum):
        RED = "red"

    assert norm({1: "a", (1, 2): "b", Color.RED: "c", None: "d", b"\x01": "e"}) == {
        "1": "a",
        "[1, 2]": "b",
        "red": "c",
        "null": "d",
        "01": "e",
    }


@pytest.mark.parametrize("reply", [pytest.param("object()", id="value"), pytest.param("{object(): 1}", id="key")])
def test_an_unnormalized_value_blocks_write(inner, reply):
    only(
        inner,
        f"""
import inner_wire

from inner_helpers import run


async def test_object(hass, setup_integration, monkeypatch):
    async def send(hass, payload, **kw):
        return {reply}

    monkeypatch.setattr(inner_wire, "send", send)
    await run(hass)
""",
    )

    result = run(inner, "--transcripts=write")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["transcripts not written: values with no normalization*", "fake turn_on_for <object>"])
    assert not (inner.path / CALLS).exists()


@pytest.mark.parametrize(
    ("boundary", "error"),
    [
        pytest.param("missing", "inner_wire.missing doesn't exist", id="missing"),
        pytest.param("Client.static", "inner_wire.Client.static is a static or class method", id="staticmethod"),
    ],
)
def test_a_bad_boundary_is_a_usage_error(inner, boundary, error):
    (inner.path / "tests/integrations/fake/wire.py").write_text(f'BOUNDARIES = [("inner_wire", "{boundary}", 0)]\n')

    result = run(inner, "--transcripts=write")

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines([f"ERROR: transcripts: wire boundary {error}"])
