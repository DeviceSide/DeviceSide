"""Hue's device classes (docs/evidence.md, Device classes): whose firmware a light behind the bridge runs.

DeviceSide sends the bridge the same CLIP v2 request for every light; the bridge picks the Zigbee call, and nothing in
CLIP v2 shows which one it picked or routes a light by any field DeviceSide could read (internals.md, Device
classes). So the class keys on the device's identity, the manufacturer core's hue integration registers from the
bridge's `product_data.manufacturer_name`:

- `hue`: Signify's own lights, which every record ran on.
- `other`, the default class: every other maker's light the bridge has paired, Friends of Hue certified ones
  included, as certification isn't Signify's firmware and no record reaches one.
- `smart_scene`: an All-Day scene, which has no fixed settings to write (set_scene's doesn't-work entry).

A scene is classed by the lights it writes: `other` when any of them is, else `hue`, as set_scene's call reaches each
light; one that writes none, or that the bridge no longer lists (set_scene rejects it), is `hue`, as no light is
reached. A room or zone is
no device of its own: the dispatcher classes it by its members (bridge.expand_group), a light with no entity in Home
Assistant included. Home Assistant registers every bridge device with its product data when the entry loads, so a
device is placed once it has an entity: nothing is provisional (no Unplaced), and with no `harms` entry (no Hue
action is timed) nothing needs to be.

Every adapter's scope holds LEVELS; why `other` sits where it does is in internals.md (Device classes), index.md
(Other brands) and the step 8 PR body.
"""

from aiohue.v2.models.resource import ResourceTypes
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .bridge import bridge_api, light_device, resource_id
from ...core.models import Target
from ...core.scope import DoesntWork, experimental, verified

# The manufacturer core's hue integration registers Signify's own devices with (homeassistant/components/hue/v2/
# device.py), lights and bridge alike: internals.md, Tested behavior, Device strings.
SIGNIFY = "Signify Netherlands B.V."

HUE = "hue"
OTHER = "other"  # the default class, never Verified (IntegrationInfo.default_class)
SMART_SCENE = "smart_scene"
CLASSES = frozenset({HUE, OTHER, SMART_SCENE})

# Every adapter's levels: Verified on Hue, whose lights every record ran on; `other` Experimental on every action, as
# none passes docs/evidence.md's Documented test (plan Decision 2): the bridge picks the Zigbee call, and other brands
# are known to depart from the calls it plausibly sends (internals.md, Device classes; the step 8 PR body).
LEVELS = verified(HUE) | experimental(OTHER)

_PAGE = "https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/hue/index.md"
SET_SCENE_DOESNT_WORK = {
    # Not harmful: a refusal sends nothing, and a wrong scene would show at once (docs/evidence.md).
    SMART_SCENE: DoesntWork(
        what="Hue smart scenes",
        reason="A smart (All-Day) scene changes with the time of day, so it has no fixed settings to write",
        source=_PAGE + "#hue-smart-scenes",
        harms=False,
    ),
}


def device_class(device: dr.DeviceEntry) -> str:
    """A light's class by its registry device: `hue` for Signify's, else the default."""
    return HUE if device.manufacturer == SIGNIFY else OTHER


def capability(hass: HomeAssistant, target: Target) -> str | None:
    """Hue's IntegrationInfo.capability: a light's class by its device, a scene's by the lights it writes; None for a
    light with no device, or a scene with a light the bridge doesn't list or Home Assistant has no device for."""
    if target.domain == "scene":
        return _scene_class(hass, target)
    return None if target.device is None else device_class(target.device)


def _scene_class(hass: HomeAssistant, target: Target) -> str | None:
    api = bridge_api(target)
    rid = resource_id(target)
    if api.scenes.smart_scene.get(rid) is not None:
        return SMART_SCENE
    if (scene := api.scenes.scene.get(rid)) is None:
        return HUE
    found = set()
    for action in scene.actions:
        if action.target.rtype != ResourceTypes.LIGHT:
            continue
        if (light := api.lights.get(action.target.rid)) is None:
            return None
        if (device := light_device(hass, target, light)) is None:
            return None
        found.add(device_class(device))
    return OTHER if OTHER in found else HUE
