"""The Hue bridge: a v1 bridge refused by every adapter, and the debug line of each write, which names the entity, never
the bridge's resource id."""

import logging
from types import SimpleNamespace

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.deviceside.integrations.hue import bridge as hue_bridge

from ...conftest import refusal, sent
from ...fixtures.hue import add_hue_entity, hue_entry

LIGHTS = SimpleNamespace(item_type=SimpleNamespace(value="light"))


@pytest.mark.usefixtures("setup_production")
@pytest.mark.parametrize(
    ("action", "data"),
    [
        pytest.param("raise_brightness", {}, id="raise_brightness"),
        pytest.param("lower_brightness", {}, id="lower_brightness"),
        pytest.param("stop", {}, id="stop"),
        pytest.param("get_attributes", {}, id="get_attributes"),
        pytest.param("set_attributes", {"brightness": 40}, id="set_attributes"),
        pytest.param("set_scene", {}, id="set_scene"),
    ],
)
async def test_a_v1_bridge_is_refused(hass, bridge, action, data):
    """A row for each adapter's own bridge_v1 check (the fade's for both brightness moves)."""
    entity_id = "scene.relax" if action == "set_scene" else "light.lamp"
    if action == "set_scene":
        bridge.scene("scene-1", [])
    else:
        bridge.light("light-1")
    entry = await hue_entry(hass, bridge, api_version=1)
    add_hue_entity(hass, entry, entity_id, "scene-1" if action == "set_scene" else "light-1")

    assert await refusal(hass, action, {"entity_id": entity_id, **data}) == "bridge_v1"
    assert bridge.puts == []


async def test_with_debug_off_a_write_looks_nothing_up(hass, monkeypatch, caplog):
    """A write names its entity through the registry only while debug logging is on."""
    looked_up = []
    monkeypatch.setattr(er.EntityRegistry, "async_get_entity_id", lambda self, *args: looked_up.append(args))
    caplog.set_level(logging.INFO, logger=hue_bridge.__name__)

    hue_bridge.log_write(hass, LIGHTS, "light-1", "put", {})

    assert looked_up == []


async def test_a_write_to_the_callers_target_is_logged_under_it(hass, monkeypatch, wire):
    """A switch_as_x wrapper of a Hue light is logged under the wrapper the caller named, not the registry's light."""
    looked_up = []
    monkeypatch.setattr(er.EntityRegistry, "async_get_entity_id", lambda self, *args: looked_up.append(args))

    hue_bridge.log_write(hass, LIGHTS, "light-1", "put", {}, "switch.lamp")

    assert sent(wire) == ["switch.lamp: sending clip light.put {}"]
    assert looked_up == []


async def test_a_resource_is_named_by_its_light_entity_or_not_at_all(hass):
    er.async_get(hass).async_get_or_create("light", "hue", "light-1", suggested_object_id="desk")

    assert hue_bridge.entity_name(hass, "light-1") == "light.desk"
    assert hue_bridge.entity_name(hass, "light-2") == "a Hue light with no entity"
