from dataclasses import dataclass
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
    CONF_EXPERIMENTAL,
    CONF_PREDICTED_STATE,
    CONF_Z2M_COLOR_MODES,
    DOMAIN,
    EXPERIMENTAL_DEFAULT,
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


@dataclass(frozen=True)
class IssueForm:
    """An issue template the options menu prefills: its menu step, the step holding the link, and what it asks."""

    step: str
    link_step: str
    template: str
    fields: tuple[str, ...]
    title: str | None  # The prefilled title's prefix; None keeps the template's own title for the reporter to finish.
    entity_required: bool = True


_DEVICE_FIELDS = ("integration", "model", "product", "firmware")
_VERSION_FIELDS = ("deviceside_version", "ha_version", "experimental_features")
# In the order of GitHub's template chooser, which sorts the forms by file name.
ISSUE_FORMS = (
    IssueForm(
        "report_device", "report_link", "device_report.yml", _DEVICE_FIELDS + _VERSION_FIELDS, "Device test result"
    ),
    IssueForm("propose_device", "proposal_link", "propose_device_or_integration.yml", _DEVICE_FIELDS, "Proposal"),
    IssueForm(
        "report_bug", "bug_link", "report_bug.yml", _DEVICE_FIELDS + _VERSION_FIELDS, None, entity_required=False
    ),
)
_FORMS_BY_STEP = {form.step: form for form in ISSUE_FORMS}


def _integration(hass: HomeAssistant, entry: er.RegistryEntry, device: dr.DeviceEntry | None) -> str:
    """DeviceSide's key for the entity's integration when it serves the entity, or when a detect hook claims it (a
    Z2M device on an MQTT broker DeviceSide can't reach yet). Otherwise the entity's platform, so a device DeviceSide
    doesn't cover (Tuya, ESPHome) still reports what people want."""
    if (runtime := hass.data.get(DATA)) is None:
        return entry.platform
    if not isinstance(target := resolve(hass, runtime.registry, entry.entity_id), str):
        return target.integration
    for info in runtime.registry.integrations.values():
        if info.ha_domain == entry.platform and info.detect is not None and info.detect(hass, entry, device):
            return info.key
    return entry.platform


async def issue_url(hass: HomeAssistant, form: IssueForm, entity_id: str | None) -> str:
    """A prefilled issue for an entity: its integration, model, product name, firmware and the two versions, as far
    as the form asks for them, and nothing that identifies the household (no entity ID, name, area or MAC)."""
    entry = er.async_get(hass).async_get(entity_id) if entity_id else None
    device = dr.async_get(hass).async_get(entry.device_id) if entry and entry.device_id else None
    integration = _integration(hass, entry, device) if entry else ""
    model_id = (device.model_id or device.model) if device else ""
    # The product name the integration reports ("Hue ambiance lamp"), with its maker; left out when it is only the ID.
    name = device.model if device and device.model_id and device.model != device.model_id else ""
    values = {
        "integration": integration,
        "model": model_id,
        "product": " ".join(filter(None, [device.manufacturer if device and name else "", name])),
        "firmware": device.sw_version if device else "",
        "deviceside_version": str((await async_get_integration(hass, DOMAIN)).version),
        "ha_version": HA_VERSION,
        # A text field, as GitHub prefills only those: "on" or "off", what the dispatcher let through.
        "experimental_features": "on" if (runtime := hass.data.get(DATA)) and runtime.experimental_features else "off",
    }
    query = {"template": form.template}
    if form.title is not None:
        device_label = " ".join(filter(None, [name, model_id]))
        subject = f"{device_label} ({integration})" if device_label and integration else device_label or integration
        query["title"] = f"{form.title}: {subject}" if subject else form.title
    query |= {field: values[field] for field in form.fields if values[field]}
    return f"{REPORT_URL}?{urlencode(query, quote_via=quote)}"


class DeviceSideOptionsFlow(config_entries.OptionsFlowWithReload):
    """A menu: the settings page, whose saving reloads the entry so the next action runs with them, and the issue
    forms, each prefilled from a light or switch."""

    _issue_url: str = ""

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(step_id="init", menu_options=["settings", *_FORMS_BY_STEP])

    async def async_step_report_device(self, user_input=None):
        return await self._pick_entity(_FORMS_BY_STEP["report_device"], user_input)

    async def async_step_report_bug(self, user_input=None):
        return await self._pick_entity(_FORMS_BY_STEP["report_bug"], user_input)

    async def async_step_propose_device(self, user_input=None):
        return await self._pick_entity(_FORMS_BY_STEP["propose_device"], user_input)

    async def async_step_report_link(self, user_input=None):
        return self._show_link("report_link", user_input)

    async def async_step_bug_link(self, user_input=None):
        return self._show_link("bug_link", user_input)

    async def async_step_proposal_link(self, user_input=None):
        return self._show_link("proposal_link", user_input)

    async def _pick_entity(self, form: IssueForm, user_input):
        """Pick a light or switch (optional for a bug, which may not be device-specific); go on to the link."""
        if user_input is not None:
            self._issue_url = await issue_url(self.hass, form, user_input.get(CONF_ENTITY))
            return self._show_link(form.link_step, None)
        key = vol.Required(CONF_ENTITY) if form.entity_required else vol.Optional(CONF_ENTITY)
        return self.async_show_form(
            step_id=form.step,
            data_schema=vol.Schema({key: EntitySelector(EntitySelectorConfig(domain=["light", "switch"]))}),
        )

    def _show_link(self, step_id: str, user_input):
        """The link, on a step of its own so the dialog carries the step's title. Submitting closes the flow with the
        options as they were: OptionsFlowWithReload reloads only on changed options, so nothing reloads."""
        if user_input is not None:
            return self.async_create_entry(data=dict(self.config_entry.options))
        return self.async_show_form(
            step_id=step_id, data_schema=vol.Schema({}), description_placeholders={"url": self._issue_url}
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
                    vol.Required(CONF_EXPERIMENTAL, default=options.get(CONF_EXPERIMENTAL, EXPERIMENTAL_DEFAULT)): bool,
                }
            ),
        )
