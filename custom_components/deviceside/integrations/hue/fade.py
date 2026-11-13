"""Hue raise and lower, brightness and saturation: one write to the light or room, with the end point and a duration
the bridge runs alone. Each action's adapter is a HueFade."""

import logging
from dataclasses import dataclass, field
from functools import partial
from statistics import mean
from typing import TYPE_CHECKING, Any, ClassVar

from homeassistant.core import HomeAssistant
from homeassistant.util.color import color_hs_to_xy, color_xy_to_hs

from .bridge import bridge_api, controller, named, resource_id, set_state
from .colors import clamp_to_gamut
from .report_filter import report_filter
from .transition_cache import MIN_BRIGHTNESS_STEP, XY, HueTransitionCache, transition_cache
from ...actions.ramp import RampRequest
from ...core.adapter import Adapter
from ...core.errors import Reason
from ...core.models import EntityResult, Status, Target
from ...core.scope import AdapterScope, verified
from ...core.transition import BRIGHTNESS, SATURATION, TransitionCache, lit_where, reported_brightness

if TYPE_CHECKING:
    from aiohue.v2 import HueBridgeV2
    from aiohue.v2.models.grouped_light import GroupedLight
    from aiohue.v2.models.light import Light

_LOGGER = logging.getLogger(__name__)


def room_lights(api: HueBridgeV2, target: Target) -> list[Light]:
    """The room's lights that dim, hidden ones included: the bridge fades them all."""
    return [light for light in api.groups.grouped_light.get_lights(resource_id(target)) if light.dimming]


def predicted_brightness(cache: TransitionCache, light: Light) -> float:
    """A room light's predicted brightness in percent, 0 while off."""
    return cache.value(light.id, BRIGHTNESS, light.dimming.brightness if light.on.on else 0.0)


def light_xy(cache: HueTransitionCache, light: Light) -> XY:
    """A color light's predicted xy: the bridge reports an xy fade's end at once."""
    return cache.xy(light.id, (light.color.xy.x, light.color.xy.y))


def lit(cache: TransitionCache, lights: list[Light]) -> list[Light]:
    """The lights that are on, or predicted above 0 %: aiohue hears a light turn on late, and a soft off reports off
    at its start."""
    return lit_where(cache, lights, lambda light: light.id, lambda light: light.on.on)


def in_soft_off(cache: TransitionCache, light_id: str) -> bool:
    """Whether a move of ours is still fading the light to off, which the bridge won't take a dimming stop for."""
    return (transition := cache.running(light_id, BRIGHTNESS)) is not None and transition.target == 0


@dataclass(frozen=True, slots=True)
class Fade:
    """One attribute's fade: each moving light's start and end, how long the bridge takes, and the write's fields
    (aiohue's set_state arguments); for saturation, each moving light's start and end xy."""

    attribute: str
    starts: dict[str, float]
    ends: dict[str, float]
    duration: float
    write: dict[str, Any]
    paths: dict[str, tuple[XY, XY]] = field(default_factory=dict)


def fade_scope(attribute: str) -> AdapterScope:
    """predicted_state is brightness's only: HA is shown the bridge's xy for saturation either way."""
    return AdapterScope(
        fields=verified(attribute),
        options=frozenset({"predicted_state"}) if attribute == BRIGHTNESS else frozenset(),
        native_groups=True,
    )


class HueFade(Adapter[RampRequest]):
    """Write the limit (or range end) with a duration for the distance left; the bridge runs the fade.

    Predictions live per light and attribute (transition_cache), so a move after a stop continues from where the light
    halted. A room is moved with one grouped_light write, so its lights converge on the end point together; each
    light's transition is recorded from its own start, and the room's start is the average of its moving lights, so
    moving one light mid room-move starts from where it really is. A move with nothing left to make (already at or past
    the limit) is unchanged with at_limit and nothing is sent.

    Brightness: raising turns the light on. Lowering to 0 % is a plain soft off, on: false with the duration and no
    brightness, so the bridge keeps the stored brightness for the next plain on. A light the bridge says can't dim is
    unchanged with fields_dropped. With predicted_state on, HA holds the start brightness while the fade runs and shows
    the end once it has (report_filter), and lowering a light or room with none lit is unchanged with off.

    Saturation is HA's hs saturation, as on Z2M and ZHA: an xy write, of the light's current hue at the end saturation
    (the hue of the mean xy, for a room, as HA shows a room), clamped to the light's gamut; a room's lights are each
    clamped by the bridge. The write has no on, so only lit lights in color move: a light or room with none that is lit
    is unchanged with off, one with no color light with fields_dropped, and a room's lights without color are passed
    by. HA is shown the bridge's xy, the end at once, with predicted_state on too.
    """

    integration: ClassVar[str] = "hue"

    def supports(self, hass: HomeAssistant, request: RampRequest, target: Target) -> str | None:
        if (reason := super().supports(hass, request, target)) is not None:
            return reason
        if (api := bridge_api(target)) is None:
            return "bridge_v1"
        if target.is_group and not api.groups.grouped_light.get_lights(resource_id(target)):
            return Reason.EMPTY_GROUP
        return None

    async def execute(self, hass: HomeAssistant, request: RampRequest, targets: list[Target]) -> list[EntityResult]:
        cache = transition_cache(hass)

        async def send(target: Target) -> EntityResult:
            api = bridge_api(target)
            writer = controller(api, target)
            rid = resource_id(target)
            if (resource := writer.get(rid)) is None:
                return self.result(target, Status.REJECTED, detail="not_on_bridge")
            # Before the write, as stop does: the bridge may report the fade's end before the write returns.
            reports = report_filter(hass, target)
            if request.attribute == BRIGHTNESS:
                fade = brightness_fade(cache, request, target, api, resource, predicted_state=reports.hiding)
            else:
                fade = saturation_fade(cache, request, target, api, resource)
            if isinstance(fade, str):
                return self.result(target, Status.UNCHANGED, detail=fade)
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug(
                    "Hue fade of %s: %s from %s to %s",
                    target.entity_id,
                    fade.attribute,
                    named(hass, fade.starts),
                    named(hass, fade.ends),
                )
            write = partial(
                set_state,
                hass,
                writer,
                rid,
                target.reported_id,
                **fade.write,
                transition_time=round(fade.duration * 1000),
            )
            async with cache.recording((light_id, fade.attribute) for light_id in fade.starts) as recorded:
                for light_id, start in fade.starts.items():
                    moving = cache.moving(light_id, fade.attribute, start, fade.ends[light_id], fade.duration)
                    if (path := fade.paths.get(light_id)) is not None:
                        cache.path(light_id, moving, *path)
                await write()
            # A stop that landed during the PUT owns the lights now: nothing is left to end.
            if all(
                cache.live(light_id, fade.attribute) is recorded[(light_id, fade.attribute)] for light_id in fade.starts
            ):
                reports.fading(fade.attribute, fade.ends, fade.duration)
            return self.result(target, Status.SENT)

        return await self.gather(hass, targets, send)


def brightness_fade(
    cache: HueTransitionCache,
    request: RampRequest,
    target: Target,
    api: HueBridgeV2,
    resource: Light | GroupedLight,
    *,
    predicted_state: bool,
) -> Fade | str:
    """The brightness fade toward the limit; fields_dropped for a light that can't dim, at_limit when there is none left
    to make.

    Lowering a light or room with none lit answers off with predicted_state on, as saturation does; with it off, the
    move plans from what aiohue reports, 0 % for an off light, so at_limit."""
    if resource.dimming is None:
        return "fields_dropped"
    up, limit = request.up, request.end()
    if target.is_group:
        lights = room_lights(api, target)
        starts = {light.id: predicted_brightness(cache, light) for light in lights}
        # Raising turns every light on, so the off ones fade in from the bottom; lowering passes them by.
        lit_lights = lit(cache, lights)
        moving = [light.id for light in (lights if up else lit_lights)]
        current = mean(starts[light.id] for light in lit_lights or lights) if lights else 0.0
    else:
        rid = resource_id(target)
        lit_lights = lit(cache, [resource])
        starts = {rid: cache.value(rid, BRIGHTNESS, reported_brightness(target))}
        moving, current = [rid], starts[rid]
    if not up and predicted_state and not lit_lights:
        return "off"
    if (limit - current if up else current - limit) < MIN_BRIGHTNESS_STEP:
        return "at_limit"
    duration = abs(limit - current) / 100 * request.sweep_time
    write = {"on": False} if limit == 0 else {"on": True if up else None, "brightness": limit}
    return Fade(
        BRIGHTNESS, {light_id: starts[light_id] for light_id in moving}, dict.fromkeys(moving, limit), duration, write
    )


def saturation_fade(
    cache: HueTransitionCache, request: RampRequest, target: Target, api: HueBridgeV2, resource: Light | GroupedLight
) -> Fade | str:
    """The saturation fade toward the limit at the current hue, as an xy fade; fields_dropped with no color light, off
    with none lit, at_limit when there is none left to make."""
    lights = api.groups.grouped_light.get_lights(resource_id(target)) if target.is_group else [resource]
    if not (color := [light for light in lights if light.color is not None]):
        return "fields_dropped"
    if not (movers := lit(cache, color)):
        return "off"
    up, limit = request.up, request.end()
    xys = {light.id: light_xy(cache, light) for light in movers}
    starts = {light.id: cache.value(light.id, SATURATION, color_xy_to_hs(*xys[light.id])[1]) for light in movers}
    current = mean(starts.values())
    if (limit - current if up else current - limit) < MIN_BRIGHTNESS_STEP:
        return "at_limit"
    hue = color_xy_to_hs(mean(x for x, _ in xys.values()), mean(y for _, y in xys.values()))[0]
    xy = color_hs_to_xy(hue, limit)
    paths = {light.id: (xys[light.id], clamp_to_gamut(light, xy)) for light in movers}
    duration = abs(limit - current) / 100 * request.sweep_time
    # A room's lights are each clamped to their own gamut by the bridge.
    write = {"color_xy": xy if target.is_group else paths[resource.id][1]}
    return Fade(SATURATION, starts, dict.fromkeys(starts, limit), duration, write, paths)
