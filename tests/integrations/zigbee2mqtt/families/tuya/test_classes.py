"""Zigbee2MQTT's Tuya family: the rules on a device's Zigbee strings, the catalog they read, and where its classes
are refused. The countdown plugs' classes and call are test_countdown.py's."""

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.integrations.zigbee2mqtt import INTEGRATION
from custom_components.deviceside.integrations.zigbee2mqtt.families import tuya
from custom_components.deviceside.zigbee import tuya as catalog

from ...conftest import DEVICES, commands, light
from ...test_classes import PLUG, TUYA, TUYA_MCU, interviewed
from .....conftest import allow_experimental, refusal
from .....conftest import call as call_service
from .....fixtures.zigbee2mqtt import IEEE, add_z2m_entity, z2m_entry


def test_the_zigbee_string_rules_read_the_catalog_s_patterns():
    """One home for Tuya's Zigbee strings, shared with ZHA: the family restates none."""
    read = {(rule.capability, name): pattern for rule in tuya.ZIGBEE_RULES for name, pattern in rule.conditions.items()}

    assert read["tuya_mcu", "zigbee_model"] is catalog.DATAPOINT_MODEL
    assert read["tuya_mcu", "zigbee_manufacturer"] is catalog.DATAPOINT_MANUFACTURER
    assert read["tuya_zcl", "zigbee_manufacturer"] is catalog.ZCL_MANUFACTURER
    assert read["tuya_zcl", "zigbee_model"] is catalog.ZCL_MODEL
    assert read["tuya_countdown_harmed", "zigbee_manufacturer"] == catalog.COUNTDOWN_HARMED_MANUFACTURER
    assert read["tuya_countdown_harmed", "zigbee_model"] == catalog.COUNTDOWN_HARMED_MODEL


@pytest.mark.parametrize(
    ("registry", "zigbee", "expected"),
    [
        (("Lidl", "HG06337"), (TUYA, "TS011F"), "tuya_ts011f"),
        (("Lidl", "HG06337"), (TUYA, "TS0001"), "tuya_zcl"),
        (("Lidl", "HG06337"), ("_TYZB01_abcdefgh", "HG06337"), "tuya_zcl"),
        (("Moes", "ZM-105"), (TUYA_MCU, "TS0601"), "tuya_mcu"),
        (("Moes", "ZM-105"), (TUYA_MCU, "ZM-105"), "tuya_mcu"),
        (("Moes", "ZM-105"), ("Moes", "TS0601"), "tuya_mcu"),
        (("Philips", "9290018217"), ("Signify Netherlands B.V.", "LWA012"), "hue"),
        (("Sengled", "E11-G13"), ("sengled", "E11-G13"), "sengled"),
        (("IKEA of Sweden", "LED1836G9"), ("IKEA of Sweden", "TRADFRI bulb E27 WW 806lm"), "other"),
        # Tuya's model is `TS` and four digits; another `TS` model under another vendor isn't Tuya's.
        (("Lidl", "HG06337"), ("Lidl", "TSV-1"), "other"),
        (("Lidl", "HG06337"), ("Lidl", "TS011"), "other"),
    ],
)
async def test_the_zigbee_strings_in_bridge_devices_place_a_rebadged_tuya_device(
    hass, setup_production, broker, registry, zigbee, expected
):
    entity_id = light(hass, broker, manufacturer=registry[0], model_id=registry[1], zigbee=zigbee)

    assert INTEGRATION.capability(hass, resolve(hass, get_runtime(hass).registry, entity_id)) == expected


async def test_turn_on_for_refuses_a_ts011f_as_not_supported_with_experimental_on(hass, setup_production, broker):
    """Z2M has no on_time converter for it, so today's call would turn the plug on with no timer
    (research/2026-11-14-lab-probe.md, §2): refused, not flagged, so Experimental features can't send it."""
    allow_experimental(hass)
    add_z2m_entity(hass, z2m_entry(hass), "switch.plug", manufacturer=PLUG[0], model_id=PLUG[1])
    broker.retained[DEVICES] = [interviewed(IEEE, TUYA, "TS011F")]

    assert await refusal(hass, "turn_on_for", {"entity_id": "switch.plug", "duration": 5}) == "not_supported"
    assert commands(broker) == []


async def test_the_ts011f_s_refusal_says_what_the_user_sees(hass, setup_production, broker):
    allow_experimental(hass)
    add_z2m_entity(hass, z2m_entry(hass), "switch.plug", manufacturer=PLUG[0], model_id=PLUG[1])
    broker.retained[DEVICES] = [interviewed(IEEE, TUYA, "TS011F")]

    with pytest.raises(HomeAssistantError) as raised:
        await call_service(hass, "turn_on_for", {"entity_id": "switch.plug", "duration": 5})
    assert raised.value.translation_placeholders["why"] == tuya.TURN_ON_FOR_NOT_SUPPORTED["tuya_ts011f"].reason
    assert "no timer, so it would stay on" in raised.value.translation_placeholders["why"]


@pytest.mark.parametrize(
    "registry",
    [
        pytest.param(("Tuya", "TS0001_switch_module"), id="tuya_zcl"),
        pytest.param(("Tuya", "TS0601_switch"), id="tuya_mcu"),
    ],
)
async def test_turn_on_for_refuses_every_tuya_class_as_not_supported_with_experimental_on(
    hass, setup_production, broker, registry
):
    """Z2M turns `on_time` into a plain On on Tuya firmware (Decision 20), so the device would stay on."""
    allow_experimental(hass)
    entity_id = light(hass, broker, manufacturer=registry[0], model_id=registry[1])

    assert await refusal(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5}) == "not_supported"
    assert commands(broker) == []


@pytest.mark.parametrize(
    ("action", "data"),
    [
        pytest.param("get_attributes", {}, id="read"),
        pytest.param("set_attributes", {"brightness": 50}, id="write"),
    ],
)
async def test_a_datapoint_device_s_raw_zcl_read_and_write_are_not_supported(
    hass, setup_production, broker, action, data
):
    """Rather than send raw ZCL a datapoint device can't take."""
    allow_experimental(hass)
    entity_id = light(hass, broker, manufacturer="Tuya", model_id="TS0601_dimmer")

    assert await refusal(hass, action, {"entity_id": entity_id, **data}) == "not_supported"
    assert commands(broker) == []
