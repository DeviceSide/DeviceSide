"""Control4 stop: the stop command at once, then a read of the Director that says where the ramp halted."""

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.control4.stop import Control4Stop

from .conftest import CONFIRMED, HALT, LAMP, READ, SENT, dimmable_lamp, ramp
from ...conftest import allow_experimental, call, refusal, result, sent
from ...fixtures.control4 import FakeDirector, add_control4_light, control4_entry, failing


async def test_a_director_that_lags_the_stop_is_read_again(hass):
    """The Director takes the command before the light has halted, so the first reads still show the ramp."""
    director = dimmable_lamp(hass, brightness=40, halt=55)
    await call(hass, "raise_brightness", LAMP)
    director.lag_reads = 2
    director.send_get_request.reset_mock()

    assert await call(hass, "stop", LAMP) == {"light.lamp": CONFIRMED}
    assert director.send_get_request.await_args_list == [READ, READ, READ]


async def test_a_ramp_halts_and_the_halt_is_read_back(hass):
    director = dimmable_lamp(hass, brightness=40, halt=55)
    await call(hass, "raise_brightness", LAMP)
    director.send_get_request.reset_mock()
    director.send_post_request.reset_mock()

    assert await call(hass, "stop", LAMP) == {"light.lamp": CONFIRMED}
    assert director.send_post_request.await_args_list == [HALT]
    assert director.send_get_request.await_args_list == [READ]


async def test_a_lit_light_at_rest_is_confirmed(hass):
    """The command with no ramp running changes nothing, so it goes first, with no read before it."""
    director = dimmable_lamp(hass, brightness=40)

    assert await call(hass, "stop", LAMP) == {"light.lamp": CONFIRMED}
    assert director.send_post_request.await_args_list == [HALT]
    assert director.brightness == 40


async def test_an_off_light_is_unchanged(hass):
    dimmable_lamp(hass, on=False)

    assert await call(hass, "stop", LAMP) == {"light.lamp": result("control4", "unchanged", detail="off")}


async def test_raise_stop_raise_continues_from_the_halt(hass):
    director = dimmable_lamp(hass, brightness=40, halt=55)
    await call(hass, "raise_brightness", LAMP)
    await call(hass, "stop", LAMP)

    await call(hass, "raise_brightness", LAMP)

    assert director.send_post_request.await_args_list[-1] == ramp(100, 2250)


async def test_a_ramp_still_running_after_the_stop_is_only_sent(hass):
    """A driver that ignored the command must not read as confirmed."""
    director = dimmable_lamp(hass, brightness=40)
    await call(hass, "raise_brightness", LAMP)
    director.ignore_stop = True
    director.send_get_request.reset_mock()

    assert await call(hass, "stop", LAMP) == {"light.lamp": {**SENT, "detail": "still_fading"}}
    assert director.send_get_request.await_count == 4


async def test_a_light_that_reports_no_target_cant_show_a_halt(hass):
    """LIGHT_LEVEL alone says nothing of a ramp, so the command is sent and never read as confirmed."""
    director = dimmable_lamp(hass, brightness=40, legacy=True)

    assert await call(hass, "stop", LAMP) == {"light.lamp": {**SENT, "detail": "halt_not_reported"}}
    assert director.send_get_request.await_count == 1


async def test_a_ramp_from_off_that_ignores_the_stop_is_not_read_as_off(hass):
    """A ramp just begun from off still reads 0: where it is heading, not its level, says it is moving."""
    director = dimmable_lamp(hass, on=False)
    await call(hass, "raise_brightness", LAMP)
    director.ignore_stop = True

    assert await call(hass, "stop", LAMP) == {"light.lamp": {**SENT, "detail": "still_fading"}}


async def test_every_stop_is_sent_before_any_read_back(hass):
    """The read-backs wait on a lagging Director; no light's halt waits on another light's read-back."""
    log: list = []
    for number in range(6):
        director = FakeDirector(brightness=40, halt=55, log=log)
        entry = control4_entry(hass, director, controller=f"00:0f:ff:00:00:{number:02x}")
        add_control4_light(hass, entry, f"light.lamp_{number}", unique_id=str(200 + number))
        director.target = 100.0
        director.lag_reads = 2
    lamps = [f"light.lamp_{number}" for number in range(6)]

    response = await call(hass, "stop", {"entity_id": lamps})

    assert response == dict.fromkeys(lamps, CONFIRMED)
    assert [command for command, _ in log[:6]] == ["SET_BRIGHTNESS_STOP"] * 6


async def test_an_on_off_light_is_refused_with_nothing_sent(hass):
    director = FakeDirector()
    add_control4_light(
        hass, control4_entry(hass, director), "light.relay", attributes={"supported_color_modes": ["onoff"]}
    )

    assert await refusal(hass, "stop", {"entity_id": "light.relay"}) == "not_dimmable"
    assert not director.send_post_request.await_args_list
    assert not director.send_get_request.await_args_list


async def test_a_failed_read_back_is_sent(hass):
    failing(dimmable_lamp(hass), "send_get_request")

    assert await call(hass, "stop", LAMP) == {"light.lamp": {**SENT, "detail": "readback_failed"}}


async def test_a_command_error_rejects_the_target(hass):
    failing(dimmable_lamp(hass), "send_post_request")

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "stop", LAMP)

    assert raised.value.translation_key == "targets_failed"


async def test_one_lights_failed_stop_doesnt_keep_the_others_from_theirs(hass):
    """Each halt runs in its own slot: the light that failed is rejected, the other is halted and read back."""
    good, bad = FakeDirector(brightness=40), FakeDirector(brightness=40)
    add_control4_light(hass, control4_entry(hass, good), "light.lamp")
    add_control4_light(hass, control4_entry(hass, bad, controller="00:0f:ff:00:00:02"), "light.far", unique_id="201")
    failing(bad, "send_post_request")

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "stop", {"entity_id": ["light.far", "light.lamp"]})

    assert raised.value.translation_key == "targets_failed"
    assert raised.value.translation_placeholders == {"summary": "light.far: error"}
    assert good.send_post_request.await_args_list == [HALT]
    assert good.send_get_request.await_count == 1


async def test_an_off_light_that_reports_no_target_is_off_not_unreported(hass):
    director = dimmable_lamp(hass, on=False, legacy=True)

    assert await call(hass, "stop", LAMP) == {"light.lamp": result("control4", "unchanged", detail="off")}
    assert director.send_get_request.await_count == 1


async def test_a_light_that_cant_be_addressed_is_refused(hass):
    add_control4_light(hass, control4_entry(hass, FakeDirector()), "light.odd", unique_id="room-7")

    assert await refusal(hass, "stop", {"entity_id": "light.odd"}) == "not_addressable"


async def test_refused_while_the_experimental_option_is_off(hass):
    director = dimmable_lamp(hass)
    allow_experimental(hass, on=False)

    assert await refusal(hass, "stop", LAMP) == "experimental_off"
    assert not director.send_post_request.await_args_list


async def test_the_command_is_logged_without_the_item_id(hass, wire):
    dimmable_lamp(hass, brightness=40)

    await call(hass, "stop", LAMP)

    assert sent(wire) == ["light.lamp: sending director SET_BRIGHTNESS_STOP {}"]


def test_scope():
    scope = Control4Stop.scope
    assert scope.experimental
    assert scope.confirmable
    assert scope.domains == {"light": Level.EXPERIMENTAL}
