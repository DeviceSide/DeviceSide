"""Control4 raise_brightness: a read of the Director's own level, then one RAMP_TO_LEVEL with a time for the
distance left."""

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.control4 import director as director_module
from custom_components.deviceside.integrations.control4.raise_brightness import Control4RaiseBrightness

from .conftest import HALT, LAMP, READ, SENT, dimmable_lamp, ramp
from ...conftest import allow_experimental, call, refusal, result, sent
from ...fixtures.control4 import FakeDirector, add_control4_light, control4_entry, failing


@pytest.mark.parametrize(
    ("data", "sent"),
    [
        pytest.param({}, ramp(100, 3000), id="to_the_top"),
        pytest.param({"limit": 70}, ramp(70, 1500), id="to_a_limit"),
        pytest.param({"sweep_time": 10}, ramp(100, 6000), id="sweep_time_is_the_full_range"),
        pytest.param({"limit": 70.4}, ramp(70, 1520), id="limit_to_a_whole_percent"),
    ],
)
async def test_reads_the_level_then_ramps_to_the_end_point(hass, data, sent):
    director = dimmable_lamp(hass, brightness=40)

    assert await call(hass, "raise_brightness", {**LAMP, **data}) == {"light.lamp": SENT}
    assert director.send_get_request.await_args_list == [READ]
    assert director.send_post_request.await_args_list == [sent]


async def test_from_off_ramps_up_from_the_bottom(hass):
    director = dimmable_lamp(hass, brightness=60, on=False)

    assert await call(hass, "raise_brightness", LAMP) == {"light.lamp": SENT}
    assert director.send_post_request.await_args_list == [ramp(100, 5000)]


@pytest.mark.parametrize(
    ("brightness", "limit"),
    [pytest.param(100, None, id="at_the_top"), pytest.param(70, 70, id="at_the_limit"), (80, 70)],
)
async def test_nothing_left_to_raise_is_unchanged(hass, brightness, limit):
    director = dimmable_lamp(hass, brightness=brightness)
    data = {} if limit is None else {"limit": limit}

    assert await call(hass, "raise_brightness", {**LAMP, **data}) == {
        "light.lamp": result("control4", "unchanged", detail="at_limit")
    }
    assert not director.send_post_request.await_args_list


async def test_a_fractional_level_is_where_the_move_starts(hass):
    """The Director's level can hold a fraction, so the distance left is measured from it as it is."""
    director = dimmable_lamp(hass, brightness=77.44)

    await call(hass, "raise_brightness", LAMP)

    assert director.send_post_request.await_args_list == [ramp(100, 1128)]


async def test_a_light_caught_mid_ramp_is_halted_and_moved_from_where_it_stopped(hass):
    """A ramp just begun still reads the level it left (Tested behavior), so that level isn't where the light is."""
    director = dimmable_lamp(hass, brightness=40, halt=55)
    await call(hass, "lower_brightness", LAMP)
    director.lag_reads = 1
    director.send_get_request.reset_mock()
    director.send_post_request.reset_mock()

    assert await call(hass, "raise_brightness", LAMP) == {"light.lamp": SENT}
    assert director.send_post_request.await_args_list == [HALT, ramp(100, 2250)]
    assert director.send_get_request.await_args_list == [READ, READ, READ]


async def test_a_ramp_that_wont_halt_is_moved_from_the_level_last_read(hass, wire):
    director = dimmable_lamp(hass, brightness=40)
    await call(hass, "lower_brightness", LAMP)
    director.ignore_stop = True
    director.send_post_request.reset_mock()

    assert await call(hass, "raise_brightness", LAMP) == {"light.lamp": SENT}
    assert director.send_post_request.await_args_list == [HALT, ramp(100, 3000)]
    assert (
        "light.lamp: ramping to 0.0, not the adapter's own to 100 (last sent 0); halting it to read where it is"
        in wire.text
    )
    assert "light.lamp: director still shows a ramp; moving from the level it reports" in wire.text


@pytest.mark.parametrize("action", ["raise_brightness", "lower_brightness"])
async def test_a_repeat_of_the_call_mid_ramp_sends_nothing_and_leaves_the_ramp_its_speed(hass, action, wire):
    """A remote that repeats while held: the adapter's own ramp to this end is already running."""
    director = dimmable_lamp(hass, brightness=40)
    await call(hass, action, LAMP)
    director.send_post_request.reset_mock()

    assert await call(hass, action, LAMP) == {"light.lamp": SENT}
    assert not director.send_post_request.await_args_list
    assert f"light.lamp: already ramping to {100 if action == 'raise_brightness' else 0}; nothing sent" in wire.text


async def test_a_ramp_the_same_way_to_another_end_is_halted_and_moved_from_where_it_stopped(hass):
    """Its level may be a second old, so a new limit is never timed from it."""
    director = dimmable_lamp(hass, brightness=40, halt=42)
    await call(hass, "raise_brightness", {**LAMP, "limit": 45})
    director.send_post_request.reset_mock()

    assert await call(hass, "raise_brightness", LAMP) == {"light.lamp": SENT}
    assert director.send_post_request.await_args_list == [HALT, ramp(100, 2900)]


async def test_the_adapters_own_ramp_is_its_own_only_while_it_can_still_be_running(hass, monkeypatch):
    """Past its time, a ramp to the same end is someone else's: a scene, or core's turn-on with a long transition."""
    director = dimmable_lamp(hass, brightness=40, halt=50)
    await call(hass, "raise_brightness", LAMP)
    director.send_post_request.reset_mock()
    now = hass.loop.time()
    assert director_module.OWN_RAMP_GRACE_S == 2.0

    monkeypatch.setattr(hass.loop, "time", lambda: now + 3 + director_module.OWN_RAMP_GRACE_S - 0.5)
    assert await call(hass, "raise_brightness", LAMP) == {"light.lamp": SENT}
    assert not director.send_post_request.await_args_list

    monkeypatch.setattr(hass.loop, "time", lambda: now + 3 + director_module.OWN_RAMP_GRACE_S + 0.5)
    assert await call(hass, "raise_brightness", LAMP) == {"light.lamp": SENT}
    assert director.send_post_request.await_args_list == [HALT, ramp(100, 2500)]


async def test_the_adapters_own_ramp_now_heading_elsewhere_is_halted(hass):
    """Its end was changed from Control4: the Director's target no longer matches the one sent."""
    director = dimmable_lamp(hass, brightness=40, halt=30)
    await call(hass, "raise_brightness", LAMP)
    director.target = 20.0
    director.send_post_request.reset_mock()

    assert await call(hass, "raise_brightness", LAMP) == {"light.lamp": SENT}
    assert director.send_post_request.await_args_list == [HALT, ramp(100, 3500)]


async def test_a_ramp_that_failed_to_send_is_not_remembered_and_a_stop_that_failed_forgets_nothing(hass):
    director = dimmable_lamp(hass, brightness=40, halt=50)
    respond = director.send_post_request.side_effect
    director.send_post_request.side_effect = ConnectionError("director unreachable")
    with pytest.raises(HomeAssistantError):
        await call(hass, "raise_brightness", LAMP)
    director.send_post_request.side_effect = respond
    director.target = 100.0
    director.send_post_request.reset_mock()

    assert await call(hass, "raise_brightness", LAMP) == {"light.lamp": SENT}
    assert director.send_post_request.await_args_list == [HALT, ramp(100, 2500)]

    director.send_post_request.side_effect = ConnectionError("director unreachable")
    with pytest.raises(HomeAssistantError):
        await call(hass, "stop", LAMP)
    director.send_post_request.side_effect = respond
    director.send_post_request.reset_mock()

    assert await call(hass, "raise_brightness", LAMP) == {"light.lamp": SENT}
    assert not director.send_post_request.await_args_list


async def test_a_repeat_to_a_fractional_limit_is_the_same_whole_percent(hass):
    director = dimmable_lamp(hass, brightness=40)
    await call(hass, "raise_brightness", {**LAMP, "limit": 70.4})
    director.send_post_request.reset_mock()

    assert await call(hass, "raise_brightness", {**LAMP, "limit": 70.4}) == {"light.lamp": SENT}
    assert not director.send_post_request.await_args_list


async def test_a_ramp_that_isnt_the_adapters_own_is_halted_though_it_heads_the_same_way(hass):
    """Started from Control4, or before Home Assistant restarted: only the last command sent says whose it is."""
    director = dimmable_lamp(hass, brightness=40, halt=50)
    director.target = 100.0

    assert await call(hass, "raise_brightness", LAMP) == {"light.lamp": SENT}
    assert director.send_post_request.await_args_list == [HALT, ramp(100, 2500)]


async def test_a_press_right_after_a_stop_waits_for_the_director_to_show_the_halt(hass):
    """The Director shows the halted ramp a moment longer (Tested behavior); the stop made it no longer its own."""
    director = dimmable_lamp(hass, brightness=40, halt=55)
    await call(hass, "raise_brightness", LAMP)
    director.lag_reads = 6
    await call(hass, "stop", LAMP)
    director.lag_reads = 1
    director.send_post_request.reset_mock()

    assert await call(hass, "raise_brightness", LAMP) == {"light.lamp": SENT}
    assert director.send_post_request.await_args_list == [HALT, ramp(100, 2250)]


@pytest.mark.parametrize(
    ("start", "first", "limit", "then", "sent"),
    [
        pytest.param(40, "raise_brightness", 45, "lower_brightness", ramp(0, 2000), id="up_to_a_low_limit"),
        pytest.param(60, "lower_brightness", 55, "raise_brightness", ramp(100, 2000), id="down_to_a_high_limit"),
    ],
)
async def test_a_ramp_to_another_end_the_other_way_is_halted_whatever_the_levels(hass, start, first, limit, then, sent):
    director = dimmable_lamp(hass, brightness=start)
    await call(hass, first, {**LAMP, "limit": limit})
    director.send_post_request.reset_mock()

    assert await call(hass, then, LAMP) == {"light.lamp": SENT}
    assert director.send_post_request.await_args_list == [HALT, sent]


async def test_a_sweep_time_longer_than_a_ramp_can_take_is_clamped(hass):
    director = dimmable_lamp(hass, brightness=0, on=False)

    response = await call(hass, "raise_brightness", {**LAMP, "sweep_time": 120})

    assert response == {"light.lamp": {**SENT, "clamped_to": 65.535}}
    assert director.send_post_request.await_args_list == [ramp(100, 65535)]


async def test_a_light_that_reports_light_level_alone_is_read(hass):
    director = dimmable_lamp(hass, brightness=40, legacy=True)

    assert await call(hass, "raise_brightness", LAMP) == {"light.lamp": SENT}
    assert director.send_post_request.await_args_list == [ramp(100, 3000)]


async def test_a_level_reported_as_text_is_read_as_a_number(hass):
    """The Director sends text for a light that has never reported."""
    director = dimmable_lamp(hass, brightness=40)
    director.text = True

    assert await call(hass, "raise_brightness", LAMP) == {"light.lamp": SENT}
    assert director.send_post_request.await_args_list == [ramp(100, 3000)]


async def test_an_on_off_light_drops_brightness(hass):
    director = FakeDirector()
    add_control4_light(
        hass, control4_entry(hass, director), "light.relay", attributes={"supported_color_modes": ["onoff"]}
    )

    assert await call(hass, "raise_brightness", {"entity_id": "light.relay"}) == {
        "light.relay": result("control4", "unchanged", detail="fields_dropped")
    }
    assert not director.send_get_request.await_args_list


async def test_refused_while_the_experimental_option_is_off(hass):
    director = dimmable_lamp(hass)
    allow_experimental(hass, on=False)

    assert await refusal(hass, "raise_brightness", LAMP) == "experimental_off"
    assert not director.send_get_request.await_args_list


async def test_lights_that_cant_be_addressed_are_refused(hass):
    add_control4_light(hass, control4_entry(hass, FakeDirector()), "light.odd", unique_id="room-7")
    add_control4_light(hass, control4_entry(hass, None), "light.no_director", unique_id="200")

    assert await refusal(hass, "raise_brightness", {"entity_id": "light.odd"}) == "not_addressable"
    assert await refusal(hass, "raise_brightness", {"entity_id": "light.no_director"}) == "not_addressable"


@pytest.mark.parametrize("method", ["send_get_request", "send_post_request"])
async def test_a_director_error_rejects_the_target(hass, method):
    failing(dimmable_lamp(hass), method)

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "raise_brightness", LAMP)

    assert raised.value.translation_key == "targets_failed"
    assert raised.value.translation_placeholders == {"summary": "light.lamp: error"}


async def test_a_light_with_no_level_is_rejected(hass):
    """No level to measure from: the target is rejected instead of moved from a guess."""
    director = dimmable_lamp(hass)
    director.send_get_request.side_effect = None
    director.send_get_request.return_value = '[{"id": 100, "varName": "LIGHT_STATE", "value": "unknown"}]'

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "raise_brightness", LAMP)

    assert raised.value.translation_key == "targets_failed"
    assert not director.send_post_request.await_args_list


async def test_the_ramp_is_logged_without_the_item_id(hass, wire):
    dimmable_lamp(hass, brightness=40)

    await call(hass, "raise_brightness", LAMP)

    assert sent(wire) == ["light.lamp: sending director RAMP_TO_LEVEL {'LEVEL': 100, 'TIME': 3000}"]


def test_scope():
    scope = Control4RaiseBrightness.scope
    assert scope.experimental
    assert scope.domains == {"light": Level.EXPERIMENTAL}
    assert scope.fields == {"brightness": Level.EXPERIMENTAL}
    assert scope.capabilities is None
