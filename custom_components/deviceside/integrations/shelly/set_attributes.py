"""Shelly set_attributes: one RGBCCT.Set without `on`, so a bulb that is off stores the values and stays off, then a
GetStatus that confirms what the device kept."""

import logging
from dataclasses import replace
from typing import Any, ClassVar

from homeassistant.core import HomeAssistant

from .addressing import address, unsupported_reason
from .rpc import get_status, light_params, rpc_device
from ...actions.set_attributes import SetAttributesRequest
from ...core.adapter import Adapter
from ...core.models import EntityResult, Status, Target
from ...core.scope import AdapterScope, verified

_LOGGER = logging.getLogger(__name__)

NOT_STORED = "not_stored"


def _expected(params: dict[str, Any]) -> dict[str, Any]:
    """The GetStatus keys that must read as written. The device's rgb is not compared: it has not been probed for
    rounding, and the mode that goes with it is."""
    return {name: params[name] for name in ("brightness", "ct", "mode") if name in params}


class ShellySetAttributes(Adapter[SetAttributesRequest]):
    """One RGBCCT.Set with brightness, ct or rgb and no `on`, then a GetStatus.

    On a Multicolor Bulb Gen3 a Set without `on` leaves the bulb as it is, on or off, and stores the values: the next
    plain on comes up with them (probe of 8 Nov). The device answers a Set with null, so only the read-back says it
    kept them: a bulb whose brightness, ct or mode don't read back as written is rejected with not_stored. A failed
    read-back reports SENT, as the timer actions do: the device accepted the Set.

    min_brightness and max_brightness are out of scope until a record covers them.
    """

    action: ClassVar[str] = "set_attributes"
    integration: ClassVar[str] = "shelly"
    scope: ClassVar[AdapterScope] = AdapterScope(
        experimental=True,
        domains=verified("light"),
        fields=verified("brightness", "color_temp_kelvin", "hs_color", "rgb_color", "xy_color"),
        capabilities=verified("RGBCCT"),
        confirmable=True,
    )

    def supports(self, hass: HomeAssistant, request: SetAttributesRequest, target: Target) -> str | None:
        return super().supports(hass, request, target) or unsupported_reason(target, self.scope.capabilities)

    async def execute(
        self, hass: HomeAssistant, request: SetAttributesRequest, targets: list[Target]
    ) -> list[EntityResult]:
        async def write(target: Target) -> EntityResult:
            rpc = address(target)
            light = replace(request.light, brightness=request.brightness)
            params = light_params(light, rpc.component, target.state)
            await rpc_device(target).call_rpc(f"{rpc.component}.Set", {"id": rpc.id, **params})
            try:
                status = await get_status(target)
            except Exception as err:  # noqa: BLE001 - aioshelly's errors can't be imported here; see addressing.py
                _LOGGER.debug("set_attributes read-back failed for %s: %s", target.entity_id, err)
                return self.result(target, Status.SENT, detail="readback_failed")
            if any(status.get(name) != value for name, value in _expected(params).items()):
                return self.result(target, Status.REJECTED, detail=NOT_STORED)
            return self.result(target, Status.CONFIRMED)

        return await self.gather(hass, targets, write)
