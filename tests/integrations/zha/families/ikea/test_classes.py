"""ZHA's IKEA family: its rules, on the catalog's strings, and its levels. turn_on_for's refusals are the
integration's (test_refusals.py)."""

import re

import pytest
from homeassistant.const import Platform

from custom_components.deviceside.core.rules import match
from custom_components.deviceside.core.scope import Level, OnDomains
from custom_components.deviceside.integrations.zha import rules
from custom_components.deviceside.integrations.zha.families import ikea
from custom_components.deviceside.zigbee import ikea as catalog


@pytest.mark.parametrize(
    ("manufacturer", "model", "expected"),
    [
        ("IKEA of Sweden", "TRADFRI bulb E27 WS opal 980lm", ikea.IKEA),
        ("IKEA of Sweden", "TRADFRI control outlet", ikea.IKEA),
        *(("IKEA of Sweden", model, ikea.IKEA_TIMER_HARMED) for model in catalog.TIMER_HARMED_MODELS),
        # A model alone, or another GU10: only the reported bulbs' strings.
        ("Another maker", "TRADFRI bulb GU10 WS 345lm", None),
        ("IKEA of Sweden", "TRADFRI bulb GU10 CWS 345lm", ikea.IKEA),
        ("IKEA of Sweden", "TRADFRI bulb GU10 WS 345lmx", ikea.IKEA),
        ("ikea of sweden", "TRADFRI bulb", None),
    ],
)
def test_ikea_rules(manufacturer, model, expected):
    assert match(ikea.RULES, rules.read(manufacturer, model, "zigpy.zcl")) == expected


def test_the_rules_read_the_catalog_s_strings():
    """One home for IKEA's Zigbee strings, shared with Zigbee2MQTT: the family restates none."""
    harmed, vendor = ikea.RULES
    assert vendor.conditions == {"manufacturer": re.escape(catalog.MANUFACTURER)}
    assert harmed.conditions["manufacturer"] == re.escape(catalog.MANUFACTURER)
    assert harmed.conditions["model"].split("|") == [re.escape(model) for model in catalog.TIMER_HARMED_MODELS]


def test_on_trial_on_the_brightness_fades_stop_and_turn_on_for_on_lights_alone():
    """Level Control's moves on Zigbee 3.0 certification, as `other`'s; turn_on_for on research naming IKEA's lights
    (plan Decision 14), its outlets and the reported bulbs refused there by the integration. Not built elsewhere."""
    scopes = {action: dict(scope.capabilities) for action, scope in ikea.FAMILY.scopes.items()}
    certified = {ikea.IKEA: Level.EXPERIMENTAL, ikea.IKEA_TIMER_HARMED: Level.EXPERIMENTAL}

    assert scopes == {
        "lower_brightness": certified,
        "raise_brightness": certified,
        "stop": certified,
        "turn_on_for": {ikea.IKEA: OnDomains(Level.EXPERIMENTAL, frozenset({Platform.LIGHT}))},
    }
