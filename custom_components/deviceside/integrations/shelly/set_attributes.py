"""Shelly set_attributes: one <Component>.Set without `on`, so a light that is off stores the values and stays off,
then a GetStatus that confirms what the device kept."""

from dataclasses import replace
from typing import Any, ClassVar

from homeassistant.core import HomeAssistant

from .addressing import address, unsupported_reason
from .rpc import get_status, light_params, set_and_read_back, whole_percent
from ...actions.set_attributes import SetAttributesRequest
from ...core.adapter import Adapter
from ...core.models import EntityResult, Status, Target
from ...core.scope import AdapterScope, experimental, verified

NOT_STORED = "not_stored"
# The components set_attributes addresses. RGBCCT's Set without `on` keeping the output as it is, and storing the
# values, is the rig's finding (probe of 8 Nov). Light, CCT, RGB and RGBW take the same <Component>.Set
# (shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Light, /CCT, /RGB, /RGBW), but whether their docs say alike
# that a Set without `on` leaves the output as it is wasn't checked (the docs host was out of reach), so they stay
# flagged rather than Documented; their color and ct are also not ported (addressing.COMPONENT_FIELDS)
# (docs/evidence.md, Levels).
SET_CAPABILITIES = verified("RGBCCT") | experimental("Light", "CCT", "RGB", "RGBW")


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


class ShellySetAttributes(Adapter[SetAttributesRequest]):
    """One <Component>.Set with brightness, ct or rgb and no `on`, then a GetStatus (RGBCCT Verified, the rest flagged).

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
        capabilities=SET_CAPABILITIES,
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
