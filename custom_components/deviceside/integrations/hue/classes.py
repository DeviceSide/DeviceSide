"""Hue's device classes (docs/evidence.md, Device classes): whose firmware a light behind the bridge runs.

DeviceSide sends the bridge the same CLIP v2 request for every light; the bridge picks the Zigbee call, and nothing in
CLIP v2 shows which one it picked or routes a light by any field DeviceSide could read (internals.md, Device
classes). So the class keys on the device's identity, the manufacturer core's hue integration registers from the
bridge's `product_data` (a model ID too, once a split-off needs one):

- `hue`: Signify's own lights, which every record ran on.
- `other`, the default class: every other maker's light the bridge has paired, Friends of Hue certified ones
  included, as certification isn't Signify's firmware and no record reaches one.
- `gledopto`: Gledopto's lights, any model, split off `other` as the bridge reports their color temperature mode
  wrong, so get_attributes doesn't serve them (internals.md, Device classes; research/2026-11-25-color-mode-misread.md).
- `smart_scene`: an All-Day scene, which has no fixed settings to write (set_scene's no known method entry).

A scene is classed by the lights it writes: the weakest of their classes on set_scene (LEVELS), a split-off before
`other` on a tie, as its refusals reach the scene too, since set_scene's call reaches each light; one that writes
none, or that the bridge no longer lists (set_scene rejects it), is `hue`, as no light is reached. A room or zone is
no device of its own: the dispatcher classes it by its members (bridge.expand_group), a light with no entity in Home
Assistant included. Home Assistant
registers every bridge device with its product data when the entry loads, so a device is placed once it has an entity:
nothing is provisional (no Unplaced), and as no Hue action's failure harms (none is timed) nothing needs to be.

Every adapter's scope holds LEVELS, but get_attributes's holds GET_ATTRIBUTES_LEVELS; why each class sits where it does
is in internals.md (Device classes) and index.md.
"""

from aiohue.v2.models.resource import ResourceTypes
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .bridge import bridge_api, light_device, resource_id
from ...const import DOCS_URL
from ...core.models import Target
from ...core.scope import OTHER, Level, NoKnownMethod, OnDomains, documented, verified

# The manufacturer core's hue integration registers Signify's own devices with (homeassistant/components/hue/v2/
# device.py), lights and bridge alike: internals.md, Tested behavior, Device strings.
SIGNIFY = "Signify Netherlands B.V."
HUE = "hue"
GLEDOPTO = "gledopto"
SMART_SCENE = "smart_scene"
# The split-off makers, by the Zigbee manufacturer string the bridge passes on as `product_data.manufacturer_name`,
# casefolded and matched in any case, as Zigbee2MQTT's Gledopto rule does: Gledopto's `GLEDOPTO` (src/devices/
# gledopto.ts, zigbee-herdsman-converters at the commit internals.md, Device classes, cites). The class is named for it.
# Each class's domains (IntegrationInfo.classes): a light, Hue's smart plug included, which the bridge shows as one,
# and a scene, classed by the lights it writes; a smart scene is a scene alone.
CLASSES = {
    HUE: frozenset({Platform.LIGHT, Platform.SCENE}),
    OTHER: frozenset({Platform.LIGHT, Platform.SCENE}),
    GLEDOPTO: frozenset({Platform.LIGHT, Platform.SCENE}),
    SMART_SCENE: frozenset({Platform.SCENE}),
}

# Every adapter's levels: Verified on Hue, whose lights every record ran on; Documented on `other`, on a bridge's one
# request (docs/evidence.md, Levels): DeviceSide sends every light the same CLIP v2 light update, which Hue Smooth
# Dimming sent every brand for brightness fades, stop, scenes and attribute writes, and no Hue action's failure harms
# (internals.md, Device classes). Gledopto takes `other`'s levels on every action but get_attributes.
LEVELS = verified(HUE) | documented(OTHER, GLEDOPTO)
# get_attributes reads `mirek_valid` for color temperature mode, which the bridge reports wrong for Gledopto lights
# (core #62497, #93459; research/2026-11-25-color-mode-misread.md): not built there (a NotBuilt entry is only for an
# action whose failure harms).
GET_ATTRIBUTES_LEVELS = verified(HUE) | documented(OTHER)

_PAGE = DOCS_URL + "docs/integrations/hue/index.md"
SET_SCENE_NO_KNOWN_METHOD = {
    # No known method: no known call can write a smart scene's settings, as it has none fixed, a limit of the scene,
    # not a call unbuilt. set_scene's failure doesn't harm (Action.failure_harms): a wrong scene shows at once.
    SMART_SCENE: NoKnownMethod(
        what="Hue smart scenes",
        reason="A smart (All-Day) scene changes with the time of day, so it has no fixed settings to write",
        source=_PAGE + "#hue-smart-scenes",
    ),
}


def device_class(device: dr.DeviceEntry) -> str:
    """A light's class by its registry device: `hue` for Signify's, a split-off maker's own, else the default."""
    if device.manufacturer == SIGNIFY:
        return HUE
    return GLEDOPTO if (device.manufacturer or "").casefold() == GLEDOPTO else OTHER


def capability(hass: HomeAssistant, target: Target) -> str | None:
    """Hue's IntegrationInfo.capability: a light's class by its device, a scene's by the lights it writes; None for a
    light with no device, or a scene with a light the bridge doesn't list or Home Assistant has no device for."""
    if target.domain == Platform.SCENE:
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
    return min(found, key=lambda name: (_scene_level(name), name == OTHER, name), default=HUE)


def _scene_level(name: str) -> Level:
    # A class's set_scene level, as AdapterScope.class_level reads it: Labs where LEVELS has no entry for scenes.
    entry = LEVELS.get(name)
    if isinstance(entry, OnDomains):
        return entry.level if Platform.SCENE in entry.domains else Level.LABS
    return Level.LABS if entry is None else entry
