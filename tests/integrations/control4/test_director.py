"""What every Control4 adapter shares: the Director request with its token retry, and the per-light lock that keeps
a stop behind the move it follows."""

import asyncio

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside.integrations.control4 import director as director_module
from custom_components.deviceside.integrations.control4.director import MOVE_SETTLE_DELAYS_S as SHIPPED_MOVE_DELAYS_S
from custom_components.deviceside.integrations.control4.director import SETTLE_DELAYS_S as SHIPPED_DELAYS_S
from custom_components.deviceside.integrations.control4.director import (
    LightLevel,
    color_temperature,
    heading_for,
    kelvin_range,
    parse_level,
    whole_percent,
)

from .conftest import CONFIRMED, LAMP, SENT, dimmable_lamp
from ...conftest import call
from ...fixtures.control4 import ITEM, BadToken, FakeDirector, add_control4_light, control4_entry


async def test_an_expired_token_rejects_the_target_until_core_refreshes_it(hass, caplog):
    """As for core's own commands: the WARNING names the error, and core's next poll refreshes the token."""
    director = dimmable_lamp(hass, brightness=40)
    director.send_get_request.side_effect = BadToken("expired")

    with pytest.raises(HomeAssistantError):
        await call(hass, "raise_brightness", LAMP)

    assert "raise_brightness on control4 failed for light.lamp: BadToken('expired')" in caplog.text


@pytest.mark.parametrize("level", ["NaN", 101, -1, "Infinity"])
async def test_a_level_outside_the_range_rejects_the_target(hass, level):
    """Nothing to size a ramp from: the light is rejected, not moved from a guess."""
    director = dimmable_lamp(hass)
    director.send_get_request.side_effect = None
    director.send_get_request.return_value = f'[{{"varName": "Brightness Percent", "value": {level}}}]'

    with pytest.raises(HomeAssistantError):
        await call(hass, "raise_brightness", LAMP)

    assert not director.send_post_request.await_args_list


async def test_no_debug_line_carries_the_directors_item_id(hass, wire):
    """The item id is a device address, which a user's pasted log must not hold."""
    add_control4_light(hass, control4_entry(hass, FakeDirector(halt=55)), "light.far", unique_id="98765")

    await call(hass, "raise_brightness", {"entity_id": "light.far"})
    await call(hass, "stop", {"entity_id": "light.far"})

    assert wire.records
    assert "98765" not in wire.text


async def test_a_read_back_waits_before_each_read_and_backs_off(hass, monkeypatch):
    """The measured schedule: a wait before the first read, as one sent at once still shows the ramp, then longer
    ones."""
    director = dimmable_lamp(hass, brightness=40)
    director.ignore_stop = True
    await call(hass, "raise_brightness", LAMP)
    events: list = []
    read = director.send_get_request.side_effect

    async def wait(delay):
        events.append(delay)

    async def get(uri):
        events.append("read")
        return await read(uri)

    director.send_get_request.side_effect = get
    # The shipped schedule, read before conftest zeroes it for every other test.
    assert SHIPPED_DELAYS_S == (0.1, 0.15, 0.3, 0.6)
    monkeypatch.setattr(director_module, "SETTLE_DELAYS_S", SHIPPED_DELAYS_S)
    monkeypatch.setattr(director_module, "_sleep", wait)

    await call(hass, "stop", LAMP)

    assert events == [0.1, "read", 0.15, "read", 0.3, "read", 0.6, "read"]


async def test_a_level_the_director_cant_mean_is_logged_as_reported(hass, wire):
    """The first bug report must hold what the Director answered, and never its item id."""
    director = dimmable_lamp(hass)
    director.send_get_request.side_effect = None
    director.send_get_request.return_value = f'[{{"id": {ITEM}, "varName": "Brightness Percent", "value": 255}}]'

    with pytest.raises(HomeAssistantError):
        await call(hass, "raise_brightness", LAMP)

    assert "light.lamp: director reports {'Brightness Percent': 255}" in wire.text
    assert f"{ITEM}" not in wire.text.replace("255", "")


async def test_a_variable_that_wasnt_asked_for_is_left_out(hass, wire):
    """Only the variables named in the read are kept, whatever the Director sends back."""
    director = dimmable_lamp(hass)
    reply = '[{"varName": "Brightness Percent", "value": 40}, {"varName": "Some Other Variable", "value": "x"}]'
    director.send_get_request.side_effect = None
    director.send_get_request.return_value = reply

    await call(hass, "raise_brightness", LAMP)

    assert "Some Other Variable" not in wire.text


async def test_a_stop_during_a_moves_read_waits_and_halts_its_ramp(hass):
    """A press and release tens of milliseconds apart: the stop must follow the ramp, or it halts nothing."""
    director = dimmable_lamp(hass, brightness=40, halt=45)
    director.gate = asyncio.Event()

    move = hass.async_create_task(call(hass, "raise_brightness", LAMP))
    while not director.log:
        await asyncio.sleep(0)
    halt = hass.async_create_task(call(hass, "stop", LAMP))
    for _ in range(20):
        await asyncio.sleep(0)
    assert [command for command, _ in director.log] == ["get"]

    director.gate.set()

    assert await move == {"light.lamp": SENT}
    assert await halt == {"light.lamp": CONFIRMED}
    assert [command for command, _ in director.log][:3] == ["get", "RAMP_TO_LEVEL", "SET_BRIGHTNESS_STOP"]
    assert director.brightness == 45


@pytest.mark.parametrize(
    ("percent", "level"), [(0, 0), (0.2, 1), (0.5, 1), (1.4, 1), (70.4, 70), (70.6, 71), (100, 100)]
)
def test_only_zero_is_off(percent, level):
    assert whole_percent(percent) == level


@pytest.mark.parametrize(
    ("brightness", "target", "ramping"),
    [
        (40, 40, False),
        (40, 41, True),
        (41, 40, True),
        (99.6, 100, True),
        (40.4, 40, True),
        (0, 100, True),
        (40, None, False),
    ],
)
def test_a_light_is_ramping_while_its_level_isnt_its_target(brightness, target, ramping):
    assert LightLevel(brightness=brightness, target=target).ramping is ramping


@pytest.mark.parametrize(("brightness", "on"), [(0, False), (0.2, True), (1, True)])
def test_any_level_above_zero_is_lit(brightness, on):
    assert LightLevel(brightness=brightness, target=None).on is on


@pytest.mark.parametrize("target", ["NaN", 101, -1, "Infinity", "x"])
def test_a_target_the_light_cant_be_heading_for_reads_as_none(target):
    """A stop is never confirmed from it: the light reads as on a driver that reports no target."""
    assert parse_level({"Brightness Percent": 40, "Brightness Target Percent": target}) == LightLevel(40, None)


async def test_a_stop_isnt_confirmed_from_a_target_that_cant_be_read(hass):
    director = dimmable_lamp(hass, brightness=40)
    director.send_get_request.side_effect = None
    director.send_get_request.return_value = (
        '[{"varName": "Brightness Percent", "value": 40}, {"varName": "Brightness Target Percent", "value": NaN}]'
    )

    assert await call(hass, "stop", LAMP) == {"light.lamp": {**SENT, "detail": "halt_not_reported"}}


async def test_a_move_held_on_one_light_doesnt_hold_a_stop_on_another(hass):
    """The lock is one item's, not the controller's."""
    director = dimmable_lamp(hass)
    add_control4_light(hass, hass.config_entries.async_entries("control4")[0], "light.neighbor", unique_id="201")
    director.gate = asyncio.Event()

    move = hass.async_create_task(call(hass, "raise_brightness", LAMP))
    while not director.log:
        await asyncio.sleep(0)
    halt = hass.async_create_task(call(hass, "stop", {"entity_id": "light.neighbor"}))
    for _ in range(20):
        await asyncio.sleep(0)

    assert director.log[:2] == [("get", ITEM), ("SET_BRIGHTNESS_STOP", 201)]

    director.gate.set()
    await move
    await halt


async def test_a_move_that_halts_a_ramp_first_waits_only_the_brief_schedule(hass, monkeypatch):
    """Its waits are spent inside a concurrency slot and the light's lock, so it takes the first two only."""
    director = dimmable_lamp(hass, brightness=40)
    await call(hass, "lower_brightness", LAMP)
    director.ignore_stop = True
    events: list = []
    read = director.send_get_request.side_effect

    async def wait(delay):
        events.append(delay)

    async def get(uri):
        events.append("read")
        return await read(uri)

    director.send_get_request.side_effect = get
    assert SHIPPED_MOVE_DELAYS_S == (0.1, 0.15)
    monkeypatch.setattr(director_module, "MOVE_SETTLE_DELAYS_S", SHIPPED_MOVE_DELAYS_S)
    monkeypatch.setattr(director_module, "_sleep", wait)

    await call(hass, "raise_brightness", LAMP)

    assert events == ["read", 0.1, "read", 0.15, "read"]


CCT = "supports_color_correlated_temperature"
LOW, HIGH = "color_correlated_temperature_min", "color_correlated_temperature_max"


def capabilities(value) -> dict:
    return {"Navigator Dynamic Capabilities": value}


@pytest.mark.parametrize(
    "held",
    [{}, capabilities({"DynamicCapabilities": {CCT: False}}), capabilities({"DynamicCapabilities": {CCT: "true"}})],
    ids=["no_capabilities_variable", "says_it_takes_none", "support_as_text"],
)
def test_a_light_that_claims_no_color_temperature_has_no_range(held):
    assert kelvin_range(held) is None


@pytest.mark.parametrize(
    "value",
    [
        "not json",
        "[]",
        {"other": {}},
        {"DynamicCapabilities": {CCT: True, LOW: 2200}},
        {"DynamicCapabilities": {CCT: True, LOW: 0, HIGH: 0}},
        {"DynamicCapabilities": {CCT: True, LOW: 6500, HIGH: 2200}},
        {"DynamicCapabilities": {CCT: True, LOW: 2200, HIGH: "inf"}},
        {"DynamicCapabilities": {CCT: True, LOW: "nan", HIGH: 6500}},
    ],
    ids=[
        "text_that_isnt_json",
        "json_that_isnt_an_object",
        "no_capabilities_in_it",
        "no_maximum",
        "empty",
        "reversed",
        "endless",
        "not_a_number",
    ],
)
def test_capabilities_that_cant_be_read_or_give_no_real_range_raise(value):
    """A light that can't say isn't passed off as one that says it lacks the field."""
    with pytest.raises(ValueError):
        kelvin_range(capabilities(value))


def test_a_range_of_one_kelvin_is_a_range():
    assert kelvin_range(capabilities({"DynamicCapabilities": {CCT: True, LOW: 2700, HIGH: 2700}})) == (2700, 2700)


def test_a_fractional_range_is_whole_kelvins():
    assert kelvin_range(capabilities({"DynamicCapabilities": {CCT: True, LOW: 2202.6, HIGH: "6536.4"}})) == (2203, 6536)


@pytest.mark.parametrize(
    ("held", "heading"),
    [
        ({"Target CCT": 2700.4, "Target Color Mode": 1}, True),
        ({"Target CCT": 2699.6, "Target Color Mode": 1}, True),
        ({"Target CCT": 2700, "Target Color Mode": 1}, True),
        ({"Target CCT": 2710, "Target Color Mode": 1}, False),
        ({"Target CCT": 2690, "Target Color Mode": 1}, False),
        ({"Current CCT": 2700, "Current Color Mode": 1}, True),
        ({"Current CCT": 2690, "Current Color Mode": 1}, False),
        ({"Target CCT": 2700, "Target Color Mode": 0, "Current Color Mode": 1}, False),
        ({"Target CCT": 2700, "Current Color Mode": 1}, False),
        ({"Target CCT": 3200, "Target Color Mode": 1, "Current CCT": "2700", "Current Color Mode": 1}, True),
        ({"Current CCT": 2700, "Current Color Mode": 0, "Target Color Mode": 1}, False),
        ({"Target CCT": "nan", "Target Color Mode": 1}, False),
        ({"Target CCT": "inf", "Target Color Mode": 1, "Current CCT": "nan", "Current Color Mode": 1}, False),
        ({}, False),
    ],
    ids=[
        "target_rounds_to_it",
        "target_rounds_up_to_it",
        "target_is_its_tens",
        "target_a_step_above",
        "target_a_step_below",
        "current_is_its_tens",
        "current_a_step_below",
        "target_in_full_color",
        "target_mode_not_reported",
        "already_at_it",
        "at_it_in_full_color",
        "target_not_a_number",
        "nothing_finite",
        "nothing_reported",
    ],
)
def test_heading_for_takes_the_target_or_the_current_each_with_its_own_mode(held, heading):
    assert heading_for(held, 2705) is heading


@pytest.mark.parametrize(
    ("held", "kelvin"),
    [
        ({"Current CCT": 2700.4, "Current Color Mode": 1}, 2700),
        ({"Current CCT": "3200", "Current Color Mode": "1"}, 3200),
        ({"Current CCT": 2700, "Current Color Mode": 0}, None),
        ({"Current CCT": 2700, "Current Color Mode": 2}, None),
        ({"Current CCT": 2700}, None),
        ({"Current CCT": 0, "Current Color Mode": 1}, None),
        ({"Current CCT": "nan", "Current Color Mode": 1}, None),
        ({"Current Color Mode": 1}, None),
    ],
    ids=["fractional", "as_text", "full_color", "another_mode", "no_mode", "zero", "not_a_number", "none_reported"],
)
def test_color_temperature_is_a_whole_kelvin_in_color_temperature_mode_only(held, kelvin):
    found = color_temperature(held)
    assert found == kelvin
    assert type(found) is type(kelvin)


def test_capabilities_that_cant_be_read_are_named_in_the_error():
    with pytest.raises(ValueError, match="'not json'"):
        kelvin_range(capabilities("not json"))
