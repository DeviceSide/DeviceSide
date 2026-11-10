"""Hue stop: halt the bridge's fades and remember where they halted, which the bridge reports late or never."""

import asyncio
from typing import TYPE_CHECKING, ClassVar

from homeassistant.core import HomeAssistant

from .bridge import bridge_api, controller, put, resource_id, stops, xy_halt
from .fade import in_soft_off, light_brightness, light_xy, lit, reported_brightness, room_lights
from .report_filter import report_filter
from .transition_cache import XY, transition_cache
from ...core.adapter import Adapter
from ...core.models import EntityResult, Request, Status, Target
from ...core.scope import AdapterScope
from ...core.transition import BRIGHTNESS, SATURATION, TransitionCache

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from aiohue.v2 import HueBridgeV2
    from aiohue.v2.controllers.groups import GroupedLightController
    from aiohue.v2.controllers.lights import LightsController


class HueStop(Adapter[Request]):
    """Send a dimming stop to the light or room, and record the predicted brightness as where it halted.

    A light whose saturation fade of ours is still running is also sent its predicted xy with a duration of 0, in the
    same PUT: the bridge has no color delta stop. A room's lights then each get their own PUT, at their own prediction.
    The bridge refuses a dimming stop during a soft off, so a light our move is fading to off is cut instead with
    on: true and its predicted brightness, no duration. A room in one is cut light by light, each at its own
    prediction. A room's halt is recorded per lit light, where predictions live. A light or room with nothing lit (off,
    or fading off from elsewhere, which can't be predicted) is unchanged with off and nothing is sent. With
    predicted_state on, HA is shown the halted brightness at once (report_filter).
    """

    action: ClassVar[str] = "stop"
    integration: ClassVar[str] = "hue"
    scope: ClassVar[AdapterScope] = AdapterScope(
        experimental=True, options=frozenset({"predicted_state"}), native_groups=True
    )

    def supports(self, hass: HomeAssistant, request: Request, target: Target) -> str | None:
        if (reason := super().supports(hass, request, target)) is not None:
            return reason
        if (api := bridge_api(target)) is None:
            return "bridge_v1"
        if (resource := controller(api, target).get(resource_id(target))) is not None and resource.dimming is None:
            return "not_dimmable"
        return None

    async def execute(self, hass: HomeAssistant, request: Request, targets: list[Target]) -> list[EntityResult]:
        cache = transition_cache(hass)

        async def send(target: Target) -> EntityResult:
            api = bridge_api(target)
            writer = controller(api, target)
            rid = resource_id(target)
            if (resource := writer.get(rid)) is None:
                return self.result(target, Status.REJECTED, detail="not_on_bridge")
            reports = report_filter(hass, target)
            if target.is_group:
                lights = lit(cache, room_lights(api, target))
                brightness = {light.id: light_brightness(cache, light) for light in lights}
            else:
                lights = lit(cache, [resource])
                brightness = {rid: cache.value(rid, BRIGHTNESS, reported_brightness(target))} if lights else {}
            if not brightness:
                return self.result(target, Status.UNCHANGED, detail="off")
            # A finished saturation fade is held at its end by the bridge already.
            fading = [light for light in lights if light.color is not None and cache.running(light.id, SATURATION)]
            saturation = {light.id: cache.value(light.id, SATURATION, 0.0) for light in fading}
            xys = {light.id: light_xy(cache, light) for light in fading}
            write = stop_write(hass, cache, api, writer, rid, brightness, xys, target.reported_id)
            keys = [(light_id, BRIGHTNESS) for light_id in brightness] + [(light_id, SATURATION) for light_id in xys]
            async with cache.recording(keys):
                for light_id, value in brightness.items():
                    cache.stopped(light_id, BRIGHTNESS, value)
                for light_id, value in saturation.items():
                    cache.path(light_id, cache.stopped(light_id, SATURATION, value), xys[light_id], xys[light_id])
                await write
            reports.halted(BRIGHTNESS, brightness)
            reports.halted(SATURATION, saturation)
            return self.result(target, Status.SENT)

        return await self.gather(hass, targets, send)


def stop_write(
    hass: HomeAssistant,
    cache: TransitionCache,
    api: HueBridgeV2,
    writer: LightsController | GroupedLightController,
    rid: str,
    brightness: dict[str, float],
    xys: dict[str, XY],
    entity_id: str | None = None,
) -> Awaitable:
    """One write to the light or room, or one per light while any is in our soft off, which the bridge refuses a
    dimming stop for (on: true at its predicted brightness ends it there instead), or in a saturation fade of ours,
    halted at its own predicted xy. A write to rid itself is traced as entity_id, the caller's target."""
    fading_off = {light_id for light_id in brightness if in_soft_off(cache, light_id)}
    if not fading_off and not xys:
        return put(hass, api, writer, rid, stops([BRIGHTNESS]), entity_id)

    def body(light_id: str) -> dict:
        halt = cut(brightness[light_id]) if light_id in fading_off else stops([BRIGHTNESS])
        return halt | (xy_halt(xys[light_id]) if light_id in xys else {})

    return asyncio.gather(
        *(
            put(hass, api, api.lights, light_id, body(light_id), entity_id if light_id == rid else None)
            for light_id in brightness
        )
    )


def cut(brightness: float) -> dict:
    """The PUT body that ends a soft off at this brightness, which the bridge takes in place of a dimming stop."""
    return {"on": {"on": True}, "dimming": {"brightness": brightness}}
