"""Gledopto on Zigbee2MQTT: its controllers and bulbs, whose converter departs from the standard calls
(research/2026-11-14-timed-on-call-patterns.md, §3), so `other`'s Documented actions don't cover them (plan Decision
24)."""

from ...rules import Rule
from .....core.scope import Family, FamilyScope, experimental

GLEDOPTO = "gledopto"

RULES = (
    # The registry manufacturer: Z2M's vendor `Gledopto`, in any case, as the devices' own Zigbee string is
    # `GLEDOPTO` (zigbee-herdsman-converters src/devices/gledopto.ts, at the research file's commit).
    Rule(GLEDOPTO, {"manufacturer": "(?i:gledopto)"}),
)

# Untested on every action: turn_on_for too, as any brand may depart there (some never switch off).
_UNTESTED = FamilyScope(capabilities=experimental(GLEDOPTO))
FAMILY = Family(
    key="gledopto",
    maintainers=(),
    classes=frozenset({GLEDOPTO}),
    scopes={
        "raise_brightness": _UNTESTED,
        "lower_brightness": _UNTESTED,
        "raise_hue": _UNTESTED,
        "lower_hue": _UNTESTED,
        "raise_saturation": _UNTESTED,
        "lower_saturation": _UNTESTED,
        "stop": _UNTESTED,
        "get_attributes": _UNTESTED,
        "set_attributes": _UNTESTED,
        "turn_on_for": _UNTESTED,
    },
)
