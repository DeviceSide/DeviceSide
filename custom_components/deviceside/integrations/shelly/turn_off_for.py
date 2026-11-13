from typing import ClassVar

from homeassistant.core import HomeAssistant

from .addressing import CAPABILITIES, RpcComponent, unsupported_reason
from .rpc import TIMER_LIMITS, set_with_timer
from ...core.adapter import Adapter
from ...core.models import EntityResult, Target, TimedRequest
from ...core.scope import AdapterScope, verified


class ShellyTurnOffFor(RpcComponent, Adapter[TimedRequest]):
    """One <Component>.Set carrying on=False and toggle_after; the device turns itself back on."""

    action: ClassVar[str] = "turn_off_for"
    integration: ClassVar[str] = "shelly"
    scope: ClassVar[AdapterScope] = AdapterScope(
        domains=verified("light", "switch"),
        duration=TIMER_LIMITS,
        confirmable=True,
        # A relay shown as a light sends the same Switch.Set.
        capabilities=CAPABILITIES,
    )

    def supports(self, hass: HomeAssistant, request: TimedRequest, target: Target) -> str | None:
        return super().supports(hass, request, target) or unsupported_reason(target)

    async def execute(self, hass: HomeAssistant, request: TimedRequest, targets: list[Target]) -> list[EntityResult]:
        async def send(target: Target) -> EntityResult:
            return await set_with_timer(hass, self, target, {"on": False, "toggle_after": request.duration_s})

        return await self.gather(hass, targets, send)
