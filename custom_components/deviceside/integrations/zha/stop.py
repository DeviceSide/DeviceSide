"""ZHA stop: halt the bulb's fades and hue cycle with level Stop and StopMoveStep, remember where they halted, and
refresh HA."""

import asyncio
import logging
from typing import ClassVar

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import Unauthorized

from . import zcl
from .addressing import unsupported_reason
from .fade import end_key, has_color, hue_moves, refresh, send_each, soft_off_restores, transition_cache, units
from ...core.adapter import Adapter, DeadlinePassed
from ...core.models import EntityResult, Request, Status, Target
from ...core.runtime import get_runtime
from ...core.scope import AdapterScope, verified
from ...core.transition import BRIGHTNESS, SATURATION, TransitionCache, hs_color, light_brightness, lit

_LOGGER = logging.getLogger(__name__)

_LEVEL_STOP = (zcl.LEVEL_CLUSTER, zcl.STOP, {})
_STOP_MOVE_STEP = (zcl.COLOR_CLUSTER, zcl.STOP_MOVE_STEP, {"options_mask": 0, "options_override": 0})


class ZHAStop(Adapter[Request]):
    """Send level Stop to each lit light, with StopMoveStep where a saturation or hue move of ours runs, record the
    predicted values as where it halted, and refresh HA at once.

    Members from one ZHA group get one groupcast per command, as in a raise or lower. The stop replaces the light's
    pending end refreshes and soft off restore, so a halted soft off leaves the light on at the halted level, as on
    Hue. Raw commands leave ZHA's transitioning flag down, so the refresh reads the halted values. A light with nothing
    lit (off, and no soft off of ours fading it) is unchanged with off and nothing is sent to it.
    """

    action: ClassVar[str] = "stop"
    integration: ClassVar[str] = "zha"
    scope: ClassVar[AdapterScope] = AdapterScope(experimental=True, domains=verified("light"), max_concurrency=2)

    def supports(self, hass: HomeAssistant, request: Request, target: Target) -> str | None:
        return super().supports(hass, request, target) or unsupported_reason(target)

    async def execute(self, hass: HomeAssistant, request: Request, targets: list[Target]) -> list[EntityResult]:
        cache = transition_cache(hass)
        runs = [self._unit(hass, request, cache, gid, lights) for gid, lights in units(hass, targets)]
        return [result for batch in await asyncio.gather(*runs) for result in batch]

    async def _unit(
        self, hass: HomeAssistant, request: Request, cache: TransitionCache, gid: int | None, lights: list[Target]
    ) -> list[EntityResult]:
        halting = lit(cache, lights)
        halting_ids = {light.entity_id for light in halting}
        off = [
            self.result(light, Status.UNCHANGED, detail="off") for light in lights if light.entity_id not in halting_ids
        ]
        if not halting:
            return off
        # A halt is predicted only where a move of ours ran: elsewhere the refresh is right at once.
        halts = {
            BRIGHTNESS: {
                light.entity_id: light_brightness(cache, light)
                for light in halting
                if cache.tracks(light.entity_id, BRIGHTNESS)
            },
            SATURATION: {
                light.entity_id: cache.value(light.entity_id, SATURATION, (hs_color(light) or (0, 0))[1])
                for light in halting
                if cache.tracks(light.entity_id, SATURATION)
            },
        }
        cycling = hue_moves(hass)
        color = [
            light
            for light in halting
            if has_color(light) and (light.entity_id in halts[SATURATION] or light.entity_id in cycling)
        ]
        failed: dict[str, Exception] = {}
        try:
            async with self.slot(hass):
                async with cache.recording(
                    (light_id, attribute) for attribute, values in halts.items() for light_id in values
                ):
                    before = {
                        (light_id, attribute): cache.forget(light_id, attribute)
                        for attribute, values in halts.items()
                        for light_id in values
                    }
                    recorded = {
                        (light_id, attribute): cache.stopped(light_id, attribute, value)
                        for attribute, values in halts.items()
                        for light_id, value in values.items()
                    }
                    if color:
                        failed |= await send_each(
                            hass,
                            gid,
                            color,
                            dict.fromkeys((light.entity_id for light in color), _STOP_MOVE_STEP),
                            request.context,
                        )
                    failed |= await send_each(
                        hass, gid, halting, dict.fromkeys(halting_ids, _LEVEL_STOP), request.context
                    )
                    # A light that didn't halt keeps what it had, unless a move or stop since owns the entry.
                    for (light_id, attribute), transition in recorded.items():
                        if light_id in failed and cache.live(light_id, attribute) is transition:
                            cache.forget(light_id, attribute)
                            cache.restore(before[(light_id, attribute)])
        except DeadlinePassed:
            _LOGGER.warning("stop on zha timed out for %s", ", ".join(sorted(halting_ids)))
            return [*off, *(self.result(light, Status.REJECTED, detail="timeout") for light in halting)]
        if errors := {light_id: err for light_id, err in failed.items() if not isinstance(err, Unauthorized)}:
            _LOGGER.warning(
                "stop on zha failed for %s", ", ".join(f"{light_id}: {err!r}" for light_id, err in errors.items())
            )
        halted = [light for light in halting if light.entity_id not in failed]
        halted_ids = {light.entity_id for light in halted}
        cycling.difference_update(halted_ids)
        soft_off_restores(hass).difference_update(halted_ids)
        runtime = get_runtime(hass)
        for light in halted:
            for attribute in (BRIGHTNESS, SATURATION):
                runtime.schedule(hass, end_key(light, attribute), [])  # cancels the fades' end refreshes and restore
        await asyncio.gather(*(refresh(hass, light, request.context) for light in halted))
        return [*off, *(self._result(light, failed) for light in halting)]

    def _result(self, light: Target, failed: dict[str, Exception]) -> EntityResult:
        if (err := failed.get(light.entity_id)) is None:
            return self.result(light, Status.SENT)
        return self.result(
            light, Status.REJECTED, detail="admin_required" if isinstance(err, Unauthorized) else "error"
        )
