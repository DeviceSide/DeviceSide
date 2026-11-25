"""Hue on Zigbee2MQTT: Philips' own lights, the class every Zigbee2MQTT record ran on (index.md, Device classes).

Z2M's `hue_native_control` option changes the Zigbee commands a Hue light gets: on, it sends on, brightness, color and
color temperature as one Philips-cluster command; off, as ZCL commands. Which actions need it which way is Hue's
(NEED, below); holding it there for an action's own publish is the integration's (native_control.py), as that runs on
every vendor's call.
"""

import re

from homeassistant.const import Platform

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

# The classes whose lights a lower sends level 1 raw, as a moveToLevel (fade.py, which joins it with Aqara's set), and
# set_attributes sends no kept-level publish after a level 1 on a lit one (set_attributes.py, Hue's set alone): Z2M's
# converter sends a brightness of 1 as level 2 on a definition with turnsOffAtBrightness1, which philips.m.light sets,
# yet a Hue bulb holds level 1 lit (rig runs 2026-11-25: ZHA and set_attributes' raw moveToLevel read 1, the converter
# 2; internals.md, `fade`). A raise from off keeps the converter's level 2 bottom, which its fade up hides. Other
# flagged brands turn off at 1, or aren't known not to, so they keep the converter's 2 (index.md, Lowest brightness).
RAW_BOTTOM: frozenset[str] = frozenset({HUE})

# Verified on every action, as every record ran on a Hue bulb.
_VERIFIED = FamilyScope(capabilities=verified(HUE))
FAMILY = Family(
    key="hue",
    maintainers=(),
    # Hue bulbs, and Hue's smart plug, which Zigbee2MQTT shows as a switch.
    classes={HUE: frozenset({Platform.LIGHT, Platform.SWITCH})},
    scopes={
        "raise_brightness": _VERIFIED,
        "lower_brightness": _VERIFIED,
        "raise_hue": _VERIFIED,
        "lower_hue": _VERIFIED,
        "raise_saturation": _VERIFIED,
        "lower_saturation": _VERIFIED,
        "stop": _VERIFIED,
        # On lights alone: no action serves a Hue plug (turn_on_for refuses it, refusals.py), so none is read
        # (docs/evidence.md, "A read serves only").
        "get_attributes": FamilyScope(capabilities=verified(HUE, domains=(Platform.LIGHT,), only=True)),
        "set_attributes": _VERIFIED,
        # On lights alone: a Hue plug (a switch) is not built (refusals.py).
        "turn_on_for": FamilyScope(capabilities=verified(HUE, domains=(Platform.LIGHT,))),
    },
)
