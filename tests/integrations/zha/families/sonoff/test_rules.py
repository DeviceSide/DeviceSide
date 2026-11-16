"""Sonoff's rule on ZHA: the SWV water valve's model."""

import pytest

from custom_components.deviceside.integrations.zha import rules
from custom_components.deviceside.integrations.zha.families import sonoff


@pytest.mark.parametrize(
    ("manufacturer", "model", "expected"),
    [
        ("SONOFF", "SWV", sonoff.SONOFF_SWV),
        # Sonoff's other devices aren't the valve.
        ("SONOFF", "ZBMINIR2", None),
    ],
)
def test_sonoff_rules(manufacturer, model, expected):
    assert rules.match(sonoff.RULES, manufacturer, model, "zigpy.zcl") == expected
