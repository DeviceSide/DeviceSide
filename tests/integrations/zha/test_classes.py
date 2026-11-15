"""ZHA's device classes: the rules on zigpy's raw Zigbee strings and the On/Off cluster's quirk, and capability's
answers."""

import pytest
from homeassistant.helpers import device_registry as dr

from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.integrations.zha import INTEGRATION, classes, zcl

from ...fixtures.zha import StandardOnOff, add_zha_entity, quirk_on_off, zha_entry

MCU_QUIRK = "zhaquirks.tuya.mcu"


@pytest.mark.parametrize(
    ("manufacturer", "model", "quirk", "expected"),
    [
        # The lab's strings (research/2026-11-14-lab-probe.md, §1); the TS011F's quirk keeps zigpy's command.
        ("Signify Netherlands B.V.", "LTA009", "zigpy.zcl", classes.HUE),
        ("_TZ3000_typdpbpg", "TS011F", "zigpy.zcl", classes.TUYA_COUNTDOWN),
        # The string reported harmed on the recipe's frame, banned on that model only (plan Decision 35).
        ("_TZ3000_gjnozsaz", "TS011F", "zigpy.zcl", classes.TUYA_COUNTDOWN_HARMED),
        ("_TZ3000_gjnozsaz", "TS0001", None, classes.TUYA_COUNTDOWN),
        # Reported on other calls, so not banned.
        ("_TZ3000_dg7fdg92", "TS011F", None, classes.TUYA_COUNTDOWN),
        ("_TZ3000_okaz9tjs", "TS011F", None, classes.TUYA_COUNTDOWN),
        ("sengled", "E11-G13", "zigpy.zcl", classes.SENGLED),
        # Older Hue bulbs' string.
        ("Philips", "LCT001", None, classes.HUE),
        # The countdown models go before Tuya's other ZCL strings, which hold its bulbs and white labels.
        ("_TZ3000_abcdefgh", "TS0001", None, classes.TUYA_COUNTDOWN),
        ("Lidl", "TS0004", None, classes.TUYA_COUNTDOWN),
        ("_TZ3000_abcdefgh", "TS0011", None, classes.TUYA_COUNTDOWN),
        ("_TZ3000_abcdefgh", "TS0726", None, classes.TUYA_COUNTDOWN),
        ("_TZ3210_abcdefgh", "TS0505B", None, classes.TUYA_ZCL),
        ("_TZ3000_abcdefgh", "TS0121", None, classes.TUYA_ZCL),
        ("_TYZB01_abcdefgh", "Plug", None, classes.TUYA_ZCL),
        ("Lidl", "TS0505B", None, classes.TUYA_ZCL),
        # The datapoint rules go first: a TS0601's model would match tuya_zcl's, and a `_TZ3210_…` datapoint device's
        # manufacturer too, which only its quirk shows.
        ("_TZE200_abcdefgh", "TS0601", None, classes.TUYA_MCU),
        ("_TZE204_abcdefgh", "Something", None, classes.TUYA_MCU),
        ("_TZ3000_uim07oem", "TS0601", MCU_QUIRK, classes.TUYA_MCU),
        ("_TZ3210_0jxeoadc", "TS0049", MCU_QUIRK, classes.TUYA_MCU),
        ("_TZ3000_abcdefgh", "TS0001", "zhaquirks.tuya", classes.TUYA_MCU),
        # A quirk elsewhere that defines its own command isn't Tuya's routing.
        ("_TZ3000_abcdefgh", "TS0001", "zhaquirks.tuyaish", classes.TUYA_COUNTDOWN),
        ("SONOFF", "SWV", "zigpy.zcl", classes.SONOFF_SWV),
        # Every Tuya rule goes before Sengled's, so a Tuya device under Sengled's name keeps its Tuya class.
        ("Sengled", "TS0601", None, classes.TUYA_MCU),
        ("SENGLED", "E1F-N5E", None, classes.SENGLED),
        # Another vendor's devices, or a Tuya string no rule reads: the default class.
        ("IKEA of Sweden", "TRADFRI bulb E27 WS opal 980lm", "zigpy.zcl", classes.OTHER),
        ("SONOFF", "ZBMINIR2", "zigpy.zcl", classes.OTHER),
        ("_TYST11_abcdefgh", "abcdefgh", None, classes.OTHER),
        # What the interview didn't read places nothing.
        (None, "TS011F", None, None),
        ("_TZ3000_typdpbpg", None, None, None),
        ("Signify Netherlands B.V.", "", None, None),
    ],
)
def test_device_class(manufacturer, model, quirk, expected):
    assert classes.device_class(manufacturer, model, quirk) == expected


def test_every_rule_names_a_class_but_the_default():
    assert {cls for cls, _field, _pattern in classes.RULES} == classes.CLASSES - {classes.OTHER}


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

    assert INTEGRATION.capability(hass, target) == classes.TUYA_COUNTDOWN


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

    assert INTEGRATION.capability(hass, target) == classes.TUYA_MCU


async def test_a_device_the_gateway_doesnt_hold_has_no_class(hass, setup_production, monkeypatch):
    add_zha_entity(hass, zha_entry(hass), "light.bulb")
    monkeypatch.setattr(zcl, "zigpy_device", lambda hass, ieee: None)

    assert INTEGRATION.capability(hass, resolve(hass, get_runtime(hass).registry, "light.bulb")) is None


@pytest.mark.parametrize(
    ("on_off", "expected"),
    [
        # A Tuya ZCL quirk's cluster that defines no command of its own inherits zigpy's.
        (type("TuyaZBOnOff", (StandardOnOff,), {"__module__": "zhaquirks.tuya"}), classes.TUYA_COUNTDOWN),
        # A cluster elsewhere that inherits a Tuya datapoint quirk's command routes as it does.
        (type("Custom", (quirk_on_off("zhaquirks.tuya.mcu"),), {"__module__": "custom_quirks"}), classes.TUYA_MCU),
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


def test_a_device_zha_did_not_register_has_no_manufacturer_string(hass):
    config = zha_entry(hass)
    device = dr.async_get(hass).async_get_or_create(config_entry_id=config.entry_id, identifiers={("mqtt", "x")})

    assert INTEGRATION.zigbee_manufacturer(hass, device) is None
