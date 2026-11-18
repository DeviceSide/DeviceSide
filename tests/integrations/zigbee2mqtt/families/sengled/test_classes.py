"""Zigbee2MQTT's Sengled family: its rule."""

import pytest

from custom_components.deviceside.integrations.zigbee2mqtt.families import sengled


@pytest.mark.parametrize(("manufacturer", "matched"), [("Sengled", True), ("Sengled Lighting", False)])
def test_the_rule_reads_z2m_s_whole_vendor_string(manufacturer, matched):
    assert [rule.matches({"manufacturer": manufacturer}) for rule in sengled.RULES] == [matched]
