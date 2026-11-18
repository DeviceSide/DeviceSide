"""Call transcripts: what each action sent on the wire in the unit tests, and what it made of the replies.

Off unless pytest runs with `--transcripts=write|check`, and refused on a run narrower than the whole suite (`-k`, `-m`,
`--lf`, `--sw`, `--deselect`, `--ignore`, `--collect-only`, paths other than the testpaths, a run from a subdirectory,
any deselection, or one where no test ran), which would drop or miss every action it didn't reach. Each
`Dispatcher._run_adapter` run opens a segment, `{integration, action, request, wire, result}`, held in a ContextVar, so
the tasks and timers the run starts (a fade's ticks) land in it too. `wire` holds each call made inside the segment at a
wire boundary, as `[call, reply]`: any non-DeviceSide service through `ServiceRegistry.async_call`, as `["service",
"<domain>.<service>", data]`, then one dict of its `blocking`, `return_response` and `target` that differ from
`async_call`'s defaults (`{"blocking": true}`; none differing, no dict), and each boundary an integration declares in
its `tests/integrations/<x>/wire.py`, `BOUNDARIES = [(module, attribute, leading args to drop[, callback index]), ...]`,
as `["<module's last name>.<attribute>", args, kwargs]` (a class's method, `Class.method`, has its instance as the first
arg, even when a test's mock on the class is called without it). A boundary with a callback index is a subscription:
the call is recorded without the callback and with no reply, and each call the callback (a sync one, at that position
among the call's args) gets is recorded as `["<name>.callback", args, kwargs]` and its reply, in the segment the
subscription was made in, whoever delivers it (from no segment, or another's) until that test ends, so the messages a
run is answered with are in its wire. A call takes its place in `wire` when
it is made and gets its reply when it returns, so a reply delivered while a call is still running (a broker answering
inside a publish) comes after the call that drew it. A boundary is wrapped at each segment's open,
around whatever a test installed there (so name it where callers look it up), and unwrapped when the test ends; a call
it makes to itself, as a test's mock calling through to the real one, records once. `result` is the run's reconciled
per-target results. A segment is serialized when its test ends, and carries no test id; a run its test didn't see
finish is left out.

Normalization: HomeAssistant and Context values are dropped (omitted from mappings and dataclasses, None in a sequence),
as they hold per-run ids; dataclasses become dicts of their fields; enums their values; sets sorted lists; bytes hex; a
class with annotations of its own (a zigpy request's schema) `{"class": <name>, "fields": {<field>: <its type's
name>}}`, an annotation with no name a placeholder; a mapping's keys are normalized too, and one that isn't then a str
becomes its JSON text (two keys that normalize alike raise); a raised exception `{"raises": <class name>}`; any other
object `"<TypeName>"`, which fails the run when it's in a segment's wire or result: an integration's library types get a
rule here.

`write`, after a run with no failures, writes `tests/integrations/<x>/calls/<action>.json`, the sorted unique segments
of each action, for each integration with a `tests/integrations/<x>/` directory, and removes the `calls/` files of
actions the run didn't see. `check` fails the run when those files would differ. Either fails an action whose adapter
has `native_groups` and no segment run on a group. Under xdist each worker hands its segments to the controller, which
writes or checks.
"""

import dataclasses
import enum
import functools
import importlib
import importlib.util
import inspect
import json
import re
from collections.abc import Callable
from contextvars import ContextVar
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any

import pytest
from homeassistant.core import Context, HomeAssistant, ServiceRegistry

from custom_components.deviceside.const import DOMAIN
from custom_components.deviceside.core.dispatcher import Dispatcher

_SEGMENT: ContextVar[dict | None] = ContextVar("transcript_segment", default=None)
# The boundaries recording in this context, so one a test's mock calls through to records once.
_ACTIVE: ContextVar[frozenset[str]] = ContextVar("transcript_active_boundaries", default=frozenset())
_WORKER_KEY = "transcripts"
_DESELECTED_KEY = "transcripts_deselected"
_NATIVE_KEY = "transcripts_native_groups"
_DESELECTED = "--transcripts={mode} needs the whole suite: this run deselects tests"
_DROPPED = (HomeAssistant, Context)
# `ServiceRegistry.async_call`'s arguments, past its service data, that change what the call does or returns.
_SERVICE_OPTIONS = ("blocking", "return_response", "target")

_DONE = {"write": "written", "check": "checked"}
_PLACEHOLDER = re.compile(r"<\w+>")
# Options that run part of the suite, as (flag, dest).
_NARROWING = (
    ("-k", "keyword"),
    ("-m", "markexpr"),
    ("--lf", "lf"),
    ("--sw", "stepwise"),
    ("--sw-skip", "stepwise_skip"),
    ("--deselect", "deselect"),
    ("--ignore", "ignore"),
    ("--ignore-glob", "ignore_glob"),
    ("--collect-only", "collectonly"),
    # Before --setup-only, which it sets too.
    ("--setup-plan", "setupplan"),
    ("--setup-only", "setuponly"),
)

type Boundary = tuple[str, str, int] | tuple[str, str, int, int]


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
        mapping = {}
        for k, v in value.items():
            if isinstance(v, _DROPPED):
                continue
            if (key := _json_key(norm(k))) in mapping:
                raise ValueError(f"transcripts: two keys of a mapping normalize to {key!r}")
            mapping[key] = norm(v)
        return mapping
    if isinstance(value, list | tuple):
        return [norm(v) for v in value]
    if isinstance(value, set | frozenset):
        return sorted((norm(v) for v in value), key=_key)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, SimpleNamespace):
        return norm(vars(value))
    if isinstance(value, type) and (fields := inspect.get_annotations(value)):
        return {"class": value.__name__, "fields": {k: _type_name(t) for k, t in fields.items()}}
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return f"<{type(value).__name__}>"


def _type_name(annotation: Any) -> str:
    """An annotation's name, or a placeholder (failing the run) for one with none, as a union's."""
    if isinstance(annotation, str):
        return annotation
    return getattr(annotation, "__name__", None) or f"<{type(annotation).__name__}>"


def _key(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _json_key(value: Any) -> str:
    """A normalized mapping key as a JSON object's key: a str as it is, anything else its JSON text."""
    return value if isinstance(value, str) else _key(value)


def _open(call: list, segment: dict | None = None) -> list | None:
    """A wire call's slot in `segment` (by default the open one), taken when the call is made so what it causes (a
    reply delivered before it returns) records after it. None when no segment is open."""
    if (segment := segment or _SEGMENT.get()) is None:
        return None
    slot = [norm(call), None]
    segment["wire"].append(slot)
    return slot


def _close(slot: list | None, reply: Any) -> None:
    """The reply (or raise) of the call that took `slot`."""
    if slot is not None:
        slot[1] = norm(reply)


class Wire:
    """A boundary's wrapper, recording each call inside a segment as `[name, args (the first `skip` dropped), kwargs]`
    and its reply. Attribute reads and writes go to the wrapped callable, so a test that sets `.return_value` on its
    mock after a call still configures the mock. A call made while the same boundary is already recording in this
    context (a test's mock calling through to the real one) isn't recorded again."""

    def __init__(self, name: str, fn: Callable, skip: int, instance: tuple = (), callback: int | None = None) -> None:
        object.__setattr__(self, "__wrapped__", fn)
        object.__setattr__(self, "_wire_name", name)
        object.__setattr__(self, "_wire_skip", skip)
        # The position of a subscription's callback among a call's args, or None.
        object.__setattr__(self, "_wire_callback", callback)
        # The instance a mock on a class was looked up on, recorded first as a method's would be, never passed on.
        object.__setattr__(self, "_wire_instance", instance)

    def __getattr__(self, attr: str) -> Any:
        return getattr(self.__wrapped__, attr)

    def __setattr__(self, attr: str, value: Any) -> None:
        setattr(self.__wrapped__, attr, value)

    def __delattr__(self, attr: str) -> None:
        delattr(self.__wrapped__, attr)

    def __get__(self, instance: Any, owner: type | None = None) -> Any:
        # A method binds as the function it wraps would. A mock on a class doesn't bind, so it's called without the
        # instance, but its wrapper records the instance all the same, so a mocked call records as the real one does.
        if instance is None:
            return self
        if hasattr(type(self.__wrapped__), "__get__"):
            return MethodType(self, instance)
        return Wire(self._wire_name, self.__wrapped__, self._wire_skip, (instance,), self._wire_callback)

    def __call__(self, *args, **kwargs) -> Any:
        if _SEGMENT.get() is None or self._wire_name in _ACTIVE.get():
            return self.__wrapped__(*args, **kwargs)
        call = [self._wire_name, list((*self._wire_instance, *args)[self._wire_skip :]), kwargs]
        if (at := self._wire_callback) is not None:
            args, call = self._subscription(args, call, at)
        slot = _open(call)
        token = _ACTIVE.set(_ACTIVE.get() | {self._wire_name})
        try:
            reply = self.__wrapped__(*args, **kwargs)
        except BaseException as err:
            _close(slot, err)
            raise
        finally:
            _ACTIVE.reset(token)
        if inspect.isawaitable(reply):
            return self._awaited(slot, reply)
        self._close_reply(slot, reply)
        return reply

    def _close_reply(self, slot: list | None, reply: Any) -> None:
        # A subscription's reply is its unsubscribe.
        _close(slot, None if self._wire_callback is not None else reply)

    def _subscription(self, args: tuple, call: list, at: int) -> tuple[tuple, list]:
        """`args` with the callback at `at` wrapped to record each call it gets, and `call` without the callback."""
        callback = args[at]
        if inspect.iscoroutinefunction(callback):
            raise TypeError(f"transcripts: {self._wire_name}'s callback must be sync")
        name = f"{self._wire_name}.callback"
        # The segment the subscription was made in, which stays open until its test ends, whoever delivers.
        segment = _SEGMENT.get()

        @functools.wraps(callback)
        def recorded(*cb_args, **cb_kwargs):
            slot = _open([name, list(cb_args), cb_kwargs], segment)
            try:
                reply = callback(*cb_args, **cb_kwargs)
            except BaseException as err:
                _close(slot, err)
                raise
            _close(slot, reply)
            return reply

        del call[1][at + len(self._wire_instance) - self._wire_skip]
        return (*args[:at], recorded, *args[at + 1 :]), call

    async def _awaited(self, slot: list | None, awaitable) -> Any:
        token = _ACTIVE.set(_ACTIVE.get() | {self._wire_name})
        try:
            reply = await awaitable
        except BaseException as err:
            _close(slot, err)
            raise
        finally:
            _ACTIVE.reset(token)
        self._close_reply(slot, reply)
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
    """A boundary's name in the wire: its module's last name and its attribute, `zha.Cluster.read_attributes`."""
    return f"{module.rpartition(".")[2]}.{attribute}"


class Recorder:
    """The `--transcripts` run: records segments per test, then writes or checks the golden files."""

    def __init__(self, mode: str, integrations: Path) -> None:
        self.mode = mode
        self.integrations = integrations
        self.boundaries = load_boundaries(integrations)
        self.collected: list[dict] = []  # the running test's segments
        self.installed: list[tuple[Any, str, bool, Wire]] = []  # the running test's wrappers: owner, name, own attr
        self.segments: dict[tuple[str, str], set[str]] = {}  # (integration, action): each segment as JSON
        self.native: set[tuple[str, str]] = set()  # (integration, action) of each run whose adapter has native_groups
        self.deselected = False
        self.ran = False  # whether any test ran, here or (under xdist) on a worker
        self.problems: list[str] = []  # what the session's end reports

    # --- recording

    def install(self) -> None:
        self._run_adapter = run_adapter = Dispatcher._run_adapter
        self._async_call = async_call = ServiceRegistry.async_call
        signature = inspect.signature(async_call)
        # The call's options a segment records, with the defaults they're recorded only when they differ from.
        defaults = {k: signature.parameters[k].default for k in _SERVICE_OPTIONS}
        recorder = self

        async def recorded_run(self, adapter, request, targets, dropped, reached, own):
            recorder.wrap()
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
            if adapter.scope.native_groups:
                recorder.native.add((adapter.integration, adapter.action))
            token = _SEGMENT.set(segment)
            try:
                results = await run_adapter(self, adapter, request, targets, dropped, reached, own)
            finally:
                _SEGMENT.reset(token)
            segment["result"] = norm(results)
            return results

        @functools.wraps(async_call)  # so a nested install reads the original's signature
        async def recorded_call(self, domain, service, *args, **kwargs):
            if domain == DOMAIN or _SEGMENT.get() is None:
                return await async_call(self, domain, service, *args, **kwargs)
            given = signature.bind(self, domain, service, *args, **kwargs).arguments
            call = ["service", f"{domain}.{service}", given.get("service_data")]
            if options := {k: given[k] for k, default in defaults.items() if given.get(k, default) != default}:
                call.append(options)
            slot = _open(call)
            try:
                reply = await async_call(self, domain, service, *args, **kwargs)
            except BaseException as err:
                _close(slot, err)
                raise
            _close(slot, reply)
            return reply

        Dispatcher._run_adapter = recorded_run
        ServiceRegistry.async_call = recorded_call

    def uninstall(self) -> None:
        Dispatcher._run_adapter = self._run_adapter
        ServiceRegistry.async_call = self._async_call
        self.unwrap()

    def wrap(self) -> None:
        """Each boundary wrapped around whatever stands there now (a test's mock, or the real one)."""
        for module, attribute, skip, *callback in self.boundaries:
            owner, name = _owner(module, attribute)
            if not isinstance(current := inspect.getattr_static(owner, name), Wire):
                wire = Wire(
                    _boundary_name(module, attribute), current, skip, callback=callback[0] if callback else None
                )
                self.installed.append((owner, name, name in vars(owner), wire))
                setattr(owner, name, wire)

    def unwrap(self) -> None:
        """Each wrapper this test installed taken back off, where it still stands."""
        while self.installed:
            owner, name, own, wire = self.installed.pop()
            if inspect.getattr_static(owner, name, None) is wire:
                if own:
                    setattr(owner, name, wire.__wrapped__)
                else:
                    delattr(owner, name)

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):
        self.collected.clear()
        try:
            return (yield)
        finally:
            self.unwrap()
            # A run still going when its test ended (no result) depends on timing, so it's left out.
            for segment in self.collected:
                if "result" in segment:
                    self.segments.setdefault((segment["integration"], segment["action"]), set()).add(_key(segment))
            self.collected.clear()

    # --- a narrowed run would drop every action it didn't reach

    def pytest_deselected(self, items) -> None:
        self.deselected = True

    def pytest_runtest_logreport(self, report) -> None:
        # Only a test's call: setup alone (--setup-only, a skip at setup) sends nothing.
        if report.when == "call":
            self.ran = True

    def pytest_collection_finish(self, session) -> None:
        if not self.deselected:
            return
        if hasattr(session.config, "workeroutput"):
            # A worker's UsageError would crash it; the controller refuses at the session's end instead.
            session.config.workeroutput[_DESELECTED_KEY] = True
            return
        raise pytest.UsageError(_DESELECTED.format(mode=self.mode))

    # --- xdist: each worker hands its segments to the controller

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodedown(self, node, error) -> None:
        output = getattr(node, "workeroutput", {})
        self.deselected |= output.get(_DESELECTED_KEY, False)
        self.native.update(tuple(key.split("|")) for key in output.get(_NATIVE_KEY, []))
        for key, segments in output.get(_WORKER_KEY, {}).items():
            self.segments.setdefault(tuple(key.split("|")), set()).update(segments)

    # --- the session's end

    def pytest_sessionfinish(self, session, exitstatus) -> None:
        if hasattr(session.config, "workeroutput"):
            session.config.workeroutput[_WORKER_KEY] = {"|".join(k): sorted(v) for k, v in self.segments.items()}
            session.config.workeroutput[_NATIVE_KEY] = sorted("|".join(k) for k in self.native)
            return
        if self.deselected:
            self.problems.append(_DESELECTED.format(mode=self.mode))
            session.exitstatus = pytest.ExitCode.USAGE_ERROR
            return
        if not self.ran:
            # Every golden file would be extra: a write would remove them all.
            self.problems.append(f"transcripts not {_DONE[self.mode]}: no test ran")
            session.exitstatus = pytest.ExitCode.USAGE_ERROR
            return
        if exitstatus != pytest.ExitCode.OK:
            self.problems.append(f"transcripts not {_DONE[self.mode]}: the run failed")
            return
        if unnormalized := self._unnormalized():
            self.problems += [
                f"transcripts not {_DONE[self.mode]}: values with no normalization (tests/transcripts.py, norm):",
                *unnormalized,
            ]
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
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
        if problems := self._groupless():
            self.problems += problems
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def _groupless(self) -> list[str]:
        """A native-groups action needs a segment whose target is a group: a group's sign-off binds to it, and without
        it a change to what the action does on a group reopens no evidence (docs/evidence.md, Release gate)."""
        owned = {path.name for path in self.integrations.glob("*/") if path.is_dir()}
        grouped = {
            key for key, segments in self.segments.items() if any(_has_group(json.loads(text)) for text in segments)
        }
        if not (missing := sorted({key for key in self.native if key[0] in owned} - grouped)):
            return []
        return [
            "native-groups actions with no group segment: test each on one of its integration's groups",
            *(f"  {integration} / {action}" for integration, action in missing),
        ]

    def _unnormalized(self) -> list[str]:
        """Each placeholder norm left in a segment's wire or result, as `<integration> <action> <TypeName>`. The
        request's `own` may hold one (its `send` function)."""
        found = set()
        for (integration, action), segments in self.segments.items():
            for text in segments:
                segment = json.loads(text)
                for value in (segment["wire"], segment["result"]):
                    found.update((integration, action, p) for p in _placeholders(value))
        return [" ".join(entry) for entry in sorted(found)]

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


def _has_group(segment: dict) -> bool:
    return any(is_group for _, _, is_group in segment["request"]["targets"])


def _placeholders(value: Any):
    """Each `"<TypeName>"` norm made inside `value`."""
    if isinstance(value, str):
        if _PLACEHOLDER.fullmatch(value):
            yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _placeholders(k)
            yield from _placeholders(_key_structure(k))
            yield from _placeholders(v)
    elif isinstance(value, list):
        for v in value:
            yield from _placeholders(v)


def _key_structure(key: str) -> Any:
    """The list or dict a non-str key became JSON text of (`_json_key`), so its placeholders are seen, or None."""
    try:
        decoded = json.loads(key)
    except ValueError:
        return None
    return decoded if isinstance(decoded, list | dict) else None


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


def _narrowed(config: pytest.Config) -> str | None:
    """Why this run covers less than the whole suite, or None. A narrowed write would drop every action it didn't
    reach, and a narrowed check would report them missing. Deselection by any other means is caught at collection,
    and a run where no test ran at the session's end.

    Paths given, or a run from a subdirectory with none (`ArgsSource.INVOCATION_DIR`), must name the testpaths (the
    rootdir when there are none); only pytest's own expansion of the testpaths is taken as is."""
    option = config.option
    for flag, dest in _NARROWING:
        if getattr(option, dest, None):
            return f"it runs with {flag}"
    if config.args_source != pytest.Config.ArgsSource.TESTPATHS:
        given = {(config.invocation_params.dir / arg).resolve() for arg in config.args}
        default = {(config.rootpath / path).resolve() for path in config.getini("testpaths")}
        if given != (default or {config.rootpath.resolve()}):
            return f"it runs {' '.join(config.args)}, not the testpaths"
    return None


def pytest_configure(config: pytest.Config) -> None:
    if mode := config.getoption("--transcripts"):
        if reason := _narrowed(config):
            raise pytest.UsageError(f"--transcripts={mode} needs the whole suite: {reason}")
        recorder = Recorder(mode, config.rootpath / "tests" / "integrations")
        recorder.install()
        config.pluginmanager.register(recorder, "transcripts-recorder")


def pytest_unconfigure(config: pytest.Config) -> None:
    if recorder := config.pluginmanager.get_plugin("transcripts-recorder"):
        recorder.uninstall()
