"""Matter turn_on_for: OnWithTimedOff on the OnOff cluster, then an OnTime and OnOff read-back."""

import logging
from typing import ClassVar

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .addressing import (
    make_on_with_timed_off,
    matter_client,
    node_id_from_unique_id,
    onoff_endpoint,
    read_timer,
    timer_matches,
    unsupported_reason,
)
from .classes import TURN_ON_FOR, TURN_ON_FOR_NOT_BUILT
from ...actions.turn_on_for import TurnOnForRequest
from ...core.adapter import Adapter
from ...core.errors import describe
from ...core.models import EntityResult, Status, Target
from ...core.scope import AdapterScope, DurationLimits, documented, verified
from ...core.zcl import MAX_TENTHS_S

_LOGGER = logging.getLogger(__name__)

# OnWithTimedOff.onTime (core/zcl.py).
_TIMER_LIMITS = DurationLimits(min_s=0.1, max_s=MAX_TENTHS_S)
# OffWaitTime 1 (0.1 s), not 0: matter.js before v0.17.2 never times off on 0 (internals.md, turn_on_for).
_OFF_WAIT_TENTHS = 1


class MatterTurnOnFor(Adapter[TurnOnForRequest]):
    """Send OnWithTimedOff on the OnOff cluster; CONFIRMED when OnOff reads on and OnTime within
    READBACK_SLACK_TENTHS under the time sent, else SENT with a detail."""

    action: ClassVar[str] = "turn_on_for"
    integration: ClassVar[str] = "matter"
    scope: ClassVar[AdapterScope] = AdapterScope(
        # Lights take the same call as plugs, behind the same LT check: Documented.
        domains=verified(Platform.SWITCH) | documented(Platform.LIGHT),
        duration=_TIMER_LIMITS,
        fields=verified(),
        capabilities=TURN_ON_FOR,
        not_built=TURN_ON_FOR_NOT_BUILT,
        confirmable=True,
    )

    def supports(self, hass: HomeAssistant, request: TurnOnForRequest, target: Target) -> str | None:
        return super().supports(hass, request, target) or unsupported_reason(hass, target)

    async def execute(
        self, hass: HomeAssistant, request: TurnOnForRequest, targets: list[Target]
    ) -> list[EntityResult]:
        async def send(target: Target) -> EntityResult:
            node_id = node_id_from_unique_id(target.entry.unique_id)
            ep_id = onoff_endpoint(target.entry.unique_id)
            client = matter_client(hass, target.entry.config_entry_id)  # supports() refused the targets without one

            on_time = round(request.duration_s * 10)
            params = {"on_off_control": 0, "on_time": on_time, "off_wait_time": _OFF_WAIT_TENTHS}
            command = make_on_with_timed_off(**params)
            _LOGGER.debug("%s: sending matter OnOff.OnWithTimedOff %s", target.reported_id, params)
            await client.send_device_command(
                node_id=node_id,
                endpoint_id=ep_id,
                command=command,
            )

            try:
                read_on_time, on_off = await read_timer(client, node_id, ep_id)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("turn_on_for matter read-back failed for %s: %s", target.entity_id, describe(err))
                return self.result(target, Status.SENT, detail="readback_failed")

            if timer_matches(read_on_time, on_off, on_time):
                return self.result(target, Status.CONFIRMED)
            return self.result(target, Status.SENT, detail="timer_not_reported")

        return await self.gather(hass, targets, send)
