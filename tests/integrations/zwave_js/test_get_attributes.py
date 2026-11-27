"""Z-Wave get_attributes: a live Multilevel Switch Get per target, as brightness and on/off."""

import logging
from unittest.mock import AsyncMock
from unittest.mock import call as mock_call

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside.integrations.zwave_js.get_attributes import level_row

from ...conftest import call, sent
from ...fixtures.zwave_js import MULTILEVEL_SWITCH, CommandClass, add_zwave_light, zwave_device

pytestmark = pytest.mark.usefixtures("setup_production")

OTHER = "other"
GET = mock_call(CommandClass.SWITCH_MULTILEVEL, "get")


@pytest.mark.parametrize(
    ("level", "row"),
    [
        (99, {"brightness": 100.0}),
        (50, {"brightness": 50.5}),
        (1, {"brightness": 1.0}),  # the lowest lit level reads 1 %, not 0
        (0, {}),  # off: no level kept for the next on
    ],
)
async def test_a_level_is_read_live(hass, level, row):
    entry, invoke, _ = zwave_device(hass, level=level)
    add_zwave_light(hass, entry, "light.dimmer", state="on")

    response = await call(hass, "get_attributes", {"entity_id": "light.dimmer"})

    assert response == {"light.dimmer": {"capability": OTHER, **row}}
    assert invoke.await_args_list == [GET]


async def test_a_v4_report_s_target_and_duration_are_not_the_reading(hass):
    """The level now is currentValue, whatever the light is moving to."""
    entry, invoke, _ = zwave_device(hass)
    invoke.return_value = {"currentValue": 20, "targetValue": 80, "duration": {"unit": "seconds", "value": 5}}
    add_zwave_light(hass, entry, "light.dimmer")

    response = await call(hass, "get_attributes", {"entity_id": "light.dimmer"})

    assert response == {"light.dimmer": {"capability": OTHER, "brightness": 20.2}}


@pytest.mark.parametrize(
    "reply",
    [None, {}, {"currentValue": None}, {"currentValue": 254}, {"currentValue": 255}, {"currentValue": -1}]
    + [{"currentValue": "50"}, {"currentValue": True}, {"currentValue": 50.5}, [50]],
    ids=["none", "empty", "no_level", "unknown", "on_unreported", "negative", "text", "bool", "float", "list"],
)
async def test_a_reply_with_no_level_is_an_error(hass, reply):
    entry, invoke, _ = zwave_device(hass)
    invoke.return_value = reply
    add_zwave_light(hass, entry, "light.dimmer")

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "get_attributes", {"entity_id": "light.dimmer"})

    assert raised.value.translation_key == "targets_failed"
    assert raised.value.translation_placeholders == {"summary": "light.dimmer: error"}


def test_level_row_names_the_reply_it_could_not_read():
    with pytest.raises(ValueError, match="answered no level: None"):
        level_row(None)


async def test_a_device_error_raises(hass):
    entry, invoke, _ = zwave_device(hass)
    invoke.side_effect = ConnectionError("node did not respond")
    add_zwave_light(hass, entry, "light.dimmer")

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "get_attributes", {"entity_id": "light.dimmer"})

    assert raised.value.translation_placeholders == {"summary": "light.dimmer: error"}


async def test_each_target_is_read_on_its_own_endpoint(hass):
    entry, _, node = zwave_device(hass, endpoints={0: [(MULTILEVEL_SWITCH, 4)], 1: [(MULTILEVEL_SWITCH, 4)]})
    node.endpoints[0].invoke_mock = AsyncMock(return_value={"currentValue": 99})
    node.endpoints[1].invoke_mock = AsyncMock(return_value={"currentValue": 0})
    add_zwave_light(hass, entry, "light.one", endpoint=0)
    add_zwave_light(hass, entry, "light.two", endpoint=1)

    response = await call(hass, "get_attributes", {"entity_id": ["light.one", "light.two"]})

    assert response == {
        "light.one": {"capability": OTHER, "brightness": 100.0},
        "light.two": {"capability": OTHER},
    }
    assert node.endpoints[0].invoke_mock.await_args_list == [GET]
    assert node.endpoints[1].invoke_mock.await_args_list == [GET]


async def test_the_call_is_logged_without_the_node(hass, wire):
    wire.set_level(logging.DEBUG)
    entry, _, _ = zwave_device(hass, level=50)
    add_zwave_light(hass, entry, "light.dimmer")

    await call(hass, "get_attributes", {"entity_id": "light.dimmer"})

    assert sent(wire) == ["light.dimmer: sending zwave_js MultilevelSwitch.get ()"]
    assert any("Multilevel Switch reported" in line for line in wire.messages)
