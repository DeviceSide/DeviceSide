"""Zigbee2MQTT's IKEA family: its rules, on the catalog's strings. turn_on_for's refusals are the
integration's (test_refusals.py); the order between rule groups is test_classification.py's."""

import re

import pytest

from custom_components.deviceside.core.rules import match
from custom_components.deviceside.integrations.zigbee2mqtt.families import ikea
from custom_components.deviceside.zigbee import ikea as catalog


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
