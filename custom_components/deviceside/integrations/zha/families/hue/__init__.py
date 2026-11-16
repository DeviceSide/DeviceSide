"""Hue bulbs on ZHA: the one class every record ran on, and Signify's own turn-on command (multi_color)."""

from ...rules import Group, Rule
from .....core.scope import Family, FamilyScope, verified

HUE = "hue"

RULES: Group = (
    # Hue bulbs' own manufacturer strings, older and newer (zha-quirks zhaquirks/philips/__init__.py, PHILIPS and
    # SIGNIFY); the lab's read `Signify Netherlands B.V.`.
    Rule(HUE, "manufacturer", r"Signify Netherlands B\.V\.|Philips"),
)

# Verified on every action: every record ran on Hue bulbs (index.md, Device classes).
_VERIFIED = FamilyScope(capabilities=verified(HUE))

FAMILY = Family(
    key="hue",
    maintainers=(),
    classes=frozenset({HUE}),
    scopes={
        "get_attributes": _VERIFIED,
        "lower_brightness": _VERIFIED,
        "lower_hue": _VERIFIED,
        "lower_saturation": _VERIFIED,
        "raise_brightness": _VERIFIED,
        "raise_hue": _VERIFIED,
        "raise_saturation": _VERIFIED,
        "set_attributes": _VERIFIED,
        "stop": _VERIFIED,
        "turn_on_for": _VERIFIED,
    },
)
