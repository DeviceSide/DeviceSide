"""Zigbee2MQTT's Hue family: its rule, and the actions that need native control."""

import pytest

from custom_components.deviceside.core.rules import Rule
from custom_components.deviceside.integrations.zigbee2mqtt.families import hue


def test_the_rule_reads_z2m_s_whole_vendor_string_off_the_registry():
    assert hue.RULES == (Rule("hue", {"manufacturer": "Philips"}),)


@pytest.mark.parametrize(("manufacturer", "matched"), [("Philips", True), ("Philips Lighting", False)])
def test_the_rule_matches_the_whole_string(manufacturer, matched):
    assert [rule.matches({"manufacturer": manufacturer}) for rule in hue.RULES] == [matched]


def test_a_timer_needs_native_control_on_and_a_brightness_or_saturation_fade_off():
    assert hue.NEED == {
        "turn_on_for": True,
        "raise_brightness": False,
        "lower_brightness": False,
        "raise_saturation": False,
        "lower_saturation": False,
    }
