"""Zigbee2MQTT's Tuya family: its two rule groups, each alone, the catalog they read, its levels, and the actions it
leaves a class out of. The countdown plugs' classes and call are test_countdown.py's; the order between its groups and
the other families' is the integration's (test_classification.py), as are turn_on_for's refusals (test_refusals.py)."""

import re

import pytest

from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.rules import match
from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.zigbee2mqtt import INTEGRATION
from custom_components.deviceside.integrations.zigbee2mqtt.families import tuya
from custom_components.deviceside.zigbee import tuya as catalog

from ...conftest import TUYA, TUYA_MCU, commands, light
from .....conftest import allow_experimental, refusal


def test_the_zigbee_string_rules_read_the_catalog_s_strings():
    """One home for Tuya's Zigbee strings, shared with ZHA: the family restates none. A pattern is the catalog's own
    object; a literal string is the catalog's, escaped."""
    read = {(rule.capability, name): pattern for rule in tuya.ZIGBEE_RULES for name, pattern in rule.conditions.items()}

    assert read["tuya_mcu", "zigbee_manufacturer"] is catalog.DATAPOINT_MANUFACTURER_PATTERN
    assert read["tuya_zcl", "zigbee_manufacturer"] is catalog.ZCL_MANUFACTURER_PATTERN
    assert read["tuya_zcl", "zigbee_model"] is catalog.ZCL_MODEL_PATTERN
    assert read["tuya_mcu", "zigbee_model"] == re.escape(catalog.DATAPOINT_MODEL)
    assert read["tuya_ts011f", "zigbee_model"] == re.escape(catalog.TS011F_MODEL)
    assert read["tuya_countdown", "zigbee_model"] == re.escape(catalog.TS011F_MODEL)
    assert read["tuya_countdown_harmed", "zigbee_manufacturer"] == re.escape(catalog.COUNTDOWN_HARMED_MANUFACTURER)
    assert read["tuya_countdown_harmed", "zigbee_model"] == re.escape(catalog.COUNTDOWN_HARMED_MODEL)


@pytest.mark.parametrize(
    ("manufacturer", "model", "expected"),
    [
        (TUYA, "TS011F", "tuya_ts011f"),
        (TUYA, "TS0001", "tuya_zcl"),
        ("_TYZB01_abcdefgh", "HG06337", "tuya_zcl"),
        (TUYA_MCU, "TS0601", "tuya_mcu"),
        (TUYA_MCU, "ZM-105", "tuya_mcu"),
        ("Moes", "TS0601", "tuya_mcu"),
        ("Moes", "TS011F", "tuya_ts011f"),  # the model alone, whatever the manufacturer
        ("Moes", "ZM-105", None),
    ],
)
def test_the_zigbee_string_rules(manufacturer, model, expected):
    assert match(tuya.ZIGBEE_RULES, {"zigbee_manufacturer": manufacturer, "zigbee_model": model}) == expected


@pytest.mark.parametrize(
    ("manufacturer", "model_id", "expected"),
    [
        ("Tuya", "TS011F_plug_1", "tuya_ts011f"),
        ("Tuya", "TS011F", "tuya_ts011f"),
        ("Tuya", "TS0601_switch", "tuya_mcu"),
        ("Tuya", "TS0001_switch_module", "tuya_zcl"),
        ("Tuya", "ZG-101Z", "tuya_zcl"),  # Tuya's own vendor string
        ("Moes", "TS0002", "tuya_zcl"),  # a Tuya definition model under another vendor
        ("Lidl", "HG06337", None),  # a rebadged Tuya plug the registry can't show: bridge/devices does
        ("Tuya", None, "tuya_zcl"),
    ],
)
def test_the_registry_rules(manufacturer, model_id, expected):
    assert match(tuya.REGISTRY_RULES, {"manufacturer": manufacturer, "model_id": model_id}) == expected


async def test_the_zigbee_strings_in_bridge_devices_place_a_rebadged_tuya_device(hass, setup_production, broker):
    entity_id = light(hass, broker, manufacturer="Lidl", model_id="HG06337", zigbee=(TUYA, "TS011F"))

    assert INTEGRATION.capability(hass, resolve(hass, get_runtime(hass).registry, entity_id)) == "tuya_ts011f"


def test_tuya_s_classes_are_untested_on_every_action_but_turn_on_for():
    """turn_on_for's levels, on Tuya's countdown, are test_countdown.py's."""
    levels = {
        level
        for action, scope in tuya.FAMILY.scopes.items()
        if action != "turn_on_for"
        for level in scope.capabilities.values()
    }

    assert levels == {Level.EXPERIMENTAL}


def test_a_datapoint_device_is_left_out_of_raw_zcl_reads_and_writes():
    left_out = {action for action, scope in tuya.FAMILY.scopes.items() if "tuya_mcu" not in scope.capabilities}

    assert left_out == {"get_attributes", "set_attributes", "turn_on_for"}


@pytest.mark.parametrize(
    ("action", "data"),
    [
        pytest.param("get_attributes", {}, id="read"),
        pytest.param("set_attributes", {"brightness": 50}, id="write"),
    ],
)
async def test_a_datapoint_device_s_raw_zcl_read_and_write_are_not_built(hass, setup_production, broker, action, data):
    """Rather than send raw ZCL a datapoint device can't take."""
    allow_experimental(hass)
    entity_id = light(hass, broker, manufacturer="Tuya", model_id="TS0601_dimmer")

    assert await refusal(hass, action, {"entity_id": entity_id, **data}) == "not_built"
    assert commands(broker) == []
