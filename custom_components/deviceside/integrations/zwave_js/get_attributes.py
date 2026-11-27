"""Z-Wave get_attributes: brightness and on/off, from a live Multilevel Switch Get of the light's endpoint."""

import logging
from typing import ClassVar

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .addressing import endpoint_for, invoke_multilevel_switch, light_reason
from .classes import GET_ATTRIBUTES
from .levels import MAX_LEVEL, level_to_percent
from ...core.adapter import Adapter
from ...core.fields import BRIGHTNESS_FIELD
from ...core.models import EntityResult, Request, Status, Target
from ...core.scope import AdapterScope, documented

_LOGGER = logging.getLogger(__name__)


def level_row(reply: object) -> dict:
    """One target's row from the reply of a Multilevel Switch Get, `{currentValue, targetValue, duration}` (the last two
    from a V4 Report, zwave-js ZJS/packages/cc/src/cc/MultilevelSwitchCC.ts#L712-L735): its brightness percent while on,
    and an empty row while off, where level 0 is no level kept for the next on (as Control4's row leaves it out).

    A reply with no level, or one outside 0 to 99 (254 is "unknown" and 255 "on, level unreported" on older versions),
    raises: a read that found nothing isn't passed off as a light with nothing to say.
    """
    level = reply.get("currentValue") if isinstance(reply, dict) else None
    if not isinstance(level, int) or isinstance(level, bool) or not 0 <= level <= MAX_LEVEL:
        raise ValueError(f"Multilevel Switch Get answered no level: {reply!r}")
    return {BRIGHTNESS_FIELD: level_to_percent(level)} if level else {}


class ZwaveGetAttributes(Adapter[Request]):
    """One live Multilevel Switch Get per target. Core's light shows the last value Z-Wave JS cached, which a move the
    device runs on its own doesn't update until the device reports; a device error raises."""

    action: ClassVar[str] = "get_attributes"
    integration: ClassVar[str] = "zwave_js"
    scope: ClassVar[AdapterScope] = AdapterScope(
        domains=documented(Platform.LIGHT),
        capabilities=GET_ATTRIBUTES,
        confirmable=True,
    )

    def supports(self, hass: HomeAssistant, request: Request, target: Target) -> str | None:
        return super().supports(hass, request, target) or light_reason(hass, target)

    async def execute(self, hass: HomeAssistant, request: Request, targets: list[Target]) -> list[EntityResult]:
        async def read(target: Target) -> EntityResult:
            # supports() found the endpoint.
            reply = await invoke_multilevel_switch(target, endpoint_for(hass, target), "get")
            row = level_row(reply)
            _LOGGER.debug("%s: Multilevel Switch reported %s, so the row is %s", target.reported_id, reply, row)
            return self.result(target, Status.CONFIRMED, data=row)

        return await self.gather(hass, targets, read)
