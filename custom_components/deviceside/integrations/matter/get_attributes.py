"""Matter get_attributes: the on/off timer, from a live read of OnOff.OnTime and OnOff.OnOff."""

from datetime import datetime
from typing import ClassVar

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .addressing import (
    endpoint_id_from_unique_id,
    matter_client,
    node_id_from_unique_id,
    read_timer,
    timer_running,
    unsupported_reason,
)
from ...core.adapter import Adapter
from ...core.models import EntityResult, Request, Status, Target
from ...core.scope import AdapterScope, documented, verified
from ...core.timer import timer_row


def on_time_row(on_time: object, on_off: object, now: datetime) -> dict:
    """One target's row from its OnTime, in tenths of a second, and OnOff.

    A timer runs only while OnTime > 0 and the target is on: the spec counts OnTime down only while on and Off zeroes
    it, but a stale OnTime on an off target is no timer. Matter has no turn_off_for here, so the timer always turns
    the target off.
    """
    if timer_running(on_time, on_off):
        return {"timer": timer_row("off", on_time / 10, now)}
    return {}


class MatterGetAttributes(Adapter[Request]):
    """One live OnTime read per target; a device error raises."""

    action: ClassVar[str] = "get_attributes"
    integration: ClassVar[str] = "matter"
    scope: ClassVar[AdapterScope] = AdapterScope(
        # Lights carry the same attributes as plugs, behind the same LT check: Documented.
        domains=verified("switch") | documented("light"),
        fields=verified(),
        confirmable=True,
    )

    def supports(self, hass: HomeAssistant, request: Request, target: Target) -> str | None:
        return super().supports(hass, request, target) or unsupported_reason(hass, target)

    async def execute(self, hass: HomeAssistant, request: Request, targets: list[Target]) -> list[EntityResult]:
        async def read(target: Target) -> EntityResult:
            # Live, not the node cache: the plug never reports OnTime on its subscription, so the cache reads 0
            # while a timer runs (docs/integration-internals.md, Matter tested behavior).
            client = matter_client(hass, target.entry.config_entry_id)  # supports() refused the targets without one
            on_time, on_off = await read_timer(
                client,
                node_id_from_unique_id(target.entry.unique_id),
                endpoint_id_from_unique_id(target.entry.unique_id),
            )
            return self.result(target, Status.CONFIRMED, data=on_time_row(on_time, on_off, dt_util.utcnow()))

        return await self.gather(hass, targets, read)
