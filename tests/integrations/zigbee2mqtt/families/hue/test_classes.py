"""Zigbee2MQTT's Hue family: its rule, its levels, and the actions that need native control."""

import pytest

from custom_components.deviceside.core.rules import Rule
from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.zigbee2mqtt import ADAPTERS
from custom_components.deviceside.integrations.zigbee2mqtt.families import hue


def test_the_rule_reads_z2m_s_whole_vendor_string_off_the_registry():
    assert hue.RULES == (Rule("hue", {"manufacturer": "Philips"}),)


@pytest.mark.parametrize(("manufacturer", "matched"), [("Philips", True), ("Philips Lighting", False)])
def test_the_rule_matches_the_whole_string(manufacturer, matched):
    assert [rule.matches({"manufacturer": manufacturer}) for rule in hue.RULES] == [matched]


def test_hue_is_verified_on_every_action_and_on_lights_alone_on_turn_on_for():
    """Every record ran on a bulb, so a Hue plug, a switch, is untested."""
    for adapter in ADAPTERS:
        assert adapter.scope.class_level("hue", "light") is Level.VERIFIED, adapter.action
    scopes = {adapter.action: adapter.scope for adapter in ADAPTERS}
    assert scopes["turn_on_for"].class_level("hue", "switch") is Level.EXPERIMENTAL


def test_a_timer_needs_native_control_on_and_a_brightness_or_saturation_fade_off():
    assert hue.NEED == {
        "turn_on_for": True,
        "raise_brightness": False,
        "lower_brightness": False,
        "raise_saturation": False,
        "lower_saturation": False,
    }
