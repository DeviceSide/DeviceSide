"""Control4 set_attributes: the light's own range, one SET_COLOR_TARGET in color temperature mode, then a read-back."""

from unittest.mock import call as director_call

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.control4.set_attributes import Control4SetAttributes

from .conftest import CONFIRMED, LAMP, SENT, dimmable_lamp
from ...conftest import allow_experimental, call, refusal, result, sent
from ...fixtures.control4 import ITEM, FakeDirector, add_control4_light, control4_entry, failing

CAPABILITIES = director_call(f"/api/v1/items/{ITEM}/variables?varnames=Navigator%20Dynamic%20Capabilities")
READ = director_call(
    f"/api/v1/items/{ITEM}/variables"
    "?varnames=Brightness%20Percent,LIGHT_LEVEL,Brightness%20Target%20Percent,Current%20CCT,Current%20Color%20Mode"
    ",Target%20CCT,Target%20Color%20Mode"
)


def color(kelvin: int):
    params = {"LIGHT_COLOR_TARGET_COLOR_CORRELATED_TEMPERATURE": kelvin, "LIGHT_COLOR_TARGET_MODE": 1}
    return director_call(f"/api/v1/items/{ITEM}/commands", "SET_COLOR_TARGET", params)


async def test_a_lit_light_changes_and_reads_the_kelvin_back(hass):
    """The entity lists brightness alone, as core's Control4 light does: the color temperature still goes out."""
    director = dimmable_lamp(hass, brightness=40)

    assert await call(hass, "set_attributes", {**LAMP, "color_temp_kelvin": 2700}) == {"light.lamp": CONFIRMED}
    assert director.send_get_request.await_args_list == [CAPABILITIES, READ]
    assert director.send_post_request.await_args_list == [color(2700)]
    assert (director.kelvin, director.brightness) == (2700, 40)


async def test_an_off_light_stays_off_and_is_only_sent(hass):
    """Once a little over a second is past the Director shows the old color temperature until the light comes on."""
    director = dimmable_lamp(hass, on=False)

    assert await call(hass, "set_attributes", {**LAMP, "color_temp_kelvin": 4000}) == {
        "light.lamp": {**SENT, "detail": "stored_while_off"}
    }
    assert director.send_post_request.await_args_list == [color(4000)]
    assert (director.brightness, director.kelvin, director.pending_kelvin) == (0, 3200, 4000)


async def test_an_off_light_showing_the_new_kelvin_is_still_only_sent(hass):
    """Off, the Director shows the new kelvin for over a second (Tested behavior): that is never a confirmation."""
    director = dimmable_lamp(hass, on=False)
    director.kelvin = director.target_kelvin = 4000

    assert await call(hass, "set_attributes", {**LAMP, "color_temp_kelvin": 4000}) == {
        "light.lamp": {**SENT, "detail": "stored_while_off"}
    }
    assert director.send_get_request.await_args_list == [CAPABILITIES, READ]


@pytest.mark.parametrize(("asked", "sent"), [(2000, 2203), (6535, 6535), (3000, 3000), (7000, 6536)])
async def test_the_kelvin_is_clamped_to_the_lights_own_range_and_reported(hass, asked, sent):
    """The light is judged against what was sent, and the result says what that was when it isn't what was asked."""
    director = dimmable_lamp(hass)

    response = await call(hass, "set_attributes", {**LAMP, "color_temp_kelvin": asked})

    assert director.send_post_request.await_args_list == [color(sent)]
    assert response == {"light.lamp": CONFIRMED if asked == sent else {**CONFIRMED, "clamped_to": sent}}


async def test_capabilities_held_as_json_text_are_read(hass):
    director = dimmable_lamp(hass)
    director.capabilities_as_text = True

    assert await call(hass, "set_attributes", {**LAMP, "color_temp_kelvin": 2700}) == {"light.lamp": CONFIRMED}
    assert director.send_post_request.await_args_list == [color(2700)]


async def test_a_light_not_yet_showing_the_kelvin_as_current_is_confirmed_by_its_target(hass):
    """The Director shows a new color temperature as current most of a second late; the target shows it first."""
    director = dimmable_lamp(hass)
    director.current_lags = True

    assert await call(hass, "set_attributes", {**LAMP, "color_temp_kelvin": 2700}) == {"light.lamp": CONFIRMED}
    assert (director.kelvin, director.target_kelvin) == (3200, 2700)
    assert director.send_get_request.await_args_list == [CAPABILITIES, READ]


async def test_a_director_that_lags_the_command_is_read_again(hass):
    """The target once showed the kelvin a read late (Tested behavior), so the read-back reads again."""
    director = dimmable_lamp(hass)
    director.lag_reads = 2

    assert await call(hass, "set_attributes", {**LAMP, "color_temp_kelvin": 2700}) == {"light.lamp": CONFIRMED}
    assert director.send_get_request.await_args_list == [CAPABILITIES, READ, READ, READ]


async def test_a_lit_light_that_never_reads_it_back_is_only_sent(hass):
    director = dimmable_lamp(hass)
    director.ignore_color = True

    assert await call(hass, "set_attributes", {**LAMP, "color_temp_kelvin": 2700}) == {
        "light.lamp": {**SENT, "detail": "color_temp_not_reported"}
    }
    assert director.send_get_request.await_count == 5


async def test_every_write_is_sent_before_any_read_back(hass):
    log: list = []
    for number in range(6):
        director = FakeDirector(log=log)
        director.lag_reads = 2
        entry = control4_entry(hass, director, controller=f"00:0f:ff:00:00:{number:02x}")
        add_control4_light(hass, entry, f"light.lamp_{number}", unique_id=str(200 + number))
    lamps = [f"light.lamp_{number}" for number in range(6)]

    response = await call(hass, "set_attributes", {"entity_id": lamps, "color_temp_kelvin": 2700})

    assert response == dict.fromkeys(lamps, CONFIRMED)
    assert [command for command, _ in log[:12]].count("SET_COLOR_TARGET") == 6


@pytest.mark.parametrize("legacy", [False, True], ids=["says_it_takes_none", "no_capabilities_variable"])
async def test_a_light_with_no_color_temperature_lacks_the_field_and_nothing_is_sent(hass, legacy):
    """As a white bulb in a mixed room is: unchanged, so the call goes on to the lights that take it."""
    director = dimmable_lamp(hass, legacy=legacy)
    director.kelvin_span = None

    assert await call(hass, "set_attributes", {**LAMP, "color_temp_kelvin": 2700}) == {
        "light.lamp": result("control4", "unchanged", detail="fields_dropped")
    }
    assert not director.send_post_request.await_args_list


async def test_a_room_with_a_light_that_lacks_it_still_sets_the_others(hass):
    director = dimmable_lamp(hass)
    plain = FakeDirector()
    plain.kelvin_span = None
    add_control4_light(
        hass, control4_entry(hass, plain, controller="00:0f:ff:00:00:01"), "light.plain", unique_id="201"
    )

    response = await call(
        hass, "set_attributes", {"entity_id": ["light.lamp", "light.plain"], "color_temp_kelvin": 2700}
    )

    assert response == {
        "light.lamp": CONFIRMED,
        "light.plain": result("control4", "unchanged", detail="fields_dropped"),
    }
    assert director.kelvin == 2700
    assert not plain.send_post_request.await_args_list


async def test_a_failed_read_back_is_sent(hass):
    failing(dimmable_lamp(hass), "send_get_request", after=1)

    assert await call(hass, "set_attributes", {**LAMP, "color_temp_kelvin": 2700}) == {
        "light.lamp": {**SENT, "detail": "readback_failed"}
    }


async def test_a_command_error_rejects_the_target(hass):
    failing(dimmable_lamp(hass), "send_post_request")

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "set_attributes", {**LAMP, "color_temp_kelvin": 2700})

    assert raised.value.translation_key == "targets_failed"


async def test_brightness_is_refused_not_dropped(hass):
    """A level written while off would be lost to core's next turn-on, so the field isn't built."""
    director = dimmable_lamp(hass)

    assert await refusal(hass, "set_attributes", {**LAMP, "brightness": 50}) == "fields_not_tested"
    assert not director.send_post_request.await_args_list


async def test_a_color_is_dropped_as_the_light_lacks_it(hass):
    director = dimmable_lamp(hass)

    assert await call(hass, "set_attributes", {**LAMP, "rgb_color": [255, 0, 0]}) == {
        "light.lamp": result("control4", "unchanged", detail="fields_dropped")
    }
    assert not director.send_get_request.await_args_list


async def test_a_light_that_cant_be_addressed_is_refused(hass):
    add_control4_light(hass, control4_entry(hass, FakeDirector()), "light.odd", unique_id="room-7")

    assert await refusal(hass, "set_attributes", {"entity_id": "light.odd", "color_temp_kelvin": 2700}) == (
        "not_addressable"
    )


async def test_refused_while_the_experimental_option_is_off(hass):
    director = dimmable_lamp(hass)
    allow_experimental(hass, on=False)

    assert await refusal(hass, "set_attributes", {**LAMP, "color_temp_kelvin": 2700}) == "experimental_off"
    assert not director.send_get_request.await_args_list


async def test_the_command_is_logged_without_the_item_id(hass, wire):
    dimmable_lamp(hass)

    await call(hass, "set_attributes", {**LAMP, "color_temp_kelvin": 2700})

    params = {"LIGHT_COLOR_TARGET_COLOR_CORRELATED_TEMPERATURE": 2700, "LIGHT_COLOR_TARGET_MODE": 1}
    assert sent(wire) == [f"light.lamp: sending director SET_COLOR_TARGET {params}"]


def test_scope():
    scope = Control4SetAttributes.scope
    assert scope.experimental
    assert scope.confirmable
    assert scope.fields == {"color_temp_kelvin": Level.EXPERIMENTAL}
    assert scope.unlisted == {"color_temp_kelvin"}


async def test_an_off_light_is_read_once(hass):
    """Off shows nothing to wait for: one capabilities read, one read-back."""
    director = dimmable_lamp(hass, on=False)

    await call(hass, "set_attributes", {**LAMP, "color_temp_kelvin": 4000})

    assert director.send_get_request.await_args_list == [CAPABILITIES, READ]


async def test_a_full_color_light_holding_an_old_target_is_not_confirmed(hass):
    """The target counts only in color temperature mode: a light that ignored the command hasn't taken it."""
    director = dimmable_lamp(hass)
    director.ignore_color = True
    director.color_mode = director.target_color_mode = 0
    director.target_kelvin = 2700

    assert await call(hass, "set_attributes", {**LAMP, "color_temp_kelvin": 2700}) == {
        "light.lamp": {**SENT, "detail": "color_temp_not_reported"}
    }


async def test_a_light_at_the_kelvin_with_no_target_reported_is_confirmed(hass):
    """With no target mode in the read, the current color temperature alone can confirm."""
    director = dimmable_lamp(hass)
    director.target_color_mode = None

    assert await call(hass, "set_attributes", {**LAMP, "color_temp_kelvin": 2700}) == {"light.lamp": CONFIRMED}


async def test_a_read_back_that_cant_be_parsed_is_sent_and_spares_the_other_lights(hass):
    """The last read-back reply holds no level: that light's write stands as sent, and the room's result stands."""
    director = dimmable_lamp(hass)
    director.ignore_color = True
    respond, reads = director.send_get_request.side_effect, []

    async def last_read_is_empty(uri):
        if "Capabilities" in uri:
            return await respond(uri)
        reads.append(uri)
        return "[]" if len(reads) == 4 else await respond(uri)

    director.send_get_request.side_effect = last_read_is_empty

    assert await call(hass, "set_attributes", {**LAMP, "color_temp_kelvin": 2700}) == {
        "light.lamp": {**SENT, "detail": "readback_failed"}
    }
    assert len(reads) == 4


async def test_capabilities_that_cant_be_read_reject_the_light_with_nothing_sent(hass):
    director = dimmable_lamp(hass)
    director.send_get_request.side_effect = None
    director.send_get_request.return_value = '[{"varName": "Navigator Dynamic Capabilities", "value": "not json"}]'

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "set_attributes", {**LAMP, "color_temp_kelvin": 2700})

    assert raised.value.translation_key == "targets_failed"
    assert not director.send_post_request.await_args_list


async def test_each_read_is_logged_with_what_the_director_reported(hass, wire):
    """The values that decide the result are in the debug log, and the Director's item id is not."""
    dimmable_lamp(hass)

    await call(hass, "set_attributes", {**LAMP, "color_temp_kelvin": 2700})

    assert "light.lamp: director reports {'Navigator Dynamic Capabilities': " in wire.text
    assert "'Target CCT': 2700" in wire.text
    assert f"/items/{ITEM}" not in wire.text


async def test_a_current_color_temperature_in_full_color_mode_doesnt_confirm(hass):
    """The current value counts only in color temperature mode, as the target does."""
    director = dimmable_lamp(hass)
    director.ignore_color = True
    director.kelvin = 2700
    director.color_mode = director.target_color_mode = 0

    assert await call(hass, "set_attributes", {**LAMP, "color_temp_kelvin": 2700}) == {
        "light.lamp": {**SENT, "detail": "color_temp_not_reported"}
    }


async def test_a_clamp_and_a_light_with_no_color_temperature_are_each_logged(hass, caplog):
    """docs/logging.md: a value changed before sending, and a skipped step, each leave a line."""
    caplog.set_level("DEBUG")
    director = dimmable_lamp(hass)

    await call(hass, "set_attributes", {**LAMP, "color_temp_kelvin": 7000})
    assert "light.lamp: 7000 K clamped to the light's 2203-6536 K" in caplog.text

    director.kelvin_span = None
    await call(hass, "set_attributes", {**LAMP, "color_temp_kelvin": 2700})
    assert "light.lamp: the light reports no color temperature; nothing sent" in caplog.text
