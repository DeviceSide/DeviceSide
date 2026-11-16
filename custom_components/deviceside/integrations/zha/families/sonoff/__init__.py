"""Sonoff on ZHA: the SWV water valve, whose timer counts whole seconds."""

from .....core.rules import Rule
from .....core.scope import Family, FamilyScope, experimental

# Sonoff's SWV water valve, which reads OnWithTimedOff's on_time as whole seconds (research, §3, Sonoff row).
SONOFF_SWV = "sonoff_swv"

RULES = (
    # zha-quirks matches it as `SONOFF` / `SWV` (zhaquirks/sonoff/swv.py).
    Rule(SONOFF_SWV, {"model": "SWV"}),
)

# Untested on every action but turn_on_for, whose call harms it: the integration refuses it there (refusals.py).
_UNTESTED = FamilyScope(capabilities=experimental(SONOFF_SWV))

FAMILY = Family(
    key="sonoff",
    maintainers=(),
    classes=frozenset({SONOFF_SWV}),
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
