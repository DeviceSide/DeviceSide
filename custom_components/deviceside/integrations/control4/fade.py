"""Control4 raise and lower brightness: one RAMP_TO_LEVEL from the level the Director reports
(docs/integrations/control4/internals.md)."""

import asyncio
import logging
from typing import ClassVar

from homeassistant.core import HomeAssistant

from .director import (
    RAMP_LIMITS,
    DirectorAdapter,
    LightLevel,
    item_lock,
    own_ramp_end,
    ramp_to_level,
    read_level,
    settle,
    stop_brightness,
    unsupported_reason,
    whole_percent,
)
from ...core.level_fade import LevelFade, Reading
from ...core.models import Target
from ...core.scope import AdapterScope, experimental
from ...core.transition import BRIGHTNESS

_LOGGER = logging.getLogger(__name__)


def fade_scope() -> AdapterScope:
    return AdapterScope(experimental=True, domains=experimental("light"), fields=experimental(BRIGHTNESS))


class Control4Fade(DirectorAdapter, LevelFade):
    """The Director's level is up to a second old mid-ramp, so a ramp is halted and read again before a move is
    sized, unless it is the adapter's own ramp to this end (director.own_ramp_end)."""

    integration: ClassVar[str] = "control4"
    fade_limits = RAMP_LIMITS

    def unaddressable(self, target: Target) -> str | None:
        return unsupported_reason(target)

    def guard(self, hass: HomeAssistant, target: Target) -> asyncio.Lock:
        return item_lock(hass, target)

    async def read(self, hass: HomeAssistant, target: Target, end: float) -> Reading:
        level = await read_level(hass, target)
        if level.ramping:
            own = own_ramp_end(hass, target)
            if level.target == own == whole_percent(end):
                return Reading(level.on, level.brightness, heading_there=True)
            _LOGGER.debug(
                "%s: ramping to %s, not the adapter's own to %s (last sent %s); halting it",
                target.reported_id,
                level.target,
                whole_percent(end),
                own,
            )
            level = await self._halted(hass, target)
        return Reading(level.on, level.brightness)

    async def _halted(self, hass: HomeAssistant, target: Target) -> LightLevel:
        # Waits inside the lock and slot, so only the brief schedule.
        await stop_brightness(hass, target)
        level = await settle(target, lambda: read_level(hass, target), lambda level: not level.ramping, brief=True)
        if level.ramping:
            _LOGGER.debug("%s: director still shows a ramp; moving from the level it reports", target.reported_id)
        return level

    async def fade_to(self, hass: HomeAssistant, target: Target, end: float, seconds: float) -> None:
        await ramp_to_level(hass, target, end, seconds)
