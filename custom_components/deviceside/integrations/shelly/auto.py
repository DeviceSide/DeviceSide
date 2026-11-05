"""The persistent auto-off / auto-on adapters' shared code: a GetConfig, then a SetConfig only on a difference."""

from typing import ClassVar, Literal

from homeassistant.core import HomeAssistant

from .addressing import unsupported_reason
from .rpc import AUTO_DELAY_LIMITS, write_auto
from ...core.adapter import Adapter
from ...core.models import EntityResult, Request, Target, TimedRequest
from ...core.scope import AdapterScope

_DOMAINS = frozenset({"light", "switch"})
# A relay shown as a light sends the same Switch.SetConfig; Light, CCT, RGB and RGBW stay out of scope until a test
# record covers them.
_CAPABILITIES = frozenset({"Switch", "RGBCCT"})


class ShellySetAuto(Adapter[TimedRequest]):
    """One <Component>.SetConfig carrying auto_<which>: true and its delay."""

    integration: ClassVar[str] = "shelly"
    which: ClassVar[Literal["off", "on"]]
    scope: ClassVar[AdapterScope] = AdapterScope(
        experimental=True,
        domains=_DOMAINS,
        duration=AUTO_DELAY_LIMITS,
        capabilities=_CAPABILITIES,
        confirmable=True,
    )

    def supports(self, hass: HomeAssistant, request: TimedRequest, target: Target) -> str | None:
        return super().supports(hass, request, target) or unsupported_reason(target, self.scope.capabilities)

    async def execute(self, hass: HomeAssistant, request: TimedRequest, targets: list[Target]) -> list[EntityResult]:
        return await self.gather(hass, targets, lambda target: write_auto(self, target, self.which, request.duration_s))


class ShellyClearAuto(Adapter[Request]):
    """One <Component>.SetConfig carrying auto_<which>: false."""

    integration: ClassVar[str] = "shelly"
    which: ClassVar[Literal["off", "on"]]
    scope: ClassVar[AdapterScope] = AdapterScope(
        experimental=True, domains=_DOMAINS, capabilities=_CAPABILITIES, confirmable=True
    )

    def supports(self, hass: HomeAssistant, request: Request, target: Target) -> str | None:
        return super().supports(hass, request, target) or unsupported_reason(target, self.scope.capabilities)

    async def execute(self, hass: HomeAssistant, request: Request, targets: list[Target]) -> list[EntityResult]:
        return await self.gather(hass, targets, lambda target: write_auto(self, target, self.which, None))
