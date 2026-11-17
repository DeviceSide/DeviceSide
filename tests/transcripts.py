"""Call transcripts: what each action sent on the wire in the unit tests, and what it made of the replies.

Off unless pytest runs with `--transcripts=write|check` (a plain or `-k` run never touches them). Each
`Dispatcher._run_adapter` run opens a segment, `{integration, action, request, wire, result}`, held in a ContextVar,
so the tasks and timers the run starts (a fade's ticks) land in it too. `wire` holds each call made inside the segment
at a wire boundary, as `[call, reply]`: any non-DeviceSide service through `ServiceRegistry.async_call`, as
`["service", "<domain>.<service>", data]`, and each boundary an integration declares in its
`tests/integrations/<x>/wire.py`, `BOUNDARIES = [(module, attribute, leading args to drop), ...]`, as
`["<module's last name>.<attribute>", args, kwargs]`. A boundary is wrapped again at each segment's open, around
whatever a test installed there, so name it where callers look it up. `result` is the run's reconciled
per-target results. A segment is serialized when its test ends, and carries no test id.

Normalization: HomeAssistant and Context values are dropped (omitted from mappings and dataclasses, None in a
sequence), as they hold per-run ids; dataclasses become dicts of their fields; enums their values; sets sorted lists;
bytes hex; a raised exception `{"raises": <class name>}`; any other object `"<TypeName>"`.

`write`, after a run with no failures, writes `tests/integrations/<x>/calls/<action>.json`, the sorted unique segments
of each action, for each integration with a `tests/integrations/<x>/` directory, and removes the `calls/` files of
actions the run didn't see. `check` fails the run when those files would differ. Under xdist each worker hands its
segments to the controller, which writes or checks.
"""

import dataclasses
import enum
import functools
import importlib
import importlib.util
import inspect
import json
from collections.abc import Callable
from contextvars import ContextVar
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from homeassistant.core import Context, HomeAssistant, ServiceRegistry

from custom_components.deviceside.const import DOMAIN
from custom_components.deviceside.core.dispatcher import Dispatcher

_SEGMENT: ContextVar[dict | None] = ContextVar("transcript_segment", default=None)
_WRAPPED = "__transcript_boundary__"
_WORKER_KEY = "transcripts"
_DROPPED = (HomeAssistant, Context)

_DONE = {"write": "written", "check": "checked"}

type Boundary = tuple[str, str, int]


def _wrapped(fn: Any) -> bool:
    # `is True`, as a test's MagicMock answers any attribute with a (truthy) mock.
    return getattr(fn, _WRAPPED, False) is True


def norm(value: Any) -> Any:  # noqa: C901
    """`value` as JSON, per the module docstring's rules."""
    if isinstance(value, _DROPPED):
        return None
    if isinstance(value, BaseException):
        return {"raises": type(value).__name__}
    if isinstance(value, enum.Enum):
        return norm(value.value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: norm(v) for f in dataclasses.fields(value) if not isinstance(v := getattr(value, f.name), _DROPPED)
        }
    if isinstance(value, dict):
        return {str(k): norm(v) for k, v in value.items() if not isinstance(v, _DROPPED)}
    if isinstance(value, list | tuple):
        return [norm(v) for v in value]
    if isinstance(value, set | frozenset):
        return sorted((norm(v) for v in value), key=_key)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, SimpleNamespace):
        return norm(vars(value))
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return f"<{type(value).__name__}>"


def _key(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _record(call: list, reply: Any) -> None:
    """One wire call and its reply (or raise), into the open segment."""
    if (segment := _SEGMENT.get()) is not None:
        segment["wire"].append([norm(call), norm(reply)])


def boundary(name: str, fn: Callable, skip: int = 0) -> Callable:
    """`fn`, recording each call inside a segment as `[name, args (the first `skip` dropped), kwargs]` and its reply."""
    if _wrapped(fn):
        return fn

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            if _SEGMENT.get() is None:
                return await fn(*args, **kwargs)
            call = [name, list(args[skip:]), kwargs]
            try:
                reply = await fn(*args, **kwargs)
            except BaseException as err:
                _record(call, err)
                raise
            _record(call, reply)
            return reply

    else:

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if _SEGMENT.get() is None:
                return fn(*args, **kwargs)
            call = [name, list(args[skip:]), kwargs]
            try:
                reply = fn(*args, **kwargs)
            except BaseException as err:
                _record(call, err)
                raise
            if inspect.isawaitable(reply):
                return _awaited(call, reply)
            _record(call, reply)
            return reply

    setattr(wrapper, _WRAPPED, True)
    return wrapper


async def _awaited(call: list, awaitable) -> Any:
    """The reply of a plain function that hands back an awaitable (a test's lambda or mock), recorded once awaited."""
    try:
        reply = await awaitable
    except BaseException as err:
        _record(call, err)
        raise
    _record(call, reply)
    return reply


def load_boundaries(integrations: Path) -> list[Boundary]:
    """Every boundary the `wire.py` files under `integrations` declare, each checked to import."""
    found = []
    for path in sorted(integrations.glob("*/wire.py")):
        spec = importlib.util.spec_from_file_location(f"_transcript_wire_{path.parent.name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for entry in module.BOUNDARIES:
            _owner(*entry[:2])
            found.append(tuple(entry))
    return found


def _owner(module: str, attribute: str) -> tuple[Any, str]:
    """The object holding `attribute` (dotted for a class's method) in `module`, and its last name."""
    *path, name = attribute.split(".")
    owner = importlib.import_module(module)
    for part in path:
        owner = getattr(owner, part)
    if not hasattr(owner, name):
        raise pytest.UsageError(f"transcripts: wire boundary {module}.{attribute} doesn't exist")
    if isinstance(inspect.getattr_static(owner, name), staticmethod | classmethod):
        # Wrapping one would turn it into an instance method.
        raise pytest.UsageError(f"transcripts: wire boundary {module}.{attribute} is a static or class method")
    return owner, name


def _boundary_name(module: str, attribute: str) -> str:
    """A boundary's name in the wire: its module's last name and its attribute, `zcl.read_attributes`."""
    return f"{module.rpartition(".")[2]}.{attribute}"


def _wrap(boundaries: list[Boundary]) -> None:
    """Each boundary wrapped around whatever stands there now."""
    for module, attribute, skip in boundaries:
        owner, name = _owner(module, attribute)
        setattr(owner, name, boundary(_boundary_name(module, attribute), getattr(owner, name), skip))


def _unwrap(boundaries: list[Boundary]) -> None:
    for module, attribute, _ in boundaries:
        owner, name = _owner(module, attribute)
        if _wrapped(current := getattr(owner, name)):
            setattr(owner, name, current.__wrapped__)


class Recorder:
    """The `--transcripts` run: records segments per test, then writes or checks the golden files."""

    def __init__(self, mode: str, integrations: Path) -> None:
        self.mode = mode
        self.integrations = integrations
        self.boundaries = load_boundaries(integrations)
        self.collected: list[dict] = []  # the running test's segments
        self.segments: dict[tuple[str, str], set[str]] = {}  # (integration, action): each segment as JSON
        self.problems: list[str] = []  # what the session's end reports

    # --- recording

    def install(self) -> None:
        self._run_adapter = run_adapter = Dispatcher._run_adapter
        self._async_call = async_call = ServiceRegistry.async_call
        recorder = self

        async def recorded_run(self, adapter, request, targets, dropped, reached, own):
            _wrap(recorder.boundaries)
            segment = {
                "integration": adapter.integration,
                "action": adapter.action,
                "request": {
                    "request": norm(request),
                    "targets": [[t.reported_id, t.entity_id, t.is_group] for t in targets],
                    "own": norm(own),
                    "dropped": norm(dropped),
                },
                "wire": [],
            }
            recorder.collected.append(segment)
            token = _SEGMENT.set(segment)
            try:
                results = await run_adapter(self, adapter, request, targets, dropped, reached, own)
            finally:
                _SEGMENT.reset(token)
            segment["result"] = norm(results)
            return results

        async def recorded_call(self, domain, service, service_data=None, *args, **kwargs):
            if domain == DOMAIN or _SEGMENT.get() is None:
                return await async_call(self, domain, service, service_data, *args, **kwargs)
            call = ["service", f"{domain}.{service}", service_data]
            try:
                reply = await async_call(self, domain, service, service_data, *args, **kwargs)
            except BaseException as err:
                _record(call, err)
                raise
            _record(call, reply)
            return reply

        Dispatcher._run_adapter = recorded_run
        ServiceRegistry.async_call = recorded_call

    def uninstall(self) -> None:
        Dispatcher._run_adapter = self._run_adapter
        ServiceRegistry.async_call = self._async_call
        _unwrap(self.boundaries)

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):
        self.collected.clear()
        try:
            return (yield)
        finally:
            # A run still going when its test ended (no result) depends on timing, so it's left out.
            for segment in self.collected:
                if "result" in segment:
                    self.segments.setdefault((segment["integration"], segment["action"]), set()).add(_key(segment))
            self.collected.clear()

    # --- xdist: each worker hands its segments to the controller

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodedown(self, node, error) -> None:
        for key, segments in getattr(node, "workeroutput", {}).get(_WORKER_KEY, {}).items():
            self.segments.setdefault(tuple(key.split("|")), set()).update(segments)

    # --- the session's end

    def pytest_sessionfinish(self, session, exitstatus) -> None:
        if hasattr(session.config, "workeroutput"):
            session.config.workeroutput[_WORKER_KEY] = {"|".join(k): sorted(v) for k, v in self.segments.items()}
            return
        if exitstatus != pytest.ExitCode.OK:
            self.problems.append(f"transcripts not {_DONE[self.mode]}: the run failed")
            return
        wanted, stale = self._files()
        if self.mode == "write":
            _write(wanted, stale)
        elif problems := self._check(wanted, stale):
            self.problems += [
                "call transcripts differ from the committed ones (pytest --transcripts=write):",
                *problems,
            ]
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def _check(self, wanted: dict[Path, str], stale: list[Path]) -> list[str]:
        """Each golden file missing, differing or extra."""
        problems = []
        for path, body in sorted(wanted.items()):
            if not path.is_file():
                problems.append(f"missing: {self._name(path)}")
            elif (old := path.read_text()) != body:
                problems.append(f"differs: {self._name(path)} ({_diff(old, body)})")
        return problems + [f"extra: {self._name(path)}" for path in stale]

    def pytest_terminal_summary(self, terminalreporter) -> None:
        if self.problems:
            terminalreporter.section("call transcripts")
            for line in self.problems:
                terminalreporter.write_line(line)

    def _files(self) -> tuple[dict[Path, str], list[Path]]:
        """Each golden file the run's segments make, as its text, and the existing ones it doesn't make."""
        owned = {path.name for path in self.integrations.glob("*/") if path.is_dir()}
        wanted = {
            self.integrations / integration / "calls" / f"{action}.json": _body(segments)
            for (integration, action), segments in self.segments.items()
            if integration in owned
        }
        stale = sorted(set(self.integrations.glob("*/calls/*.json")) - wanted.keys())
        return wanted, stale

    def _name(self, path: Path) -> str:
        return str(path.relative_to(self.integrations.parent.parent))


def _write(wanted: dict[Path, str], stale: list[Path]) -> None:
    for path, body in wanted.items():
        if not path.is_file() or path.read_text() != body:
            path.parent.mkdir(exist_ok=True)
            path.write_text(body)
    for path in stale:
        path.unlink()
        if not any(path.parent.iterdir()):
            path.parent.rmdir()


def _body(segments: set[str]) -> str:
    return json.dumps([json.loads(s) for s in sorted(segments)], indent=1, sort_keys=True) + "\n"


def _diff(old: str, new: str) -> str:
    """How many segments a golden file gains and loses, or that its text alone changed."""
    try:
        before = {_key(s) for s in json.loads(old)}
    except ValueError, TypeError:
        return "unreadable"
    after = {_key(s) for s in json.loads(new)}
    if before == after:
        return "formatting"
    return f"+{len(after - before)} -{len(before - after)} segments"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--transcripts",
        choices=("write", "check"),
        default=None,
        help="write or check the call transcripts in tests/integrations/<x>/calls/ (tests/transcripts.py)",
    )


def pytest_configure(config: pytest.Config) -> None:
    if mode := config.getoption("--transcripts"):
        recorder = Recorder(mode, config.rootpath / "tests" / "integrations")
        recorder.install()
        config.pluginmanager.register(recorder, "transcripts-recorder")


def pytest_unconfigure(config: pytest.Config) -> None:
    if recorder := config.pluginmanager.get_plugin("transcripts-recorder"):
        recorder.uninstall()
