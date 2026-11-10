"""Matter turn_on_for: OnWithTimedOff on the OnOff cluster, then an OnTime and OnOff read-back."""

import logging
from typing import ClassVar

from homeassistant.core import HomeAssistant

from .addressing import (
    endpoint_id_from_unique_id,
    make_on_with_timed_off,
    matter_client,
    node_id_from_unique_id,
    read_timer,
    timer_running,
    unsupported_reason,
)
from ...actions.turn_on_for import TurnOnForRequest
from ...core.adapter import Adapter
from ...core.models import EntityResult, Status, Target
from ...core.scope import AdapterScope, DurationLimits, documented, verified
from ...core.wire import wire_trace

_LOGGER = logging.getLogger(__name__)

# OnWithTimedOff.onTime is a uint16 in tenths of a second; the spec caps it at 65534 tenths, so 6553.4 s is the most.
_TIMER_LIMITS = DurationLimits(min_s=0.1, max_s=6553.4)


class MatterTurnOnFor(Adapter[TurnOnForRequest]):
    """Send OnWithTimedOff on the OnOff cluster."""

    action: ClassVar[str] = "turn_on_for"
    integration: ClassVar[str] = "matter"
    scope: ClassVar[AdapterScope] = AdapterScope(
        # Lights take the same OnWithTimedOff as plugs, behind the same LT check: Documented until a record covers them.
        domains=verified("switch") | documented("light"),
        siblings={"light": "switch"},
        duration=_TIMER_LIMITS,
        fields=verified(),
        # capabilities=None covers every endpoint that passes the LT feature check.
        confirmable=True,
    )

    def supports(self, hass: HomeAssistant, request: TurnOnForRequest, target: Target) -> str | None:
        return super().supports(hass, request, target) or unsupported_reason(hass, target)

    async def execute(
        self, hass: HomeAssistant, request: TurnOnForRequest, targets: list[Target]
    ) -> list[EntityResult]:
        async def send(target: Target) -> EntityResult:
            node_id = node_id_from_unique_id(target.entry.unique_id)
            ep_id = endpoint_id_from_unique_id(target.entry.unique_id)
            client = matter_client(hass, target.entry.config_entry_id)  # supports() refused the targets without one

            on_time = round(request.duration_s * 10)
            params = {"on_off_control": 0, "on_time": on_time, "off_wait_time": 0}
            command = make_on_with_timed_off(**params)
            wire_trace(hass, target.reported_id, "matter", "OnOff.OnWithTimedOff", params)
            await client.send_device_command(
                node_id=node_id,
                endpoint_id=ep_id,
                command=command,
            )

            try:
                on_time, on_off = await read_timer(client, node_id, ep_id)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("turn_on_for matter read-back failed for %s: %s", target.entity_id, err)
                return self.result(target, Status.SENT, detail="readback_failed")

            if timer_running(on_time, on_off):
                return self.result(target, Status.CONFIRMED)
            return self.result(target, Status.SENT, detail="timer_not_reported")

        return await self.gather(hass, targets, send)
