"""Hue's rule on ZHA: its bulbs' two manufacturer strings."""

import pytest

from custom_components.deviceside.integrations.zha import rules
from custom_components.deviceside.integrations.zha.families import hue


@pytest.mark.parametrize(
    ("manufacturer", "model", "expected"),
    [
        # The lab's string (research/2026-11-14-lab-probe.md, §1).
        ("Signify Netherlands B.V.", "LTA009", hue.HUE),
        # Older Hue bulbs' string.
        ("Philips", "LCT001", hue.HUE),
        # The whole string, not a part of it.
        ("Philips Lighting", "LCT001", None),
        ("IKEA of Sweden", "TRADFRI bulb E27 WS opal 980lm", None),
    ],
)
def test_hue_rules(manufacturer, model, expected):
    assert rules.match(hue.RULES, manufacturer, model, "zigpy.zcl") == expected
