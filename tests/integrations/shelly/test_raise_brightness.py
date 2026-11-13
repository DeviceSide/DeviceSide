"""Shelly raise_brightness: a GetStatus for the device's own level, then one <Component>.Set with
transition_duration for the distance left."""

from unittest.mock import call as rpc_call

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.shelly.raise_brightness import ShellyRaiseBrightness

from .conftest import BULB, SENT, dimmable_bulb
from ...conftest import allow_experimental, call, refusal, result
from ...fixtures.shelly import OTHER_LIGHT_COMPONENTS, add_shelly_entity, failing, shelly_device

READ = rpc_call("RGBCCT.GetStatus", {"id": 0})


def fade(brightness: int, duration: float):
    return rpc_call("RGBCCT.Set", {"id": 0, "on": True, "brightness": brightness, "transition_duration": duration})


@pytest.mark.parametrize(
    ("data", "sent"),
    [
        pytest.param({}, fade(100, 3.0), id="to_the_top"),
        pytest.param({"limit": 70}, fade(70, 1.5), id="to_a_limit"),
        pytest.param({"sweep_time": 10}, fade(100, 6.0), id="sweep_time_is_the_full_range"),
        pytest.param({"limit": 70.4}, fade(70, 1.52), id="limit_to_a_whole_percent"),
    ],
)
async def test_reads_the_level_then_sends_the_end_point_with_a_transition(hass, setup_production, data, sent):
    call_rpc = dimmable_bulb(hass, brightness=40)

    assert await call(hass, "raise_brightness", {**BULB, **data}) == {"light.bulb": SENT}
    assert call_rpc.await_args_list == [READ, sent]


async def test_from_off_fades_in_from_the_bottom(hass, setup_production):
    """The device fades in from 1 %, not its stored level, so the whole range is the distance (rig, 8 Nov)."""
    call_rpc = dimmable_bulb(hass, brightness=60, on=False)

    assert await call(hass, "raise_brightness", BULB) == {"light.bulb": SENT}
    assert call_rpc.await_args_list == [READ, fade(100, 5.0)]


@pytest.mark.parametrize(
    ("brightness", "limit"),
    [pytest.param(100, None, id="at_the_top"), pytest.param(70, 70, id="at_the_limit"), (80, 70)],
)
async def test_nothing_left_to_raise_is_unchanged(hass, setup_production, brightness, limit):
    call_rpc = dimmable_bulb(hass, brightness=brightness)
    data = {} if limit is None else {"limit": limit}

    assert await call(hass, "raise_brightness", {**BULB, **data}) == {
        "light.bulb": result("shelly", "unchanged", detail="at_limit")
    }
    assert call_rpc.await_args_list == [READ]


async def test_a_short_fade_takes_the_devices_shortest(hass, setup_production):
    call_rpc = dimmable_bulb(hass, brightness=95)

    assert await call(hass, "raise_brightness", BULB) == {"light.bulb": SENT}
    assert call_rpc.await_args_list[-1] == fade(100, 0.5)


async def test_a_sweep_time_faster_than_the_device_is_clamped(hass, setup_production):
    call_rpc = dimmable_bulb(hass, brightness=0, on=False)

    response = await call(hass, "raise_brightness", {**BULB, "sweep_time": 0.2})

    assert response == {"light.bulb": {**SENT, "clamped_to": 0.5}}
    assert call_rpc.await_args_list[-1] == fade(100, 0.5)


async def test_a_relay_shown_as_a_light_drops_brightness(hass, setup_production):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(
        hass, entry, "light.relay", "switch:0", state="on", attributes={"supported_color_modes": ["onoff"]}
    )

    assert await call(hass, "raise_brightness", {"entity_id": "light.relay"}) == {
        "light.relay": result("shelly", "unchanged", detail="fields_dropped")
    }
    assert not call_rpc.await_args_list


@pytest.mark.parametrize(("key", "component"), OTHER_LIGHT_COMPONENTS)
async def test_other_light_components_are_experimental(hass, setup_production, key, component):
    """Only RGBCCT is rig-proven: DimStop halting a timed fade is documented for none of them. The rest take the
    same calls, addressed to their own component."""
    entry, call_rpc = shelly_device(hass, status={"output": True, "brightness": 40})
    add_shelly_entity(hass, entry, "light.lamp", key, state="on")

    assert await refusal(hass, "raise_brightness", {"entity_id": "light.lamp"}) == "experimental_off"
    assert not call_rpc.await_args_list

    allow_experimental(hass)
    assert await call(hass, "raise_brightness", {"entity_id": "light.lamp"}) == {"light.lamp": SENT}
    assert call_rpc.await_args_list == [
        rpc_call(f"{component}.GetStatus", {"id": 0}),
        rpc_call(f"{component}.Set", {"id": 0, "on": True, "brightness": 100, "transition_duration": 3.0}),
    ]


@pytest.mark.parametrize("verb", ["GetStatus", "Set"])
async def test_a_device_error_rejects_the_target(hass, setup_production, verb):
    failing(dimmable_bulb(hass), verb)

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "raise_brightness", BULB)

    assert raised.value.translation_key == "targets_failed"
    assert raised.value.translation_placeholders == {"summary": "light.bulb: error"}


@pytest.mark.parametrize(
    ("component", "level"),
    [("RGBCCT", Level.VERIFIED), ("Switch", None), *((c, Level.EXPERIMENTAL) for _, c in OTHER_LIGHT_COMPONENTS)],
)
def test_scope(component, level):
    scope = ShellyRaiseBrightness.scope
    assert not scope.experimental
    assert scope.fields == {"brightness": Level.VERIFIED}
    assert scope.capabilities.get(component) is level
