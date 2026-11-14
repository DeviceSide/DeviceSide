"""Control4 raise and lower brightness: one RAMP_TO_LEVEL with a time for the distance left, from the level the
Director reports. Each action's adapter is a Control4Fade."""

import asyncio
import logging
from contextvars import ContextVar
from typing import TYPE_CHECKING, ClassVar

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
from ...core.level_fade import LevelFade
from ...core.models import EntityResult, Target
from ...core.scope import AdapterScope, experimental
from ...core.transition import BRIGHTNESS

if TYPE_CHECKING:
    from ...actions.ramp import RampRequest

_LOGGER = logging.getLogger(__name__)
# The whole-percent level the call in flight ramps to, and whether the target's read found the adapter's own ramp
# already heading there.
_ASKED: ContextVar[int | None] = ContextVar("control4_asked_end", default=None)
_RUNNING: ContextVar[bool] = ContextVar("control4_own_ramp_running", default=False)
# RAMP_TO_LEVEL is sent a whole percent.
MIN_STEP = 1.0


def fade_scope() -> AdapterScope:
    return AdapterScope(experimental=True, domains=experimental("light"), fields=experimental(BRIGHTNESS))


class Control4Fade(DirectorAdapter, LevelFade):
    """A read of the Director's level, then one RAMP_TO_LEVEL to the limit (or range end) with a time for the
    distance left; the light runs the ramp (core.level_fade).

    The Director reports the level mid-ramp only about once a second, and exactly once a ramp has halted
    (docs/integrations/control4/internals.md, Tested behavior). So a move is never sized from a mid-ramp level. A
    light the read finds at rest moves from where it is, with no prediction kept, and a change made from Control4
    can't leave one stale. A light it finds ramping is halted first and read again, as when the direction or the
    limit changes with no stop between, or a press follows a stop before the Director shows the halt: a mid-ramp
    level may be a second old, and for a ramp just begun is still the level it left, which would pass a light on its
    way up by as off. The one ramp left running is the adapter's own to this same end, as a remote that repeats
    while held asks for: nothing is sent, so the ramp keeps its speed, and the call reports sent. Which ramp is its
    own it knows from the last command it sent the light, for as long as that ramp can still be running
    (director.own_ramp_end), not from the Director. A driver
    that reports no target can't show a ramp, so its lights always move from the level reported. The read, any halt
    and the ramp run under the light's lock, which core takes ahead of the concurrency slot, so a stop that arrives
    between them waits and halts the ramp. Raising turns a light that is off on, ramping up from the bottom;
    lowering passes it by, unchanged with off. Lowering to 0 ends off; a limit above 0 never does. A sweep_time
    longer than a full-range ramp can take (65.535 s) is clamped, with clamped_to. An on/off light lacks brightness,
    so the dispatcher leaves it unchanged with fields_dropped.
    """

    integration: ClassVar[str] = "control4"
    fade_limits = RAMP_LIMITS
    min_step: ClassVar[float] = MIN_STEP

    def unaddressable(self, target: Target) -> str | None:
        return unsupported_reason(target)

    def guard(self, hass: HomeAssistant, target: Target) -> asyncio.Lock:
        return item_lock(hass, target)

    async def execute(self, hass: HomeAssistant, request: RampRequest, targets: list[Target]) -> list[EntityResult]:
        # Each target's move runs as its own task, which copies this context: read and fade_to see the call's end.
        asked = _ASKED.set(whole_percent(request.end()))
        try:
            return await super().execute(hass, request, targets)
        finally:
            _ASKED.reset(asked)

    async def read(self, hass: HomeAssistant, target: Target) -> tuple[bool, float]:
        level = await read_level(hass, target)
        _RUNNING.set(False)
        if level.ramping:
            own = own_ramp_end(hass, target)
            if level.target == own == _ASKED.get():
                _RUNNING.set(True)
            else:
                _LOGGER.debug(
                    "%s: ramping to %s, not the adapter's own to %s (last sent %s); halting it to read where it is",
                    target.reported_id,
                    level.target,
                    _ASKED.get(),
                    own,
                )
                level = await self._halted(hass, target)
        return level.on, level.brightness

    async def _halted(self, hass: HomeAssistant, target: Target) -> LightLevel:
        """Halt the ramp in flight and read where the light stopped. The waits are the first two of the stop's
        (director.MOVE_SETTLE_DELAYS_S), a quarter of a second at most, as they are spent inside the light's lock and
        the move's concurrency slot: a stop for this light, and with four slots taken any Control4 call, waits them
        out. A Director that still shows a ramp after them, as for a driver that ignores the stop, leaves the last
        level read to move from, as nothing better is known."""
        await stop_brightness(hass, target)
        level = await settle(target, lambda: read_level(hass, target), lambda level: not level.ramping, brief=True)
        if level.ramping:
            _LOGGER.debug("%s: director still shows a ramp; moving from the level it reports", target.reported_id)
        return level

    async def fade_to(self, hass: HomeAssistant, target: Target, end: float, seconds: float) -> None:
        if _RUNNING.get():
            _LOGGER.debug("%s: already ramping to %s; nothing sent", target.reported_id, _ASKED.get())
            return
        await ramp_to_level(hass, target, end, seconds)
