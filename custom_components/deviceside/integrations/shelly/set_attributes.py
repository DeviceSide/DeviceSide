"""Shelly set_attributes: one <Component>.Set without `on`, so a light that is off stores the values and stays off,
then a GetStatus that confirms what the device kept."""

import logging
from dataclasses import replace
from typing import Any, ClassVar

from homeassistant.components.light import ATTR_COLOR_TEMP_KELVIN, ATTR_HS_COLOR, ATTR_RGB_COLOR, ATTR_XY_COLOR
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .addressing import COLOR_LABS, COMPONENT_FIELDS, address, unsupported_reason
from .rpc import get_status, light_params, set_and_read_back, whole_percent
from ...actions.set_attributes import LIMITS, SetAttributesRequest
from ...core.adapter import Adapter
from ...core.errors import NOT_STORED
from ...core.fields import BRIGHTNESS_FIELD
from ...core.models import EntityResult, Status, Target
from ...core.scope import AdapterScope, documented, verified

_LOGGER = logging.getLogger(__name__)

# The components set_attributes addresses. RGBCCT's Set without `on` keeping the output as it is, and storing the
# values, is the rig's finding (probe of 8 Nov). Shelly documents the brightness Set of Light, CCT, RGB and RGBW
# identically to RGBCCT's, differing only in addressing, so they are Documented; no page, RGBCCT's included, says what
# a Set without `on` does, so they inherit RGBCCT's Verified behavior as the same call
# (docs/integrations/shelly/research/2026-11-17-set-on-sibling-components.md; docs/evidence.md, Levels). Their color
# and ct are in Labs on RGB, RGBW and CCT (addressing.COLOR_LABS): dropped while Labs is off.
SET_CAPABILITIES = verified("RGBCCT") | documented("Light", "CCT", "RGB", "RGBW")


def _clamped(current: float, request: SetAttributesRequest) -> int | None:
    """The whole-percent brightness min/max_brightness move the stored one to, or None when already within them."""
    clamped = current
    if request.min_brightness is not None:
        clamped = max(request.min_brightness, clamped)
    if request.max_brightness is not None:
        clamped = min(request.max_brightness, clamped)
    clamped = whole_percent(clamped)
    return clamped if clamped != current else None


def _expected(params: dict[str, Any], component: str) -> dict[str, Any]:
    """The GetStatus keys that must read as written: brightness, ct and mode, and on RGB and RGBW the rgb and white
    too (Labs). RGBCCT's rgb is not compared: it has not been probed for rounding, and the mode that goes with it is."""
    names = ("brightness", "ct", "mode") + (("rgb", "white") if component in ("RGB", "RGBW") else ())
    return {name: params[name] for name in names if name in params}


class ShellySetAttributes(Adapter[SetAttributesRequest]):
    """One <Component>.Set with brightness, ct or rgb (white too on RGBW) and no `on`, then a GetStatus.

    On a Multicolor Bulb Gen3 a Set without `on` leaves the bulb as it is, on or off, and stores the values: the next
    plain on comes up with them (probe of 8 Nov). The device answers a Set with null, so only the read-back says it
    kept them: a light whose brightness, ct or mode (on RGB and RGBW, rgb or white too) don't read back as written is
    rejected with not_stored. A failed read-back reports SENT, as the timer actions do: the device accepted the Set.

    min_brightness and max_brightness clamp the brightness the bulb has stored, read first with a GetStatus, which
    reports it while the bulb is off; an explicit brightness wins. A bulb already within them is unchanged.
    """

    action: ClassVar[str] = "set_attributes"
    integration: ClassVar[str] = "shelly"
    scope: ClassVar[AdapterScope] = AdapterScope(
        domains=verified(Platform.LIGHT),
        fields=verified(
            BRIGHTNESS_FIELD,
            ATTR_COLOR_TEMP_KELVIN,
            ATTR_HS_COLOR,
            ATTR_RGB_COLOR,
            ATTR_XY_COLOR,
            *LIMITS,
        ),
        capabilities=SET_CAPABILITIES,
        class_labs=COLOR_LABS,
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
            # The dispatcher drops the fields HA's state says the light lacks; the component is the device's word.
            dropped = request.light.present() - COMPONENT_FIELDS[rpc.component]
            light = replace(request.light.without(dropped), brightness=brightness)
            params = light_params(light, rpc.component, target.state)
            if not params:
                return self.result(target, Status.UNCHANGED, detail="fields_dropped" if dropped else "within_limits")
            expected = _expected(params, rpc.component)

            def judge(status: dict[str, Any]) -> EntityResult:
                if any(status.get(name) != value for name, value in expected.items()):
                    _LOGGER.debug(
                        "%s: not stored: sent %s, read %s",
                        target.reported_id,
                        expected,
                        {name: status.get(name) for name in expected},
                    )
                    return self.result(target, Status.REJECTED, detail=NOT_STORED)
                return self.result(target, Status.CONFIRMED, detail="fields_dropped" if dropped else None)

            return await set_and_read_back(hass, self, target, params, judge)

        return await self.gather(hass, targets, write)
