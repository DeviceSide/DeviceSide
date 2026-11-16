"""ZHA's device classes: capability's answers from zigpy's raw Zigbee strings and the On/Off cluster's quirk, and the
string the report form gets. Each family's rules are tested in families/<family>/, their composition in
test_families.py, and the class of each listed device in test_classification.py."""

import pytest
from homeassistant.helpers import device_registry as dr

from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.integrations.zha import INTEGRATION, classes, zcl
from custom_components.deviceside.integrations.zha.families import tuya

from ...fixtures.zha import StandardOnOff, add_zha_entity, quirk_on_off, zha_entry

MCU_QUIRK = "zhaquirks.tuya.mcu"


@pytest.mark.parametrize(("manufacturer", "model"), [(None, "TS011F"), ("_TZ3000_typdpbpg", None), ("sengled", "")])
def test_a_device_whose_interview_did_not_read_a_string_has_no_class(manufacturer, model):
    """No rule can place it, whatever the other string says: None, never the default class."""
    assert classes.device_class(manufacturer, model, "zigpy.zcl") is None


async def test_capability_reads_zigpys_strings_not_the_registry(hass, setup_production):
    """A v2 quirk's friendly name replaces the registry's strings, so the class comes from zigpy's."""
    add_zha_entity(
        hass,
        zha_entry(hass),
        "switch.plug",
        ieee="00:00:00:00:00:00:00:01",
        unique_id="00:00:00:00:00:00:00:01-1",
        strings=("_TZ3000_typdpbpg", "TS011F"),
    )
    registry = get_runtime(hass).registry
    target = resolve(hass, registry, "switch.plug")
    dr.async_get(hass).async_update_device(target.device.id, manufacturer="Friendly", model="Smart plug")
    target = resolve(hass, registry, "switch.plug")

    assert INTEGRATION.capability(hass, target) == tuya.TUYA_COUNTDOWN


async def test_capability_reads_the_quirk_on_the_targets_endpoint(hass, setup_production):
    add_zha_entity(
        hass,
        zha_entry(hass),
        "switch.valve",
        ieee="00:00:00:00:00:00:00:02",
        unique_id="00:00:00:00:00:00:00:02-1",
        strings=("_TZ3210_0jxeoadc", "TS0049"),
        on_off=quirk_on_off(MCU_QUIRK),
    )
    target = resolve(hass, get_runtime(hass).registry, "switch.valve")

    assert INTEGRATION.capability(hass, target) == tuya.TUYA_MCU


async def test_a_device_the_gateway_doesnt_hold_has_no_class(hass, setup_production, monkeypatch):
    add_zha_entity(hass, zha_entry(hass), "light.bulb")
    monkeypatch.setattr(zcl, "zigpy_device", lambda hass, ieee: None)

    assert INTEGRATION.capability(hass, resolve(hass, get_runtime(hass).registry, "light.bulb")) is None


@pytest.mark.parametrize(
    ("on_off", "expected"),
    [
        # A Tuya ZCL quirk's cluster that defines no command of its own inherits zigpy's.
        (type("TuyaZBOnOff", (StandardOnOff,), {"__module__": "zhaquirks.tuya"}), tuya.TUYA_COUNTDOWN),
        # A cluster elsewhere that inherits a Tuya datapoint quirk's command routes as it does.
        (type("Custom", (quirk_on_off("zhaquirks.tuya.mcu"),), {"__module__": "custom_quirks"}), tuya.TUYA_MCU),
    ],
)
async def test_the_quirk_is_the_module_that_defines_command(hass, setup_production, on_off, expected):
    ieee = "00:00:00:00:00:00:00:03"
    add_zha_entity(
        hass,
        zha_entry(hass),
        "switch.plug",
        ieee=ieee,
        unique_id=f"{ieee}-1",
        strings=("_TZ3000_x", "TS0001"),
        on_off=on_off,
    )

    assert INTEGRATION.capability(hass, resolve(hass, get_runtime(hass).registry, "switch.plug")) == expected


def _device(hass, entity_id: str) -> dr.DeviceEntry:
    registry = dr.async_get(hass)
    return registry.async_get(resolve(hass, get_runtime(hass).registry, entity_id).entry.device_id)


async def test_the_report_form_gets_zigpy_s_manufacturer_string_not_the_registry_s(hass, setup_production):
    """A v2 quirk's friendly name replaces the registry's strings; zigpy keeps the device's own (classes.py)."""
    entity_id = add_zha_entity(hass, zha_entry(hass), "switch.plug", strings=("_TZ3000_abcdefgh", "TS011F"))
    device = _device(hass, entity_id)
    dr.async_get(hass).async_update_device(device.id, manufacturer="Tuya")

    assert INTEGRATION.zigbee_manufacturer(hass, _device(hass, entity_id)) == "_TZ3000_abcdefgh"


async def test_a_device_the_gateway_does_not_hold_has_no_manufacturer_string(hass, setup_production, monkeypatch):
    entity_id = add_zha_entity(hass, zha_entry(hass), "light.lamp")
    monkeypatch.setattr(zcl, "zigpy_device", lambda hass, ieee: None)

    assert INTEGRATION.zigbee_manufacturer(hass, _device(hass, entity_id)) is None


@pytest.mark.parametrize("unread", [None, ""])
async def test_a_string_the_interview_did_not_read_is_no_manufacturer_string(hass, setup_production, unread):
    entity_id = add_zha_entity(hass, zha_entry(hass), "light.lamp", strings=(unread, "TS011F"))

    assert INTEGRATION.zigbee_manufacturer(hass, _device(hass, entity_id)) is None


def test_a_device_zha_did_not_register_has_no_manufacturer_string(hass):
    config = zha_entry(hass)
    device = dr.async_get(hass).async_get_or_create(config_entry_id=config.entry_id, identifiers={("mqtt", "x")})

    assert INTEGRATION.zigbee_manufacturer(hass, device) is None
