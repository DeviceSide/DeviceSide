"""AdapterScope levels: each domain, capability and field carries one; a call's level is the weakest it touches.

The scopes of the real adapters are checked here too: the invariants the dispatcher's gate relies on.
"""

import ast
from pathlib import Path

import pytest

from custom_components.deviceside.core.adapter import Adapter
from custom_components.deviceside.core.registry import AdapterRegistry
from custom_components.deviceside.core.scope import (
    AdapterScope,
    Level,
    documented,
    experimental,
    reported,
    verified,
)

PACKAGE = Path(__file__).resolve().parents[2] / "custom_components" / "deviceside"
# What reads the Experimental features option: only the option's definition, the entry setup and the dispatcher may.
OPTION_NAMES = {"CONF_EXPERIMENTAL", "EXPERIMENTAL_DEFAULT", "experimental_features"}
OPTION_READERS = {"const.py", "__init__.py", "config_flow.py", "core/runtime.py", "core/dispatcher.py"}


def test_levels_order_weakest_first():
    assert Level.EXPERIMENTAL < Level.DOCUMENTED < Level.REPORTED < Level.VERIFIED


def test_helpers_merge_into_one_mapping():
    assert verified("a") | reported("b") | documented("c") | experimental("d") == {
        "a": Level.VERIFIED,
        "b": Level.REPORTED,
        "c": Level.DOCUMENTED,
        "d": Level.EXPERIMENTAL,
    }


def test_defaults_are_a_verified_light_with_every_capability():
    scope = AdapterScope()

    assert scope.domains == {"light": Level.VERIFIED}
    assert scope.level("light", "anything") is Level.VERIFIED


@pytest.mark.parametrize(
    ("domain", "capability", "level"),
    [
        ("switch", None, Level.VERIFIED),
        ("switch", "Switch", Level.VERIFIED),
        ("switch", "Light", Level.DOCUMENTED),  # the weaker capability lowers a Verified domain
        ("light", "Switch", Level.DOCUMENTED),  # and a Documented domain lowers a Verified capability
    ],
)
def test_level_is_the_weakest_item_touched(domain, capability, level):
    scope = AdapterScope(
        domains=verified("switch") | documented("light"), capabilities=verified("Switch") | documented("Light")
    )

    assert scope.level(domain, capability) is level


@pytest.mark.parametrize(
    ("fields", "level"),
    [
        ((), Level.VERIFIED),
        (("brightness",), Level.REPORTED),
        (("brightness", "transition"), Level.EXPERIMENTAL),
    ],
)
def test_level_folds_in_the_fields_the_call_carries(fields, level):
    scope = AdapterScope(fields=reported("brightness") | experimental("transition"))

    assert scope.level("light", None, fields) is level


def test_a_capability_outside_the_scope_counts_as_experimental():
    """supports() lets a call with nothing to do past whatever its capability; the gate must not raise on it."""
    scope = AdapterScope(capabilities=verified("RGBCCT"))

    assert scope.level("light", "Switch") is Level.EXPERIMENTAL


def test_a_documented_field_is_refused():
    with pytest.raises(ValueError, match="fields are never Documented"):
        AdapterScope(fields=documented("brightness"))


@pytest.mark.parametrize("helper", [verified, reported, experimental])
def test_a_field_may_be_verified_reported_or_experimental(helper):
    assert AdapterScope(fields=helper("brightness")).fields == helper("brightness")


def test_mappings_are_read_only_copies_and_the_scope_hashes():
    shared = verified("Switch")
    scope = AdapterScope(capabilities=shared)
    shared["Light"] = Level.VERIFIED

    assert "Light" not in scope.capabilities
    with pytest.raises(TypeError):
        scope.domains["switch"] = Level.VERIFIED
    assert hash(scope) == hash(scope)


def _adapters() -> list[Adapter]:
    return [adapter for _, _, adapter in AdapterRegistry.discover().matrix() if adapter is not None]


def test_only_the_dispatcher_and_entry_setup_read_the_experimental_option():
    """The dispatcher is the one gate: an adapter, action or other core module that read the option could change how
    a proven item behaves."""
    found = [
        f"{path.relative_to(PACKAGE)}:{node.lineno}"
        for path in PACKAGE.rglob("*.py")
        if path.relative_to(PACKAGE).as_posix() not in OPTION_READERS
        for node in ast.walk(ast.parse(path.read_text()))
        if (isinstance(node, ast.Name) and node.id in OPTION_NAMES)
        or (isinstance(node, ast.Attribute) and node.attr in OPTION_NAMES)
        or (isinstance(node, ast.alias) and node.name in OPTION_NAMES)
        or (isinstance(node, ast.Constant) and node.value == "experimental_features")
    ]
    assert found == []


def test_an_adapter_with_capabilities_names_the_one_a_call_reaches():
    """Without capability(), the gate would weigh only the domain and fields, and let an Experimental capability by."""
    missing = [
        f"{adapter.integration} / {adapter.action}"
        for adapter in _adapters()
        if adapter.scope.capabilities is not None and type(adapter).capability is Adapter.capability
    ]
    assert missing == []


def _covers(stop: AdapterScope | None, items: str, item: str, level: Level) -> bool:
    if stop is None:
        return False
    mapping = getattr(stop, items)
    if mapping is None:  # stop addresses every capability, as Verified
        return True
    return mapping.get(item, -1) >= level


def test_every_move_has_a_stop_at_least_as_strong():
    """A raise or lower that starts where stop is refused, or gated behind the option, can't be halted. Item levels
    only: group reach (native_groups against expand_group), refusals in supports() that don't come from scope, and the
    adapter-level flag (cut-release --release catches a released move with a flagged stop) are not compared."""
    adapters = _adapters()
    stops = {adapter.integration: adapter.scope for adapter in adapters if adapter.action == "stop"}
    gaps = []
    for adapter in adapters:
        if not adapter.action.startswith(("raise_", "lower_")):
            continue
        stop = stops.get(adapter.integration)
        name = f"{adapter.integration} / {adapter.action}"
        for domain, level in adapter.scope.domains.items():
            if not _covers(stop, "domains", domain, level):
                gaps.append(f"{name}: domain {domain} ({level.name})")
        if adapter.scope.capabilities is None:
            if stop is None or stop.capabilities is not None:
                gaps.append(f"{name}: every capability, which stop doesn't cover")
            continue
        for capability, level in adapter.scope.capabilities.items():
            if not _covers(stop, "capabilities", capability, level):
                gaps.append(f"{name}: capability {capability} ({level.name})")
    assert gaps == []
