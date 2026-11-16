"""Hue on Zigbee2MQTT: Philips' own lights, the class every Zigbee2MQTT record ran on (index.md, Device classes).

Z2M's `hue_native_control` option changes the Zigbee commands a Hue light gets: on, it sends on, brightness, color and
color temperature as one Philips-cluster command; off, as ZCL commands. Which actions need it which way is Hue's
(NEED, below); holding it there for an action's own publish is the integration's (native_control.py), as that runs on
every vendor's call.
"""

import re

from .....core.rules import Rule
from .....core.scope import Family, FamilyScope, verified

# Z2M's vendor string for Hue, which HA's device registry shows as the manufacturer; native_control.py reads it too.
HUE_MANUFACTURER = "Philips"

HUE = "hue"

# The integration places `hue` by the registry alone (families/__init__.py, REGISTRY_PLACED), which holds only while
# this rule reads nothing but the registry.
RULES = (Rule(HUE, {"manufacturer": re.escape(HUE_MANUFACTURER)}),)

# Each action's need of `hue_native_control` on a Hue light: True on, False off. An action left out works either way
# and leaves the option alone: a stop, a hue move and a read or write of settings pass on the rig with the option on
# and off.
NEED: dict[str, bool] = {
    # With a color; without one it works either way. A Hue bulb drops a color sent while it is off, so as ZCL it
    # lights at its last color first.
    "turn_on_for": True,
    # Sent native, a long raise runs about 2.3x faster than its transition, and a soft off reports `onOff: 0` at once
    # while the bulb still fades.
    "raise_brightness": False,
    "lower_brightness": False,
    # Its color has no hue, which the native command turns to xy, so the fade would run as MoveToColor, and jump at a
    # stop.
    "raise_saturation": False,
    "lower_saturation": False,
}

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
