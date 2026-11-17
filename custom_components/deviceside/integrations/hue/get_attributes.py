"""Hue get_attributes: brightness, color temperature and color from aiohue's cache of the bridge, lights off too."""

from collections.abc import Iterable
from statistics import mean
from typing import TYPE_CHECKING, ClassVar

from homeassistant.components.light import ATTR_COLOR_MODE, ColorMode
from homeassistant.const import STATE_ON, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util.color import color_temperature_mired_to_kelvin

from .bridge import bridge_api, resource_id
from .classes import LEVELS
from .fade import light_xy, lit
from .transition_cache import HueTransitionCache, transition_cache
from ...core.adapter import Adapter
from ...core.color import xy_row
from ...core.errors import Reason
from ...core.models import EntityResult, Request, Status, Target
from ...core.scope import AdapterScope
from ...core.transition import BRIGHTNESS

if TYPE_CHECKING:
    from aiohue.v2 import HueBridgeV2
    from aiohue.v2.models.light import Light


def light_row(hass: HomeAssistant, api: HueBridgeV2, cache: HueTransitionCache, light: Light) -> dict:
    """One light's attributes, its brightness and color predicted while a move runs (the bridge reports the end
    value)."""
    row = attributes(hass, api, cache, [light])
    if light.dimming:
        row["brightness"] = round(cache.value(light.id, BRIGHTNESS, light.dimming.brightness), 1)
    return row


def in_color_temp_mode(hass: HomeAssistant, api: HueBridgeV2, light: Light) -> bool:
    """Whether the light is in color temperature mode, as core's hue integration decides it (v2/light.py,
    color_temp_active; internals.md, Device classes): a certified light's `mirek_valid`; for one that isn't, which
    doesn't set the flag reliably, the color mode core shows for it while it is on, which follows core's own last
    command (so not a DeviceSide set_attributes write, nor the Hue app's), else the flag. Never with no mirek, or 0,
    which core treats as no value (and which would divide by zero)."""
    if not (feature := light.color_temperature) or not feature.mirek:
        return False
    if (device := api.devices.get(light.owner.rid)) is None or device.product_data.certified:
        return feature.mirek_valid
    entity_id = er.async_get(hass).async_get_entity_id(Platform.LIGHT, "hue", light.id)
    if (state := hass.states.get(entity_id) if entity_id else None) is None or state.state != STATE_ON:
        # Core shows no color mode for a light that is off, or one it has no entity for: the bridge's flag is all
        # there is, as for a certified light.
        return feature.mirek_valid
    return state.attributes.get(ATTR_COLOR_MODE) == ColorMode.COLOR_TEMP


def attributes(hass: HomeAssistant, api: HueBridgeV2, cache: HueTransitionCache, lights: Iterable[Light]) -> dict:
    """The lights' attributes under HA's names, each averaged over the lights that have it.

    Brightness is Hue's percent, as hue_dimmer returned it, so a read can be written back with set_attributes.
    Color temperature counts only lights in color temperature mode (in_color_temp_mode), as core's hue integration
    decides it. Color is each light's predicted xy, so a light mid saturation fade reads where it is.
    """
    lights = list(lights)
    row: dict = {}
    if levels := [light.dimming.brightness for light in lights if light.dimming]:
        row["brightness"] = round(mean(levels), 1)
    kelvins = [
        color_temperature_mired_to_kelvin(light.color_temperature.mirek)
        for light in lights
        if in_color_temp_mode(hass, api, light)
    ]
    if kelvins:
        row["color_temp_kelvin"] = round(mean(kelvins))
    if xys := [light_xy(cache, light) for light in lights if light.color]:
        row.update(xy_row(round(mean(x for x, _ in xys), 4), round(mean(y for _, y in xys), 4)))
    return row


class HueGetAttributes(Adapter[Request]):
    """One row per target from aiohue's cache, which keeps what the bridge last reported after HA shows a light off.

    A room or zone row follows the bridge and core's hue integration: brightness is the grouped_light's (the
    average of the lights that are on), color temperature and color average the lights that are on. With every
    light off the bridge reports nothing useful, so the row averages all the room's lights. Brightness and color read
    through the transition cache, so a light or room mid-move reports where it is, not the end value the bridge
    reports; a room then averages its lit lights' predictions.
    """

    action: ClassVar[str] = "get_attributes"
    integration: ClassVar[str] = "hue"
    scope: ClassVar[AdapterScope] = AdapterScope(capabilities=LEVELS, confirmable=True, native_groups=True)

    def supports(self, hass: HomeAssistant, request: Request, target: Target) -> str | None:
        if (reason := super().supports(hass, request, target)) is not None:
            return reason
        if target.is_group and not bridge_api(target).groups.grouped_light.get_lights(resource_id(target)):
            return Reason.EMPTY_GROUP
        return None

    async def execute(self, hass: HomeAssistant, request: Request, targets: list[Target]) -> list[EntityResult]:
        cache = transition_cache(hass)
        results = []
        for target in targets:
            api = bridge_api(target)
            if not target.is_group:
                if (light := api.lights.get(resource_id(target))) is None:
                    results.append(self.result(target, Status.REJECTED, detail="not_on_bridge"))
                else:
                    results.append(self.result(target, Status.CONFIRMED, data=light_row(hass, api, cache, light)))
                continue

            grouped = api.groups.grouped_light
            lights = grouped.get_lights(resource_id(target))
            on = [light for light in lights if light.on.on]
            row = attributes(hass, api, cache, on or lights)
            dimmable = [light for light in lights if light.dimming]
            if any(cache.tracks(light.id, BRIGHTNESS) for light in dimmable):
                # Mid-move the bridge reports end values; average the lit lights' predictions instead. A light
                # still moving counts as lit: a room moved up from all off is on before aiohue hears so.
                lights_lit = lit(cache, dimmable) or dimmable
                predicted = [cache.value(light.id, BRIGHTNESS, light.dimming.brightness) for light in lights_lit]
                row["brightness"] = round(mean(predicted), 1)
            elif on and (group := grouped.get(resource_id(target))) is not None and group.dimming is not None:
                row["brightness"] = round(group.dimming.brightness, 1)
            results.append(self.result(target, Status.CONFIRMED, data=row))
        return results
