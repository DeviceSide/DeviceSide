"""ZHA's Sonoff family: its rule, on the SWV water valve's model, and its levels."""

import pytest

from custom_components.deviceside.core.rules import match
from custom_components.deviceside.core.scope import Level
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
    assert match(sonoff.RULES, rules.read(manufacturer, model, "zigpy.zcl")) == expected


def test_the_valve_is_untested_on_every_action_it_is_served_on():
    """turn_on_for, which the integration refuses it on (test_refusals.py), is left out."""
    assert "turn_on_for" not in sonoff.FAMILY.scopes
    assert {level for scope in sonoff.FAMILY.scopes.values() for level in scope.capabilities.values()} == {
        Level.EXPERIMENTAL
    }
