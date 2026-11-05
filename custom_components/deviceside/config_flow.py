from urllib.parse import quote, urlencode

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig
from homeassistant.loader import async_get_integration

from .const import (
    CONF_PREDICTED_STATE,
    CONF_Z2M_COLOR_MODES,
    DOMAIN,
    NAME,
    PREDICTED_STATE_DEFAULT,
    Z2M_COLOR_MODES_DEFAULT,
)
from .core.resolver import resolve
from .core.runtime import DATA

REPORT_URL = "https://github.com/jasonmx/DeviceSide/issues/new"
CONF_ENTITY = "entity_id"


class DeviceSideConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DeviceSide."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> DeviceSideOptionsFlow:
        return DeviceSideOptionsFlow()

    async def async_step_user(self, user_input=None):
        """Handle the initial step when the user clicks 'Add Integration'."""
        if user_input is not None:
            return self.async_create_entry(title=NAME, data={})

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
        )


async def device_report_url(hass: HomeAssistant, entity_id: str) -> str:
    """A prefilled device report for an entity: its integration, model, firmware and the two versions, and nothing
    that identifies the household (no entity ID, name, area or MAC).

    The integration is DeviceSide's key when it serves the entity. Otherwise it is the entity's platform, so a device
    DeviceSide doesn't cover (Tuya, ESPHome) still reports what people want.
    """
    entry = er.async_get(hass).async_get(entity_id)
    device = dr.async_get(hass).async_get(entry.device_id) if entry and entry.device_id else None
    integration = entry.platform if entry else ""
    if (runtime := hass.data.get(DATA)) is not None and entry is not None:
        target = resolve(hass, runtime.registry, entity_id)
        if not isinstance(target, str):
            integration = target.integration
    fields = {
        "integration": integration,
        "model": (device.model_id or device.model) if device else "",
        "firmware": device.sw_version if device else "",
        "deviceside_version": str((await async_get_integration(hass, DOMAIN)).version),
        "ha_version": HA_VERSION,
    }
    query = urlencode({"template": "device_report.yml", **{k: v for k, v in fields.items() if v}}, quote_via=quote)
    return f"{REPORT_URL}?{query}"


class DeviceSideOptionsFlow(config_entries.OptionsFlowWithReload):
    """A menu: the settings page, whose saving reloads the entry so the next action runs with them, and a report."""

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(step_id="init", menu_options=["settings", "report_device"])

    async def async_step_report_device(self, user_input=None):
        """Pick a light or switch; end on a link to a prefilled device report. Aborting avoids a reload."""
        if user_input is not None:
            url = await device_report_url(self.hass, user_input[CONF_ENTITY])
            return self.async_abort(reason="report_link", description_placeholders={"url": url})
        return self.async_show_form(
            step_id="report_device",
            data_schema=vol.Schema(
                {vol.Required(CONF_ENTITY): EntitySelector(EntitySelectorConfig(domain=["light", "switch"]))}
            ),
        )

    async def async_step_settings(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PREDICTED_STATE, default=options.get(CONF_PREDICTED_STATE, PREDICTED_STATE_DEFAULT)
                    ): bool,
                    vol.Required(
                        CONF_Z2M_COLOR_MODES, default=options.get(CONF_Z2M_COLOR_MODES, Z2M_COLOR_MODES_DEFAULT)
                    ): bool,
                }
            ),
        )
