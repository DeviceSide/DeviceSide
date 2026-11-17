"""Sengled bulbs on ZHA: their class (internals.md, Tested behavior)."""

from homeassistant.const import Platform

from .....core.rules import Rule
from .....core.scope import Family, FamilyScope, experimental

SENGLED = "sengled"

RULES = (
    # The lab's E11-G13 reads `sengled`.
    Rule(SENGLED, {"manufacturer": "(?i:sengled)"}),
)

# Untested on every action but turn_on_for, whose call harms it: the integration refuses it there (refusals.py).
_UNTESTED = FamilyScope(capabilities=experimental(SENGLED))

FAMILY = Family(
    key="sengled",
    maintainers=(),
    classes={SENGLED: frozenset({Platform.LIGHT})},
    scopes={
        "get_attributes": _UNTESTED,
        "lower_brightness": _UNTESTED,
        "lower_hue": _UNTESTED,
        "lower_saturation": _UNTESTED,
        "raise_brightness": _UNTESTED,
        "raise_hue": _UNTESTED,
        "raise_saturation": _UNTESTED,
        "set_attributes": _UNTESTED,
        "stop": _UNTESTED,
    },
)
