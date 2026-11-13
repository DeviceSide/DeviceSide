"""The Hue debug line of each write: the entity it names, never the bridge's resource id."""

import logging
from types import SimpleNamespace

from homeassistant.helpers import entity_registry as er

from custom_components.deviceside.integrations.hue import bridge

from ...conftest import sent

LIGHTS = SimpleNamespace(item_type=SimpleNamespace(value="light"))


async def test_with_debug_off_a_write_looks_nothing_up(hass, monkeypatch, caplog):
    """A write names its entity through the registry only while debug logging is on."""
    looked_up = []
    monkeypatch.setattr(er.EntityRegistry, "async_get_entity_id", lambda self, *args: looked_up.append(args))
    caplog.set_level(logging.INFO, logger=bridge.__name__)

    bridge.log_write(hass, LIGHTS, "light-1", "put", {})

    assert looked_up == []


async def test_a_write_to_the_callers_target_is_logged_under_it(hass, monkeypatch, wire):
    """A switch_as_x wrapper of a Hue light is logged under the wrapper the caller named, not the registry's light."""
    looked_up = []
    monkeypatch.setattr(er.EntityRegistry, "async_get_entity_id", lambda self, *args: looked_up.append(args))

    bridge.log_write(hass, LIGHTS, "light-1", "put", {}, "switch.lamp")

    assert sent(wire) == ["switch.lamp: sending clip light.put {}"]
    assert looked_up == []


async def test_a_resource_is_named_by_its_light_entity_or_not_at_all(hass):
    er.async_get(hass).async_get_or_create("light", "hue", "light-1", suggested_object_id="desk")

    assert bridge.entity_name(hass, "light-1") == "light.desk"
    assert bridge.entity_name(hass, "light-2") == "a Hue light with no entity"
