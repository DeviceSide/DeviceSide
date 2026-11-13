"""Control4 get_attributes: brightness and color temperature from the Director's variables for the light."""

from typing import Any, ClassVar

from homeassistant.core import HomeAssistant

from .director import (
    BRIGHTNESS_PERCENT,
    COLOR_MODE,
    CURRENT_CCT,
    LIGHT_LEVEL,
    LIGHT_STATE,
    DirectorAdapter,
    color_temperature,
    parse_level,
    read_variables,
    unsupported_reason,
)
from ...core.models import EntityResult, Request, Status, Target
from ...core.scope import AdapterScope, experimental

_VARIABLES = (BRIGHTNESS_PERCENT, LIGHT_LEVEL, LIGHT_STATE, CURRENT_CCT, COLOR_MODE)


def attributes_row(held: dict[str, Any]) -> dict:
    """One target's row from its variables. Brightness is the Director's percent, at most about a second old
    mid-ramp, and is left out for a light that is off: it reads 0 then, not a level kept for the next on. Color
    temperature is the one the light is at, or last had: it reads while off too (bar a moment after a write while
    off, see director.CURRENT_CCT), and is left out of a light not in color temperature mode. A light
    that reports on or off and no level, as an on/off light may, has no brightness to give; one that reports
    neither raises, so a read that found nothing isn't passed off as a light with nothing to say."""
    row: dict = {}
    if BRIGHTNESS_PERCENT in held or LIGHT_LEVEL in held or LIGHT_STATE not in held:
        level = parse_level(held)
        if level.on:
            row["brightness"] = level.brightness
    if (kelvin := color_temperature(held)) is not None:
        row["color_temp_kelvin"] = kelvin
    return row


class Control4GetAttributes(DirectorAdapter):
    """One read of the light's variables per target. Core shows a Control4 light's brightness only, as of its last
    poll of the Director (every 5 s by default, its DEFAULT_SCAN_INTERVAL); this reads the Director itself, whose
    level is at most about a second old mid-ramp, and adds the color temperature. A light whose level can't be read
    is rejected; a light that is off with no color temperature has nothing to report and returns an empty row."""

    action: ClassVar[str] = "get_attributes"
    integration: ClassVar[str] = "control4"
    scope: ClassVar[AdapterScope] = AdapterScope(experimental=True, domains=experimental("light"), confirmable=True)

    def supports(self, hass: HomeAssistant, request: Request, target: Target) -> str | None:
        return super().supports(hass, request, target) or unsupported_reason(target)

    async def execute(self, hass: HomeAssistant, request: Request, targets: list[Target]) -> list[EntityResult]:
        async def read(target: Target) -> EntityResult:
            row = attributes_row(await read_variables(hass, target, _VARIABLES))
            return self.result(target, Status.CONFIRMED, data=row)

        return await self.gather(hass, targets, read)
