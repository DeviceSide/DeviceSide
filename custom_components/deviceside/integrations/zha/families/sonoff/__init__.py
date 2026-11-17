"""Sonoff on ZHA: the SWV water valve, whose timer counts whole seconds."""

from .....core.rules import Rule
from .....core.scope import Family

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
    # In no scope: turn_on_for's call harms it, so the integration refuses it there (refusals.py), and get_attributes
    # reads only what another action serves (core/registry.py, check_queries; plan Decision 25).
)
