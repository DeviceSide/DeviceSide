"""Zigbee2MQTT's lifecycle hooks (`IntegrationInfo.setup` and `remove`), so the component root names no integration.

Setup starts what Z2M keeps running while the entry is loaded; remove puts back what it changed in Z2M.
"""

from functools import partial

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import bridge_cache, color_modes, restore_journal
from ...const import CONF_Z2M_COLOR_MODES, Z2M_COLOR_MODES_DEFAULT


async def setup(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Start the bridge cache, whose online pays any hue_native_control restore left owed (so a Z2M offline at
    startup is paid when it's back), and the color-modes pass, as two background tasks so neither's MQTT wait holds
    the other."""
    replay = partial(restore_journal.request_replay, hass)
    entry.async_create_background_task(hass, bridge_cache.async_setup(hass, entry, replay), "z2m bridge cache")
    enabled = entry.options.get(CONF_Z2M_COLOR_MODES, Z2M_COLOR_MODES_DEFAULT)
    entry.async_create_background_task(hass, color_modes.async_setup(hass, entry, enabled), "z2m color modes")


async def remove(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await color_modes.async_remove(hass)
