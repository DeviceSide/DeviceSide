"""Zigbee2MQTT's lifecycle hooks: what loading and deleting an entry starts and puts back."""

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.deviceside.const import CONF_Z2M_COLOR_MODES, DOMAIN
from custom_components.deviceside.integrations.zigbee2mqtt import INTEGRATION, lifecycle, restore_journal


def test_the_integration_declares_the_hooks():
    assert INTEGRATION.setup is lifecycle.setup
    assert INTEGRATION.remove is lifecycle.remove


@pytest.mark.parametrize(
    ("options", "enabled"), [({}, True), ({CONF_Z2M_COLOR_MODES: True}, True), ({CONF_Z2M_COLOR_MODES: False}, False)]
)
async def test_setup_starts_the_bridge_cache_with_the_replay_and_the_color_modes(hass, options, enabled):
    entry = MockConfigEntry(domain=DOMAIN, options=options)
    entry.add_to_hass(hass)
    with (
        patch.object(lifecycle.bridge_cache, "async_setup", new=AsyncMock()) as bridge,
        patch.object(lifecycle.color_modes, "async_setup", new=AsyncMock()) as colors,
        patch.object(restore_journal, "request_replay") as request_replay,
    ):
        await lifecycle.setup(hass, entry)
        await hass.async_block_till_done()

    bridge.assert_awaited_once()
    assert bridge.await_args.args[:2] == (hass, entry)
    bridge.await_args.args[2]()  # on_online is the journal's replay request
    request_replay.assert_called_once_with(hass)
    colors.assert_awaited_once_with(hass, entry, enabled)


async def test_remove_puts_back_the_color_modes(hass):
    entry = MockConfigEntry(domain=DOMAIN)
    with patch.object(lifecycle.color_modes, "async_remove", new=AsyncMock()) as put_back:
        await lifecycle.remove(hass, entry)

    put_back.assert_awaited_once_with(hass)
