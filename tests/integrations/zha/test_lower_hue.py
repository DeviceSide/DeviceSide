"""ZHA lower_hue: EnhancedMoveHue down, a cycle at a rate the bulb runs until a stop."""

import pytest

from custom_components.deviceside.integrations.zha import zcl

from .conftest import SENT, bulb, sent, unchanged
from ...conftest import call

pytestmark = pytest.mark.usefixtures("setup_production", "clock", "bulbs")


async def test_a_cycle_in_the_sweep_time(hass, commands):
    bulb(hass)

    assert await call(hass, "lower_hue", {"entity_id": "light.bulb", "sweep_time": 10}) == {"light.bulb": SENT}
    assert sent(commands) == [(0x0300, 0x41, {"move_mode": 3, "rate": 6554})]


async def test_an_off_light_is_unchanged(hass, commands):
    bulb(hass, state="off")

    assert await call(hass, "lower_hue", {"entity_id": "light.bulb"}) == {"light.bulb": unchanged("off")}
    assert not commands


async def test_dropped_without_enhanced_hue(hass, commands):
    zcl.enhanced_hue.return_value = False
    bulb(hass)

    assert await call(hass, "lower_hue", {"entity_id": "light.bulb"}) == {"light.bulb": unchanged("fields_dropped")}
    assert not commands
