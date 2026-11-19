"""The config entry's migration: minor 2 renamed the Labs option's key, keeping the user's choice."""

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.deviceside import async_migrate_entry
from custom_components.deviceside.const import DOMAIN
from custom_components.deviceside.core.runtime import get_runtime


async def set_up(hass: HomeAssistant, entry: MockConfigEntry) -> bool:
    entry.add_to_hass(hass)
    loaded = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return loaded


@pytest.mark.parametrize("on", [True, False])
async def test_an_rc_entry_keeps_its_labs_choice_under_the_new_key(hass: HomeAssistant, on: bool):
    entry = MockConfigEntry(
        domain=DOMAIN, version=1, minor_version=1, options={"predicted_state": False, "experimental_features": on}
    )

    assert await set_up(hass, entry)

    assert entry.minor_version == 2
    assert entry.options == {"predicted_state": False, "labs": on}
    assert get_runtime(hass).labs is on


async def test_an_entry_without_options_gets_none(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, version=1, minor_version=1)

    assert await set_up(hass, entry)

    assert entry.minor_version == 2
    assert entry.options == {}
    assert get_runtime(hass).labs is False


@pytest.mark.parametrize("minor_version", [2, 3])
async def test_an_entry_at_minor_2_or_later_is_untouched(hass: HomeAssistant, minor_version: int):
    """The old key is moved only from a minor 1 entry; a later one (minor 3 is from a newer build) is left as saved."""
    options = {"experimental_features": True}
    entry = MockConfigEntry(domain=DOMAIN, version=1, minor_version=minor_version, options=options)

    assert await set_up(hass, entry)

    assert entry.minor_version == minor_version
    assert entry.options == options
    assert get_runtime(hass).labs is False


async def test_an_entry_from_a_future_major_version_is_refused(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, version=2, minor_version=1, options={"labs": True})

    assert not await set_up(hass, entry)

    assert entry.state is ConfigEntryState.MIGRATION_ERROR
    assert entry.options == {"labs": True}
    # HA refuses it before calling the migration, which refuses it too.
    assert await async_migrate_entry(hass, entry) is False
