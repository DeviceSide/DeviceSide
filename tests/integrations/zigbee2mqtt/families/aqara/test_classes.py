"""Zigbee2MQTT's Aqara family: its rule."""

import pytest

from custom_components.deviceside.integrations.zigbee2mqtt.families import aqara


@pytest.mark.parametrize(
    ("zigbee_manufacturer", "matched"),
    [
        ("Aqara", True),  # the T2 bulbs' own Zigbee string
        ("LUMI", False),  # Z2M's vendor `Aqara` also covers these, left to the rules after it
        ("Aqara Lighting", False),  # the whole string, not a prefix
    ],
)
def test_the_rule_reads_the_zigbee_manufacturer_string(zigbee_manufacturer, matched):
    assert [rule.matches({"zigbee_manufacturer": zigbee_manufacturer}) for rule in aqara.RULES] == [matched]


def test_the_registry_vendor_alone_places_nothing():
    assert [rule.matches({"manufacturer": "Aqara"}) for rule in aqara.RULES] == [False]
