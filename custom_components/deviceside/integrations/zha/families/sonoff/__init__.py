"""Sonoff on ZHA: the SWV water valve, whose timer counts whole seconds."""

from .....core.rules import Rule
from .....core.scope import Family, FamilyScope, experimental

# Sonoff's SWV water valve, which reads OnWithTimedOff's on_time as whole seconds (research, §3, Sonoff row).
SONOFF_SWV = "sonoff_swv"

RULES = (
    # zha-quirks matches it as `SONOFF` / `SWV` (zhaquirks/sonoff/swv.py).
    Rule(SONOFF_SWV, {"model": "SWV"}),
)

FAMILY = Family(
    key="sonoff",
    maintainers=(),
    # A valve on the On/Off cluster, which ZHA shows as a switch: no action for lights alone reaches it.
    classes={SONOFF_SWV: frozenset({"switch"})},
    # Untested on get_attributes. turn_on_for's call harms it: the integration refuses it there (refusals.py).
    scopes={"get_attributes": FamilyScope(capabilities=experimental(SONOFF_SWV))},
)
