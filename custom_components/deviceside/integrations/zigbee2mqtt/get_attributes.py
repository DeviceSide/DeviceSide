"""Zigbee2MQTT get_attributes: on/off timer, brightness, color temperature and color, read live from each bulb.

An off bulb's brightness is Z2M's, the level it comes back at (Reader.read). A Tuya countdown plug is refused: its
OnTime holds the countdown last set, not the time left (refusals.py; internals.md, Tuya's countdown, P6).
"""

from datetime import datetime
from typing import ClassVar

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .adapter import Z2MAdapter
from .addressing import not_addressable
from .classes import class_scope
from .members import member_lights, unaddressable
from .read import Reader, reader
from ...core.errors import Reason
from ...core.models import EntityResult, Request, Status, Target
from ...core.scope import AdapterScope, labs, verified
from ...core.zcl_row import average, zcl_row


class Z2MGetAttributes(Z2MAdapter[Request]):
    """One row per target from live ZCL reads (read.py): Hue bulbs on Z2M don't report, so HA's state can be stale.

    A group's row follows Hue's room row: its members are read one after another and averaged over the lit ones,
    or over all of them when every member is off. It has a timer only when every lit member runs one, and then it
    is the longest. A read that fails raises, so the call raises targets_failed.
    """

    action: ClassVar[str] = "get_attributes"
    integration: ClassVar[str] = "zigbee2mqtt"
    scope: ClassVar[AdapterScope] = AdapterScope(
        # Switches are in Labs, but no class is served on one (docs/evidence.md, "A read serves only"):
        # turn_on_for serves only Tuya's countdown plugs there, which this read refuses (refusals.py).
        domains=verified(Platform.LIGHT) | labs(Platform.SWITCH),
        **class_scope("get_attributes"),
        confirmable=True,
        native_groups=True,  # read through its members, which only Z2M's bridge/groups knows
    )

    def supports(self, hass: HomeAssistant, request: Request, target: Target) -> str | None:
        return (
            super().supports(hass, request, target)
            or not_addressable(hass, target, reads_state=True)
            or unaddressable(hass, target, every=False)
        )

    async def execute(self, hass: HomeAssistant, request: Request, targets: list[Target]) -> list[EntityResult]:
        async def read(target: Target) -> EntityResult:
            if not target.is_group:
                async with reader(hass, [target]) as reading:
                    return self.result(target, Status.CONFIRMED, data=zcl_row(*await _read(reading, target)))
            members = await member_lights(hass, target)
            if not members:
                return self.result(target, Status.UNSUPPORTED, detail=Reason.EMPTY_GROUP)
            # One after another inside the group's own task: gathering them would nest the concurrency limits.
            async with reader(hass, members) as reading:
                reads = [await _read(reading, member) for member in members]
            lit = [(attributes, now) for attributes, now in reads if attributes.get("onOff")]
            return self.result(target, Status.CONFIRMED, data=average([zcl_row(*one) for one in lit or reads]))

        return await self.gather(hass, targets, read)


async def _read(reading: Reader, target: Target) -> tuple[dict, datetime]:
    """The target's attributes, and when they were read, which a timer's end counts from."""
    return await reading.read(target), dt_util.utcnow()
