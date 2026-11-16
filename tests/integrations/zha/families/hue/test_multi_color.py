"""Hue's multiColor turn-on against a fake zha gateway, since the zha library isn't a dev dependency."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError, Unauthorized, UnknownUser

from custom_components.deviceside.integrations.zha.addressing import Address
from custom_components.deviceside.integrations.zha.families.hue import multi_color

from .....conftest import sent
from .....fixtures.zha import IEEE

ADDR = Address(IEEE, 11)
# The real one: conftest fakes multi_color.turn_on for every test.
TURN_ON = multi_color.turn_on


async def test_turn_on_sends_multicolor_on_at_the_level_with_no_fade(hass, gateway, cluster):
    """Flags 0x0013 (on, brightness, fade time), then on, the level and a fade of 0, as Z2M's hue_native_control."""
    cluster.request = AsyncMock(return_value=SimpleNamespace(status=0))

    assert await TURN_ON(hass, ADDR, 1, Context(), entity_id="light.lamp") is True

    gateway.get_device.return_value.async_get_cluster.assert_called_once_with(11, 0xFC03, cluster_type="in")
    general, command_id, _schema, payload = cluster.request.await_args.args
    assert (general, command_id, payload) == (False, 0x00, bytes.fromhex("1300 01 01 0000"))
    assert cluster.request.await_args.kwargs == {"manufacturer": 0x100B}


async def test_turn_on_without_hues_cluster_sends_nothing(hass, gateway, cluster):
    gateway.get_device.return_value.async_get_cluster.side_effect = KeyError(0xFC03)
    cluster.request = AsyncMock()

    assert await TURN_ON(hass, ADDR, 1, Context(), entity_id="light.lamp") is False
    cluster.request.assert_not_awaited()


async def test_turn_on_failed_status_raises(hass, gateway, cluster):
    cluster.request = AsyncMock(return_value=SimpleNamespace(status=0x81))

    with pytest.raises(HomeAssistantError, match="answered 129"):
        await TURN_ON(hass, ADDR, 1, Context(), entity_id="light.lamp")


async def test_turn_on_refuses_a_non_admin_as_zha_does(hass, gateway, cluster, hass_read_only_user):
    """It goes to zigpy, past zha's admin-only action, so it makes the same check."""
    cluster.request = AsyncMock()

    with pytest.raises(Unauthorized):
        await TURN_ON(hass, ADDR, 1, Context(user_id=hass_read_only_user.id), entity_id="light.lamp")
    cluster.request.assert_not_awaited()


async def test_turn_on_refuses_an_unknown_user(hass, gateway, cluster):
    cluster.request = AsyncMock()

    with pytest.raises(UnknownUser):
        await TURN_ON(hass, ADDR, 1, Context(user_id="no-such-user"), entity_id="light.lamp")
    cluster.request.assert_not_awaited()


async def test_turn_on_without_the_device_raises(hass, gateway):
    gateway.get_device.return_value = None

    with pytest.raises(LookupError, match="not found"):
        await TURN_ON(hass, ADDR, 1, None, entity_id="light.lamp")


async def test_turn_on_lets_an_admin_through(hass, gateway, cluster, hass_admin_user):
    cluster.request = AsyncMock(return_value=SimpleNamespace(status=0))

    assert await TURN_ON(hass, ADDR, 1, Context(user_id=hass_admin_user.id), entity_id="light.lamp") is True


async def test_turn_on_is_logged_with_its_payload(hass, gateway, cluster, wire):
    cluster.request = AsyncMock(return_value=SimpleNamespace(status=0))

    await TURN_ON(hass, ADDR, 1, None, entity_id="light.lamp")

    assert sent(wire) == ["light.lamp: sending zcl 0xfc03/0x00 130001010000"]
