from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_EXPERIMENTAL,
    CONF_PREDICTED_STATE,
    CONF_Z2M_COLOR_MODES,
    DOMAIN,
    EXPERIMENTAL_DEFAULT,
    PREDICTED_STATE_DEFAULT,
    Z2M_COLOR_MODES_DEFAULT,
)
from .core import ha_watch
from .core.actions import async_setup_services
from .core.dispatcher import Dispatcher
from .core.registry import AdapterRegistry
from .core.runtime import DATA, DeviceSideData, get_runtime
from .integrations.zigbee2mqtt import bridge_cache, color_modes

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType):
    # Discovery imports every integration module, so it runs in the import executor rather than the event loop.
    registry = await hass.async_add_import_executor_job(AdapterRegistry.discover)
    hass.data[DATA] = DeviceSideData(registry=registry, dispatcher=Dispatcher(hass, registry))
    # Services are registered once per HA run, not per entry; handlers refuse calls until the entry loads.
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    # An entry saved before the option existed has no options: it gets the default.
    runtime = get_runtime(hass)
    runtime.predicted_state = entry.options.get(CONF_PREDICTED_STATE, PREDICTED_STATE_DEFAULT)
    runtime.experimental_features = entry.options.get(CONF_EXPERIMENTAL, EXPERIMENTAL_DEFAULT)
    # Per entry, not in async_setup: unloading detaches every listener, and a reload runs only this again.
    runtime.listen("ha_watch", hass, lambda: ha_watch.attach(hass, runtime.registry.call_resolvers()))
    entry.async_create_background_task(hass, bridge_cache.async_setup(hass, entry), "z2m bridge cache")
    enabled = entry.options.get(CONF_Z2M_COLOR_MODES, Z2M_COLOR_MODES_DEFAULT)
    entry.async_create_background_task(hass, color_modes.async_setup(hass, entry, enabled), "z2m color modes")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    runtime = get_runtime(hass)
    runtime.cancel_pending()
    runtime.detach_all()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry):
    await color_modes.async_remove(hass)
