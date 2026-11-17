"""Migration repairs: v0.0.1's `device_side` leftovers get a fixable repair, Hue Smooth Dimming an instructions-only
one, and each clears when its condition is gone."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.components.repairs import repairs_flow_manager
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.deviceside.const import DOMAIN
from custom_components.deviceside.migrations import async_check_migrations

from .conftest import unload_mock_entries

LEGACY = "legacy_device_side"
CALLS = "legacy_device_side_calls"
HUE_DIMMER = "migrate_hue_dimmer"

unload_hue_dimmer = unload_mock_entries("hue_dimmer")


@pytest.fixture
def hass_config_dir(hass_tmp_config_dir: str) -> str:
    """A temp config dir, so the tests can create and delete custom_components/device_side."""
    return hass_tmp_config_dir


def legacy_folder(hass: HomeAssistant, manifest: dict | None = {"domain": "device_side"}) -> Path:  # noqa: B006
    folder = Path(hass.config.path("custom_components", "device_side"))
    folder.mkdir(parents=True)
    (folder / "__init__.py").write_text("")
    if manifest is not None:
        (folder / "manifest.json").write_text(json.dumps(manifest))
    return folder


def legacy_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain="device_side")
    entry.add_to_hass(hass)
    return entry


def issue(hass: HomeAssistant, issue_id: str) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, issue_id)


async def fix(hass: HomeAssistant) -> dict:
    """Run the legacy repair's fix flow through HA's repairs manager: show the form, then submit it. The manager
    finds DeviceSide's repairs platform only once DeviceSide is loaded (the `setup_integration` fixture)."""
    assert await async_setup_component(hass, "repairs", {})
    manager = repairs_flow_manager(hass)
    form = await manager.async_init(DOMAIN, data={"issue_id": LEGACY})
    assert form["type"] is FlowResultType.FORM
    assert form["step_id"] == "confirm"
    assert form["description_placeholders"] == {"folder": hass.config.path("custom_components", "device_side")}
    return await manager.async_configure(form["flow_id"], {})


async def test_nothing_to_migrate_clears_stale_issues(hass: HomeAssistant):
    for issue_id in (LEGACY, HUE_DIMMER):
        ir.async_create_issue(
            hass, DOMAIN, issue_id, is_fixable=False, severity=ir.IssueSeverity.WARNING, translation_key=issue_id
        )

    await async_check_migrations(hass)

    assert issue(hass, LEGACY) is None
    assert issue(hass, HUE_DIMMER) is None


@pytest.mark.parametrize(("entry", "folder"), [(True, False), (False, True), (True, True)])
async def test_legacy_leftovers_raise_a_fixable_issue(hass: HomeAssistant, entry, folder):
    if entry:
        legacy_entry(hass)
    if folder:
        legacy_folder(hass)

    await async_check_migrations(hass)

    found = issue(hass, LEGACY)
    assert found is not None
    assert found.is_fixable
    assert not found.is_persistent
    assert found.severity is ir.IssueSeverity.WARNING
    assert found.translation_placeholders == {"folder": hass.config.path("custom_components", "device_side")}


async def test_fix_removes_entries_and_folder(hass: HomeAssistant, setup_integration):
    legacy_entry(hass)
    legacy_entry(hass)
    folder = legacy_folder(hass)
    await async_check_migrations(hass)

    result = await fix(hass)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert hass.config_entries.async_entries("device_side") == []
    assert not folder.exists()
    # The manager deletes the fixed issue; the next start's check finds nothing to raise it again.
    assert issue(hass, LEGACY) is None
    await async_check_migrations(hass)
    assert issue(hass, LEGACY) is None


@pytest.mark.parametrize("manifest", [{"domain": "something_else"}, None, "not json"])
async def test_guard_keeps_a_folder_that_is_not_device_side(hass: HomeAssistant, setup_integration, manifest):
    legacy_entry(hass)
    folder = legacy_folder(hass, None if manifest == "not json" else manifest)
    if manifest == "not json":
        (folder / "manifest.json").write_text("{")
    await async_check_migrations(hass)

    result = await fix(hass)

    # Left for the user, so the Fix aborts and the issue stays rather than reporting it fixed.
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "folder_left"
    assert hass.config_entries.async_entries("device_side") == []
    assert (folder / "__init__.py").exists()
    assert issue(hass, LEGACY) is not None


async def test_guard_keeps_a_symlinked_folder(hass: HomeAssistant, setup_integration, tmp_path: Path):
    target = tmp_path / "checkout"
    target.mkdir()
    (target / "manifest.json").write_text(json.dumps({"domain": "device_side"}))
    link = Path(hass.config.path("custom_components", "device_side"))
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)
    await async_check_migrations(hass)

    assert (await fix(hass))["reason"] == "folder_left"
    assert (target / "manifest.json").exists()


async def test_fix_that_cannot_delete_the_folder_aborts(hass: HomeAssistant, setup_integration):
    legacy_entry(hass)
    folder = legacy_folder(hass)
    await async_check_migrations(hass)

    with patch("custom_components.deviceside.migrations.shutil.rmtree", side_effect=PermissionError):
        result = await fix(hass)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "folder_left"
    assert result["description_placeholders"] == {"folder": str(folder)}
    assert hass.config_entries.async_entries("device_side") == []
    assert issue(hass, LEGACY) is not None


@pytest.mark.parametrize("state", [ConfigEntryState.LOADED, ConfigEntryState.NOT_LOADED])
async def test_hue_dimmer_entry_raises_an_instructions_issue(hass: HomeAssistant, state):
    entry = MockConfigEntry(domain="hue_dimmer")
    entry.add_to_hass(hass)
    entry.mock_state(hass, state)

    await async_check_migrations(hass)

    found = issue(hass, HUE_DIMMER)
    assert found is not None
    assert not found.is_fixable
    assert found.severity is ir.IssueSeverity.WARNING
    assert found.learn_more_url == "https://github.com/DeviceSide/DeviceSide#coming-from-hue-smooth-dimming"


async def test_ignored_hue_dimmer_issue_stays_ignored(hass: HomeAssistant):
    MockConfigEntry(domain="hue_dimmer").add_to_hass(hass)
    await async_check_migrations(hass)
    ir.async_ignore_issue(hass, DOMAIN, HUE_DIMMER, True)

    await async_check_migrations(hass)

    assert issue(hass, HUE_DIMMER).dismissed_version is not None


async def test_setup_runs_the_checks(hass: HomeAssistant, fake_registry):
    legacy_entry(hass)
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert issue(hass, LEGACY) is not None


async def test_fix_removes_the_legacy_actions(hass: HomeAssistant, setup_integration):
    legacy_entry(hass)
    legacy_folder(hass)
    for service in ("turn_on_for", "turn_off_for"):
        hass.services.async_register("device_side", service, lambda call: None)
    await async_check_migrations(hass)

    await fix(hass)

    assert not hass.services.has_service("device_side", "turn_on_for")
    assert not hass.services.has_service("device_side", "turn_off_for")


def automations(action: str) -> dict:
    return {
        "automation": [
            {
                "id": "hall_1",
                "alias": "Hall [night]",
                "triggers": [{"trigger": "event", "event_type": "test"}],
                "actions": [{"choose": [{"conditions": [], "sequence": [{"action": action}]}]}],
            },
            {
                "alias": "Porch",
                "triggers": [{"trigger": "event", "event_type": "test"}],
                "actions": [{"service": action}],
            },
        ]
    }


def scripts(action: str) -> dict:
    return {"script": {"stairs": {"alias": "Stairs", "sequence": [{"action": action, "data": {"seconds": 5}}]}}}


async def calls_setup(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "automation", automations("device_side.turn_on_for"))
    assert await async_setup_component(hass, "script", scripts("device_side.turn_off_for"))
    await hass.async_block_till_done()


async def reload(hass: HomeAssistant, domain: str, config: dict) -> None:
    with patch("homeassistant.config.load_yaml_config_file", autospec=True, return_value=config):
        await hass.services.async_call(domain, "reload", blocking=True)
    await hass.async_block_till_done()


async def test_legacy_calls_listed_until_renamed(hass: HomeAssistant, setup_integration):
    await calls_setup(hass)

    found = issue(hass, CALLS)
    assert found is not None
    assert not found.is_fixable
    assert found.severity is ir.IssueSeverity.WARNING
    assert found.translation_placeholders == {
        "items": "- [Hall \\[night\\]](/config/automation/edit/hall_1)\n- Porch\n- [Stairs](/config/script/edit/stairs)"
    }

    await reload(hass, "automation", automations("deviceside.turn_on_for"))
    assert issue(hass, CALLS).translation_placeholders == {"items": "- [Stairs](/config/script/edit/stairs)"}

    await reload(hass, "script", scripts("deviceside.turn_off_for"))
    assert issue(hass, CALLS) is None


async def test_no_calls_issue_while_the_legacy_entry_is_there(hass: HomeAssistant, setup_integration):
    entry = legacy_entry(hass)
    legacy_folder(hass)
    await calls_setup(hass)
    assert issue(hass, CALLS) is None

    # The Fix removes the entry, so the calls it leaves are listed at once.
    await async_check_migrations(hass)
    await fix(hass)

    assert hass.config_entries.async_get_entry(entry.entry_id) is None
    assert issue(hass, CALLS) is not None
