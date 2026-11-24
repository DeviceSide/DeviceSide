"""Zigbee2MQTT's Tuya family: its two rule groups, each alone, the catalog they read, the datapoint countdown's
definitions, and the raw ZCL calls it leaves a datapoint device out of. The countdown plugs' classes and call are
test_countdown.py's; the order between its groups and the other families' is the integration's
(test_classification.py), as are turn_on_for's refusals (test_refusals.py)."""

import re

import pytest

from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.rules import match
from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.core.scope import Unplaced
from custom_components.deviceside.integrations.zigbee2mqtt import INTEGRATION
from custom_components.deviceside.integrations.zigbee2mqtt.families import tuya
from custom_components.deviceside.integrations.zigbee2mqtt.families.tuya import datapoint
from custom_components.deviceside.zigbee import tuya as catalog

from ...conftest import DEVICES, TUYA, TUYA_MCU, commands, light
from .....conftest import allow_labs, refusal


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


# Every definition on Tuya's datapoint countdown, and its class, by its expose's value_max
# (research/2026-11-24-tuya-datapoint-call.md, §3).
DATAPOINT_DEFINITIONS = {
    "ZDMS16-1": "tuya_datapoint",
    "ZOT60": "tuya_datapoint",
    "FK_V02": "tuya_datapoint",
    "GL-SPI-206P": "tuya_datapoint",
    "SFD02-Z": "tuya_datapoint",
    "SFD02-Z_2": "tuya_datapoint",
    "QADZ1LR": "tuya_datapoint",
    "TS0601_dimmer_1_gang_1": "tuya_datapoint",
    "TS0601_dimmer_1_gang_2": "tuya_datapoint",
    "TS0601_dimmer_5": "tuya_datapoint",
    "MG-ZG01W": "tuya_datapoint",
    "_TZE28C1000000_jlbsptkl": "tuya_datapoint",
    "ZMS-206US-1": "tuya_datapoint",
    "TO-DM-W/B": "tuya_datapoint_24h",
    "TS0601_multifunction_switch": "tuya_datapoint_24h",
    "D1Z": "tuya_datapoint_24h",
    "D5Z": "tuya_datapoint_24h",
    "ZBS16": "tuya_datapoint_2h",
}
COUNTDOWN = frozenset({"state", "countdown"})


def datapoint_fields(definition: str, exposes=COUNTDOWN) -> dict:
    return {
        "zigbee_manufacturer": TUYA_MCU,
        "zigbee_model": "TS0601",
        "definition_model": definition,
        "exposes": exposes,
    }


def test_each_datapoint_class_s_limit_is_its_definitions_value_max():
    assert datapoint.CLASS_MAX_S == {"tuya_datapoint": 43200, "tuya_datapoint_24h": 86400, "tuya_datapoint_2h": 7210}
    assert {model: datapoint.CLASS_MAX_S[name] for model, name in DATAPOINT_DEFINITIONS.items()} == dict(
        datapoint.DATAPOINT_DEFINITIONS
    )


@pytest.mark.parametrize(("definition", "expected"), DATAPOINT_DEFINITIONS.items())
def test_each_datapoint_definition_with_the_device_s_countdown_takes_its_limit_s_class(definition, expected):
    assert match(tuya.ZIGBEE_RULES, datapoint_fields(definition)) == expected


@pytest.mark.parametrize(
    ("definition", "exposes"),
    [
        # An admitted definition whose countdown isn't the device's: per endpoint, or none.
        pytest.param("TS0601_dimmer_1_gang_1", frozenset({"state"}), id="no_device_countdown"),
        # Definitions research leaves out, or doesn't name.
        pytest.param("ZBN-DJ-63", COUNTDOWN, id="left_out"),
        pytest.param("TS0601_dimmer_2", COUNTDOWN, id="multi_gang"),
        pytest.param("TS0601_dimmer_9", COUNTDOWN, id="not_named"),
        # Each model matches whole: escaped, and no prefix or longer name of one.
        pytest.param("ZDMS16-1x", COUNTDOWN, id="longer"),
        pytest.param("ZDMS16", COUNTDOWN, id="prefix"),
        pytest.param("TO-DM-WxB", COUNTDOWN, id="escaped"),
    ],
)
def test_any_other_datapoint_device_stays_tuya_mcu(definition, exposes):
    assert match(tuya.ZIGBEE_RULES, datapoint_fields(definition, exposes)) == "tuya_mcu"


def datapoint_light(hass, broker, definition: str, exposes: list) -> str:
    """A Tuya datapoint dimmer Z2M registers under its definition, and lists in bridge/devices with it."""
    entity_id = light(hass, broker, manufacturer="Tuya", model_id=definition, zigbee=(TUYA_MCU, "TS0601"))
    broker.retained[DEVICES][-1]["definition"] = {"model": definition, "exposes": exposes}
    return entity_id


STATE = {"type": "light", "features": [{"name": "state", "property": "state"}]}


def countdown(endpoint: str | None = None) -> dict:
    """ZHC's countdown expose; withEndpoint keeps the name and suffixes the property."""
    if endpoint is None:
        return {"type": "numeric", "name": "countdown", "property": "countdown", "unit": "s"}
    return {"type": "numeric", "name": "countdown", "property": f"countdown_{endpoint}", "endpoint": endpoint}


async def test_bridge_devices_places_a_datapoint_device_by_its_definition(hass, setup_production, broker):
    entity_id = datapoint_light(hass, broker, "TS0601_dimmer_1_gang_1", [STATE, countdown()])

    assert INTEGRATION.capability(hass, resolve(hass, get_runtime(hass).registry, entity_id)) == "tuya_datapoint"


async def test_a_multi_gang_datapoint_device_stays_tuya_mcu(hass, setup_production, broker):
    """Its countdowns are per endpoint, so the definition exposes none for the device."""
    entity_id = datapoint_light(hass, broker, "ZMS-206EU-2", [STATE, countdown("l1"), countdown("l2")])

    assert INTEGRATION.capability(hass, resolve(hass, get_runtime(hass).registry, entity_id)) == "tuya_mcu"


async def test_an_admitted_definition_whose_countdown_is_per_endpoint_stays_tuya_mcu(hass, setup_production, broker):
    """The expose guard on the real path: rules.definition_fields drops a per-endpoint copy, so an allowlisted
    definition exposing only `countdown_l1` has no countdown for the device."""
    entity_id = datapoint_light(hass, broker, "TS0601_dimmer_1_gang_1", [STATE, countdown("l1")])

    assert INTEGRATION.capability(hass, resolve(hass, get_runtime(hass).registry, entity_id)) == "tuya_mcu"


async def test_until_bridge_devices_lists_it_a_datapoint_device_waits(hass, setup_production, broker):
    """The registry can't show its exposes, so it stays an Unplaced tuya_mcu until bridge/devices lists it."""
    entity_id = datapoint_light(hass, broker, "TS0601_dimmer_1_gang_1", [STATE, countdown()])
    del broker.retained[DEVICES]

    assert INTEGRATION.capability(hass, resolve(hass, get_runtime(hass).registry, entity_id)) == Unplaced("tuya_mcu")


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


@pytest.mark.parametrize(
    ("action", "data"),
    [
        pytest.param("get_attributes", {}, id="read"),
        pytest.param("set_attributes", {"brightness": 50}, id="write"),
    ],
)
async def test_a_datapoint_device_s_raw_zcl_read_and_write_are_not_built(hass, setup_production, broker, action, data):
    """Rather than send raw ZCL a datapoint device can't take."""
    allow_labs(hass)
    entity_id = light(hass, broker, manufacturer="Tuya", model_id="TS0601_dimmer")

    assert await refusal(hass, action, {"entity_id": entity_id, **data}) == "not_built"
    assert commands(broker) == []
