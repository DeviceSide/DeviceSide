"""Control4 stop: SET_BRIGHTNESS_STOP halts the light's ramp, then a read of the Director says where it halted."""

import asyncio
from typing import ClassVar

from homeassistant.core import HomeAssistant

from .director import (
    DirectorAdapter,
    LightLevel,
    dimmable,
    item_lock,
    read_level,
    settle,
    stop_brightness,
    unsupported_reason,
)
from ...core.models import EntityResult, Request, Status, Target
from ...core.readback import read_back
from ...core.scope import AdapterScope, experimental


class Control4Stop(DirectorAdapter):
    """A SET_BRIGHTNESS_STOP to every target first, then the read-backs.

    Each one goes with no read before it, so the halt waits on nothing: with no ramp running it changes nothing.
    Every target's is out before any read-back begins, and the read-backs' waits hold no concurrency slot, so a
    large room's last light is halted as soon as its first. Before it takes a concurrency slot, it waits only for a
    move on the same light that is still between its read and its ramp (a quarter of a second more if that move is
    halting a ramp already running first), so it halts that ramp instead of slipping in ahead of it.

    The read after it is the halt itself, as the Director holds a halted light's level exactly, so nothing is
    predicted; a raise or lower after it reads the Director again. The Director may lag the command, so a read that
    still shows a ramp is repeated briefly. A light still heading for a target after that is only sent, so a driver
    that ignored the command never reads as confirmed; so is one on a driver that reports no target, which can't
    show a halt, and one whose read-back failed. A light at rest at 0 is unchanged with off. A light with no
    brightness is refused.
    """

    action: ClassVar[str] = "stop"
    integration: ClassVar[str] = "control4"
    scope: ClassVar[AdapterScope] = AdapterScope(experimental=True, domains=experimental("light"), confirmable=True)

    def supports(self, hass: HomeAssistant, request: Request, target: Target) -> str | None:
        # Ahead of the scope check: an on/off light can never take a stop, whatever is tested.
        if target.domain == "light" and not dimmable(target):
            return "not_dimmable"
        return super().supports(hass, request, target) or unsupported_reason(target)

    async def execute(self, hass: HomeAssistant, request: Request, targets: list[Target]) -> list[EntityResult]:
        async def halt(target: Target) -> EntityResult:
            await stop_brightness(hass, target)
            return self.result(target, Status.SENT)

        halted = await self.gather(hass, targets, halt, hold=lambda target: item_lock(hass, target))

        async def confirm(target: Target, sent: EntityResult) -> EntityResult:
            return await self._read_back(hass, target) if sent.status is Status.SENT else sent

        return list(await asyncio.gather(*(confirm(t, sent) for t, sent in zip(targets, halted, strict=True))))

    async def _read(self, hass: HomeAssistant, target: Target) -> LightLevel:
        """One read in a slot of its own, so the waits between reads hold none."""
        async with self.slot(hass):
            return await read_level(hass, target)

    async def _read_back(self, hass: HomeAssistant, target: Target) -> EntityResult:
        async def settled(target: Target) -> LightLevel:
            return await settle(target, lambda: self._read(hass, target), lambda level: not level.ramping)

        def judge(level: LightLevel) -> EntityResult:
            if level.ramping:
                return self.result(target, Status.SENT, detail="still_fading")
            if not level.on:
                return self.result(target, Status.UNCHANGED, detail="off")
            if level.target is None:
                return self.result(target, Status.SENT, detail="halt_not_reported")
            return self.result(target, Status.CONFIRMED)

        return await read_back(self, target, settled, judge)
