"""The persistent auto-off / auto-on adapters' shared code: a GetConfig, then a SetConfig only on a difference."""

from typing import ClassVar, Literal

from homeassistant.core import HomeAssistant

from .addressing import AUTO_CAPABILITIES, AUTO_SIBLINGS, RpcComponent, unsupported_reason
from .rpc import AUTO_DELAY_LIMITS, write_auto
from ...core.adapter import Adapter
from ...core.models import EntityResult, Request, Target, TimedRequest
from ...core.scope import AdapterScope, verified

_DOMAINS = verified("light", "switch")


class ShellySetAuto(RpcComponent, Adapter[TimedRequest]):
    """One <Component>.SetConfig carrying auto_<which>: true and its delay."""

    integration: ClassVar[str] = "shelly"
    which: ClassVar[Literal["off", "on"]]
    scope: ClassVar[AdapterScope] = AdapterScope(
        domains=_DOMAINS,
        duration=AUTO_DELAY_LIMITS,
        capabilities=AUTO_CAPABILITIES,
        siblings=AUTO_SIBLINGS,
        confirmable=True,
    )

    def supports(self, hass: HomeAssistant, request: TimedRequest, target: Target) -> str | None:
        return super().supports(hass, request, target) or unsupported_reason(target)

    async def execute(self, hass: HomeAssistant, request: TimedRequest, targets: list[Target]) -> list[EntityResult]:
        return await self.gather(
            hass, targets, lambda target: write_auto(hass, self, target, self.which, request.duration_s)
        )


class ShellyClearAuto(RpcComponent, Adapter[Request]):
    """One <Component>.SetConfig carrying auto_<which>: false."""

    integration: ClassVar[str] = "shelly"
    which: ClassVar[Literal["off", "on"]]
    scope: ClassVar[AdapterScope] = AdapterScope(
        domains=_DOMAINS, capabilities=AUTO_CAPABILITIES, siblings=AUTO_SIBLINGS, confirmable=True
    )

    def supports(self, hass: HomeAssistant, request: Request, target: Target) -> str | None:
        return super().supports(hass, request, target) or unsupported_reason(target)

    async def execute(self, hass: HomeAssistant, request: Request, targets: list[Target]) -> list[EntityResult]:
        return await self.gather(hass, targets, lambda target: write_auto(hass, self, target, self.which, None))
