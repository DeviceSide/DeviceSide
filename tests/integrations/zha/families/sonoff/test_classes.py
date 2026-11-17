"""ZHA's Sonoff family: its rule, on the SWV water valve's model, and its scopes."""

import pytest

from custom_components.deviceside.core.rules import match
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


def test_the_valve_is_in_no_scope():
    """turn_on_for refuses it (test_refusals.py), and get_attributes reads only what another action serves (plan
    Decision 25), so no action holds it."""
    assert sonoff.FAMILY.scopes == {}
