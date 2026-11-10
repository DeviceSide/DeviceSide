"""A get_attributes row from a Zigbee light's raw ZCL attributes, shared by the Zigbee integrations.

Attributes go by zigbee-herdsman's names (`currentLevel`, `colorMode`), the ZCL spec's in camel case; ZHA reads by
attribute ID and maps them to these names first.
"""

from datetime import datetime
from statistics import mean

from homeassistant.util.color import color_temperature_mired_to_kelvin

from .color import hs_row, xy_row
from .timer import timer_row

# ColorMode (0x0008) and EnhancedColorMode (0x4001): the attributes that set the light's color. Only the enhanced one
# has enhanced hue.
_HS, _XY, _COLOR_TEMP, _ENHANCED_HS = 0, 1, 2, 3
_MAX_LEVEL = 254  # CurrentLevel, CurrentHue and CurrentSaturation all top out at 0xFE
_MAX_ENHANCED_HUE = 65535
_MAX_XY = 65535


def zcl_row(attributes: dict, now: datetime | None = None, *, xy_first: bool = False) -> dict:
    """One light's row from the attributes read, under HA's names; what wasn't read is left out.

    Brightness is a percent of CurrentLevel, as Hue's row is. Only the color of the active ColorMode (EnhancedColorMode
    where read) is reported, as core does. In a hue mode, hue and saturation win, unless `xy_first`: ZHA shows the
    bulb's own x and y in every mode but color temperature, and HA's hs to xy conversion isn't the bulb's. Lights
    keep these attributes while off, so they read then too. OnTime is the time left on an OnWithTimedOff timer, in
    tenths, and reads 0 with none; it counts only while OnOff reads on, as a Tuya TS011F counts it down while off.
    """
    row: dict = {}
    if (level := attributes.get("currentLevel")) is not None:
        row["brightness"] = round(level * 100 / _MAX_LEVEL, 1)
    row |= _color(attributes, xy_first)
    if attributes.get("onOff") and attributes.get("onTime"):
        row["timer"] = timer_row("off", attributes["onTime"] / 10, now)
    return row


def _color(attributes: dict, xy_first: bool) -> dict:
    if "enhancedColorMode" in attributes:
        mode = attributes["enhancedColorMode"]
    elif (mode := attributes.get("colorMode")) == _ENHANCED_HS:
        mode = None  # not a ColorMode value
    if mode == _COLOR_TEMP:
        mireds = attributes.get("colorTemperature")
        return {"color_temp_kelvin": color_temperature_mired_to_kelvin(mireds)} if mireds else {}
    hs = _hs(attributes, mode)
    # A light in a hue mode keeps its xy current too, so one whose read left out hue and saturation reports that.
    xy = None
    if mode in (_HS, _XY, _ENHANCED_HS) and "currentX" in attributes and "currentY" in attributes:
        xy = (round(attributes["currentX"] / _MAX_XY, 4), round(attributes["currentY"] / _MAX_XY, 4))
    if hs is not None and (xy is None or not xy_first):
        return hs_row(*hs)
    return xy_row(*xy) if xy is not None else {}


def _hs(attributes: dict, mode: int | None) -> tuple[float, float] | None:
    if "currentSaturation" not in attributes:
        return None
    if mode == _ENHANCED_HS and "enhancedCurrentHue" in attributes:
        hue = attributes["enhancedCurrentHue"] * 360 / _MAX_ENHANCED_HUE
    elif mode == _HS and "currentHue" in attributes:
        hue = attributes["currentHue"] * 360 / _MAX_LEVEL
    else:
        return None
    return round(hue, 3), round(attributes["currentSaturation"] * 100 / _MAX_LEVEL, 3)


def average(rows: list[dict]) -> dict:
    """A group's row from its members' rows, chosen by the caller as Hue's room row is: the lit ones, or all.

    Brightness and color temperature average the rows that have them; xy averages too and the other colors follow
    from it. A timer is reported only when every row has one, and then it is the longest.
    """
    row: dict = {}
    if levels := [r["brightness"] for r in rows if "brightness" in r]:
        row["brightness"] = round(mean(levels), 1)
    if kelvins := [r["color_temp_kelvin"] for r in rows if "color_temp_kelvin" in r]:
        row["color_temp_kelvin"] = round(mean(kelvins))
    if xys := [r["xy_color"] for r in rows if "xy_color" in r]:
        row |= xy_row(round(mean(x for x, _ in xys), 4), round(mean(y for _, y in xys), 4))
    if rows and all("timer" in r for r in rows):
        row["timer"] = max((r["timer"] for r in rows), key=lambda timer: timer["remaining_s"])
    return row
