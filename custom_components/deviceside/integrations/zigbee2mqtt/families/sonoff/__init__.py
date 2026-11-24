"""Sonoff on Zigbee2MQTT: the relays whose firmware takes the persistent auto-off, "inching", and the two plugs it is
not built for.

Z2M exposes inching as one write-only composite, `inching_control_set` (ZHC's `sonoffExtend.inchingControlSet`), which
it sends as a manufacturer-specific command on cluster 0xFC11 (research/sonoff/2026-11-24-inching.md, §1). The device
has no read path ZHC or Z2M uses, so the call is `sent` (inching.py). An allowlist of Z2M's definition models, as
docs/evidence.md (In Labs) admits only the identities research names, and the composite's presence for the whole device
(`exposes` holds endpoint-less properties alone, rules.definition_fields), which keeps the 2-gang MINI-ZB2GS out: its
composite is per endpoint, so it waits on per-endpoint addressing. The definition is read from bridge/devices alone: a
Sonoff device stays `other` and Unplaced until it lists it.

The S60ZBTPF and S60ZBTPG plugs have the same composite, but DISABLE is reported to have no effect on them (Z2M #31799),
so `clear_auto_off` would leave the plug pulsing: a class of their own, refused on both auto-off actions (refusals.py).

On every other action they keep what `other` gave them: sonoff_inching stays in Labs on the brightness fades and stop
(classes.py), a plug has none of those, and both are refused on turn_on_for (refusals.py).
"""

import re
from collections.abc import Mapping

from homeassistant.const import Platform

from .inching import CLEAR_AUTO_OFF, SET_AUTO_OFF
from ...bridge import INCHING_COMPOSITE
from .....core.rules import Rule
from .....core.scope import Family, FamilyScope, labs

# The single-channel Sonoff relays and dimmer whose definition exposes the composite, a Z2M definition model each
# (ZHC src/devices/sonoff.ts at its master of 2026-11-24, checked in research/sonoff/2026-11-24-inching.md, §1; the
# white label MINI-ZBD is a definition model of its own in Z2M's list).
INCHING_MODELS = (
    "ZBMINIR2",
    "MINI-ZBD",  # white label of ZBMINIR2
    "ZBMicro",
    "MINI-ZB1GS",
    "MINI-ZB1GSP",
    "BASIC-ZB1GSP",
    "S61SZBTPB",
    "MINI-ZBDIM",  # a dimmer, so a light
)
# The S60 plugs, whose DISABLE is reported to have no effect (module docstring).
S60_MODELS = ("S60ZBTPF", "S60ZBTPG")

# Single-channel Sonoff firmware on inching (MINI-ZBDIM is a light, the rest switches).
SONOFF_INCHING = "sonoff_inching"
# The S60 plugs: the composite, but DISABLE reported not to work, so the auto-off actions are not built (refusals.py).
SONOFF_S60 = "sonoff_s60"


def _rule(name: str, models: tuple[str, ...]) -> Rule:
    return Rule(name, {"definition_model": "|".join(map(re.escape, models)), "exposes": re.escape(INCHING_COMPOSITE)})


# Read off the definition in bridge/devices alone.
RULES = (_rule(SONOFF_INCHING, INCHING_MODELS), _rule(SONOFF_S60, S60_MODELS))

# Level Control's moves and stop, as `other`'s are (classes.py): the class leaves `other`, so keeps what it had. The
# S60 plugs are switches, which no action for lights alone reaches (core/registry.py, check_classes).
_CERTIFIED = FamilyScope(capabilities=labs(SONOFF_INCHING))
# In Labs on research, sent `inching_control_set` (inching.py), so a group with one falls back to its members.
_AUTO_OFF: Mapping[str, FamilyScope] = {
    "set_auto_off": FamilyScope(capabilities=labs(SONOFF_INCHING), own_calls={SONOFF_INCHING: SET_AUTO_OFF}),
    "clear_auto_off": FamilyScope(capabilities=labs(SONOFF_INCHING), own_calls={SONOFF_INCHING: CLEAR_AUTO_OFF}),
}

FAMILY = Family(
    key="sonoff",
    maintainers=(),
    classes={
        SONOFF_INCHING: frozenset({Platform.LIGHT, Platform.SWITCH}),
        SONOFF_S60: frozenset({Platform.SWITCH}),
    },
    scopes={
        "raise_brightness": _CERTIFIED,
        "lower_brightness": _CERTIFIED,
        "stop": _CERTIFIED,
        **_AUTO_OFF,
    },
)
