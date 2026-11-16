"""Hue on Zigbee2MQTT: Philips' own lights, the class every Zigbee2MQTT record ran on (index.md, Device classes).

Z2M's `hue_native_control` option changes the Zigbee commands a Hue light gets, so the actions that need it one way
hold it there for their own publish (native_control.py).
"""

import re

from ...rules import Rule
from .....core.scope import Family, FamilyScope, verified

# Z2M's vendor string for Hue, which HA's device registry shows as the manufacturer; native_control.py reads it too.
HUE_MANUFACTURER = "Philips"

HUE = "hue"

RULES = (Rule(HUE, {"manufacturer": re.escape(HUE_MANUFACTURER)}),)
# The classes the registry alone places for good: the vendor is Z2M's own Philips string, which the definition sets
# and no later report changes, so a Hue device needn't wait for its Zigbee strings (classes.placed). It holds only
# while no rule reading those strings comes first, which the integration checks (families/__init__.py).
REGISTRY_PLACED = frozenset({HUE})

# Verified on every action, as every record ran on a Hue bulb.
_VERIFIED = FamilyScope(capabilities=verified(HUE))
FAMILY = Family(
    key="hue",
    maintainers=(),
    classes=frozenset({HUE}),
    scopes={
        "raise_brightness": _VERIFIED,
        "lower_brightness": _VERIFIED,
        "raise_hue": _VERIFIED,
        "lower_hue": _VERIFIED,
        "raise_saturation": _VERIFIED,
        "lower_saturation": _VERIFIED,
        "stop": _VERIFIED,
        "get_attributes": _VERIFIED,
        "set_attributes": _VERIFIED,
        # On lights alone, as every record ran on a bulb, so a Hue plug (a switch) is untested.
        "turn_on_for": FamilyScope(capabilities=verified(HUE, domains=("light",))),
    },
)
