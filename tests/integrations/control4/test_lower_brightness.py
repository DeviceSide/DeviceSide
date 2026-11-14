"""Control4 lower_brightness: a read of the Director's own level, then one RAMP_TO_LEVEL down, to off at 0."""

import pytest

from custom_components.deviceside.integrations.control4.lower_brightness import Control4LowerBrightness
from custom_components.deviceside.integrations.control4.raise_brightness import Control4RaiseBrightness

from .conftest import HALT, LAMP, READ, SENT, dimmable_lamp, ramp
from ...conftest import call, result


@pytest.mark.parametrize(
    ("data", "sent"),
    [
        pytest.param({}, ramp(0, 3000), id="to_off"),
        pytest.param({"limit": 30}, ramp(30, 1500), id="to_a_limit"),
        pytest.param({"sweep_time": 10}, ramp(0, 6000), id="sweep_time_is_the_full_range"),
        pytest.param({"limit": 0.4}, ramp(1, 2980), id="a_limit_above_zero_never_ends_off"),
    ],
)
async def test_reads_the_level_then_ramps_down(hass, data, sent):
    director = dimmable_lamp(hass, brightness=60)

    assert await call(hass, "lower_brightness", {**LAMP, **data}) == {"light.lamp": SENT}
    assert director.send_get_request.await_args_list == [READ]
    assert director.send_post_request.await_args_list == [sent]


async def test_an_off_light_is_passed_by(hass):
    director = dimmable_lamp(hass, on=False)

    assert await call(hass, "lower_brightness", LAMP) == {"light.lamp": result("control4", "unchanged", detail="off")}
    assert not director.send_post_request.await_args_list


async def test_a_light_ramping_up_from_off_is_halted_and_lowered_not_passed_by_as_off(hass):
    """A raise from off, then a lower with no stop between: the Director still reads 0 for a ramp just begun."""
    director = dimmable_lamp(hass, on=False, halt=12)
    await call(hass, "raise_brightness", LAMP)
    director.send_post_request.reset_mock()

    director.send_get_request.reset_mock()

    assert await call(hass, "lower_brightness", LAMP) == {"light.lamp": SENT}
    assert director.send_post_request.await_args_list == [HALT, ramp(0, 600)]
    # The halt shows on the first read after it, which ends the reads.
    assert director.send_get_request.await_args_list == [READ, READ]


async def test_a_light_ramping_down_from_the_top_is_halted_and_raised_not_left_as_at_its_limit(hass):
    director = dimmable_lamp(hass, brightness=100, halt=90)
    await call(hass, "lower_brightness", LAMP)
    director.send_post_request.reset_mock()

    assert await call(hass, "raise_brightness", LAMP) == {"light.lamp": SENT}
    assert director.send_post_request.await_args_list == [HALT, ramp(100, 500)]


@pytest.mark.parametrize(("brightness", "limit"), [pytest.param(30, 30, id="at_the_limit"), (20, 30)])
async def test_nothing_left_to_lower_is_unchanged(hass, brightness, limit):
    director = dimmable_lamp(hass, brightness=brightness)

    assert await call(hass, "lower_brightness", {**LAMP, "limit": limit}) == {
        "light.lamp": result("control4", "unchanged", detail="at_limit")
    }
    assert not director.send_post_request.await_args_list


def test_scope():
    assert Control4LowerBrightness.scope.fields == Control4RaiseBrightness.scope.fields
    assert Control4LowerBrightness.scope.domains == Control4RaiseBrightness.scope.domains
