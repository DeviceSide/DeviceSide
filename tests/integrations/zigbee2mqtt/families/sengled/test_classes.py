"""Zigbee2MQTT's Sengled family: its rule, and turn_on_for's refusal."""

import pytest

from custom_components.deviceside.integrations.zigbee2mqtt.families import sengled

from ...conftest import commands, light
from .....conftest import allow_experimental, refusal


@pytest.mark.parametrize(("manufacturer", "matched"), [("Sengled", True), ("Sengled Lighting", False)])
def test_the_rule_reads_z2m_s_whole_vendor_string(manufacturer, matched):
    assert [rule.matches({"manufacturer": manufacturer}) for rule in sengled.RULES] == [matched]


async def test_turn_on_for_is_not_supported(hass, setup_production, broker):
    """Rather than send `on_time`, which the Sengled ignores."""
    allow_experimental(hass)
    entity_id = light(hass, broker, manufacturer="Sengled", model_id="E11-G13")

    assert await refusal(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5}) == "not_supported"
    assert commands(broker) == []
