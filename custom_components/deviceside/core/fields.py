"""The fields a target can't take at all, read from its state as light.turn_on's filter_turn_on_params reads them."""

from typing import TYPE_CHECKING

from homeassistant.components.light import (
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_SUPPORTED_COLOR_MODES,
    ATTR_TRANSITION,
    ATTR_XY_COLOR,
    LightEntityFeature,
    brightness_supported,
    color_supported,
    color_temp_supported,
)
from homeassistant.const import ATTR_SUPPORTED_FEATURES, Platform

if TYPE_CHECKING:  # models.py imports this module (LIGHT_FIELDS)
    from .models import Request, Target

# Each action's fields by the light capability they need. Core converts between color forms before it filters, so a
# color is lacked only without any color mode, and a color temperature only without that or a color mode.
# Brightness keeps its literal names: DeviceSide's brightness is a percent, and HA's ATTR_BRIGHTNESS is 0-255, so HA's
# constant would mislead. Same for the limits. The other fields are HA's own names.
BRIGHTNESS_FIELD = "brightness"
BRIGHTNESS = frozenset({BRIGHTNESS_FIELD, "min_brightness", "max_brightness"})
COLORS = frozenset({ATTR_HS_COLOR, ATTR_RGB_COLOR, ATTR_XY_COLOR})
COLOR_TEMP = frozenset({ATTR_COLOR_TEMP_KELVIN})
COLOR = COLORS | {"hue", "saturation"}  # hue and saturation are DeviceSide's
TRANSITION = frozenset({ATTR_TRANSITION})
# The light.turn_on fields an action may accept, under their light.turn_on names.
LIGHT_FIELDS = (BRIGHTNESS_FIELD, ATTR_COLOR_TEMP_KELVIN, ATTR_HS_COLOR, ATTR_RGB_COLOR, ATTR_XY_COLOR, ATTR_TRANSITION)
# Every field a light's state can say it lacks: the only ones AdapterScope.unlisted may name.
LACKABLE = BRIGHTNESS | COLOR_TEMP | COLOR | TRANSITION


def lacking(target: Target, request: Request, unlisted: frozenset[str] = frozenset()) -> frozenset[str]:
    """The request's fields the target lacks. A switch, or the switch a switch_as_x light drives, lacks them all.

    A light whose state doesn't list its color modes or features lacks nothing by that attribute: only a state that
    says the light can't take a field drops it. A light never lacks a field in `unlisted` (the adapter's
    AdapterScope.unlisted), which the adapter takes whatever the state says; a switch still lacks it.
    """
    present = request.fields_present()
    if not present or target.domain != Platform.LIGHT:
        return present
    attributes = target.state.attributes if target.state is not None else {}
    lacked: set[str] = set()
    if (modes := attributes.get(ATTR_SUPPORTED_COLOR_MODES)) is not None:
        if not brightness_supported(modes):
            lacked |= BRIGHTNESS
        if not color_supported(modes):
            lacked |= COLOR
            if not color_temp_supported(modes):
                lacked |= COLOR_TEMP
    features = attributes.get(ATTR_SUPPORTED_FEATURES)
    if features is not None and not features & LightEntityFeature.TRANSITION:
        lacked |= TRANSITION
    return present & (lacked - unlisted)
