"""core.ha_entity: HA's live entity objects, and a guarded write to a private attribute an integration keeps."""

import logging
from types import SimpleNamespace

from homeassistant.helpers.entity_component import DATA_INSTANCES

from custom_components.device_side.core import ha_entity as module
from custom_components.device_side.core.ha_entity import ha_entity, replace_if_set


def test_a_set_attribute_is_replaced():
    light = SimpleNamespace(_last_brightness=100.0)
    replace_if_set(light, "_last_brightness", 40.0)
    assert light._last_brightness == 40.0


def test_an_unset_attribute_is_left_alone():
    """A light that wasn't soft-offed keeps HA's plain on."""
    light = SimpleNamespace(_last_brightness=None)
    replace_if_set(light, "_last_brightness", 40.0)
    assert light._last_brightness is None


def test_no_entity_is_a_no_op():
    replace_if_set(None, "_last_brightness", 40.0)


def test_a_missing_attribute_warns_once_and_never_raises(caplog, monkeypatch):
    monkeypatch.setattr(module, "_missing", set())
    renamed = SimpleNamespace()
    with caplog.at_level(logging.WARNING, logger=module.__name__):
        replace_if_set(renamed, "_last_brightness", 40.0)
        replace_if_set(renamed, "_last_brightness", 40.0)
    assert not hasattr(renamed, "_last_brightness")
    assert [(record.levelno, record.message) for record in caplog.records] == [
        (
            logging.WARNING,
            "SimpleNamespace has no _last_brightness, so Home Assistant's own behavior stays: a plain turn_on after "
            "set_attributes while the light is off may come on at the old level",
        )
    ]


async def test_ha_entity_finds_the_loaded_entity(hass, monkeypatch):
    lamp = object()
    component = SimpleNamespace(get_entity=lambda entity_id: lamp if entity_id == "light.lamp" else None)
    monkeypatch.setitem(hass.data, DATA_INSTANCES, {"light": component})
    assert ha_entity(hass, "light.lamp") is lamp
    assert ha_entity(hass, "light.other") is None
    assert ha_entity(hass, "switch.plug") is None  # no switch component loaded
