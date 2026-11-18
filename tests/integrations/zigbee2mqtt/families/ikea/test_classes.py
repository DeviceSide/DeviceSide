"""Zigbee2MQTT's IKEA family: its rules, on the catalog's strings, and its levels. turn_on_for's refusals are the
integration's (test_refusals.py); the order between rule groups is test_classification.py's."""

import re

import pytest
from homeassistant.const import Platform

from custom_components.deviceside.core.rules import match
from custom_components.deviceside.core.scope import Level, OnDomains
from custom_components.deviceside.integrations.zigbee2mqtt.families import ikea
from custom_components.deviceside.zigbee import ikea as catalog

from ...conftest import commands, light
from .....conftest import allow_experimental, refusal


def fields(zigbee: tuple[str, str], registry: tuple[str, str] = ("IKEA", "LED1836G9")) -> dict:
    """A device's rule fields once bridge/devices lists its Zigbee strings."""
    return {
        "manufacturer": registry[0],
        "model": None,
        "model_id": registry[1],
        "zigbee_manufacturer": zigbee[0],
        "zigbee_model": zigbee[1],
    }


@pytest.mark.parametrize(
    ("zigbee", "expected"),
    [
        (("IKEA of Sweden", "TRADFRI bulb E27 WW 806lm"), ikea.IKEA),
        (("IKEA of Sweden", "TRADFRI control outlet"), ikea.IKEA),
        *((("IKEA of Sweden", model), ikea.IKEA_TIMER_HARMED) for model in catalog.TIMER_HARMED_MODELS),
        (("IKEA of Sweden", "TRADFRI bulb GU10 CWS 345lm"), ikea.IKEA),
        (("Another maker", "TRADFRI bulb GU10 WS 345lm"), None),
        (("ikea of sweden", "TRADFRI bulb"), None),
    ],
)
def test_ikea_rules(zigbee, expected):
    assert match(ikea.RULES, fields(zigbee)) == expected


def test_the_registry_alone_places_no_ikea_device():
    """Z2M's vendor `IKEA` names no class: the rules wait for the device's own Zigbee strings."""
    assert match(ikea.RULES, {"manufacturer": "IKEA", "model": None, "model_id": "LED2005R5/LED2106R3"}) is None


def test_the_rules_read_the_catalog_s_strings():
    """One home for IKEA's Zigbee strings, shared with ZHA: the family restates none."""
    harmed, vendor = ikea.RULES
    assert vendor.conditions == {"zigbee_manufacturer": re.escape(catalog.MANUFACTURER)}
    assert harmed.conditions["zigbee_manufacturer"] == re.escape(catalog.MANUFACTURER)
    assert harmed.conditions["zigbee_model"].split("|") == [re.escape(model) for model in catalog.TIMER_HARMED_MODELS]


def test_on_trial_on_the_brightness_fades_stop_and_turn_on_for_on_lights_alone():
    """Level Control's moves on Zigbee 3.0 certification, as `other`'s; turn_on_for on research naming IKEA's lights
    (plan Decision 14), its outlets and the reported bulbs refused there by the integration. Not built elsewhere."""
    scopes = {action: dict(scope.capabilities) for action, scope in ikea.FAMILY.scopes.items()}
    certified = {ikea.IKEA: Level.EXPERIMENTAL, ikea.IKEA_TIMER_HARMED: Level.EXPERIMENTAL}

    assert scopes == {
        "raise_brightness": certified,
        "lower_brightness": certified,
        "stop": certified,
        "turn_on_for": {ikea.IKEA: OnDomains(Level.EXPERIMENTAL, frozenset({Platform.LIGHT}))},
    }


async def test_a_bulb_reported_to_stay_on_is_not_built_on_turn_on_for(hass, setup_production, broker):
    """Reported turned on by a unicast timer and never off (Zigbee2MQTT #29158): refused even with Experimental
    features on."""
    entity_id = light(
        hass,
        broker,
        manufacturer="IKEA",
        model_id="LED2005R5/LED2106R3",
        zigbee=("IKEA of Sweden", "TRADFRIbulbGU10WS345lm"),
    )
    allow_experimental(hass)

    assert await refusal(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5}) == "not_built"
    assert commands(broker) == []
