from dataclasses import dataclass
from urllib.parse import quote, urlencode

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
)
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
    title: str  # The prefilled title's prefix.
    multiple: bool = False  # Takes several devices, not one.


_DEVICE_FIELDS = ("integration", "model", "product", "firmware")
_VERSION_FIELDS = ("deviceside_version", "ha_version", "experimental_features")
# In the order of GitHub's template chooser, which sorts the forms by file name.
ISSUE_FORMS = (
    IssueForm(
        "report_device",
        "report_link",
        "device_report.yml",
        ("devices",) + _VERSION_FIELDS,
        "Device report",
        multiple=True,
    ),
    IssueForm("propose_device", "proposal_link", "propose_device_or_integration.yml", _DEVICE_FIELDS, "Proposal"),
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


@dataclass(frozen=True)
class _DeviceFacts:
    """What the registries say about one entity's device; blank where they say nothing."""

    integration: str = ""
    model: str = ""
    product: str = ""
    firmware: str = ""
    label: str = ""  # The product name and model, for a title.

    @property
    def subject(self) -> str:
        if self.label and self.integration:
            return f"{self.label} ({self.integration})"
        return self.label or self.integration

    @property
    def line(self) -> str:
        """One line of the report's Devices field."""
        return " \u00b7 ".join(filter(None, [self.integration, self.product, self.model, self.firmware]))


def _device_facts(hass: HomeAssistant, entity_id: str) -> tuple[str, _DeviceFacts]:
    """The entity's device key (its device ID, else the entity's own) and the facts a report carries."""
    entry = er.async_get(hass).async_get(entity_id)
    if entry is None:
        return entity_id, _DeviceFacts()
    device = dr.async_get(hass).async_get(entry.device_id) if entry.device_id else None
    model_id = (device.model_id or device.model) if device else ""
    # The product name the integration reports ("Hue ambiance lamp"), with its maker; left out when it is only the ID.
    name = device.model if device and device.model_id and device.model != device.model_id else ""
    return (entry.device_id or entity_id), _DeviceFacts(
        integration=_integration(hass, entry, device),
        model=model_id or "",
        product=" ".join(filter(None, [device.manufacturer if device and name else "", name])),
        firmware=(device.sw_version or "") if device else "",
        label=" ".join(filter(None, [name, model_id])),
    )


_TITLE_LIMIT = 200  # GitHub's is 256; the prefix and "and N more" fit in the rest.


def _title(prefix: str, subjects: list[str]) -> str:
    """The prefix and as many subjects as fit the limit (always the first), then "and N more"."""
    shown = subjects[:1]
    for subject in subjects[1:]:
        if len(f"{prefix}: {', '.join([*shown, subject])}") > _TITLE_LIMIT:
            break
        shown.append(subject)
    if not shown:
        return prefix
    title = f"{prefix}: {', '.join(shown)}"
    more = len(subjects) - len(shown)
    return f"{title} and {more} more" if more else title


async def issue_url(hass: HomeAssistant, form: IssueForm, entity_ids: list[str]) -> str:
    """A prefilled issue for the entities' devices (one entry per device), the two versions and whether Experimental
    features was on, as far as the form asks for them, and nothing that identifies the household (no entity ID, name,
    area or MAC)."""
    # One entry per distinct device facts, so several devices of one model give one line.
    devices = list(dict.fromkeys(dict(_device_facts(hass, entity_id) for entity_id in entity_ids).values()))
    first = devices[0] if devices else _DeviceFacts()
    values = {
        "integration": first.integration,
        "model": first.model,
        "product": first.product,
        "firmware": first.firmware,
        "devices": "\n".join(device.line for device in devices if device.line),
        "deviceside_version": str((await async_get_integration(hass, DOMAIN)).version),
        "ha_version": HA_VERSION,
        # A text field, as GitHub prefills only those. Left out, not "off", when DeviceSide isn't loaded.
        "experimental_features": ""
        if (runtime := hass.data.get(DATA)) is None
        else ("on" if runtime.experimental_features else "off"),
    }
    query = {"template": form.template}
    subjects = list(dict.fromkeys(filter(None, (device.subject for device in devices))))
    query["title"] = _title(form.title, subjects)
    query |= {field: values[field] for field in form.fields if values[field]}
    return f"{REPORT_URL}?{urlencode(query, quote_via=quote)}"


class DeviceSideOptionsFlow(config_entries.OptionsFlowWithReload):
    """A menu: the settings page, whose saving reloads the entry so the next action runs with them, and the issue
    forms, each prefilled from a light or switch."""

    _issue_url: str = ""

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(step_id="init", menu_options=["settings", *_FORMS_BY_STEP])

    async def async_step_report_device(self, user_input=None):
        return await self._pick_entities(_FORMS_BY_STEP["report_device"], user_input)

    async def async_step_propose_device(self, user_input=None):
        return await self._pick_entities(_FORMS_BY_STEP["propose_device"], user_input)

    async def async_step_report_link(self, user_input=None):
        return self._show_link("report_link", user_input)

    async def async_step_proposal_link(self, user_input=None):
        return self._show_link("proposal_link", user_input)

    async def _pick_entities(self, form: IssueForm, user_input):
        """Pick the lights and switches (one, for a form that takes a single device), then show the link."""
        if user_input is not None:
            picked = user_input[CONF_ENTITY]
            self._issue_url = await issue_url(self.hass, form, picked if isinstance(picked, list) else [picked])
            return self._show_link(form.link_step, None)
        return self.async_show_form(
            step_id=form.step,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ENTITY): EntitySelector(
                        EntitySelectorConfig(domain=["light", "switch"], multiple=form.multiple)
                    )
                }
            ),
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
