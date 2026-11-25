"""Aqara on Zigbee2MQTT: its lights, a class of their own so a record on one bulb brings the class to Verified
(index.md, Device classes): Verified on the actions its records pass, in Labs on `other`'s others."""

from homeassistant.const import Platform

from .....core.rules import Rule
from .....core.scope import Family, FamilyScope, verified

AQARA = "aqara"

# The device's own Zigbee manufacturer string, not Z2M's vendor: the vendor `Aqara` also covers devices whose string is
# `LUMI`, which stay in `other`. Like IKEA's, it waits for bridge/devices (classes.py, placed).
RULES = (Rule(AQARA, {"zigbee_manufacturer": "Aqara"}),)

# The classes whose lights a lower sends level 1 raw, as a moveToLevel (fade.py), joined with Hue's (families/hue,
# RAW_BOTTOM). Z2M's converter sends a brightness of 1 as moveToLevelWithOnOff, which switched the unflagged T2 bulb
# off at a lower to 0.4 %, while set_attributes' raw moveToLevel to level 1 held it lit
# (rig run 2026-11-25, Decision 11; research/aqara, internals.md `fade`). set_attributes keeps Hue's set alone.
RAW_BOTTOM: frozenset[str] = frozenset({AQARA})

# `other`'s actions for lights (classes.py): Level Control's moves and stop, which a Zigbee 3.0 dimmable light must
# take, and raw ZCL reads and writes. Verified where an Aqara bulb's record passes; the moves with stop, which must
# halt them (tests/core/test_scope.py). Everything it takes is Verified.
_VERIFIED = FamilyScope(capabilities=verified(AQARA))

FAMILY = Family(
    key="aqara",
    maintainers=(),
    classes={AQARA: frozenset({Platform.LIGHT})},
    scopes={
        "raise_brightness": _VERIFIED,
        "lower_brightness": _VERIFIED,
        "stop": _VERIFIED,
        "get_attributes": _VERIFIED,
        "set_attributes": _VERIFIED,
    },
    # Not in the other scopes: not built there. Hue and saturation actions are not built, as the bulb has xy and color
    # temperature only, and turn_on_for is a refusal entry (refusals.py), as the bulb ignored a timed on from off; both
    # in index.md (Aqara) and research/aqara/2026-11-25-agl003-probe.md.
)
