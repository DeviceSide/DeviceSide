"""Shelly set_attributes: one RGBCCT.Set without `on`, so a bulb that is off stores the values and stays off, then a
GetStatus that confirms what the device kept."""

from dataclasses import replace
from typing import Any, ClassVar

from homeassistant.core import HomeAssistant

from .addressing import RpcComponent, address, unsupported_reason
from .rpc import get_status, light_params, set_and_read_back, whole_percent
from ...actions.set_attributes import SetAttributesRequest
from ...core.adapter import Adapter
from ...core.models import EntityResult, Status, Target
from ...core.scope import AdapterScope, verified

NOT_STORED = "not_stored"


def _clamped(current: float, request: SetAttributesRequest) -> int | None:
    """The whole-percent brightness min/max_brightness move the stored one to, or None when already within them."""
    clamped = current
    if request.min_brightness is not None:
        clamped = max(request.min_brightness, clamped)
    if request.max_brightness is not None:
        clamped = min(request.max_brightness, clamped)
    clamped = whole_percent(clamped)
    return clamped if clamped != current else None


def _expected(params: dict[str, Any]) -> dict[str, Any]:
    """The GetStatus keys that must read as written. The device's rgb is not compared: it has not been probed for
    rounding, and the mode that goes with it is."""
    return {name: params[name] for name in ("brightness", "ct", "mode") if name in params}


class ShellySetAttributes(RpcComponent, Adapter[SetAttributesRequest]):
    """One RGBCCT.Set with brightness, ct or rgb and no `on`, then a GetStatus.

    On a Multicolor Bulb Gen3 a Set without `on` leaves the bulb as it is, on or off, and stores the values: the next
    plain on comes up with them (probe of 8 Nov). The device answers a Set with null, so only the read-back says it
    kept them: a bulb whose brightness, ct or mode don't read back as written is rejected with not_stored. A failed
    read-back reports SENT, as the timer actions do: the device accepted the Set.

    min_brightness and max_brightness clamp the brightness the bulb has stored, read first with a GetStatus, which
    reports it while the bulb is off; an explicit brightness wins. A bulb already within them is unchanged.
    """

    action: ClassVar[str] = "set_attributes"
    integration: ClassVar[str] = "shelly"
    scope: ClassVar[AdapterScope] = AdapterScope(
        domains=verified("light"),
        fields=verified(
            "brightness", "color_temp_kelvin", "hs_color", "rgb_color", "xy_color", "min_brightness", "max_brightness"
        ),
        capabilities=verified("RGBCCT"),
        confirmable=True,
    )

    def supports(self, hass: HomeAssistant, request: SetAttributesRequest, target: Target) -> str | None:
        return super().supports(hass, request, target) or unsupported_reason(target)

    async def execute(
        self, hass: HomeAssistant, request: SetAttributesRequest, targets: list[Target]
    ) -> list[EntityResult]:
        async def write(target: Target) -> EntityResult:
            rpc = address(target)
            brightness = request.brightness
            if brightness is None and (request.min_brightness is not None or request.max_brightness is not None):
                brightness = _clamped((await get_status(target))["brightness"], request)
            light = replace(request.light, brightness=brightness)
            params = light_params(light, rpc.component, target.state)
            if not params:
                return self.result(target, Status.UNCHANGED, detail="within_limits")
            expected = _expected(params)

            def judge(status: dict[str, Any]) -> EntityResult:
                if any(status.get(name) != value for name, value in expected.items()):
                    return self.result(target, Status.REJECTED, detail=NOT_STORED)
                return self.result(target, Status.CONFIRMED)

            return await set_and_read_back(hass, self, target, params, judge)

        return await self.gather(hass, targets, write)
