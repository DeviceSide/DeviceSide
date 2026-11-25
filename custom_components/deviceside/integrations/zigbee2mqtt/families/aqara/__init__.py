"""Aqara on Zigbee2MQTT: its lights, a class of their own so a record on one bulb brings the class to Verified
(index.md, Device classes): Verified on the actions its records pass, in Labs on `other`'s others."""

from homeassistant.const import Platform

from .....core.rules import Rule
from .....core.scope import Family, FamilyScope, labs, verified

AQARA = "aqara"

# The device's own Zigbee manufacturer string, not Z2M's vendor: the vendor `Aqara` also covers devices whose string is
# `LUMI`, which fall to the rules after the families': `standard_light` when on its table, else `other`. Like IKEA's,
# it waits for bridge/devices (classes.py, placed).
RULES = (Rule(AQARA, {"zigbee_manufacturer": "Aqara"}),)

# `other`'s actions for lights (classes.py): Level Control's moves and stop, which a Zigbee 3.0 dimmable light must
# take, and raw ZCL reads and writes. Verified where an Aqara bulb's record passes; the moves with stop, which must
# halt them (tests/core/test_scope.py). get_attributes stays in Labs, as its record also runs an hs color mode case
# (keeps_and_reads_hs_while_off) this bulb can't pass, so the rig writes no Aqara rows for it.
_LABS = FamilyScope(capabilities=labs(AQARA))
_VERIFIED = FamilyScope(capabilities=verified(AQARA))

FAMILY = Family(
    key="aqara",
    maintainers=(),
    classes={AQARA: frozenset({Platform.LIGHT})},
    scopes={
        "raise_brightness": _VERIFIED,
        "lower_brightness": _VERIFIED,
        "stop": _VERIFIED,
        "get_attributes": _LABS,
        "set_attributes": _VERIFIED,
    },
    # Not in the other scopes: not built there. Hue and saturation actions are not built, as the bulb has xy and color
    # temperature only, and turn_on_for is a refusal entry (refusals.py), as the bulb ignored a timed on from off; both
    # in index.md (Aqara) and research/aqara/2026-11-25-agl003-probe.md.
)
