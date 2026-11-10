"""Registry building: guarded integration import, adapter validation, matrix iteration."""

import importlib
import logging
from dataclasses import replace

import pytest

from custom_components.deviceside import actions
from custom_components.deviceside.core.registry import AdapterRegistry

from ..conftest import FAKE_INTEGRATIONS


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
    registry = AdapterRegistry(actions.discover(), FAKE_INTEGRATIONS)

    assert [(action, integration, adapter is not None) for action, integration, adapter in registry.matrix()] == [
        ("clear_auto_off", "broken_integration", False),
        ("clear_auto_off", "fake", False),
        ("clear_auto_off", "fake_special", False),
        ("clear_auto_on", "broken_integration", False),
        ("clear_auto_on", "fake", False),
        ("clear_auto_on", "fake_special", False),
        ("get_attributes", "broken_integration", False),
        ("get_attributes", "fake", False),
        ("get_attributes", "fake_special", False),
        ("lower_brightness", "broken_integration", False),
        ("lower_brightness", "fake", False),
        ("lower_brightness", "fake_special", False),
        ("lower_hue", "broken_integration", False),
        ("lower_hue", "fake", False),
        ("lower_hue", "fake_special", False),
        ("lower_saturation", "broken_integration", False),
        ("lower_saturation", "fake", False),
        ("lower_saturation", "fake_special", False),
        ("raise_brightness", "broken_integration", False),
        ("raise_brightness", "fake", False),
        ("raise_brightness", "fake_special", False),
        ("raise_hue", "broken_integration", False),
        ("raise_hue", "fake", False),
        ("raise_hue", "fake_special", False),
        ("raise_saturation", "broken_integration", False),
        ("raise_saturation", "fake", False),
        ("raise_saturation", "fake_special", False),
        ("set_attributes", "broken_integration", False),
        ("set_attributes", "fake", True),
        ("set_attributes", "fake_special", False),
        ("set_auto_off", "broken_integration", False),
        ("set_auto_off", "fake", False),
        ("set_auto_off", "fake_special", False),
        ("set_auto_on", "broken_integration", False),
        ("set_auto_on", "fake", False),
        ("set_auto_on", "fake_special", False),
        ("set_scene", "broken_integration", False),
        ("set_scene", "fake", False),
        ("set_scene", "fake_special", False),
        ("stop", "broken_integration", False),
        ("stop", "fake", False),
        ("stop", "fake_special", False),
        ("turn_off_for", "broken_integration", False),
        ("turn_off_for", "fake", True),
        ("turn_off_for", "fake_special", False),
        ("turn_on_for", "broken_integration", False),
        ("turn_on_for", "fake", True),
        ("turn_on_for", "fake_special", True),
    ]


def test_adapter_for_unknown_action_is_refused():
    from types import SimpleNamespace

    from ..fakes.fake_integration import INTEGRATION, FakeTurnOnFor

    class Stray(FakeTurnOnFor):
        action = "no_such_action"

    with pytest.raises(ValueError, match="unknown action"):
        AdapterRegistry(actions.discover(), [SimpleNamespace(INTEGRATION=INTEGRATION, ADAPTERS=[Stray])])


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


def test_call_resolvers_are_keyed_by_ha_domain():
    registry = AdapterRegistry.discover()

    assert set(registry.call_resolvers()) == {"hue", "zha", "mqtt"}


def test_two_call_resolvers_for_one_ha_domain_are_refused():
    registry = AdapterRegistry(actions.discover(), FAKE_INTEGRATIONS)
    for info in registry.available_integrations():
        registry.integrations[info.key] = replace(info, ha_domain="shared", call_resolver=object())

    with pytest.raises(ValueError, match="ha_domain shared"):
        registry.call_resolvers()
