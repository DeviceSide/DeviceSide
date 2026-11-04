"""HA's live entity objects, for an adapter that must correct what an integration keeps in one.

These reach into another integration's private attributes, so every access is guarded: a rename in HA leaves HA's
own behavior in place, logged once at debug, and never raises.
"""

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_component import DATA_INSTANCES

_LOGGER = logging.getLogger(__name__)

_missing: set[str] = set()  # "Type.attribute" already logged as absent


def ha_entity(hass: HomeAssistant, entity_id: str) -> Entity | None:
    """HA's entity object for an entity_id, or None if its domain's component or the entity isn't loaded."""
    component = hass.data.get(DATA_INSTANCES, {}).get(entity_id.partition(".")[0])
    return component.get_entity(entity_id) if component is not None else None


def replace_if_set(obj: Any, attribute: str, value: Any) -> None:
    """Set `obj.attribute` to `value` only when it already holds one (not None); no `obj` is a no-op."""
    if obj is None:
        return
    if not hasattr(obj, attribute):
        if (key := f"{type(obj).__qualname__}.{attribute}") not in _missing:
            _missing.add(key)
            _LOGGER.warning(
                "%s has no %s, so Home Assistant's own behavior stays: a plain turn_on after set_attributes while the "
                "light is off may come on at the old level",
                type(obj).__qualname__,
                attribute,
            )
        return
    if getattr(obj, attribute) is not None:
        setattr(obj, attribute, value)
