"""Control4 set_attributes: one SET_COLOR_TARGET in color temperature mode, which leaves a light that is off off, then
a read of what the light kept."""

import asyncio
import logging
from dataclasses import replace
from typing import Any, ClassVar

from homeassistant.core import HomeAssistant

from .director import (
    CAPABILITIES,
    COLOR_MODE,
    CURRENT_CCT,
    LEVEL_VARIABLES,
    TARGET_CCT,
    TARGET_COLOR_MODE,
    DirectorAdapter,
    LightLevel,
    heading_for,
    kelvin_range,
    parse_level,
    read_variables,
    set_color_temperature,
    settle,
    unsupported_reason,
)
from ...actions.set_attributes import SetAttributesRequest
from ...core.models import EntityResult, Status, Target
from ...core.readback import read_back
from ...core.scope import AdapterScope, experimental

COLOR_TEMP = "color_temp_kelvin"
_LOGGER = logging.getLogger(__name__)
_READ_BACK = (*LEVEL_VARIABLES, CURRENT_CCT, COLOR_MODE, TARGET_CCT, TARGET_COLOR_MODE)


class Control4SetAttributes(DirectorAdapter):
    """Color temperature alone: a read of the light's own range, one SET_COLOR_TARGET, then a read-back.

    Core shows a Control4 light as brightness-only, so the color temperature is unlisted on the entity and only the
    light can say whether it takes one: its capabilities variable gives the range, the kelvin is clamped to it (with
    clamped_to), and a light that reports none lacks the field, so it is unchanged with fields_dropped, as a white
    bulb in a mixed room is on any integration. Every write goes out before any read-back. A light that is on changes
    to the kelvin and shows it as its target at once, or after a moment's lag in the Director, so it is confirmed;
    one that still shows neither that target nor that color temperature once the read-backs are spent is only sent.
    A light that is off stays off and comes on at the new color temperature, but the Director shows it for a little
    over a second and then the old one again (docs/integrations/control4/internals.md, Tested behavior), so it is
    sent with stored_while_off, never confirmed.

    Brightness is not taken. The light's level for its next on (SET_PRESET_LEVEL) holds for a turn-on from Control4,
    but core's light.turn_on always sends a level of its own, so a brightness written while off would be lost to the
    first turn-on from Home Assistant. Full color is not built: no light with it has been tested.
    """

    action: ClassVar[str] = "set_attributes"
    integration: ClassVar[str] = "control4"
    scope: ClassVar[AdapterScope] = AdapterScope(
        experimental=True,
        domains=experimental("light"),
        fields=experimental(COLOR_TEMP),
        unlisted=frozenset({COLOR_TEMP}),
        confirmable=True,
    )

    def supports(self, hass: HomeAssistant, request: SetAttributesRequest, target: Target) -> str | None:
        return super().supports(hass, request, target) or unsupported_reason(target)

    async def execute(
        self, hass: HomeAssistant, request: SetAttributesRequest, targets: list[Target]
    ) -> list[EntityResult]:
        async def write(target: Target) -> EntityResult:
            span = kelvin_range(await read_variables(hass, target, (CAPABILITIES,)))
            if span is None:
                _LOGGER.debug("%s: the light reports no color temperature; nothing sent", target.reported_id)
                return self.result(target, Status.UNCHANGED, detail="fields_dropped")
            asked = request.light.color_temp_kelvin
            kelvin = min(max(asked, span[0]), span[1])
            if kelvin != asked:
                _LOGGER.debug("%s: %s K clamped to the light's %s-%s K", target.reported_id, asked, *span)
            await set_color_temperature(hass, target, kelvin)
            sent[target.reported_id] = kelvin
            return self.result(target, Status.SENT, clamped_to=kelvin if kelvin != asked else None)

        sent: dict[str, int] = {}
        written = await self.gather(hass, targets, write)

        async def confirm(target: Target, result: EntityResult) -> EntityResult:
            if (kelvin := sent.get(target.reported_id)) is None:
                return result
            return replace(await self._read_back(hass, target, kelvin), clamped_to=result.clamped_to)

        return list(await asyncio.gather(*(confirm(t, result) for t, result in zip(targets, written, strict=True))))

    async def _read_back(self, hass: HomeAssistant, target: Target, kelvin: int) -> EntityResult:
        """Read until a lit light shows the kelvin, each read in a slot of its own so the waits hold none. A read
        that can't be parsed fails inside read_back, as a read that failed: the write stands as sent."""

        async def read() -> tuple[LightLevel, dict[str, Any]]:
            async with self.slot(hass):
                held = await read_variables(hass, target, _READ_BACK)
            return parse_level(held), held

        def shown(read: tuple[LightLevel, dict[str, Any]]) -> bool:
            level, held = read
            return not level.on or heading_for(held, kelvin)

        def judge(read: tuple[LightLevel, dict[str, Any]]) -> EntityResult:
            level, held = read
            if not level.on:
                return self.result(target, Status.SENT, detail="stored_while_off")
            if not heading_for(held, kelvin):
                return self.result(target, Status.SENT, detail="color_temp_not_reported")
            return self.result(target, Status.CONFIRMED)

        return await read_back(self, target, lambda _target: settle(target, read, shown), judge)
