"""Shelly lower_brightness: a GetStatus for the device's own level, then one <Component>.Set with transition_duration:
to a limit with on, or to 0 as the device's own soft off."""

from unittest.mock import call as rpc_call

import pytest

from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.shelly.lower_brightness import ShellyLowerBrightness
from custom_components.deviceside.integrations.shelly.raise_brightness import ShellyRaiseBrightness

from .conftest import BULB, SENT, call, dimmable_bulb
from ...conftest import result

READ = rpc_call("RGBCCT.GetStatus", {"id": 0})


async def test_to_zero_is_the_devices_soft_off(hass, setup_production):
    """on: false with a transition fades out and keeps the stored level for the next on (rig, 8 Nov)."""
    call_rpc = dimmable_bulb(hass, brightness=60)

    assert await call(hass, "lower_brightness", BULB) == {"light.bulb": SENT}
    assert call_rpc.await_args_list == [
        READ,
        rpc_call("RGBCCT.Set", {"id": 0, "on": False, "transition_duration": 3.0}),
    ]


async def test_to_a_limit_stays_on(hass, setup_production):
    call_rpc = dimmable_bulb(hass, brightness=60)

    assert await call(hass, "lower_brightness", {**BULB, "limit": 20}) == {"light.bulb": SENT}
    assert call_rpc.await_args_list[-1] == rpc_call(
        "RGBCCT.Set", {"id": 0, "on": True, "brightness": 20, "transition_duration": 2.0}
    )


async def test_an_off_light_is_unchanged(hass, setup_production):
    call_rpc = dimmable_bulb(hass, brightness=60, on=False)

    assert await call(hass, "lower_brightness", BULB) == {"light.bulb": result("shelly", "unchanged", detail="off")}
    assert call_rpc.await_args_list == [READ]


@pytest.mark.parametrize(("brightness", "limit"), [(20, 20), (10, 20)])
async def test_nothing_left_to_lower_is_unchanged(hass, setup_production, brightness, limit):
    call_rpc = dimmable_bulb(hass, brightness=brightness)

    response = await call(hass, "lower_brightness", {**BULB, "limit": limit})

    assert response == {"light.bulb": result("shelly", "unchanged", detail="at_limit")}
    assert call_rpc.await_args_list == [READ]


async def test_the_bottom_level_still_fades_off(hass, setup_production):
    call_rpc = dimmable_bulb(hass, brightness=1)

    assert await call(hass, "lower_brightness", BULB) == {"light.bulb": SENT}
    assert call_rpc.await_args_list[-1] == rpc_call("RGBCCT.Set", {"id": 0, "on": False, "transition_duration": 0.5})


def test_scope():
    scope = ShellyLowerBrightness.scope
    assert not scope.experimental
    assert scope.fields == {"brightness": Level.VERIFIED}
    assert scope.capabilities == ShellyRaiseBrightness.scope.capabilities
