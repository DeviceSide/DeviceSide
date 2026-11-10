"""zcl.command against a mock service, and zcl.read_attributes against a fake zha gateway, since the zha library
isn't a dev dependency."""

import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError, Unauthorized, UnknownUser
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.deviceside.integrations.zha import zcl
from custom_components.deviceside.integrations.zha.addressing import Address

from ...conftest import traced
from ...fixtures.zha import IEEE

ADDR = Address(IEEE, 11)
# The real one: conftest fakes zcl.hue_turn_on for every test.
HUE_TURN_ON = zcl.hue_turn_on


@pytest.fixture
def cluster():
    return SimpleNamespace(read_attributes=AsyncMock(return_value=({zcl.ON_OFF: True, zcl.ON_TIME: 48}, {})))


@pytest.fixture
def gateway(hass, monkeypatch, cluster):
    """Fake zha's hass.data and zigpy.types.EUI64; EUI64.convert passes the IEEE through."""
    device = MagicMock()
    device.async_get_cluster.return_value = cluster
    gw = MagicMock()
    gw.get_device.return_value = device
    types = SimpleNamespace(EUI64=SimpleNamespace(convert=lambda ieee: ieee), Struct=object, SerializableBytes=bytes)
    monkeypatch.setitem(hass.data, "zha", SimpleNamespace(gateway_proxy=SimpleNamespace(gateway=gw)))
    monkeypatch.setitem(sys.modules, "zigpy.types", types)
    return gw


async def test_reads_the_values_uncached_in_one_request(hass, gateway, cluster):
    read = await zcl.read_attributes(hass, ADDR, zcl.ON_OFF_CLUSTER, (zcl.ON_OFF, zcl.ON_TIME))

    assert read == {zcl.ON_OFF: True, zcl.ON_TIME: 48}

    gateway.get_device.assert_called_once_with(IEEE)
    gateway.get_device.return_value.async_get_cluster.assert_called_once_with(11, 0x0006, cluster_type="in")
    cluster.read_attributes.assert_awaited_once_with([0x0000, 0x4001], allow_cache=False, only_cache=False)


async def test_failed_attribute_raises(hass, gateway, cluster):
    cluster.read_attributes.return_value = ({zcl.ON_OFF: True}, {zcl.ON_TIME: "UNSUPPORTED_ATTRIBUTE"})

    with pytest.raises(LookupError, match="0x4001 not read: UNSUPPORTED_ATTRIBUTE"):
        await zcl.read_attributes(hass, ADDR, zcl.ON_OFF_CLUSTER, (zcl.ON_OFF, zcl.ON_TIME))


async def test_missing_device_raises(hass, gateway):
    gateway.get_device.return_value = None

    with pytest.raises(LookupError, match="not found"):
        await zcl.read_attributes(hass, ADDR, zcl.ON_OFF_CLUSTER, (zcl.ON_TIME,))


async def test_without_zha_installed_raises_import_error(hass, monkeypatch):
    monkeypatch.setitem(sys.modules, "zigpy.types", None)

    with pytest.raises(ImportError):
        await zcl.read_attributes(hass, ADDR, zcl.ON_OFF_CLUSTER, (zcl.ON_TIME,))


@pytest.mark.parametrize("data", [None, SimpleNamespace(gateway_proxy=None)])
async def test_without_a_zha_gateway_raises_value_error(hass, monkeypatch, data):
    """ZHA not set up, or set up without a gateway yet: get_zha_gateway's error, without importing zha."""
    if data is None:
        monkeypatch.delitem(hass.data, "zha", raising=False)
    else:
        monkeypatch.setitem(hass.data, "zha", data)

    with pytest.raises(ValueError, match="No ZHA gateway"):
        zcl.gateway(hass)


async def test_optional_attribute_rides_the_request_and_is_left_out_when_missing(hass, gateway, cluster):
    cluster.read_attributes.return_value = ({zcl.ON_OFF: True}, {zcl.ON_TIME: "UNSUPPORTED_ATTRIBUTE"})

    read = await zcl.read_attributes(hass, ADDR, zcl.ON_OFF_CLUSTER, (zcl.ON_OFF,), optional=(zcl.ON_TIME,))

    assert read == {zcl.ON_OFF: True}
    cluster.read_attributes.assert_awaited_once_with([0x0000, 0x4001], allow_cache=False, only_cache=False)


async def test_command_issues_a_server_command_to_the_in_cluster_with_the_callers_context(hass):
    commands = async_mock_service(hass, "zha", "issue_zigbee_cluster_command")
    context = Context()

    await zcl.command(hass, ADDR, zcl.LEVEL_CLUSTER, zcl.MOVE_TO_LEVEL, {"level": 40}, context, entity_id="light.lamp")

    assert commands[0].data == {
        "ieee": IEEE,
        "endpoint_id": 11,
        "cluster_id": 0x0008,
        "cluster_type": "in",
        "command": 0x00,
        "command_type": "server",
        "params": {"level": 40},
    }
    assert commands[0].context is context


@pytest.mark.parametrize(("capabilities", "expected"), [(31, True), (16, False)])
async def test_enhanced_hue_from_zigpys_cache(hass, gateway, cluster, capabilities, expected):
    """The A60 reports 31 (enhanced hue among them), a color temperature bulb 16 (probe 13a)."""
    cluster.get = MagicMock(return_value=capabilities)

    assert await zcl.enhanced_hue(hass, ADDR) is expected
    cluster.get.assert_called_once_with(zcl.COLOR_CAPABILITIES)
    gateway.get_device.return_value.async_get_cluster.assert_called_once_with(11, 0x0300, cluster_type="in")
    cluster.read_attributes.assert_not_awaited()


async def test_enhanced_hue_read_once_when_not_cached(hass, gateway, cluster):
    cluster.get = MagicMock(return_value=None)
    cluster.read_attributes.return_value = ({zcl.COLOR_CAPABILITIES: 31}, {})

    assert await zcl.enhanced_hue(hass, ADDR) is True
    cluster.read_attributes.assert_awaited_once_with([0x400A], allow_cache=False, only_cache=False)


async def test_no_color_cluster_is_no_enhanced_hue(hass, gateway):
    gateway.get_device.return_value.async_get_cluster.side_effect = KeyError(0x0300)

    assert await zcl.enhanced_hue(hass, ADDR) is False


async def test_enhanced_hue_read_error_raises(hass, gateway, cluster):
    """A light that didn't answer may have enhanced hue, so it isn't taken to lack it."""
    cluster.get = MagicMock(return_value=None)
    cluster.read_attributes.return_value = ({}, {zcl.COLOR_CAPABILITIES: "TIMEOUT"})

    with pytest.raises(LookupError, match="0x400a not read: TIMEOUT"):
        await zcl.enhanced_hue(hass, ADDR)


async def test_enhanced_hue_missing_device_raises(hass, gateway):
    gateway.get_device.return_value = None

    with pytest.raises(LookupError, match="not found"):
        await zcl.enhanced_hue(hass, ADDR)


async def test_group_command_sends_positional_args(hass):
    calls = async_mock_service(hass, "zha", "issue_zigbee_group_command")
    context = Context()

    await zcl.group_command(hass, 2, zcl.LEVEL_CLUSTER, zcl.STOP, [], context)

    assert [call.data for call in calls] == [{"group": 2, "cluster_id": 8, "command": 3, "args": []}]
    assert calls[0].context is context


@pytest.mark.parametrize(("percent", "level"), [(0, 1), (0.1, 1), (50, 127), (100, 254)])
def test_level(percent, level):
    assert zcl.level(percent) == level


async def test_hue_turn_on_sends_multicolor_on_at_the_level_with_no_fade(hass, gateway, cluster):
    """Flags 0x0013 (on, brightness, fade time), then on, the level and a fade of 0, as Z2M's hue_native_control."""
    cluster.request = AsyncMock(return_value=SimpleNamespace(status=0))

    assert await HUE_TURN_ON(hass, ADDR, 1, Context(), entity_id="light.lamp") is True

    gateway.get_device.return_value.async_get_cluster.assert_called_once_with(11, 0xFC03, cluster_type="in")
    general, command_id, _schema, payload = cluster.request.await_args.args
    assert (general, command_id, payload) == (False, 0x00, bytes.fromhex("1300 01 01 0000"))
    assert cluster.request.await_args.kwargs == {"manufacturer": 0x100B}


async def test_hue_turn_on_without_hues_cluster_sends_nothing(hass, gateway, cluster):
    gateway.get_device.return_value.async_get_cluster.side_effect = KeyError(0xFC03)
    cluster.request = AsyncMock()

    assert await HUE_TURN_ON(hass, ADDR, 1, Context(), entity_id="light.lamp") is False
    cluster.request.assert_not_awaited()


async def test_hue_turn_on_failed_status_raises(hass, gateway, cluster):
    cluster.request = AsyncMock(return_value=SimpleNamespace(status=0x81))

    with pytest.raises(HomeAssistantError, match="answered 129"):
        await HUE_TURN_ON(hass, ADDR, 1, Context(), entity_id="light.lamp")


async def test_hue_turn_on_refuses_a_non_admin_as_zha_does(hass, gateway, cluster, hass_read_only_user):
    """It goes to zigpy, past zha's admin-only action, so it makes the same check."""
    cluster.request = AsyncMock()

    with pytest.raises(Unauthorized):
        await HUE_TURN_ON(hass, ADDR, 1, Context(user_id=hass_read_only_user.id), entity_id="light.lamp")
    cluster.request.assert_not_awaited()


async def test_hue_turn_on_refuses_an_unknown_user(hass, gateway, cluster):
    cluster.request = AsyncMock()

    with pytest.raises(UnknownUser):
        await HUE_TURN_ON(hass, ADDR, 1, Context(user_id="no-such-user"), entity_id="light.lamp")
    cluster.request.assert_not_awaited()


async def test_hue_turn_on_without_the_device_raises(hass, gateway):
    gateway.get_device.return_value = None

    with pytest.raises(LookupError, match="not found"):
        await HUE_TURN_ON(hass, ADDR, 1, None, entity_id="light.lamp")


async def test_hue_turn_on_lets_an_admin_through(hass, gateway, cluster, hass_admin_user):
    cluster.request = AsyncMock(return_value=SimpleNamespace(status=0))

    assert await HUE_TURN_ON(hass, ADDR, 1, Context(user_id=hass_admin_user.id), entity_id="light.lamp") is True


async def test_command_is_traced_by_entity_without_the_address(hass, wire):
    async_mock_service(hass, "zha", "issue_zigbee_cluster_command")

    await zcl.command(hass, ADDR, zcl.LEVEL_CLUSTER, zcl.MOVE_TO_LEVEL, {"level": 40}, None, entity_id="light.lamp")

    assert traced(wire) == [("light.lamp", "zcl", "0x0008/0x00", {"level": 40})]
    assert IEEE not in json.dumps(wire[0].data)


async def test_group_command_is_traced_on_the_groups_light(hass, wire):
    async_mock_service(hass, "zha", "issue_zigbee_group_command")
    er.async_get(hass).async_get_or_create("light", "zha", "light_zha_group_0x0002", suggested_object_id="room")

    await zcl.group_command(hass, 2, zcl.LEVEL_CLUSTER, zcl.STOP, [], None)

    assert traced(wire) == [("light.room", "zcl", "0x0008/0x03", {"args": []})]


async def test_hue_turn_on_is_traced_with_its_payload(hass, gateway, cluster, wire):
    cluster.request = AsyncMock(return_value=SimpleNamespace(status=0))

    await HUE_TURN_ON(hass, ADDR, 1, None, entity_id="light.lamp")

    assert traced(wire) == [("light.lamp", "zcl", "0xfc03/0x00", {"data": "130001010000"})]
