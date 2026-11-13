"""The raise and lower of an integration whose device reports its own level, mid-fade included: read that level,
then send one timed set for the distance left. The device runs the fade, and nothing is predicted."""

import logging
from abc import abstractmethod
from contextlib import AbstractAsyncContextManager, nullcontext
from typing import TYPE_CHECKING, ClassVar

from homeassistant.core import HomeAssistant

from .adapter import Adapter
from .models import EntityResult, Status, Target
from .scope import DurationLimits

if TYPE_CHECKING:  # core doesn't import actions at run time
    from ..actions.ramp import RampRequest

_LOGGER = logging.getLogger(__name__)


class LevelFade(Adapter["RampRequest"]):
    """A read of the device's level, then one set to the limit (or range end) with a time for the distance left.

    The level is the device's own, so a move after a stop or mid-fade starts from where the light is, and a change
    made elsewhere can't leave a prediction stale. Raising turns a light that is off on, fading in from the bottom;
    lowering passes it by, unchanged with off. A move with less than `min_step` left is unchanged with at_limit. A
    sweep_time outside what a full-range fade can take on the device (`fade_limits`) is clamped, with clamped_to.
    """

    # What a full-range fade can take on the device.
    fade_limits: ClassVar[DurationLimits]
    # The device's brightness resolution, in percent: a shorter distance is nothing to send.
    min_step: ClassVar[float] = 1.0

    @abstractmethod
    def unaddressable(self, target: Target) -> str | None:
        """Why the integration can't send this target a call at all, or None. Sync and cheap: no I/O."""

    @abstractmethod
    async def read(self, hass: HomeAssistant, target: Target) -> tuple[bool, float]:
        """Whether the light is lit, and its level in percent, as the device reports them now. The level of a light
        that isn't lit is ignored: a raise starts it from 0."""

    @abstractmethod
    async def fade_to(self, hass: HomeAssistant, target: Target, end: float, seconds: float) -> None:
        """One set fading to `end` percent over `seconds`; 0 ends off."""

    def seconds(self, distance: float, sweep_time: float) -> float:
        """How long a fade over `distance` percent takes at the sweep_time's speed."""
        return distance / 100 * sweep_time

    def guard(self, hass: HomeAssistant, target: Target) -> AbstractAsyncContextManager:
        """Held from the read to the set, for an integration whose stop must not slip in between them."""
        return nullcontext()

    def supports(self, hass: HomeAssistant, request: RampRequest, target: Target) -> str | None:
        if (reason := super().supports(hass, request, target)) is not None:
            return reason
        # Nothing left to send: the dispatcher reports it unchanged with fields_dropped, whatever the target.
        return None if request.nothing_to_do() else self.unaddressable(target)

    async def execute(self, hass: HomeAssistant, request: RampRequest, targets: list[Target]) -> list[EntityResult]:
        sweep_time = min(max(request.sweep_time, self.fade_limits.min_s), self.fade_limits.max_s)
        clamped_to = sweep_time if sweep_time != request.sweep_time else None

        async def move(target: Target) -> EntityResult:
            async with self.guard(hass, target):
                lit, level = await self.read(hass, target)
                current = level if lit else 0.0
                end = request.end()
                if not request.up and not lit:
                    return self._skipped(target, "off", lit, level, end)
                if (end - current if request.up else current - end) < self.min_step:
                    return self._skipped(target, "at_limit", lit, level, end)
                await self.fade_to(hass, target, end, self.seconds(abs(end - current), sweep_time))
            return self.result(target, Status.SENT, clamped_to=clamped_to)

        return await self.gather(hass, targets, move)

    def _skipped(self, target: Target, detail: str, lit: bool, level: float, end: float) -> EntityResult:
        """Nothing sent, on what the device reported: logged with the values that decided it."""
        _LOGGER.debug(
            "%s on %s: %s reads lit=%s level=%s, end %s: nothing sent (%s)",
            self.action,
            self.integration,
            target.entity_id,
            lit,
            level,
            end,
            detail,
        )
        return self.result(target, Status.UNCHANGED, detail=detail)
