"""Registry building: guarded integration import, adapter validation, matrix iteration."""

import importlib
import logging
from dataclasses import replace
from itertools import product
from types import SimpleNamespace

import pytest

from custom_components.deviceside import actions
from custom_components.deviceside.core.registry import AdapterRegistry
from custom_components.deviceside.core.scope import verified

from ..conftest import FAKE_INTEGRATIONS
from ..fakes.fake_integration import ADAPTERS, INTEGRATION, FakeTurnOnFor


def _registry(adapters=ADAPTERS, info=INTEGRATION) -> AdapterRegistry:
    """A registry of the fake integration alone, with these adapters and this info."""
    return AdapterRegistry(actions.discover(), [SimpleNamespace(INTEGRATION=info, ADAPTERS=adapters)])


def test_broken_integration_is_recorded_unavailable_and_others_load():
    registry = AdapterRegistry(actions.discover(), FAKE_INTEGRATIONS)

    broken = registry.integrations["broken_integration"]
    assert not broken.available
    assert "fakelib" in broken.unavailable_reason
    assert [info.key for info in registry.available_integrations()] == ["fake", "fake_special"]
    assert registry.adapter("turn_on_for", "fake").integration == "fake"


@pytest.mark.parametrize(
    ("missing", "level"),
    [("fakelib", logging.DEBUG), ("homeassistant.components.fake.gone", logging.WARNING), (None, logging.DEBUG)],
)
def test_import_failure_warns_only_when_our_code_is_out_of_step(monkeypatch, caplog, missing, level):
    def fail(module):
        raise ImportError(f"no {missing}", name=missing)

    discovered = actions.discover()
    monkeypatch.setattr(importlib, "import_module", fail)
    with caplog.at_level(logging.DEBUG, logger="custom_components.deviceside.core.registry"):
        registry = AdapterRegistry(discovered, ["custom_components.deviceside.integrations.fake"])

    assert not registry.integrations["fake"].available
    assert [record.levelno for record in caplog.records] == [level]


def test_matrix_lists_every_pair_sorted():
    discovered = actions.discover()
    registry = AdapterRegistry(discovered, FAKE_INTEGRATIONS)
    matrix = list(registry.matrix())

    keys = sorted(action.key for action in discovered)
    integrations = ["broken_integration", "fake", "fake_special"]
    assert [(action, integration) for action, integration, _ in matrix] == list(product(keys, integrations))
    assert [(action, integration) for action, integration, adapter in matrix if adapter is not None] == [
        ("set_attributes", "fake"),
        ("turn_off_for", "fake"),
        ("turn_on_for", "fake"),
        ("turn_on_for", "fake_special"),
    ]


def test_adapter_for_unknown_action_is_refused():
    class Stray(FakeTurnOnFor):
        action = "no_such_action"

    with pytest.raises(ValueError, match="unknown action"):
        _registry([Stray])


def test_an_adapter_naming_capabilities_must_list_them_in_its_scope():
    class Named(FakeTurnOnFor):
        def capability(self, hass, target):
            return "Switch"

    with pytest.raises(ValueError, match="names capabilities but its scope lists none"):
        _registry([Named])

    class Listed(Named):
        scope = replace(FakeTurnOnFor.scope, capabilities=verified("Switch"))

    _registry([Listed])


def test_an_adapter_listing_capabilities_must_name_them():
    class Unnamed(FakeTurnOnFor):
        scope = replace(FakeTurnOnFor.scope, capabilities=verified("Switch"))

    with pytest.raises(ValueError, match="lists capabilities in its scope but names none"):
        _registry([Unnamed])


@pytest.mark.parametrize(
    ("maintainers", "error"),
    [
        ((), "non-empty tuple"),
        (["jasonmx"], "non-empty tuple"),
        (("@jasonmx",), "not GitHub handles"),
        (("jason mx",), "not GitHub handles"),
        (("-jasonmx",), "not GitHub handles"),
        (("a" * 40,), "not GitHub handles"),
        (("jasonmx", "jasonmx"), "twice"),
    ],
)
def test_an_integration_must_name_its_maintainers_by_handle(maintainers, error):
    with pytest.raises(ValueError, match=error):
        _registry(info=replace(INTEGRATION, maintainers=maintainers))


def test_several_maintainers_are_accepted():
    registry = _registry(info=replace(INTEGRATION, maintainers=("jasonmx", "a-b", "a" * 39)))
    assert registry.integrations["fake"].maintainers == ("jasonmx", "a-b", "a" * 39)


def test_production_discovery_imports_cleanly():
    registry = AdapterRegistry.discover()
    assert set(registry.actions) == {
        "clear_auto_off",
        "clear_auto_on",
        "get_attributes",
        "lower_brightness",
        "lower_hue",
        "lower_saturation",
        "raise_brightness",
        "raise_hue",
        "raise_saturation",
        "set_attributes",
        "set_auto_off",
        "set_auto_on",
        "set_scene",
        "stop",
        "turn_off_for",
        "turn_on_for",
    }
    assert registry.integrations["shelly"].available
    assert registry.integrations["hue"].available
    assert registry.adapter("turn_on_for", "shelly") is not None
    assert registry.adapter("turn_off_for", "shelly") is not None
    assert all(info.maintainers for info in registry.available_integrations())


def test_each_adapter_takes_its_actions_kind_which_ends_its_warnings():
    registry = AdapterRegistry.discover()

    query, command = registry.adapter("get_attributes", "hue"), registry.adapter("stop", "hue")
    setting = registry.adapter("set_auto_off", "shelly")

    assert query.consequence == "so its attributes aren't reported"
    assert command.consequence == "so HA may show the old values"
    assert setting.consequence == "so the device may keep its old setting"


def test_call_resolvers_are_keyed_by_ha_domain():
    registry = AdapterRegistry.discover()

    assert set(registry.call_resolvers()) == {"hue", "zha", "mqtt"}


def test_two_call_resolvers_for_one_ha_domain_are_refused():
    registry = AdapterRegistry(actions.discover(), FAKE_INTEGRATIONS)
    for info in registry.available_integrations():
        registry.integrations[info.key] = replace(info, ha_domain="shared", call_resolver=object())

    with pytest.raises(ValueError, match="ha_domain shared"):
        registry.call_resolvers()


def test_an_import_that_raises_anything_marks_the_integration_unavailable_and_logs_it(monkeypatch, caplog):
    def fail(module):
        raise AttributeError("module 'homeassistant.components.fake' has no attribute 'gone'")

    discovered = actions.discover()
    monkeypatch.setattr(importlib, "import_module", fail)
    with caplog.at_level(logging.DEBUG, logger="custom_components.deviceside.core.registry"):
        registry = AdapterRegistry(discovered, ["custom_components.deviceside.integrations.fake"])

    info = registry.integrations["fake"]
    assert not info.available
    assert "AttributeError" in info.unavailable_reason
    assert [record.levelno for record in caplog.records] == [logging.WARNING]
    assert caplog.records[0].exc_info is not None
