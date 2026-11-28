"""Each row of the plan's class table, placed from fake python-kasa device objects: the class is the device's own, read
by name (never by importing kasa)."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.deviceside.core.models import Target
from custom_components.deviceside.integrations.tplink import INTEGRATION
from custom_components.deviceside.integrations.tplink.addressing import unsupported_reason

from ...fixtures.tplink import (
    IOT_ID,
    SMART_ID,
    DeviceType,
    add_tplink_entity,
    iot_device,
    smart_device,
    tplink_entry,
)

# Core's unique_ids (tplink/entity.py, tplink/light.py): a switch's is the legacy device id (an IOT plug's "<mac>_<id>"
# shortened to its id); a light's the mac without colons, unless it has a parent or children, or is an IOT dimmer.
MAC_ID = "AABBCCDDEEFF"


def _target(hass, entity_id: str) -> Target:
    entry = er.async_get(hass).async_get(entity_id)
    config_entry = hass.config_entries.async_get_entry(entry.config_entry_id)
    return Target(entity_id, entity_id.split(".")[0], "tplink", entry, None, config_entry, None)


def _place(hass, entity_id: str, unique_id: str, device, loaded: bool = True) -> Target:
    entry, _ = tplink_entry(hass, device, loaded)
    add_tplink_entity(hass, entry, entity_id, unique_id)
    return _target(hass, entity_id)


def _iot(device_type, parent=None):
    return iot_device(device_type, AsyncMock(), parent=parent)


def _smart(device_type, parent=None, device_id=SMART_ID):
    return smart_device(device_type, AsyncMock(), device_id=device_id, parent=parent)


@pytest.mark.parametrize("device_type", [DeviceType.Plug, DeviceType.WallSwitch])
def test_an_iot_plug_or_wall_switch_is_iot_plug(hass, device_type):
    target = _place(hass, "switch.plug", IOT_ID, _iot(device_type))
    assert INTEGRATION.capability(hass, target) == "iot_plug"
    assert unsupported_reason(target) is None


def test_an_iot_strip_outlet_is_its_own_class(hass):
    strip = _iot(DeviceType.Strip)
    outlet = _iot(DeviceType.StripSocket, parent=strip)
    outlet.device_id = f"{strip.mac}_{IOT_ID}01"
    entry, _ = tplink_entry(hass, strip)
    add_tplink_entity(hass, entry, "switch.outlet", f"{IOT_ID}01")
    assert INTEGRATION.capability(hass, _target(hass, "switch.outlet")) == "iot_strip_outlet"


@pytest.mark.parametrize("device_type", [DeviceType.Plug, DeviceType.WallSwitch])
def test_a_smart_plug_or_wall_switch_with_no_parent_is_smart_plug(hass, device_type):
    target = _place(hass, "switch.plug", SMART_ID, _smart(device_type))
    assert INTEGRATION.capability(hass, target) == "smart_plug"


@pytest.mark.parametrize(
    ("parent_type", "name"), [(DeviceType.Strip, "smart_strip_child"), (DeviceType.Hub, "smart_hub_child")]
)
def test_a_smart_child_is_the_class_of_its_parent(hass, parent_type, name):
    parent = _smart(parent_type)
    _smart(DeviceType.Plug, parent=parent, device_id="child0001")
    entry, _ = tplink_entry(hass, parent)
    add_tplink_entity(hass, entry, "switch.child", "child0001")
    assert INTEGRATION.capability(hass, _target(hass, "switch.child")) == name


@pytest.mark.parametrize("device_type", [DeviceType.Bulb, DeviceType.Dimmer, DeviceType.LightStrip])
def test_a_smart_light_is_smart_light(hass, device_type):
    target = _place(hass, "light.bulb", MAC_ID, _smart(device_type))
    assert INTEGRATION.capability(hass, target) == "smart_light"


def test_a_smart_dimmer_child_is_smart_light(hass):
    """A KS240's light is a child of the device, so its light entity's unique_id is the legacy device id."""
    parent = _smart(DeviceType.WallSwitch)
    _smart(DeviceType.Dimmer, parent=parent, device_id="child0002")
    entry, _ = tplink_entry(hass, parent)
    add_tplink_entity(hass, entry, "light.dimmer", "child0002")
    assert INTEGRATION.capability(hass, _target(hass, "light.dimmer")) == "smart_light"


@pytest.mark.parametrize("device_type", [DeviceType.Bulb, DeviceType.LightStrip])
def test_an_iot_bulb_or_light_strip_is_iot_light(hass, device_type):
    target = _place(hass, "light.bulb", MAC_ID, _iot(device_type))
    assert INTEGRATION.capability(hass, target) == "iot_light"


def test_an_iot_dimmer_is_iot_light_under_its_legacy_device_id(hass):
    target = _place(hass, "light.dimmer", IOT_ID, _iot(DeviceType.Dimmer))
    assert INTEGRATION.capability(hass, target) == "iot_light"


@pytest.mark.parametrize(
    ("entity_id", "unique_id", "device_type"),
    [
        ("switch.strip_parent", IOT_ID, DeviceType.Strip),  # a strip parent has no primary entity
        ("sensor.plug_power", f"{IOT_ID}_current_consumption", DeviceType.Plug),  # another entity of a plug
        ("switch.plug_led", f"{IOT_ID}_led", DeviceType.Plug),
    ],
)
def test_an_entity_that_is_no_devices_primary_one_cannot_be_addressed(hass, entity_id, unique_id, device_type):
    target = _place(hass, entity_id, unique_id, _iot(device_type))
    assert INTEGRATION.capability(hass, target) is None
    assert unsupported_reason(target) == "not_addressable"


@pytest.mark.parametrize("device_type", [DeviceType.Hub, DeviceType.Fan])
def test_a_device_of_another_type_cannot_be_addressed(hass, device_type):
    target = _place(hass, "switch.other", SMART_ID, _smart(device_type))
    assert INTEGRATION.capability(hass, target) is None
    assert unsupported_reason(target) == "not_addressable"


def test_a_device_not_yet_loaded_has_no_class_and_no_refusal_of_its_own(hass):
    target = _place(hass, "switch.plug", IOT_ID, _iot(DeviceType.Plug), loaded=False)
    assert INTEGRATION.capability(hass, target) is None
    assert unsupported_reason(target) is None
