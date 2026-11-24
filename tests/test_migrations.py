"""The Hue Smooth Dimming repair: raised, instructions only, while a hue_dimmer entry exists; cleared once none is."""

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.deviceside.const import DOMAIN
from custom_components.deviceside.migrations import async_check_hue_dimmer

from .conftest import unload_mock_entries

HUE_DIMMER = "migrate_hue_dimmer"

unload_hue_dimmer = unload_mock_entries("hue_dimmer")


def issue(hass: HomeAssistant) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, HUE_DIMMER)


async def test_no_hue_dimmer_clears_a_stale_issue(hass: HomeAssistant):
    ir.async_create_issue(
        hass, DOMAIN, HUE_DIMMER, is_fixable=False, severity=ir.IssueSeverity.WARNING, translation_key=HUE_DIMMER
    )

    async_check_hue_dimmer(hass)

    assert issue(hass) is None


@pytest.mark.parametrize("state", [ConfigEntryState.LOADED, ConfigEntryState.NOT_LOADED])
async def test_hue_dimmer_entry_raises_an_instructions_issue(hass: HomeAssistant, state):
    entry = MockConfigEntry(domain="hue_dimmer")
    entry.add_to_hass(hass)
    entry.mock_state(hass, state)

    async_check_hue_dimmer(hass)

    found = issue(hass)
    assert found is not None
    assert not found.is_fixable
    assert not found.is_persistent
    assert found.severity is ir.IssueSeverity.WARNING
    assert found.learn_more_url == "https://github.com/DeviceSide/DeviceSide#coming-from-hue-smooth-dimming"


async def test_ignored_issue_stays_ignored(hass: HomeAssistant):
    MockConfigEntry(domain="hue_dimmer").add_to_hass(hass)
    async_check_hue_dimmer(hass)
    ir.async_ignore_issue(hass, DOMAIN, HUE_DIMMER, True)

    async_check_hue_dimmer(hass)

    assert issue(hass).dismissed_version is not None


async def test_setup_runs_the_check(hass: HomeAssistant, fake_registry):
    MockConfigEntry(domain="hue_dimmer").add_to_hass(hass)
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert issue(hass) is not None
