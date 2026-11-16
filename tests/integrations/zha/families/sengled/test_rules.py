"""Sengled's rule on ZHA: its manufacturer string, in any case."""

import pytest

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
    assert rules.match(sengled.RULES, manufacturer, model, "zigpy.zcl") == expected
