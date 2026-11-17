"""Control4's inventory, read as the Control4 entry loads: Light Group driver groups are native, and a light whose
capabilities say it can't stop is refused stop."""

import json
from unittest.mock import call as director_call

from homeassistant.config_entries import ConfigEntryState

from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.integrations.control4 import INTEGRATION, inventory

from .conftest import CONFIRMED
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
    rows = [capabilities(1, False), capabilities(2, True), capabilities(3, None), {"id": 4, "value": "x"}, {"value": {}}]
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


async def test_a_group_gets_one_command(hass):
    director = group_director()
    await office(hass, director)

    assert await call(hass, "stop", {"entity_id": "light.office"}) == {"light.office": CONFIRMED}
    assert [command for command in director.log if command[0] != "get"] == [("SET_BRIGHTNESS_STOP", GROUP)]


async def test_a_group_whose_members_cant_be_read_is_a_plain_light(hass, caplog):
    director = group_director()
    failing(director, "send_get_request")
    await office(hass, director)

    assert not target(hass, "light.office").is_group
    assert "it runs as a plain light" in caplog.text
    assert "stop is sent to every light" in caplog.text
    assert str(DRIVER_ITEM) not in caplog.text
    assert inventory.can_stop(hass, target(hass, "light.left"))


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


async def test_a_light_that_can_t_stop_is_refused_stop_with_nothing_sent(hass):
    director = group_director(no_stop=(101,))
    await office(hass, director)
    director.log.clear()

    assert await refusal(hass, "stop", {"entity_id": "light.left"}) == "stop_not_supported"
    assert director.log == []
    assert await call(hass, "stop", {"entity_id": "light.right"}) == {"light.right": CONFIRMED}
