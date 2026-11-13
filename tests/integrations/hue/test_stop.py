"""Hue stop: a dimming stop to the light or room, or a cut where our soft off runs, recorded where it halted."""

import asyncio

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.color import color_hs_to_xy, color_xy_to_hs

from custom_components.deviceside.core.transition import BRIGHTNESS, SATURATION
from custom_components.deviceside.integrations.hue.transition_cache import transition_cache

from .conftest import SENT, STOP, color_lamp, color_room, hs_xy, lamp, mixed_room, report_off, room, xy_halt
from ...conftest import call, refusal, result, sent

pytestmark = pytest.mark.usefixtures("setup_production")


async def test_stop_halts_a_room_with_one_write(hass, bridge):
    entity_id = await room(hass, bridge)

    response = await call(hass, "stop", {"entity_id": entity_id})

    assert response == {entity_id: SENT}
    assert bridge.puts == [("grouped_light/grouped-1", {"dimming_delta": {"action": "stop"}})]


async def test_stop_on_a_light_without_dimming_is_refused(hass, bridge):
    entity_id = await lamp(hass, bridge, brightness=None, mirek=None)

    assert await refusal(hass, "stop", {"entity_id": entity_id}) == "not_dimmable"


async def test_room_stop_mid_move_up_from_off_holds_each_light(hass, bridge, clock):
    # aiohue still shows both lights off; they count as lit because they are still moving.
    entity_id = await mixed_room(hass, bridge, None, None)
    await call(hass, "raise_brightness", {"entity_id": entity_id, "sweep_time": 10})
    clock.now += 3
    await call(hass, "stop", {"entity_id": entity_id})
    clock.now += 10

    response = await call(hass, "get_attributes", {"entity_id": [entity_id, "light.one"]})

    assert bridge.puts[1] == ("grouped_light/grouped-1", STOP)
    assert response["light.one"]["brightness"] == 30.0
    assert response["light.room"]["brightness"] == 30.0


async def test_stop_cuts_our_soft_off_with_on_and_the_predicted_brightness(hass, bridge, clock):
    # The bridge refuses a dimming stop during a soft off; on: true with a brightness and no duration ends it there.
    entity_id = await lamp(hass, bridge, brightness_pct=100.0)
    await call(hass, "lower_brightness", {"entity_id": entity_id, "sweep_time": 10})
    report_off(bridge, "light-1")
    hass.states.async_set(entity_id, "off", {})
    clock.now += 3

    response = await call(hass, "stop", {"entity_id": entity_id})
    clock.now += 10
    read = await call(hass, "get_attributes", {"entity_id": entity_id})

    assert response == {entity_id: SENT}
    assert bridge.puts[1] == ("light/light-1", {"on": {"on": True}, "dimming": {"brightness": 70.0}})
    assert read[entity_id]["brightness"] == 70.0


async def test_stop_cuts_a_rooms_soft_off_light_by_light(hass, bridge, clock):
    # Measured on a single light only, so each light gets its own write at its own prediction.
    entity_id = await mixed_room(hass, bridge, 100.0, 50.0)
    await call(hass, "lower_brightness", {"entity_id": entity_id, "sweep_time": 10})
    report_off(bridge, "one", "two")
    clock.now += 2.5  # 7.5 s from the average 75 %: a third of the way down for each light

    response = await call(hass, "stop", {"entity_id": entity_id})

    assert response == {entity_id: SENT}
    assert bridge.puts[0] == ("grouped_light/grouped-1", {"on": {"on": False}, "dynamics": {"duration": 7500}})
    assert sorted(bridge.puts[1:]) == [
        ("light/one", {"on": {"on": True}, "dimming": {"brightness": pytest.approx(200 / 3)}}),
        ("light/two", {"on": {"on": True}, "dimming": {"brightness": pytest.approx(100 / 3)}}),
    ]


async def test_room_cut_stops_a_light_moving_on_its_own(hass, bridge, clock):
    # One light turned back up mid soft off isn't fading off: it takes the dimming stop, not the cut.
    entity_id = await mixed_room(hass, bridge, 100.0, 100.0)
    await call(hass, "lower_brightness", {"entity_id": entity_id, "sweep_time": 10})
    report_off(bridge, "one", "two")
    clock.now += 4
    await call(hass, "raise_brightness", {"entity_id": "light.one", "sweep_time": 10})
    clock.now += 1

    await call(hass, "stop", {"entity_id": entity_id})

    assert sorted(bridge.puts[2:]) == [
        ("light/one", STOP),
        ("light/two", {"on": {"on": True}, "dimming": {"brightness": pytest.approx(50.0)}}),
    ]


@pytest.mark.parametrize("target", ["light", "room"])
async def test_stop_on_an_off_light_sends_nothing(hass, bridge, target):
    # Off, or fading off from elsewhere (the bridge reports off at the start): nothing to predict or stop.
    entity_id = await (lamp if target == "light" else room)(hass, bridge, state="off")

    response = await call(hass, "stop", {"entity_id": entity_id})

    assert response == {entity_id: result("hue", "unchanged", detail="off")}
    assert bridge.puts == []


async def test_stop_after_our_soft_off_ends_sends_nothing(hass, bridge, clock):
    entity_id = await lamp(hass, bridge, brightness_pct=100.0)
    await call(hass, "lower_brightness", {"entity_id": entity_id, "sweep_time": 2})
    report_off(bridge, "light-1")
    hass.states.async_set(entity_id, "off", {})
    clock.now += 3

    response = await call(hass, "stop", {"entity_id": entity_id})

    assert response[entity_id]["detail"] == "off"
    assert bridge.puts == [("light/light-1", {"on": {"on": False}, "dynamics": {"duration": 2000}})]


def along(start: tuple[float, float], end: tuple[float, float], fraction: float) -> tuple[float, float]:
    return tuple(a + (b - a) * fraction for a, b in zip(start, end, strict=True))


async def test_stop_halts_each_room_light_at_its_own_predicted_xy(hass, bridge, clock):
    # The lights converge on one end xy from different starts, so one grouped write would jump one of them.
    entity_id = await color_room(hass, bridge, {"one": (200.0, 50.0), "two": (200.0, 10.0), "white": None})
    await call(hass, "raise_saturation", {"entity_id": entity_id, "sweep_time": 10})
    end = (bridge.puts[0][1]["color"]["xy"]["x"], bridge.puts[0][1]["color"]["xy"]["y"])
    duration = bridge.puts[0][1]["dynamics"]["duration"] / 1000
    clock.now += duration / 2

    response = await call(hass, "stop", {"entity_id": entity_id})

    assert response == {entity_id: SENT}
    assert sorted(bridge.puts[1:]) == [
        ("light/one", STOP | xy_halt(along(hs_xy(200.0, 50.0), end, 0.5))),
        ("light/two", STOP | xy_halt(along(hs_xy(200.0, 10.0), end, 0.5))),
        ("light/white", STOP),
    ]


async def test_stop_after_a_saturation_fade_has_run_is_a_plain_stop(hass, bridge, clock):
    entity_id = await color_lamp(hass, bridge)
    await call(hass, "raise_saturation", {"entity_id": entity_id, "sweep_time": 2})
    clock.now += 3

    await call(hass, "stop", {"entity_id": entity_id})

    assert bridge.puts[1] == ("light/light-1", STOP)


async def test_stop_cuts_a_soft_off_and_halts_its_saturation_in_one_write(hass, bridge, clock):
    entity_id = await color_lamp(hass, bridge, (200.0, 90.0), brightness_pct=100.0)
    await call(hass, "lower_brightness", {"entity_id": entity_id, "sweep_time": 10})
    await call(hass, "lower_saturation", {"entity_id": entity_id, "sweep_time": 10, "limit": 0})
    report_off(bridge, "light-1")
    hass.states.async_set(entity_id, "off", {})
    duration = bridge.puts[1][1]["dynamics"]["duration"] / 1000
    clock.now += duration / 4

    await call(hass, "stop", {"entity_id": entity_id})

    hue = color_xy_to_hs(*hs_xy(200.0, 90.0))[0]
    halt = along(hs_xy(200.0, 90.0), color_hs_to_xy(hue, 0), 0.25)
    cut = {"on": {"on": True}, "dimming": {"brightness": pytest.approx(100 - duration / 4 * 10)}}
    assert bridge.puts[2] == ("light/light-1", cut | xy_halt(halt))


async def test_stop_halts_brightness_and_saturation_in_one_write(hass, bridge, clock):
    entity_id = await color_lamp(hass, bridge, (200.0, 90.0), brightness_pct=20.0)
    await call(hass, "raise_brightness", {"entity_id": entity_id, "sweep_time": 10})
    await call(hass, "lower_saturation", {"entity_id": entity_id, "sweep_time": 10, "limit": 0})
    duration = bridge.puts[1][1]["dynamics"]["duration"] / 1000
    clock.now += duration / 2

    await call(hass, "stop", {"entity_id": entity_id})

    hue = color_xy_to_hs(*hs_xy(200.0, 90.0))[0]
    assert bridge.puts[2] == ("light/light-1", STOP | xy_halt(along(hs_xy(200.0, 90.0), color_hs_to_xy(hue, 0), 0.5)))


async def test_a_room_stop_is_logged_on_the_rooms_light_without_its_resource_id(hass, bridge, wire):
    entity_id = await room(hass, bridge)

    await call(hass, "stop", {"entity_id": entity_id})

    assert sent(wire) == [f"{entity_id}: sending clip grouped_light.put {{'dimming_delta': {{'action': 'stop'}}}}"]


async def test_a_failed_light_in_a_room_cut_rolls_back_only_its_own_prediction(hass, bridge, clock, caplog):
    entity_id = await mixed_room(hass, bridge, 100.0, 100.0)
    await call(hass, "lower_brightness", {"entity_id": entity_id, "sweep_time": 10})
    report_off(bridge, "one", "two")
    clock.now += 4
    bridge.failing.add("two")

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "stop", {"entity_id": entity_id})
    read = await call(hass, "get_attributes", {"entity_id": ["light.one", "light.two"]})

    assert raised.value.translation_placeholders["summary"] == f"{entity_id}: some_lights_failed"
    assert read["light.one"]["brightness"] == pytest.approx(60.0)  # halted where it was
    assert read["light.two"]["brightness"] == pytest.approx(60.0)  # the soft off's own prediction still stands, 4 s in
    assert "stop on hue failed for light.two in light.room, so they may keep fading" in caplog.text


async def test_a_room_stop_where_every_light_fails_is_rejected(hass, bridge, clock):
    entity_id = await mixed_room(hass, bridge, 100.0, 100.0)
    await call(hass, "lower_brightness", {"entity_id": entity_id, "sweep_time": 10})
    report_off(bridge, "one", "two")
    bridge.failing.update({"one", "two"})

    with pytest.raises(HomeAssistantError):
        await call(hass, "stop", {"entity_id": entity_id})


async def test_a_stop_cancelled_mid_write_leaves_the_predictions_it_found(hass, bridge, clock):
    entity_id = await color_lamp(hass, bridge, (200.0, 90.0), brightness_pct=20.0)
    await call(hass, "raise_brightness", {"entity_id": entity_id, "sweep_time": 10})
    await call(hass, "lower_saturation", {"entity_id": entity_id, "sweep_time": 10, "limit": 0})
    cache = transition_cache(hass)
    before = {attribute: cache.live("light-1", attribute) for attribute in (BRIGHTNESS, SATURATION)}
    path = cache._paths["light-1"]
    clock.now += 2
    sent = asyncio.Event()

    async def hang(*args, **kwargs):
        sent.set()
        await asyncio.Event().wait()

    bridge.api.request = hang
    task = asyncio.create_task(call(hass, "stop", {"entity_id": entity_id}))
    await sent.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert all(before[attribute] is cache.live("light-1", attribute) for attribute in before)
    assert cache._paths["light-1"] is path
