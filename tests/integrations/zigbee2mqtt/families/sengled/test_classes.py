"""Zigbee2MQTT's Sengled family: its rule, its levels, and turn_on_for, which it leaves out."""

import pytest

from custom_components.deviceside.integrations.zigbee2mqtt import ADAPTERS
from custom_components.deviceside.integrations.zigbee2mqtt.families import sengled


@pytest.mark.parametrize(("manufacturer", "matched"), [("Sengled", True), ("Sengled Lighting", False)])
def test_the_rule_reads_z2m_s_whole_vendor_string(manufacturer, matched):
    assert [rule.matches({"manufacturer": manufacturer}) for rule in sengled.RULES] == [matched]


def test_sengled_is_not_built_on_every_action():
    """ZHA's probe found it departs, and no pass or research admits it (docs/evidence.md, On trial)."""
    assert not any("sengled" in adapter.scope.capabilities for adapter in ADAPTERS)
