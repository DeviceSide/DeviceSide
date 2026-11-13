"""Control4 get_attributes: one read of the Director's variables, the brightness it holds and the color temperature."""

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.control4.get_attributes import Control4GetAttributes

from .conftest import LAMP, dimmable_lamp
from ...conftest import allow_experimental, call, refusal
from ...fixtures.control4 import FakeDirector, add_control4_light, control4_entry, failing


async def test_reads_brightness_and_color_temperature_in_one_request(hass):
    director = dimmable_lamp(hass, brightness=40)

    assert await call(hass, "get_attributes", LAMP) == {"light.lamp": {"brightness": 40.0, "color_temp_kelvin": 3200}}
    assert director.send_get_request.await_count == 1
    assert not director.send_post_request.await_args_list


async def test_brightness_is_the_level_the_director_holds(hass):
    """Mid-ramp the Director reads fractions (Tested behavior); the row carries the level as it holds it."""
    dimmable_lamp(hass, brightness=77.44)

    assert (await call(hass, "get_attributes", LAMP))["light.lamp"]["brightness"] == 77.44


async def test_an_off_light_reports_its_color_temperature_alone(hass):
    """Off reads a level of 0, which is not a level kept for the next on, so brightness is left out."""
    dimmable_lamp(hass, on=False)

    assert await call(hass, "get_attributes", LAMP) == {"light.lamp": {"color_temp_kelvin": 3200}}


async def test_a_light_in_full_color_mode_reports_no_color_temperature(hass):
    director = dimmable_lamp(hass, brightness=40)
    director.color_mode = 0

    assert await call(hass, "get_attributes", LAMP) == {"light.lamp": {"brightness": 40.0}}


async def test_a_light_on_an_older_driver_reports_brightness_alone(hass):
    dimmable_lamp(hass, brightness=40, legacy=True)

    assert await call(hass, "get_attributes", LAMP) == {"light.lamp": {"brightness": 40.0}}


async def test_an_off_light_with_nothing_to_report_returns_an_empty_row(hass):
    dimmable_lamp(hass, on=False, legacy=True)

    assert await call(hass, "get_attributes", LAMP) == {"light.lamp": {}}


async def test_an_on_off_light_that_reports_no_level_returns_an_empty_row(hass):
    """LIGHT_STATE alone: no brightness to give, and a room that holds one still gets its other rows."""
    director = dimmable_lamp(hass)
    director.on_off = True

    assert await call(hass, "get_attributes", LAMP) == {"light.lamp": {}}


async def test_a_read_that_finds_no_variables_rejects_the_target(hass):
    director = dimmable_lamp(hass)
    director.send_get_request.side_effect = None
    director.send_get_request.return_value = "[]"

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "get_attributes", LAMP)

    assert raised.value.translation_key == "targets_failed"


async def test_values_reported_as_text_are_read_as_numbers(hass):
    director = dimmable_lamp(hass, brightness=40)
    director.text = True

    assert await call(hass, "get_attributes", LAMP) == {"light.lamp": {"brightness": 40.0, "color_temp_kelvin": 3200}}


async def test_a_director_error_rejects_the_target(hass):
    failing(dimmable_lamp(hass), "send_get_request")

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "get_attributes", LAMP)

    assert raised.value.translation_key == "targets_failed"


async def test_a_light_that_cant_be_addressed_is_refused(hass):
    add_control4_light(hass, control4_entry(hass, FakeDirector()), "light.odd", unique_id="room-7")

    assert await refusal(hass, "get_attributes", {"entity_id": "light.odd"}) == "not_addressable"


async def test_refused_while_the_experimental_option_is_off(hass):
    director = dimmable_lamp(hass)
    allow_experimental(hass, on=False)

    assert await refusal(hass, "get_attributes", LAMP) == "experimental_off"
    assert not director.send_get_request.await_args_list


def test_scope():
    scope = Control4GetAttributes.scope
    assert scope.experimental
    assert scope.confirmable
    assert scope.domains == {"light": Level.EXPERIMENTAL}


async def test_the_read_is_logged_with_what_the_director_reported(hass, wire):
    dimmable_lamp(hass, brightness=40)

    await call(hass, "get_attributes", LAMP)

    assert "light.lamp: director reports {'Brightness Percent': 40.0" in wire.text
