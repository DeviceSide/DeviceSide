import asyncio
import logging
from dataclasses import dataclass
from urllib.parse import quote, urlencode

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_ENTITY_ID, Platform
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
)
from homeassistant.loader import async_get_integration

from . import coverage
from .const import (
    CONF_LABS,
    CONF_PREDICTED_STATE,
    CONF_Z2M_COLOR_MODES,
    DOMAIN,
    LABS_DEFAULT,
    NAME,
    PREDICTED_STATE_DEFAULT,
    REPO_URL,
    Z2M_COLOR_MODES_DEFAULT,
)
from .core.errors import describe
from .core.resolver import SWITCH_AS_X, resolve
from .core.runtime import DATA

_LOGGER = logging.getLogger(__name__)

REPORT_URL = REPO_URL + "/issues/new"


class DeviceSideConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DeviceSide."""

    VERSION = 1
    # 2: the Labs option's key was renamed (async_migrate_entry).
    MINOR_VERSION = 2

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
    domains: tuple[str, ...] | None = None  # The entity domains its picker offers; None, any.
    known_only: bool = False  # Its picker offers only entities on an integration DeviceSide has.
    device_only: bool = False  # Its picker offers only entities on a device, not helpers, automations or scenes.


_VERSION_FIELDS = ("deviceside_version", "ha_version", "labs")
# In the order of GitHub's template chooser, which sorts the forms by file name.
ISSUE_FORMS = (
    IssueForm(
        "report_device",
        "report_link",
        "device_report.yml",
        ("devices",) + _VERSION_FIELDS,
        "Device report",
        multiple=True,
        domains=(Platform.LIGHT, Platform.SWITCH),  # The only ones that run actions.
        known_only=True,  # Another integration's switches are mostly its settings (Adaptive Lighting's).
    ),
    IssueForm(
        "propose_device",
        "proposal_link",
        "propose_device_or_integration.yml",
        ("devices",),
        "Proposal",
        multiple=True,
        # The domains that control a device. A sensor isn't one, and button, number, select, text and time entities
        # are mostly a device's settings, with no category to filter them by.
        domains=(
            Platform.LIGHT,
            Platform.SWITCH,
            Platform.FAN,
            Platform.COVER,
            Platform.CLIMATE,
            Platform.LOCK,
            Platform.VALVE,
            Platform.MEDIA_PLAYER,
            Platform.SIREN,
            Platform.HUMIDIFIER,
            Platform.WATER_HEATER,
            Platform.VACUUM,
            Platform.LAWN_MOWER,
            Platform.REMOTE,
            Platform.ALARM_CONTROL_PANEL,
            Platform.CAMERA,
        ),
        device_only=True,
    ),
)
_FORMS_BY_STEP = {form.step: form for form in ISSUE_FORMS}


def _picker(hass: HomeAssistant, form: IssueForm) -> EntitySelectorConfig:
    """The form's entity picker, as an include list, which HA checks on submit (its integration filter only narrows
    the dropdown). It leaves out a config or diagnostic entity (a Sonos speaker's loudness switch), which isn't the
    device, and a hidden one; a known_only form's offers only the entities on an integration DeviceSide has and the
    switch_as_x wrappers over them (all of them, without DeviceSide's runtime); a device_only form's only the entities
    on a device."""
    runtime = hass.data.get(DATA)
    platforms = (
        {info.ha_domain for info in runtime.registry.integrations.values()} | {SWITCH_AS_X}
        if form.known_only and runtime is not None
        else None
    )
    config = EntitySelectorConfig(
        multiple=form.multiple,
        include_entities=[
            entry.entity_id
            for entry in er.async_get(hass).entities.values()
            if (form.domains is None or entry.domain in form.domains)
            and entry.entity_category is None
            and entry.hidden_by is None
            and (platforms is None or entry.platform in platforms)
            and (not form.device_only or entry.device_id is not None)
        ],
    )
    if form.domains is not None:
        config["domain"] = list(form.domains)
    return config


def _integration(hass: HomeAssistant, entry: er.RegistryEntry, device: dr.DeviceEntry | None) -> str:
    """DeviceSide's key for the entity's integration when it serves the entity, or when a detect hook claims it (a
    Z2M device on an MQTT broker DeviceSide can't reach yet). Otherwise the entity's platform, so a device DeviceSide
    doesn't cover (Tuya, ESPHome) still reports what people want."""
    if (runtime := hass.data.get(DATA)) is None:
        return entry.platform
    if not isinstance(target := resolve(hass, runtime.registry, entry.entity_id), str):
        return target.integration
    for info in (*runtime.registry.integrations.values(), *runtime.registry.unsupported.values()):
        if info.ha_domain == entry.platform and info.detect is not None and info.detect(hass, entry, device):
            return info.key
    return entry.platform


@dataclass(frozen=True)
class _DeviceFacts:
    """What the registries say about one entity's device; blank where they say nothing."""

    integration: str = ""
    model: str = ""
    product: str = ""
    # The maker: on an integration with a zigbee_manufacturer hook, the device's own Zigbee manufacturer string
    # (`_TZ3000_…`), which a Tuya class keys on (docs/evidence.md, Device classes) and HA's registry may not show (Z2M's
    # definition vendor), blank when the hook has none; elsewhere the registry's manufacturer. Blank, too, where it
    # would repeat the product's.
    manufacturer: str = ""
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
        return " \u00b7 ".join(
            filter(None, [self.integration, self.product, self.model, self.manufacturer, self.firmware])
        )


def _device_facts(hass: HomeAssistant, entity_id: str) -> tuple[str, _DeviceFacts]:
    """The entity's device key (its device ID, else the entity's own) and the facts a report carries."""
    entry = er.async_get(hass).async_get(entity_id)
    if entry is None:
        return entity_id, _DeviceFacts()
    device = dr.async_get(hass).async_get(entry.device_id) if entry.device_id else None
    model_id = (device.model_id or device.model) if device else ""
    # The product name the integration reports ("Hue ambiance lamp"), with its maker; left out when it is only the ID.
    name = device.model if device and device.model_id and device.model != device.model_id else ""
    integration = _integration(hass, entry, device)
    product = " ".join(filter(None, [device.manufacturer if device and name else "", name]))
    manufacturer = _manufacturer(hass, integration, device) if device else ""
    return (entry.device_id or entity_id), _DeviceFacts(
        integration=integration,
        model=model_id or "",
        product=product,
        manufacturer="" if product.startswith(manufacturer) else manufacturer,
        firmware=(device.sw_version or "") if device else "",
        label=" ".join(filter(None, [name, model_id])),
    )


def _manufacturer(hass: HomeAssistant, integration: str, device: dr.DeviceEntry) -> str:
    """The device's own Zigbee manufacturer string from its integration's hook (IntegrationInfo.zigbee_manufacturer),
    blank when the hook has none or raises: the registry's would be another string (Z2M's vendor), which a report
    can't be matched by. The registry's manufacturer for an integration without the hook."""
    runtime = hass.data.get(DATA)
    info = runtime.registry.integrations.get(integration) if runtime is not None else None
    if info is None or info.zigbee_manufacturer is None:
        return device.manufacturer or ""
    try:
        return info.zigbee_manufacturer(hass, device) or ""
    except Exception as err:  # noqa: BLE001 - a broken hook must not break the form; the string is left out
        _LOGGER.debug("%s: no Zigbee manufacturer string for the report form: %s", integration, describe(err))
        return ""


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
    """A prefilled issue for the entities' devices (one entry per device), the two versions and whether Labs was on,
    as far as the form asks for them, and nothing that identifies the household (no entity ID, name, area or MAC)."""
    # One entry per distinct device facts, so several devices of one model give one line.
    devices = list(dict.fromkeys(dict(_device_facts(hass, entity_id) for entity_id in entity_ids).values()))
    values = {
        "devices": "\n".join(device.line for device in devices if device.line),
        "deviceside_version": str((await async_get_integration(hass, DOMAIN)).version),
        "ha_version": HA_VERSION,
        # A text field, as GitHub prefills only those. Left out, not "off", when DeviceSide isn't loaded.
        "labs": "" if (runtime := hass.data.get(DATA)) is None else ("on" if runtime.labs else "off"),
    }
    query = {"template": form.template}
    subjects = list(dict.fromkeys(filter(None, (device.subject for device in devices))))
    query["title"] = _title(form.title, subjects)
    query |= {field: values[field] for field in form.fields if values[field]}
    return f"{REPORT_URL}?{urlencode(query, quote_via=quote)}"


class DeviceSideOptionsFlow(config_entries.OptionsFlowWithReload):
    """A menu: the settings page (with the device coverage), whose saving reloads the entry so the next action runs
    with them, and the issue forms, each prefilled from the entities picked."""

    _issue_url: str = ""

    _wait: asyncio.Task[None] | None = None
    _waited = False

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
        """Pick the entities (one, for a form that takes a single device), then show the link."""
        if user_input is not None:
            picked = user_input[CONF_ENTITY_ID]
            self._issue_url = await issue_url(self.hass, form, picked if isinstance(picked, list) else [picked])
            return self._show_link(form.link_step, None)
        return self.async_show_form(
            step_id=form.step,
            data_schema=vol.Schema({vol.Required(CONF_ENTITY_ID): EntitySelector(_picker(self.hass, form))}),
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
        """What DeviceSide runs on each light and switch, collapsed above the options. Saving reloads the entry
        only if an option changed (OptionsFlowWithReload). First, while an integration is still listing its devices
        (coverage.waiting), HA's progress spinner for at most coverage.WAIT_S."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        if not self._waited:
            if self._wait is None and (pending := coverage.waiting(self.hass)):
                self._wait = self.hass.async_create_task(coverage.settle(pending))
            if self._wait is not None:
                if not self._wait.done():
                    return self.async_show_progress(
                        step_id="settings", progress_action="waiting_for_devices", progress_task=self._wait
                    )
                self._waited = True
                return self.async_show_progress_done(next_step_id="settings")
            self._waited = True

        options = self.config_entry.options
        labs = options.get(CONF_LABS, LABS_DEFAULT)
        found = await coverage.collect(self.hass)
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
                    vol.Required(CONF_LABS, default=labs): bool,
                }
            ),
            description_placeholders={
                "features": str(found.features_now),
                "devices": str(found.devices_now),
                "legend": coverage.legend(),
                "table": coverage.table(self.hass, found),
                # What Labs would add: said only while Labs is off and something is in Labs.
                "labs_adds": (
                    f"Turn on Labs: adds {found.features_in_labs} features on {found.devices_in_labs} devices. "
                    if not labs and found.features_in_labs
                    else ""
                ),
            },
        )
