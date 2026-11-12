"""Tests for the single-instance config flow, its options and entry setup."""

import asyncio
from urllib.parse import parse_qs, urlparse

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration
from homeassistant.setup import async_set_domains_to_be_loaded, async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockModule, mock_integration

from custom_components.deviceside.config_flow import _FORMS_BY_STEP, _title, issue_url
from custom_components.deviceside.const import (
    CONF_EXPERIMENTAL,
    CONF_PREDICTED_STATE,
    CONF_Z2M_COLOR_MODES,
    DOMAIN,
    NAME,
)
from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.runtime import get_runtime

from .conftest import load_entry, unload_mock_entries
from .fixtures.zha import IEEE, add_zha_entity, zha_entry


async def open_settings(hass: HomeAssistant, entry: MockConfigEntry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "settings"})


async def report_for(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    entity_ids: str | list[str],
    step: str = "report_device",
    link_step: str = "report_link",
) -> tuple[dict, str]:
    """Run an issue step for the entities (a list, for the form that takes several), and return the prefill fields
    from its link, and the link."""
    options_before = dict(entry.options)
    runtime_before = get_runtime(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": step})
    assert result["type"] is FlowResultType.FORM
    if step == "report_device" and isinstance(entity_ids, str):
        entity_ids = [entity_ids]  # the report form takes a list of devices; the proposal form takes one
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"entity_id": entity_ids})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == link_step
    url = result["description_placeholders"]["url"]
    assert url.startswith("https://github.com/DeviceSide/DeviceSide/issues/new?")
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == options_before  # closing the dialog saves nothing
    assert get_runtime(hass) is runtime_before  # and a reload would have built a new runtime
    return {key: value for key, [value] in parse_qs(urlparse(url).query).items()}, url


def add_mqtt_light(hass: HomeAssistant, identifier: str, object_id: str = "desk") -> None:
    """light.desk (or another) on an MQTT broker that isn't loaded, so DeviceSide can't serve it."""
    mqtt = MockConfigEntry(domain="mqtt")
    mqtt.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=mqtt.entry_id, identifiers={("mqtt", identifier)}, model="Bulb", sw_version="2.0"
    )
    er.async_get(hass).async_get_or_create(
        "light", "mqtt", f"u3-{object_id}", suggested_object_id=object_id, config_entry=mqtt, device_id=device.id
    )


async def test_user_step_creates_entry(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == {}


async def test_second_entry_aborts(hass: HomeAssistant):
    MockConfigEntry(domain=DOMAIN).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_entry_loads_and_unloads(hass: HomeAssistant):
    entry = await load_entry(hass)
    assert entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_an_integration_stuck_in_setup_does_not_hold_deviceside_back(hass: HomeAssistant):
    """HA holds an integration's setup until each of its after_dependencies being set up has finished. A ZHA that
    never finishes must leave DeviceSide's actions up, refusing only ZHA's targets."""
    setting_up = asyncio.Event()

    async def hang(hass, config):
        setting_up.set()
        await asyncio.Event().wait()

    mock_integration(hass, MockModule("zha", async_setup=hang))
    async_set_domains_to_be_loaded(hass, {"zha", DOMAIN})  # as bootstrap does: HA waits only on these
    zha_setup = hass.async_create_task(async_setup_component(hass, "zha", {}))
    await setting_up.wait()
    zha = MockConfigEntry(domain="zha")
    zha.add_to_hass(hass)
    zha.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    entry = MockConfigEntry(domain=DOMAIN)  # not load_entry, whose block_till_done would wait on the hung ZHA
    entry.add_to_hass(hass)

    try:
        async with asyncio.timeout(5):
            assert await hass.config_entries.async_setup(entry.entry_id)
        assert hass.services.has_service(DOMAIN, "turn_on_for")
        add_zha_entity(hass, zha, "light.a")
        assert resolve(hass, get_runtime(hass).registry, "light.a") == "integration_not_loaded"
    finally:
        zha_setup.cancel()


async def test_predicted_state_is_on_for_an_entry_without_options(hass: HomeAssistant):
    await load_entry(hass)
    assert get_runtime(hass).predicted_state is True


async def test_saving_the_option_reloads_the_entry_with_it(hass: HomeAssistant):
    entry = await load_entry(hass)

    result = await open_settings(hass, entry)
    assert result["data_schema"]({}) == {
        CONF_PREDICTED_STATE: True,
        CONF_Z2M_COLOR_MODES: True,
        CONF_EXPERIMENTAL: False,
    }
    assert get_runtime(hass).experimental_features is False
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PREDICTED_STATE: False, CONF_EXPERIMENTAL: True}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_PREDICTED_STATE: False, CONF_Z2M_COLOR_MODES: True, CONF_EXPERIMENTAL: True}
    assert entry.state is ConfigEntryState.LOADED
    assert get_runtime(hass).predicted_state is False
    assert get_runtime(hass).experimental_features is True

    result = await open_settings(hass, entry)
    assert result["data_schema"]({}) == {
        CONF_PREDICTED_STATE: False,
        CONF_Z2M_COLOR_MODES: True,
        CONF_EXPERIMENTAL: True,
    }


async def test_the_options_menu_offers_settings_and_the_issue_forms(hass: HomeAssistant):
    entry = await load_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["settings", "report_device", "propose_device"]


async def test_a_report_for_a_supported_light_lists_its_integration_product_model_and_firmware(
    hass: HomeAssistant, zha
):
    entry = await load_entry(hass)
    add_zha_entity(hass, zha, "light.kitchen_lamp")
    device = dr.async_get(hass).async_get(er.async_get(hass).async_get("light.kitchen_lamp").device_id)
    dr.async_get(hass).async_update_device(
        device.id,
        manufacturer="Signify Netherlands B.V.",
        model="Hue ambiance lamp",
        model_id="LTA009",
        sw_version="0x01002a00",
        name="Kitchen lamp",
    )

    fields, url = await report_for(hass, entry, "light.kitchen_lamp")

    assert fields == {
        "template": "device_report.yml",
        "title": "Device report: Hue ambiance lamp LTA009 (zha)",
        "devices": "zha \u00b7 Signify Netherlands B.V. Hue ambiance lamp \u00b7 LTA009 \u00b7 0x01002a00",
        "deviceside_version": (await async_get_integration(hass, DOMAIN)).version,
        "ha_version": HA_VERSION,
        "experimental_features": "off",
    }
    for private in ("light.kitchen_lamp", "kitchen", "Kitchen", IEEE, "00%3A17"):
        assert private not in url


async def test_a_report_for_an_unsupported_platform_uses_the_raw_platform(hass: HomeAssistant):
    """Tuya isn't served, and those reports are the demand signal for new adapters."""
    entry = await load_entry(hass)
    tuya = MockConfigEntry(domain="tuya")
    tuya.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=tuya.entry_id, identifiers={("tuya", "x")}, model="Dimmer", sw_version="1.0"
    )
    er.async_get(hass).async_get_or_create(
        "light", "tuya", "u1", suggested_object_id="den", config_entry=tuya, device_id=device.id
    )

    fields, url = await report_for(hass, entry, "light.den")

    assert fields["devices"] == "tuya \u00b7 Dimmer \u00b7 1.0"  # no model_id, so the model is the whole name
    assert fields["title"] == "Device report: Dimmer (tuya)"
    assert "den" not in url


async def test_a_report_for_an_entity_without_a_device_leaves_those_fields_out(hass: HomeAssistant):
    entry = await load_entry(hass)
    er.async_get(hass).async_get_or_create("switch", "template", "u2", suggested_object_id="virtual")

    fields, _ = await report_for(hass, entry, "switch.virtual")

    assert fields["devices"] == "template"
    assert fields["title"] == "Device report: template"
    assert {"deviceside_version", "ha_version"} <= fields.keys()


async def test_a_report_for_an_entity_outside_the_registry_leaves_the_integration_blank(hass: HomeAssistant):
    entry = await load_entry(hass)
    hass.states.async_set("light.ghost", "off")

    fields, _ = await report_for(hass, entry, "light.ghost")

    assert "devices" not in fields
    assert fields["title"] == "Device report"


@pytest.mark.parametrize(("step", "multiple"), [("report_device", True), ("propose_device", False)])
async def test_each_issue_step_offers_only_lights_and_switches(hass: HomeAssistant, step, multiple):
    entry = await load_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": step})
    selector = result["data_schema"].schema["entity_id"]
    assert selector.config["domain"] == ["light", "switch"]
    assert selector.config["multiple"] is multiple


async def test_a_z2m_device_deviceside_cannot_serve_still_reports_as_zigbee2mqtt(hass: HomeAssistant):
    """Z2M's identifier tells its devices from other MQTT ones, even with the broker down."""
    entry = await load_entry(hass)
    add_mqtt_light(hass, "zigbee2mqtt_0x0017880102030405")

    fields, _ = await report_for(hass, entry, "light.desk")

    assert fields["devices"] == "zigbee2mqtt \u00b7 Bulb \u00b7 2.0"
    assert fields["title"] == "Device report: Bulb (zigbee2mqtt)"


async def test_a_plain_mqtt_device_reports_as_mqtt(hass: HomeAssistant):
    entry = await load_entry(hass)
    add_mqtt_light(hass, "tasmota_ABC123")

    fields, _ = await report_for(hass, entry, "light.desk")

    assert fields["devices"] == "mqtt \u00b7 Bulb \u00b7 2.0"


async def test_a_report_for_two_devices_lists_one_line_each(hass: HomeAssistant, zha):
    entry = await load_entry(hass)
    add_zha_entity(hass, zha, "light.a")
    add_mqtt_light(hass, "tasmota_ABC123")

    fields, url = await report_for(hass, entry, ["light.a", "light.desk"])

    assert fields["devices"] == "zha\nmqtt \u00b7 Bulb \u00b7 2.0"
    assert fields["title"] == "Device report: zha, Bulb (mqtt)"
    for private in ("light.a", "light.desk", "desk", IEEE, "00%3A17"):
        assert private not in url


async def test_two_entities_of_one_device_give_one_line(hass: HomeAssistant, zha):
    entry = await load_entry(hass)
    add_zha_entity(hass, zha, "light.a")
    add_zha_entity(hass, zha, "switch.b", unique_id=f"{IEEE}-12")

    fields, _ = await report_for(hass, entry, ["light.a", "switch.b"])

    assert fields["devices"] == "zha"
    assert fields["title"] == "Device report: zha"


async def test_several_devices_of_one_model_give_one_line_and_one_subject(hass: HomeAssistant):
    entry = await load_entry(hass)
    add_mqtt_light(hass, "tasmota_A")
    add_mqtt_light(hass, "tasmota_B", object_id="hall")

    fields, _ = await report_for(hass, entry, ["light.desk", "light.hall"])

    assert fields["devices"] == "mqtt \u00b7 Bulb \u00b7 2.0"
    assert fields["title"] == "Device report: Bulb (mqtt)"


def test_a_long_title_keeps_the_first_subject_and_counts_the_rest():
    subjects = [f"Device number {n} of the long list" for n in range(30)]

    title = _title("Device report", subjects)

    assert len(title) <= 256
    assert title.startswith("Device report: Device number 0 of the long list, Device number 1")
    assert title.endswith(f" and {30 - title.count('Device number')} more")
    assert _title("Device report", subjects[:2]) == "Device report: " + ", ".join(subjects[:2])
    assert _title("Device report", []) == "Device report"


async def test_a_report_says_whether_experimental_features_was_on(hass: HomeAssistant):
    """A report on an Experimental item means something else with the option off: it was refused, not tried."""
    entry = await load_entry(hass)
    get_runtime(hass).experimental_features = True

    add_mqtt_light(hass, "tasmota_ABC123")

    fields, _ = await report_for(hass, entry, ["light.desk"])

    assert fields["experimental_features"] == "on"


async def test_a_report_leaves_experimental_features_out_when_deviceside_is_not_loaded(hass: HomeAssistant):
    """Unknown is not "off": a blank field asks the reporter rather than claiming the option was off."""
    url = await issue_url(hass, _FORMS_BY_STEP["report_device"], [])

    assert "experimental_features" not in parse_qs(urlparse(url).query)


async def test_a_proposal_carries_the_device_but_not_the_versions(hass: HomeAssistant):
    """The proposal form has no version fields: DeviceSide doesn't run the device yet."""
    entry = await load_entry(hass)
    add_mqtt_light(hass, "tasmota_ABC123")

    fields, _ = await report_for(hass, entry, "light.desk", "propose_device", "proposal_link")

    assert fields == {
        "template": "propose_device_or_integration.yml",
        "title": "Proposal: Bulb (mqtt)",
        "integration": "mqtt",
        "model": "Bulb",
        "firmware": "2.0",
    }


async def test_a_device_report_needs_a_device(hass: HomeAssistant):
    entry = await load_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "report_device"})
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(result["flow_id"], {})


unload_mock_zha_entries = unload_mock_entries("zha")


@pytest.fixture
def zha(hass: HomeAssistant) -> MockConfigEntry:
    return zha_entry(hass)
