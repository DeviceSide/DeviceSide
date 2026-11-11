"""predicted_state: the bridge's reports of our fades hidden from aiohue (so HA), and DeviceSide's predictions sent."""

import asyncio
import logging
from contextvars import Context

import pytest
from aiohue.v2.controllers.events import EventType
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.core.transition import BRIGHTNESS, SATURATION
from custom_components.deviceside.integrations.hue.report_filter import _END_PREFIX
from custom_components.deviceside.integrations.hue.transition_cache import MIN_BRIGHTNESS_STEP, transition_cache

from .conftest import light_event, setup_room
from ...conftest import advance, call, wall_clock_now
from ...fixtures.hue import add_hue_entity, add_hue_group, hue_entry

pytestmark = pytest.mark.usefixtures("setup_production")

# light "one" from 20 % to full at sweep_time 10 takes 8 s.
FADE_S = 8.0


async def settle(hass) -> None:
    """Let HA's tasks finish, then aiohue's: it applies events in bare tasks, which block_till_done doesn't wait on."""
    await hass.async_block_till_done()
    for _ in range(3):
        await asyncio.sleep(0)


def report(bridge, event: dict) -> None:
    bridge.api.events.emit(EventType.RESOURCE_UPDATED, event)


def shown(bridge, light_id: str) -> tuple[bool, float]:
    """What aiohue holds for the light, which is what HA shows."""
    light = bridge.api.lights[light_id]
    return light.on.on, light.dimming.brightness


def room_shown(bridge) -> tuple[bool, float | None]:
    group = bridge.api.groups.grouped_light["1"]
    return group.on.on, group.dimming.brightness if group.dimming else None


async def raise_one(hass) -> None:
    await call(hass, "raise_brightness", {"entity_id": "light.one", "sweep_time": 10})


async def test_aiohue_applies_an_event_after_a_synchronous_subscriber(bridge):
    # Hiding rests on this: aiohue's controllers apply an event in a task, so a synchronous subscriber edits it first.
    bridge.light("one", on=True, brightness=20.0)
    api = await bridge.load()

    def edit(_event_type, data):
        data["dimming"]["brightness"] = 33.0

    api.events.subscribe(edit, event_filter=EventType.RESOURCE_UPDATED)
    report(bridge, light_event("one", brightness=90.0))
    assert api.lights["one"].dimming.brightness == 20.0
    await asyncio.sleep(0)

    assert api.lights["one"].dimming.brightness == 33.0


async def test_ha_holds_the_start_value_while_the_fade_runs(hass, bridge, clock):
    await setup_room(hass, bridge)
    await raise_one(hass)

    report(bridge, light_event("one", brightness=100.0))  # the bridge's end value, at the start
    clock.now += 3.0
    report(bridge, light_event("one", brightness=45.0))  # the bulb, a little late
    await settle(hass)

    assert shown(bridge, "one") == (True, 20.0)


async def test_the_end_is_shown_once_the_fade_has_run(hass, bridge, clock):
    await setup_room(hass, bridge)
    start = wall_clock_now()
    await raise_one(hass)
    report(bridge, light_event("one", brightness=100.0))

    await advance(hass, start, FADE_S - 0.5)
    assert shown(bridge, "one") == (True, 20.0)
    await advance(hass, start, FADE_S + 0.1)
    assert shown(bridge, "one") == (True, 100.0)


async def test_a_stop_shows_the_halt_and_drops_the_end(hass, bridge, clock):
    await setup_room(hass, bridge)
    start = wall_clock_now()
    await raise_one(hass)
    clock.now += 4.0

    await call(hass, "stop", {"entity_id": "light.one"})
    await settle(hass)
    assert shown(bridge, "one") == (True, 60.0)

    await advance(hass, start, FADE_S + 1)
    assert shown(bridge, "one") == (True, 60.0)


async def test_a_change_from_ha_drops_the_end(hass, bridge, clock):
    await setup_room(hass, bridge)
    async_mock_service(hass, "light", "turn_on")
    start = wall_clock_now()
    await raise_one(hass)

    await hass.services.async_call("light", "turn_on", {"entity_id": "light.one"}, blocking=True)
    report(bridge, light_event("one", brightness=55.0))  # what the turn_on set, though on the path
    await advance(hass, start, FADE_S + 1)

    assert shown(bridge, "one") == (True, 55.0)


async def test_a_color_change_from_ha_mid_fade_hands_ha_back_to_the_bridge(hass, bridge, clock):
    # Nothing will show the fade's end now, so HA shows the end the bridge reported at its start.
    await setup_room(hass, bridge)
    async_mock_service(hass, "light", "turn_on")
    await raise_one(hass)
    report(bridge, light_event("one", brightness=100.0))
    clock.now += 2.0

    warmer = {"entity_id": "light.one", "color_temp_kelvin": 3000}
    await hass.services.async_call("light", "turn_on", warmer, blocking=True)
    await settle(hass)

    assert shown(bridge, "one") == (True, 100.0)


async def test_a_change_from_ha_after_a_stop_keeps_the_halt(hass, bridge, clock):
    await setup_room(hass, bridge)
    async_mock_service(hass, "light", "turn_on")
    await raise_one(hass)
    report(bridge, light_event("one", brightness=100.0))
    clock.now += 4.0
    await call(hass, "stop", {"entity_id": "light.one"})

    warmer = {"entity_id": "light.one", "color_temp_kelvin": 3000}
    await hass.services.async_call("light", "turn_on", warmer, blocking=True)
    await settle(hass)

    assert shown(bridge, "one") == (True, 60.0)


async def test_unloading_mid_fade_hands_ha_back_to_the_bridge(hass, bridge, clock, setup_production):
    await setup_room(hass, bridge)
    await raise_one(hass)
    report(bridge, light_event("one", brightness=100.0))
    await settle(hass)

    assert await hass.config_entries.async_unload(setup_production.entry_id)
    await settle(hass)

    assert shown(bridge, "one") == (True, 100.0)


async def test_set_attributes_mid_fade_reaches_ha(hass, bridge, clock):
    await setup_room(hass, bridge)
    start = wall_clock_now()
    await raise_one(hass)
    clock.now += 4.0

    await call(hass, "set_attributes", {"entity_id": "light.one", "brightness": 40})
    report(bridge, light_event("one", brightness=40.0))  # on the path, but a write of its own
    await advance(hass, start, FADE_S + 1)

    assert shown(bridge, "one") == (True, 40.0)


async def test_a_soft_off_stays_on_until_its_end(hass, bridge, clock):
    await setup_room(hass, bridge)
    start = wall_clock_now()
    await call(hass, "lower_brightness", {"entity_id": "light.one", "sweep_time": 10})  # 2 s

    report(bridge, light_event("one", on=False))
    await settle(hass)
    assert shown(bridge, "one") == (True, 20.0)

    await advance(hass, start, 2.1)
    assert shown(bridge, "one") == (False, 20.0)  # the bridge keeps the brightness through a soft off


@pytest.mark.parametrize("min_dim_level", [5.0, 0.2, None], ids=["white", "ambiance", "none_reported"])
async def test_up_from_off_shows_on_at_the_lowest_step(hass, bridge, clock, min_dim_level):
    """Where the fade starts, whatever the light's min_dim_level: that is light output, not a brightness, and a Hue
    White on at 0.4 % reports 0.4 (probe, 2026-11-02)."""
    bridge.light("one", on=False, brightness=60.0)
    entry = await hue_entry(hass, bridge)
    add_hue_entity(hass, entry, "light.one", "one")
    bridge.api.lights["one"].dimming.min_dim_level = min_dim_level

    await call(hass, "raise_brightness", {"entity_id": "light.one", "sweep_time": 10})
    report(bridge, light_event("one", on=True, brightness=100.0))
    await settle(hass)

    assert shown(bridge, "one") == (True, MIN_BRIGHTNESS_STEP)


async def test_a_room_shows_the_mean_of_its_lit_lights(hass, bridge, clock):
    await setup_room(hass, bridge)
    await call(hass, "raise_brightness", {"entity_id": "light.room", "sweep_time": 10})
    report(bridge, {"id": "1", "type": "grouped_light", "dimming": {"brightness": 100.0}})
    await settle(hass)
    assert room_shown(bridge) == (True, 20.0)

    clock.now += 4.0
    await call(hass, "stop", {"entity_id": "light.room"})
    await settle(hass)

    assert room_shown(bridge) == (True, 60.0)
    assert shown(bridge, "one") == shown(bridge, "two") == (True, 60.0)


async def test_a_room_up_from_off_shows_on(hass, bridge, clock):
    bridge.light("one", on=False, brightness=60.0)
    bridge.light("two", on=False, brightness=60.0)
    bridge.room("1", ["one", "two"], brightness=60.0)
    entry = await hue_entry(hass, bridge)
    members = [add_hue_entity(hass, entry, f"light.{light_id}", light_id) for light_id in ("one", "two")]
    add_hue_group(hass, entry, "light.room", "1", members)

    await call(hass, "raise_brightness", {"entity_id": "light.room", "sweep_time": 10})
    report(bridge, {"id": "1", "type": "grouped_light", "on": {"on": True}, "dimming": {"brightness": 100.0}})
    for light_id in ("one", "two"):
        report(bridge, light_event(light_id, on=True, brightness=100.0))
    await settle(hass)

    assert room_shown(bridge) == (True, MIN_BRIGHTNESS_STEP)


@pytest.mark.parametrize("action", ["raise_brightness", "lower_brightness"])
async def test_a_room_its_bridge_has_not_reported_on_yet_shows_on_at_the_start(hass, bridge, clock, action):
    # The rig saw this for ~1 s: a room turned on just before the move, its lights reported on, the room not yet.
    await setup_room(hass, bridge)
    bridge.api.groups.grouped_light["1"].on.on = False

    await call(hass, action, {"entity_id": "light.room", "sweep_time": 10})
    await settle(hass)

    assert room_shown(bridge) == (True, 20.0)


async def test_a_stale_report_after_a_stop_stays_hidden(hass, bridge, clock):
    # The rig saw a bulb report, 4 s after a stop, the brightness it held before the move.
    await setup_room(hass, bridge)
    await raise_one(hass)
    clock.now += 4.0
    await call(hass, "stop", {"entity_id": "light.one"})

    clock.now += 4.0
    report(bridge, light_event("one", brightness=56.0))
    await settle(hass)

    assert shown(bridge, "one") == (True, 60.0)


async def test_off_from_elsewhere_mid_fade_shows_at_once_and_drops_the_end(hass, bridge, clock):
    await setup_room(hass, bridge)
    start = wall_clock_now()
    await raise_one(hass)
    report(bridge, light_event("one", brightness=100.0))
    clock.now += 2.0

    report(bridge, light_event("one", on=False))  # the Hue app
    await advance(hass, start, FADE_S + 1)

    assert shown(bridge, "one") == (False, 100.0)  # the end value the bridge reported, handed back


async def test_a_color_change_from_elsewhere_mid_fade_shows_at_once(hass, bridge, clock):
    # Our brightness writes never report a color temperature, so the color changed elsewhere; the brightness in the
    # same event is still the fade's, which a color change doesn't stop.
    await setup_room(hass, bridge)
    await raise_one(hass)

    report(bridge, light_event("one", brightness=70.0, color_temperature={"mirek": 300}))
    await settle(hass)

    assert shown(bridge, "one") == (True, 20.0)
    assert bridge.api.lights["one"].color_temperature.mirek == 300


async def test_a_color_report_mid_room_fade_keeps_the_brightness_prediction(hass, bridge, clock):
    # rig-run-2026-11-11-085849: mid-fade a bulb reported a stale brightness, then a color the bridge had reported
    # wrongly before the fade. The color forgot the whole light and handed HA the stale brightness for good.
    await setup_room(hass, bridge)
    start = wall_clock_now()
    await call(hass, "raise_brightness", {"entity_id": "light.room", "sweep_time": 10})
    for light_id in ("one", "two"):
        report(bridge, light_event(light_id, brightness=100.0))  # the bridge's end values, at the start
    report(bridge, {"id": "1", "type": "grouped_light", "dimming": {"brightness": 100.0}})
    clock.now += FADE_S - 0.5

    report(bridge, light_event("one", brightness=96.44))  # the bulb, mid-fade
    report(bridge, light_event("one", color_temperature={"mirek": 298}, color={"xy": {"x": 0.4141, "y": 0.3958}}))
    await settle(hass)
    assert shown(bridge, "one") == (True, 20.0)  # the hidden 96.44 not handed back
    assert bridge.api.lights["one"].color_temperature.mirek == 298

    await advance(hass, start, FADE_S + 0.1)
    await settle(hass)
    clock.now += 1.0
    assert shown(bridge, "one") == shown(bridge, "two") == (True, 100.0)
    assert room_shown(bridge) == (True, 100.0)
    response = await call(hass, "get_attributes", {"entity_id": ["light.room", "light.one"]})
    assert response["light.one"]["brightness"] == response["light.room"]["brightness"] == 100.0


async def test_a_brightness_report_mid_saturation_fade_keeps_the_saturation_prediction(hass, bridge, clock):
    # Every color key is the saturation move's, so only a brightness from elsewhere is real; the xy fade runs on.
    await setup_room(hass, bridge)
    cache = transition_cache(hass)
    await raise_one(hass)  # attaches the filter
    cache.forget("one", BRIGHTNESS)
    cache.moving("one", SATURATION, 20.0, 80.0, 10.0)
    clock.now += 2.0

    report(bridge, light_event("one", brightness=55.0))  # the Hue app
    await settle(hass)

    assert cache.live("one", SATURATION) is not None
    assert shown(bridge, "one") == (True, 55.0)


async def test_off_from_elsewhere_mid_fade_forgets_only_the_brightness(hass, bridge, clock):
    await setup_room(hass, bridge)
    cache = transition_cache(hass)
    await raise_one(hass)
    cache.moving("one", SATURATION, 20.0, 80.0, 10.0)
    clock.now += 2.0

    report(bridge, light_event("one", on=False))  # the Hue app
    await settle(hass)

    assert cache.live("one", BRIGHTNESS) is None
    assert cache.live("one", SATURATION) is not None
    assert not any(key.endswith(f"one:{BRIGHTNESS}") for key in get_runtime(hass).pending)


async def test_option_off_shows_what_the_bridge_reports(hass, bridge, clock):
    get_runtime(hass).predicted_state = False
    await setup_room(hass, bridge)
    start = wall_clock_now()
    await raise_one(hass)

    report(bridge, light_event("one", brightness=100.0))
    await settle(hass)
    assert shown(bridge, "one") == (True, 100.0)

    clock.now += 4.0
    await call(hass, "stop", {"entity_id": "light.one"})
    await advance(hass, start, FADE_S + 1)
    assert shown(bridge, "one") == (True, 100.0)


async def test_an_aiohue_that_applies_events_at_once_falls_back_to_the_bridge(hass, bridge, clock, caplog):
    await setup_room(hass, bridge)
    bridge.api.lights._handle_event = lambda *_args: None

    with caplog.at_level(logging.WARNING):
        await raise_one(hass)
    report(bridge, light_event("one", brightness=100.0))
    await settle(hass)

    assert "Hue fades show what the bridge reports" in caplog.text
    assert shown(bridge, "one") == (True, 100.0)


async def test_the_first_move_hides_the_end_the_bridge_reports_during_the_write(hass, bridge, clock, monkeypatch):
    await setup_room(hass, bridge)  # no filter yet: the first move attaches it
    put = bridge.api.request

    async def report_during_put(method, path, json=None, **kwargs):
        if method == "put":
            report(bridge, light_event("one", brightness=100.0))  # the bridge's end value, before the write returns
        return await put(method, path, json=json, **kwargs)

    monkeypatch.setattr(bridge.api, "request", report_during_put)

    await raise_one(hass)
    await settle(hass)

    assert shown(bridge, "one") == (True, 20.0)


async def test_detaching_drops_the_bridges_filter_but_not_a_newer_one(hass, bridge, clock):
    await setup_room(hass, bridge)
    await raise_one(hass)
    filters = get_runtime(hass).integration_state["hue_filters"]
    ((entry_id, reports),) = filters.items()

    reports.attach()()  # a second subscription of the same filter, detached
    assert entry_id not in filters

    filters[entry_id] = newer = object()
    reports.attach()()
    assert filters[entry_id] is newer


async def test_a_stop_landing_during_the_fades_write_leaves_no_end_job(hass, bridge, clock):
    await setup_room(hass, bridge)
    cache = transition_cache(hass)
    request = bridge.api.request

    async def stop_lands(*args, **kwargs):
        # A stop is its own call, so it records outside the fade's recording block.
        Context().run(cache.stopped, "one", "brightness", 50.0)
        return await request(*args, **kwargs)

    bridge.api.request = stop_lands
    await raise_one(hass)

    assert not [key for key in get_runtime(hass).pending if key.startswith(_END_PREFIX)]
