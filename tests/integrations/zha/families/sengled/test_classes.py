"""ZHA's Sengled family: its rule, on its manufacturer string in any case, and its levels."""

import pytest

from custom_components.deviceside.core.rules import match
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


def test_sengled_is_in_no_scope():
    """Not built on every action (docs/evidence.md, On trial): its probe found it departs, and turn_on_for's call harms
    it, which the integration refuses there with a reason (test_refusals.py)."""
    assert sengled.FAMILY.scopes == {}
