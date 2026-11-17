"""Zigbee2MQTT's Gledopto family: its rule, and its levels."""

import pytest

from custom_components.deviceside.integrations.zigbee2mqtt import ADAPTERS
from custom_components.deviceside.integrations.zigbee2mqtt.families import gledopto


@pytest.mark.parametrize(
    ("manufacturer", "matched"),
    [
        ("Gledopto", True),  # Z2M's vendor string
        ("GLEDOPTO", True),  # the Zigbee string, in any case
        ("Gledopto Lighting", False),  # the whole string, not a prefix
    ],
)
def test_the_rule_reads_the_vendor_in_any_case(manufacturer, matched):
    assert [rule.matches({"manufacturer": manufacturer}) for rule in gledopto.RULES] == [matched]


def test_gledopto_is_not_built_on_every_action():
    """Its converter departs from the standard calls (Decision 24), and no pass or research admits it
    (docs/evidence.md, On trial)."""
    assert not any("gledopto" in adapter.scope.capabilities for adapter in ADAPTERS)
