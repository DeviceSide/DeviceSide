"""Zigbee2MQTT's Hue family: its rule, the string native control shares with it, and its levels."""

from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.zigbee2mqtt import ADAPTERS
from custom_components.deviceside.integrations.zigbee2mqtt.families import hue
from custom_components.deviceside.integrations.zigbee2mqtt.families.hue import native_control
from custom_components.deviceside.integrations.zigbee2mqtt.rules import Rule


def test_the_hue_rule_and_native_control_read_one_string():
    assert native_control.HUE_MANUFACTURER is hue.HUE_MANUFACTURER
    assert hue.RULES == (Rule("hue", {"manufacturer": "Philips"}),)


def test_hue_is_verified_on_every_action_and_on_lights_alone_on_turn_on_for():
    """Every record ran on a bulb, so a Hue plug, a switch, is untested."""
    for adapter in ADAPTERS:
        assert adapter.scope.class_level("hue", "light") is Level.VERIFIED, adapter.action
    scopes = {adapter.action: adapter.scope for adapter in ADAPTERS}
    assert scopes["turn_on_for"].class_level("hue", "switch") is Level.EXPERIMENTAL
