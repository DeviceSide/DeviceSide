"""What every Control4 adapter shares: the Director request with its token retry, and the per-light lock that keeps
a stop behind the move it follows."""

import asyncio
from unittest.mock import AsyncMock
from unittest.mock import call as director_call

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.integrations.control4 import director as director_module
from custom_components.deviceside.integrations.control4.director import MOVE_SETTLE_DELAYS_S as SHIPPED_MOVE_DELAYS_S
from custom_components.deviceside.integrations.control4.director import SETTLE_DELAYS_S as SHIPPED_DELAYS_S
from custom_components.deviceside.integrations.control4.director import LightLevel, parse_level, whole_percent

from .conftest import CONFIRMED, LAMP, SENT, dimmable_lamp, ramp
from ...conftest import call
from ...fixtures.control4 import ITEM, BadToken, FakeDirector, add_control4_light, control4_entry, failing


def director_call_ramp(item: int):
    return director_call(f"/api/v1/items/{item}/commands", "RAMP_TO_LEVEL", {"LEVEL": 100, "TIME": 3000})


def expired(director: FakeDirector, method: str = "send_get_request") -> None:
    """Make the Director refuse every `method` request as core's does once its token has expired."""
    getattr(director, method).side_effect = BadToken("expired")


def core_refresh(monkeypatch, hass, fresh: FakeDirector | None) -> AsyncMock:
    """Stand in for the entity update, on which core's poll swaps a fresh Director into the entry."""

    async def swap(hass, entity_id) -> None:
        # Yields first, as core's poll does, so calls refused together are all waiting before the swap lands.
        await asyncio.sleep(0)
        if fresh is not None:
            hass.config_entries.async_entries("control4")[0].runtime_data.director = fresh

    update = AsyncMock(side_effect=swap)
    monkeypatch.setattr(director_module, "async_update_entity", update)
    return update


@pytest.mark.parametrize("method", ["send_get_request", "send_post_request"])
async def test_an_expired_token_is_refreshed_and_the_request_retried(hass, monkeypatch, method):
    """Core refreshes the token only from its own polling, so a call landing first asks it to."""
    old, fresh = dimmable_lamp(hass, brightness=40), FakeDirector(brightness=40)
    expired(old, method)
    update = core_refresh(monkeypatch, hass, fresh)

    assert await call(hass, "raise_brightness", LAMP) == {"light.lamp": SENT}
    assert update.await_count == 1
    assert fresh.send_post_request.await_args_list == [ramp(100, 3000)]


async def test_a_token_refused_again_after_the_refresh_rejects_the_target(hass, monkeypatch):
    old, fresh = dimmable_lamp(hass, brightness=40), FakeDirector(brightness=40)
    expired(old)
    expired(fresh)
    update = core_refresh(monkeypatch, hass, fresh)

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "raise_brightness", LAMP)

    assert raised.value.translation_key == "targets_failed"
    assert update.await_count == 1
    assert (old.send_get_request.await_count, fresh.send_get_request.await_count) == (1, 1)


async def test_an_expired_token_core_doesnt_refresh_rejects_the_target(hass, monkeypatch, wire):
    """Core swapped no Director in: the refusal stands, the stale one isn't asked again, and the log says so."""
    old = dimmable_lamp(hass, brightness=40)
    expired(old)
    update = core_refresh(monkeypatch, hass, None)

    with pytest.raises(HomeAssistantError):
        await call(hass, "raise_brightness", LAMP)

    assert update.await_args.args[1] == "light.lamp"
    assert old.send_get_request.await_count == 1
    assert "light.lamp: director refused an expired token (BadToken('expired')); core swapped no Director in" in (
        wire.text
    )


async def test_lights_refused_together_ask_core_once_and_all_retry(hass, monkeypatch):
    """Core's coordinator debounces a second ask, which would swap nothing in: the rest wait and find it swapped."""
    old, fresh = FakeDirector(brightness=40), FakeDirector(brightness=40)
    expired(old)
    entry = control4_entry(hass, old)
    lamps = [add_control4_light(hass, entry, f"light.lamp_{n}", unique_id=str(200 + n)) for n in range(3)]
    update = core_refresh(monkeypatch, hass, fresh)

    assert await call(hass, "raise_brightness", {"entity_id": lamps}) == dict.fromkeys(lamps, SENT)
    assert update.await_count == 1
    # The fake holds one light for every item, so the later lamps find the first one's ramp and halt it first.
    assert [command for command, _ in fresh.log].count("RAMP_TO_LEVEL") == 3


async def test_the_refresh_runs_outside_the_lights_lock(hass, monkeypatch):
    """The lock covers the read and the ramp only: a stop for the light isn't held up by the cloud round trip."""
    old, fresh = dimmable_lamp(hass, brightness=40), FakeDirector(brightness=40)
    expired(old)
    entry = hass.config_entries.async_entries("control4")[0]
    locked: list[bool] = []

    async def swap(hass, entity_id) -> None:
        locks = get_runtime(hass).integration_state["control4_item_locks"]
        locked.extend(lock.locked() for lock in locks.values())
        entry.runtime_data.director = fresh

    monkeypatch.setattr(director_module, "async_update_entity", AsyncMock(side_effect=swap))

    assert await call(hass, "raise_brightness", LAMP) == {"light.lamp": SENT}
    assert locked == [False]


async def test_a_refresh_that_outlasts_the_deadline_rejects_the_target(hass, monkeypatch, wire):
    old = dimmable_lamp(hass, brightness=40)
    expired(old)

    async def stuck(hass, entity_id) -> None:
        raise TimeoutError

    monkeypatch.setattr(director_module, "async_update_entity", AsyncMock(side_effect=stuck))

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "raise_brightness", LAMP)

    assert raised.value.translation_placeholders == {"summary": "light.lamp: timeout"}
    assert "raise_brightness on control4 timed out for light.lamp: director refused an expired token" in wire.text


async def test_a_refused_light_is_retried_under_its_lock_and_the_others_keep_their_results(hass, monkeypatch, wire):
    """One entry's token has expired, another's hasn't: each light's own result comes back, the healthy one sent
    once, and the retry holds the light's lock as the first try did."""
    old, fresh, healthy = dimmable_lamp(hass, brightness=40), FakeDirector(brightness=40), FakeDirector(brightness=40)
    expired(old)
    far = control4_entry(hass, healthy, controller="00:0f:ff:00:00:02")
    add_control4_light(hass, far, "light.far", unique_id="201")
    update = core_refresh(monkeypatch, hass, fresh)
    locked: list[bool] = []
    read = fresh.send_get_request.side_effect

    async def get(uri):
        locks = get_runtime(hass).integration_state["control4_item_locks"]
        locked.append(next(lock for (_, item), lock in locks.items() if item == ITEM).locked())
        return await read(uri)

    fresh.send_get_request.side_effect = get

    assert await call(hass, "raise_brightness", {"entity_id": ["light.far", "light.lamp"]}) == {
        "light.far": SENT,
        "light.lamp": SENT,
    }
    assert update.await_count == 1
    assert healthy.send_post_request.await_args_list == [director_call_ramp(201)]
    assert fresh.send_post_request.await_args_list == [ramp(100, 3000)]
    assert locked == [True]
    assert "light.lamp: director refused an expired token; core refreshed it, retrying" in wire.text


async def test_a_light_refused_again_after_the_refresh_is_logged_as_failed(hass, monkeypatch, caplog):
    old, fresh = dimmable_lamp(hass, brightness=40), FakeDirector(brightness=40)
    expired(old)
    expired(fresh)
    core_refresh(monkeypatch, hass, fresh)

    with pytest.raises(HomeAssistantError):
        await call(hass, "raise_brightness", LAMP)

    assert "raise_brightness on control4 failed for light.lamp: BadToken('expired')" in caplog.text


async def test_an_error_that_isnt_an_expired_token_asks_core_for_nothing(hass, monkeypatch):
    director = dimmable_lamp(hass, brightness=40)
    failing(director, "send_get_request")
    update = core_refresh(monkeypatch, hass, FakeDirector())

    with pytest.raises(HomeAssistantError):
        await call(hass, "raise_brightness", LAMP)

    assert update.await_count == 0
    assert director.send_get_request.await_count == 1


async def test_an_entry_unloaded_during_the_refresh_rejects_the_target(hass, monkeypatch, wire):
    """Core's poll left no Director at all: the refusal stands, and nothing is asked of None."""
    old = dimmable_lamp(hass, brightness=40)
    expired(old)
    entry = hass.config_entries.async_entries("control4")[0]

    async def unload(hass, entity_id) -> None:
        entry.runtime_data.director = None

    monkeypatch.setattr(director_module, "async_update_entity", AsyncMock(side_effect=unload))

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "raise_brightness", LAMP)

    assert raised.value.translation_key == "targets_failed"
    assert old.send_get_request.await_count == 1
    assert "core swapped no Director in" in wire.text


async def test_a_refusal_that_lands_after_another_calls_refresh_retries_on_the_fresh_director(hass, monkeypatch):
    """The Director a call used is what it compares with, so a swap made meanwhile isn't mistaken for none."""
    old, fresh = dimmable_lamp(hass, brightness=40), FakeDirector(brightness=40)
    entry = hass.config_entries.async_entries("control4")[0]

    async def refused_after_the_swap(uri):
        entry.runtime_data.director = fresh
        raise BadToken("expired")

    old.send_get_request.side_effect = refused_after_the_swap
    update = core_refresh(monkeypatch, hass, fresh)

    assert await call(hass, "raise_brightness", LAMP) == {"light.lamp": SENT}
    assert update.await_count == 0


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
        (40, 40.4, False),
        (40, 40.45, False),
        (40, 40.5, True),
        (40.5, 40, True),
        (0, 100, True),
        (40, None, False),
    ],
)
def test_a_light_is_ramping_from_half_a_percent_off_its_target(brightness, target, ramping):
    """RAMP_TO_LEVEL is sent whole percents, so a level within half of one of its target is there."""
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


async def test_a_reply_already_parsed_is_read_as_it_is(hass):
    director = dimmable_lamp(hass, brightness=40)
    director.send_get_request.side_effect = None
    director.send_get_request.return_value = [{"varName": "Brightness Percent", "value": 40}]

    assert await call(hass, "raise_brightness", LAMP) == {"light.lamp": SENT}
    assert director.send_post_request.await_args_list == [ramp(100, 3000)]


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


def test_brightness_percent_is_read_ahead_of_light_level():
    """The tested lights report Brightness Percent; LIGHT_LEVEL is the fallback when it is absent."""
    assert parse_level({"LIGHT_LEVEL": 10, "Brightness Percent": 40}).brightness == 40
    assert parse_level({"LIGHT_LEVEL": 10}).brightness == 10
