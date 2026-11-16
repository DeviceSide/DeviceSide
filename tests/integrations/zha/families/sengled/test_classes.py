"""ZHA's Sengled family: its rule, on its manufacturer string in any case, and its levels."""

import pytest

from custom_components.deviceside.core.rules import match
from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.zha import rules
from custom_components.deviceside.integrations.zha.families import sengled


@pytest.mark.parametrize(
    ("manufacturer", "model", "expected"),
    [
        # The lab's E11-G13 reads `sengled`.
        ("sengled", "E11-G13", sengled.SENGLED),
        ("SENGLED", "E1F-N5E", sengled.SENGLED),
        ("Sengled", "TS0601", sengled.SENGLED),  # alone; Tuya's rules run first (test_classification.py)
        ("sengled optoelectronics", "E11-G13", None),
    ],
)
def test_sengled_rules(manufacturer, model, expected):
    assert match(sengled.RULES, rules.read(manufacturer, model, "zigpy.zcl")) == expected


def test_sengled_is_untested_on_every_action_it_is_served_on():
    """turn_on_for, which the integration refuses it on (test_refusals.py), is left out."""
    assert "turn_on_for" not in sengled.FAMILY.scopes
    assert {level for scope in sengled.FAMILY.scopes.values() for level in scope.capabilities.values()} == {
        Level.EXPERIMENTAL
    }
