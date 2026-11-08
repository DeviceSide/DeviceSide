"""Shelly stop: DimStop halts the device's fade, then a GetStatus reads where it halted."""

from typing import Any, ClassVar

from homeassistant.core import HomeAssistant

from .addressing import DIMMING_CAPABILITIES, address, unsupported_reason
from .rpc import dim_stop, get_status, read_back
from ...core.adapter import Adapter
from ...core.models import EntityResult, Request, Status, Target
from ...core.scope import AdapterScope, verified


class ShellyStop(Adapter[Request]):
    """DimStop to each target at once, then a GetStatus.

    DimStop goes first, with no read before it, so the halt waits on nothing: with no fade running it changes nothing
    (rig, 8 Nov). The read after it is the halt itself, exact and settled (rig, 8 Nov), so nothing is predicted; a
    raise or lower after it reads the device again. A halted soft off leaves the light on at the halt level. A light
    that reads off is unchanged with off. A light still fading after the stop is only sent, so a device that ignored
    it never reads as confirmed; a failed read-back is sent too. A relay shown as a light is not dimmable.
    """

    action: ClassVar[str] = "stop"
    integration: ClassVar[str] = "shelly"
    scope: ClassVar[AdapterScope] = AdapterScope(
        experimental=True, domains=verified("light"), capabilities=DIMMING_CAPABILITIES, confirmable=True
    )

    def supports(self, hass: HomeAssistant, request: Request, target: Target) -> str | None:
        if (reason := super().supports(hass, request, target) or unsupported_reason(target)) is not None:
            return reason
        if address(target).component == "Switch":
            return "not_dimmable"
        return unsupported_reason(target, self.scope.capabilities)

    async def execute(self, hass: HomeAssistant, request: Request, targets: list[Target]) -> list[EntityResult]:
        async def halt(target: Target) -> EntityResult:
            await dim_stop(target)

            def judge(status: dict[str, Any]) -> EntityResult:
                if not status.get("output"):
                    return self.result(target, Status.UNCHANGED, detail="off")
                if status.get("transition"):
                    return self.result(target, Status.SENT, detail="still_fading")
                return self.result(target, Status.CONFIRMED)

            return await read_back(self, target, get_status, judge)

        return await self.gather(hass, targets, halt)
