import asyncio
import logging
from collections.abc import Awaitable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_EXPERIMENTAL,
    CONF_PREDICTED_STATE,
    DOMAIN,
    EXPERIMENTAL_DEFAULT,
    PREDICTED_STATE_DEFAULT,
)
from .core import ha_watch
from .core.actions import async_setup_services
from .core.dispatcher import Dispatcher
from .core.errors import describe, traceback_is_safe
from .core.registry import AdapterRegistry
from .core.runtime import DATA, DeviceSideData, get_runtime
from .core.scope import CaveatKind, IntegrationInfo

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
_LOGGER = logging.getLogger(__name__)


# The setup warning per caveat (docs/evidence.md, Caveats): integration, action, then the caveat's reason.
CAVEAT_WARNINGS = {
    CaveatKind.UNTESTED_FIX: "%s %s ships an untested fix (%s): it changed and no one could test it before this "
    "release; please report whether it works",
    CaveatKind.UNMAINTAINED: "%s %s is unmaintained (%s): no one is fixing it; use at your own risk",
}


def warn_caveats(registry: AdapterRegistry) -> None:
    """One warning per adapter with a caveat; the adapter stays live."""
    for action, integration, adapter in registry.matrix():
        if adapter is not None and (caveat := adapter.scope.caveat) is not None:
            _LOGGER.warning(CAVEAT_WARNINGS[caveat.kind], integration, action, caveat.reason)


HOOK_CONSEQUENCES = {
    "setup": "its actions may not work until DeviceSide is reloaded",
    "remove": "a change it made to another system may be left in place",
}


async def _guarded(info: IntegrationInfo, hook: str, hook_call: Awaitable[None]) -> None:
    """Await an integration's lifecycle hook; its failure is logged and never stops another integration's."""
    try:
        await hook_call
    except Exception as err:  # noqa: BLE001 - one integration's hook must not take the others down
        # The catch-all of an integration's own bug, so the traceback is the diagnosis (docs/logging.md); an HTTP
        # client error's is kept out, as it prints the request's URL and headers.
        _LOGGER.exception(
            "Integration %s %s hook failed: %s, so %s",
            info.key,
            hook,
            describe(err),
            HOOK_CONSEQUENCES[hook],
            exc_info=traceback_is_safe(err),
        )


async def async_setup(hass: HomeAssistant, config: ConfigType):
    # Discovery imports every integration module, so it runs in the import executor rather than the event loop.
    registry = await hass.async_add_import_executor_job(AdapterRegistry.discover)
    hass.data[DATA] = runtime = DeviceSideData(registry=registry, dispatcher=Dispatcher(hass, registry))
    warn_caveats(registry)

    @callback
    def stopping(_event: Event) -> None:
        # An unload leaves the must-run jobs to run; HA stopping takes them too, as it takes every timer.
        runtime.cancel_pending(must_run=True)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stopping)
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
    for info in runtime.registry.available_integrations():
        if info.setup is not None:
            entry.async_create_background_task(
                hass, _guarded(info, "setup", info.setup(hass, entry)), f"{info.key} setup"
            )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    runtime = get_runtime(hass)
    runtime.cancel_pending()
    runtime.detach_all()
    # integration_state stays: it describes the devices (fades still running, a soft off's restore, Z2M's option
    # locks and restores), which an options save doesn't change, and the must-run jobs left to run still read it.
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry):
    # An entry deleted while not loaded (disabled, or failed at startup) may precede async_setup: discover then.
    runtime = hass.data.get(DATA)
    registry = runtime.registry if runtime else await hass.async_add_import_executor_job(AdapterRegistry.discover)
    await asyncio.gather(
        *(
            _guarded(info, "remove", info.remove(hass, entry))
            for info in registry.available_integrations()
            if info.remove is not None
        )
    )
