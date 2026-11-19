"""Control4's device classes (docs/evidence.md, Device classes): what the light's driver does with the call.

DeviceSide sends every Control4 light the same Director commands, and the driver behind the light item decides what
they do. The class keys on what the driver says it can do, read with the inventory as the Control4 entry loads:

- `no_stop`: a light whose capabilities say `supports_brightness_stop: false`. It ignores a stop, and its Director shows
  a ramp's end at once (Tested behavior on Chowmain's Link Client and Control4's own Hue driver), so a stop can't be
  sent or confirmed, and a raise or lower couldn't be halted. Link Client also jumps to the level, ignoring the time.
- `other`, the default class: every other light, the tested "Zigbee 3 Light" bulb and Light Group driver included.

A light group is classed by its members (inventory.expand_group). Before its entry's inventory has loaded, a light is
`other`, Unplaced: no Control4 action's failure harms, so that only keeps it out of a response's class.
"""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from . import inventory
from .director import item_id
from ...const import DOCS_URL
from ...core.models import Target
from ...core.scope import OTHER, NoKnownMethod, Unplaced, labs

NO_STOP = "no_stop"
CLASSES = {name: frozenset({Platform.LIGHT}) for name in (NO_STOP, OTHER)}

_SOURCE = DOCS_URL + "docs/integrations/control4/index.md#lights-whose-driver-cant-stop-a-ramp"
_WHAT = "lights whose driver can't stop a ramp"
# raise_brightness, lower_brightness (fade.py) and stop: a move nothing can halt would run to its end.
MOVE_NO_KNOWN_METHOD = {
    NO_STOP: NoKnownMethod(
        what=_WHAT,
        reason="The light's driver says it can't stop a ramp, so a raise or lower couldn't be halted",
        source=_SOURCE,
    )
}
STOP_NO_KNOWN_METHOD = {
    NO_STOP: NoKnownMethod(
        what=_WHAT, reason="The light's driver says it can't stop a ramp, and it ignores the stop", source=_SOURCE
    )
}
MOVE_LEVELS = labs(OTHER)
# get_attributes and set_attributes read and write every driver alike.
LEVELS = labs(NO_STOP, OTHER)


def capability(hass: HomeAssistant, target: Target) -> str:
    """Control4's IntegrationInfo.capability: the light's class by what its driver says it can do."""
    if (held := inventory.held(hass, target)) is None:
        return Unplaced(OTHER)
    return NO_STOP if item_id(target) in held.no_stop else OTHER
