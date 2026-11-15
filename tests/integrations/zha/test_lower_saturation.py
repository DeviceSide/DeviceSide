"""ZHA lower_saturation: MoveToSaturation to the limit, or MoveToColor to the xy of the current hue at it on a light
without hue and saturation."""

import pytest

from custom_components.deviceside.integrations.zha import zcl

from .conftest import SENT, XY_ONLY, bulb, sent, xy
from ...conftest import call

pytestmark = pytest.mark.usefixtures("setup_production", "clock", "bulbs")


async def test_sends_the_end_saturation(hass, commands):
    """#411: a MoveToColor fade's stop jumped on the A60, watched; MoveToSaturation's held."""
    bulb(hass)

    response = await call(hass, "lower_saturation", {"entity_id": "light.bulb", "limit": 20, "sweep_time": 10})

    assert response == {"light.bulb": SENT}
    assert sent(commands) == [(0x0300, 0x03, {"saturation": 51, "transition_time": 40})]


async def test_a_light_without_hue_and_saturation_gets_the_end_point_at_its_hue(hass, commands):
    zcl.color_capabilities.return_value = XY_ONLY
    bulb(hass)

    await call(hass, "lower_saturation", {"entity_id": "light.bulb", "limit": 20, "sweep_time": 10})

    assert sent(commands) == [(0x0300, 0x07, {**xy(200, 20), "transition_time": 40})]


async def test_a_light_in_color_temperature_gets_the_end_point_at_its_hue(hass, commands):
    """Its own hue may be stale, so it fades from the hue Home Assistant shows."""
    bulb(hass, color_mode="color_temp")

    await call(hass, "lower_saturation", {"entity_id": "light.bulb", "limit": 20, "sweep_time": 10})

    assert sent(commands) == [(0x0300, 0x07, {**xy(200, 20), "transition_time": 40})]


async def test_lowers_to_white(hass, commands):
    bulb(hass)

    await call(hass, "lower_saturation", {"entity_id": "light.bulb", "limit": 0, "sweep_time": 10})

    assert sent(commands) == [(0x0300, 0x03, {"saturation": 0, "transition_time": 60})]
