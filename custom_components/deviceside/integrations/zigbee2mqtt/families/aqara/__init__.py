"""Aqara on Zigbee2MQTT: its lights, in Labs on `other`'s actions for lights, as a class of their own so a record on one
bulb can bring the class to Verified (index.md, Device classes)."""

from homeassistant.const import Platform

from .....core.rules import Rule
from .....core.scope import Family, FamilyScope, labs

AQARA = "aqara"

# The device's own Zigbee manufacturer string, not Z2M's vendor: the vendor `Aqara` also covers devices whose string is
# `LUMI`, which stay in `other`. Like IKEA's, it waits for bridge/devices (classes.py, placed).
RULES = (Rule(AQARA, {"zigbee_manufacturer": "Aqara"}),)

# `other`'s actions for lights, at its level (classes.py): Level Control's moves and stop, which a Zigbee 3.0 dimmable
# light must take, and raw ZCL reads and writes.
_LABS = FamilyScope(capabilities=labs(AQARA))

FAMILY = Family(
    key="aqara",
    maintainers=(),
    classes={AQARA: frozenset({Platform.LIGHT})},
    scopes={
        "raise_brightness": _LABS,
        "lower_brightness": _LABS,
        "stop": _LABS,
        "get_attributes": _LABS,
        "set_attributes": _LABS,
    },
    # Not in the other scopes: not built there. Hue and saturation wait on the probe of its ColorCapabilities (the bulb
    # stays in xy color mode), and its timer behavior is unprobed.
)
