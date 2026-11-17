"""Control4's inventory, read as the Control4 entry loads: Light Group driver groups are native, and each light's
driver names its class (classes.py)."""

import json
from unittest.mock import call as director_call

import pytest
from homeassistant.config_entries import ConfigEntryState

from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.integrations.control4 import INTEGRATION, inventory

from .conftest import CONFIRMED, SENT
from ...conftest import call, refusal
from ...fixtures.control4 import FakeDirector, add_control4_light, control4_entry, failing

DRIVER_ITEM, GROUP = 199, 200
ITEMS = [
    {"id": DRIVER_ITEM, "parentId": 14, "filename": "light_group.c4z"},
    {"id": GROUP, "parentId": DRIVER_ITEM},
    {"id": 90, "parentId": 14, "filename": "zigbee_light.c4z"},
    {"id": 101, "parentId": 90},
]
PROPERTIES = director_call(f"/api/v1/items/{DRIVER_ITEM}/properties")
CAPABILITIES = director_call("/api/v1/items/variables?varnames=Navigator%20Dynamic%20Capabilities")


def capabilities(item: int, stops: bool | None) -> dict:
    dynamic = {"dimmer": True} if stops is None else {"dimmer": True, "supports_brightness_stop": stops}
    return {"id": item, "varName": "Navigator Dynamic Capabilities", "value": {"DynamicCapabilities": dynamic}}


def group_director(members: str = "101,102,103", no_stop: tuple[int, ...] = ()) -> FakeDirector:
    """A Director whose Light Group driver lists `members` and whose `no_stop` lights say they can't stop; every light
    item reads as the fake's one light."""
    director = FakeDirector()
    variables = director.send_get_request.side_effect

    async def get(uri: str) -> str:
        if uri.endswith("/properties"):
            return json.dumps([{"name": "Log Level", "value": "3 - Info"}, {"name": "Lights", "value": members}])
        if uri == CAPABILITIES.args[0]:
            rows = [capabilities(item, item not in no_stop) for item in (GROUP, 101, 102, *no_stop)]
            return json.dumps([*rows, capabilities(90, None), {"id": 91, "value": "x"}])
        return await variables(uri)

    director.send_get_request.side_effect = get
    return director


async def office(hass, director: FakeDirector):
    """The group and two of its three lights as core's control4 integration registers them; the third has no
    entity. The group's members are loaded."""
    entry = control4_entry(hass, director)
    entry.runtime_data.director_all_items = ITEMS
    add_control4_light(hass, entry, "light.office", unique_id=str(GROUP))
    add_control4_light(hass, entry, "light.left", unique_id="101")
    add_control4_light(hass, entry, "light.right", unique_id="102")
    await inventory.load(hass, entry)
    return entry


def target(hass, entity_id: str):
    return resolve(hass, get_runtime(hass).registry, entity_id)


def test_the_driver_s_light_item_is_the_group():
    assert inventory.group_items(ITEMS) == [(DRIVER_ITEM, GROUP)]


def test_only_a_light_that_says_so_can_t_stop():
    rows = [
        capabilities(1, False),
        capabilities(2, True),
        capabilities(3, None),
        {"id": 4, "value": "x"},
        {"value": {}},
    ]
    assert inventory.parse_no_stop(rows) == frozenset({1})


def test_members_are_the_lights_property_s_item_ids():
    assert inventory.parse_members([{"name": "Lights", "value": "2415, 2411,x"}]) == (2415, 2411)
    assert inventory.parse_members([{"name": "Lights", "value": ""}]) == ()
    assert inventory.parse_members([]) == ()


async def test_a_group_expands_to_its_lights_with_entities(hass):
    director = group_director()
    await office(hass, director)

    group = target(hass, "light.office")
    assert group.is_group
    assert [member.entity_id for member in INTEGRATION.expand_group(hass, group)] == ["light.left", "light.right"]
    assert not target(hass, "light.left").is_group
    assert director.send_get_request.await_args_list == [PROPERTIES, CAPABILITIES]


MEMBERS = {"capabilities": ["other"], "member_capabilities": {"light.left": "other", "light.right": "other"}}


@pytest.mark.parametrize(
    ("action", "data", "row", "commands"),
    [
        ("get_attributes", {}, {"brightness": 40.0, "color_temp_kelvin": 3200}, []),
        ("raise_brightness", {}, SENT, ["RAMP_TO_LEVEL"]),
        ("lower_brightness", {}, SENT, ["RAMP_TO_LEVEL"]),
        ("set_attributes", {"color_temp_kelvin": 2700}, CONFIRMED, ["SET_COLOR_TARGET"]),
        ("stop", {}, CONFIRMED, ["SET_BRIGHTNESS_STOP"]),
    ],
)
async def test_a_group_gets_one_command(hass, action, data, row, commands):
    director = group_director()
    await office(hass, director)
    director.log.clear()

    assert await call(hass, action, {"entity_id": "light.office", **data}) == {"light.office": {**row, **MEMBERS}}
    assert {item for _, item in director.log} == {GROUP}
    assert [command for command, _ in director.log if command != "get"] == commands


@pytest.mark.parametrize(
    ("action", "row", "command"),
    [("raise_brightness", SENT, "RAMP_TO_LEVEL"), ("stop", CONFIRMED, "SET_BRIGHTNESS_STOP")],
)
async def test_a_group_with_a_light_that_can_t_stop_moves_its_other_lights_alone(hass, action, row, command):
    director = group_director(no_stop=(101,))
    await office(hass, director)
    director.log.clear()

    assert await call(hass, action, {"entity_id": "light.office"}) == {"light.right": {**row, "capability": "other"}}
    assert {item for _, item in director.log} == {102}
    assert [name for name, _ in director.log if name != "get"] == [command]


async def test_a_group_whose_members_cant_be_read_is_a_plain_light(hass, caplog):
    director = group_director()
    failing(director, "send_get_request")
    await office(hass, director)

    assert not target(hass, "light.office").is_group
    assert "it runs as a plain light" in caplog.text
    assert "every light is taken to stop" in caplog.text
    assert str(DRIVER_ITEM) not in caplog.text
    assert INTEGRATION.capability(hass, target(hass, "light.left")) == "other"


async def test_setup_loads_a_loaded_entry_and_again_when_it_loads(hass, setup_production):
    director = group_director("101")
    entry = await office(hass, director)
    get_runtime(hass).integration_state.clear()
    deviceside = hass.config_entries.async_entries("deviceside")[0]

    await inventory.setup(hass, deviceside)
    assert target(hass, "light.office").is_group

    director.send_get_request.reset_mock()
    entry.mock_state(hass, ConfigEntryState.LOADED)
    await hass.async_block_till_done()
    assert director.send_get_request.await_args_list == [PROPERTIES, CAPABILITIES]


async def test_a_light_whose_driver_can_t_stop_is_refused_every_move_with_nothing_sent(hass):
    """Its driver ignores a stop (Tested behavior), so a raise or lower couldn't be halted."""
    director = group_director(no_stop=(101,))
    await office(hass, director)
    director.log.clear()

    for action in ("raise_brightness", "lower_brightness", "stop"):
        assert await refusal(hass, action, {"entity_id": "light.left"}) == "no_known_method"
    assert director.log == []
    assert await call(hass, "stop", {"entity_id": "light.right"}) == {
        "light.right": {**CONFIRMED, "capability": "other"}
    }
