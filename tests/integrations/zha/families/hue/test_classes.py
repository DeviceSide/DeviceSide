"""ZHA's Hue family: its rule, on its bulbs' two manufacturer strings, and its levels."""

import pytest

from custom_components.deviceside.core.rules import match
from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.zha import ADAPTERS, rules
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
    assert match(hue.RULES, rules.read(manufacturer, model, "zigpy.zcl")) == expected


def test_hue_is_verified_on_every_action():
    """Every record ran on Hue bulbs."""
    assert {adapter.scope.capabilities["hue"] for adapter in ADAPTERS} == {Level.VERIFIED}
