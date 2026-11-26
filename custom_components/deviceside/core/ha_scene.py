"""Home Assistant scenes: which entity IDs are one, and what each light in one asks for.

A scene is an entity in the `homeassistant` scene platform, found as core's `entities_in_scene` finds it, not through
the entity registry: a YAML scene with no `id` has no registry entry. Its states are read from the live entity on each
call, so an edit or reload applies, and a scene removed meanwhile reads as gone. `scene_config` is core-internal, so the
read is guarded as in `ha_entity`: a rename in HA reads as no scene, never an exception.

A light's state becomes the request core's `light/reproduce_state.py` would send, minus what `set_attributes` has no
field for (`effect`, `transition`), as Hue's `set_scene` skips effects.
"""

import logging
from typing import Any, Final

from homeassistant.components.homeassistant.scene import DATA_PLATFORM
from homeassistant.components.light import (
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_XY_COLOR,
    ColorMode,
)
from homeassistant.components.light.reproduce_state import COLOR_MODE_TO_ATTRIBUTE
from homeassistant.const import STATE_OFF, STATE_ON, Platform
from homeassistant.core import HomeAssistant, State

from .models import LightFields
from ..actions.set_attributes import SetAttributesRequest

_LOGGER = logging.getLogger(__name__)

OFF: Final = "off"  # a light the scene holds off: turned off, not written
LightWrite = SetAttributesRequest | str | None  # a request, OFF, or None: on, nothing to write (unchanged)

# The color attributes a request carries, in core's order for a state with no usable color mode.
_COLORS = (ATTR_HS_COLOR, ATTR_COLOR_TEMP_KELVIN, ATTR_RGB_COLOR, ATTR_XY_COLOR)
# Modes whose own attribute `set_attributes` has no field for: they take the state's hs_color (HA keeps it for each).
_HS_MODES = frozenset({ColorMode.RGBW, ColorMode.RGBWW, ColorMode.WHITE})


def _scene_states(hass: HomeAssistant, entity_id: str) -> dict[str, State] | None:
    """The scene's states, or None if no such scene is loaded."""
    platform = hass.data.get(DATA_PLATFORM)
    entity = platform.entities.get(entity_id) if platform is not None else None
    states = getattr(getattr(entity, "scene_config", None), "states", None)
    return states if isinstance(states, dict) else None


def is_ha_scene(hass: HomeAssistant, entity_id: str) -> bool:
    """Whether entity_id is a Home Assistant scene loaded now."""
    return _scene_states(hass, entity_id) is not None


def scene_lights(hass: HomeAssistant, entity_id: str) -> dict[str, LightWrite] | None:
    """What each light in the scene asks for, by entity_id, or None if the scene is gone.

    A non-light member (a switch, a cover) is left out at DEBUG: it isn't a fault. So is a light whose state is neither
    on nor off, as core's reproduce_state ignores it.
    """
    if (states := _scene_states(hass, entity_id)) is None:
        return None
    lights: dict[str, LightWrite] = {}
    for member, state in states.items():
        if member.partition(".")[0] != Platform.LIGHT:
            _LOGGER.debug("Scene %s: skipping %s, not a light", entity_id, member)
        elif state.state not in (STATE_ON, STATE_OFF):
            _LOGGER.debug("Scene %s: skipping %s, state %s is neither on nor off", entity_id, member, state.state)
        else:
            lights[member] = light_write(state)
    return lights


def light_write(state: State) -> LightWrite:
    """One light's scene state as OFF, a SetAttributesRequest, or None when it is on with nothing to write."""
    if state.state == STATE_OFF:
        return OFF
    attributes = state.attributes
    brightness = attributes.get("brightness")  # ha-255: HA state reports a byte
    request = SetAttributesRequest(
        light=_color(state),
        # Level 1 is 0.4 %: no floor is raised. 0 is no level (core would turn the light off), so it writes nothing.
        brightness=brightness / 255 * 100 if brightness else None,  # ha-255: converts HA's byte to a percent
    )
    return None if request.nothing_to_do() else request


def _color(state: State) -> LightFields:
    attributes = state.attributes
    mode = attributes.get(ATTR_COLOR_MODE, ColorMode.UNKNOWN)
    if mode == ColorMode.UNKNOWN:  # a scene from before color modes: the first color present, as core does
        name = next((name for name in _COLORS if attributes.get(name) is not None), None)
    elif mode in _HS_MODES:
        name = ATTR_HS_COLOR
    elif mode in COLOR_MODE_TO_ATTRIBUTE:
        name = COLOR_MODE_TO_ATTRIBUTE[mode].parameter
    else:  # onoff, brightness: no color
        name = None
    if name is None:
        return LightFields()
    value = attributes.get(name)
    if value is None:
        _LOGGER.debug("Scene state for %s names color mode %s but holds no %s", state.entity_id, mode, name)
        return LightFields()
    return LightFields.from_data({name: _typed(name, value)})


def _typed(name: str, value: Any) -> Any:
    """The value as LightFields holds it: YAML scenes give lists, where a light's own state gives tuples."""
    if name == ATTR_COLOR_TEMP_KELVIN:
        return int(value)
    if name == ATTR_RGB_COLOR:
        return tuple(int(part) for part in value)
    return tuple(float(part) for part in value)
