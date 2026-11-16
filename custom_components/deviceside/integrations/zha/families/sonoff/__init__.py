"""Sonoff on ZHA: the SWV water valve, whose timer counts whole seconds."""

from ...rules import Group, Rule
from .....core.scope import Family, FamilyScope, NotSupported, experimental

# Sonoff's SWV water valve, which reads OnWithTimedOff's on_time as whole seconds (research, §3, Sonoff row).
SONOFF_SWV = "sonoff_swv"

RULES: Group = (
    # zha-quirks matches it as `SONOFF` / `SWV` (zhaquirks/sonoff/swv.py).
    Rule(SONOFF_SWV, "model", "SWV"),
)

_UNTESTED = FamilyScope(capabilities=experimental(SONOFF_SWV))
_RESEARCH = "https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zigbee2mqtt/research/"
# turn_on_for's call harms it (docs/evidence.md, When today's call harms a class): a call that would work is known,
# but isn't built. `harms`, so core also refuses a target it can't class.
_TURN_ON_FOR = FamilyScope(
    not_supported={
        # Z2M's call in whole seconds (on_off_fixed_on_time) works on it; ZHA's tenths would run ten times as long.
        SONOFF_SWV: NotSupported(
            reason="It reads ZHA's timer in seconds, so it would stay open about ten times longer than asked",
            source=_RESEARCH + "2026-11-14-tuya-countdown.md",
            harms=True,
        ),
    }
)

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
        "turn_on_for": _TURN_ON_FOR,
    },
)
