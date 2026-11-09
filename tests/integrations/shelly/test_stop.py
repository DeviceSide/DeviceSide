"""Shelly stop: DimStop at once, then a GetStatus that reads where the fade halted."""

from unittest.mock import call as rpc_call

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside.integrations.shelly.raise_brightness import ShellyRaiseBrightness
from custom_components.deviceside.integrations.shelly.stop import ShellyStop

from .conftest import BULB, CONFIRMED, SENT, dimmable_bulb, unchanged
from ...conftest import allow_experimental, call, refusal
from ...fixtures.shelly import OTHER_LIGHT_COMPONENTS, add_shelly_entity, failing, shelly_device

STOP = rpc_call("RGBCCT.DimStop", {"id": 0})
READ = rpc_call("RGBCCT.GetStatus", {"id": 0})


async def test_a_fade_halts_and_the_halt_is_read_back(hass, setup_production):
    call_rpc = dimmable_bulb(hass, brightness=40, halt={"brightness": 55})
    await call(hass, "raise_brightness", BULB)
    call_rpc.reset_mock()

    assert await call(hass, "stop", BULB) == {"light.bulb": CONFIRMED}
    assert call_rpc.await_args_list == [STOP, READ]


async def test_a_lit_light_with_no_fade_is_confirmed(hass, setup_production):
    """DimStop with no fade running changes nothing (rig, 8 Nov), so it goes first, with no read before it."""
    call_rpc = dimmable_bulb(hass, brightness=40)

    assert await call(hass, "stop", BULB) == {"light.bulb": CONFIRMED}
    assert call_rpc.await_args_list == [STOP, READ]


async def test_an_off_light_is_unchanged(hass, setup_production):
    dimmable_bulb(hass, on=False)

    assert await call(hass, "stop", BULB) == {"light.bulb": unchanged("off")}


async def test_a_halted_soft_off_stays_on(hass, setup_production):
    call_rpc = dimmable_bulb(hass, brightness=60, halt={"brightness": 39})
    await call(hass, "lower_brightness", BULB)

    assert await call(hass, "stop", BULB) == {"light.bulb": CONFIRMED}
    status = call_rpc.side_effect("RGBCCT.GetStatus", {"id": 0})
    assert (status["output"], status["brightness"]) == (True, 39)


async def test_raise_stop_raise_continues_from_the_halt(hass, setup_production):
    call_rpc = dimmable_bulb(hass, brightness=40, halt={"brightness": 55})
    await call(hass, "raise_brightness", BULB)
    await call(hass, "stop", BULB)

    await call(hass, "raise_brightness", BULB)

    assert call_rpc.await_args_list[-1] == rpc_call(
        "RGBCCT.Set", {"id": 0, "on": True, "brightness": 100, "transition_duration": 2.25}
    )


async def test_an_empty_transition_is_not_a_fade(hass, setup_production):
    call_rpc = dimmable_bulb(hass)
    respond = call_rpc.side_effect

    async def idle_with_null_transition(method, params):
        status = respond(method, params)
        return {**status, "transition": None} if method.endswith(".GetStatus") else status

    call_rpc.side_effect = idle_with_null_transition

    assert await call(hass, "stop", BULB) == {"light.bulb": CONFIRMED}


async def test_a_fade_still_running_after_the_stop_is_only_sent(hass, setup_production):
    """A device that ignored the DimStop must not read as confirmed."""
    call_rpc = dimmable_bulb(hass, brightness=40)
    await call(hass, "raise_brightness", BULB)
    respond = call_rpc.side_effect

    async def ignoring_stop(method, params):
        return None if method.endswith(".DimStop") else respond(method, params)

    call_rpc.side_effect = ignoring_stop

    assert await call(hass, "stop", BULB) == {"light.bulb": {**SENT, "detail": "still_fading"}}


async def test_a_failed_read_back_is_sent(hass, setup_production):
    failing(dimmable_bulb(hass), "GetStatus")

    assert await call(hass, "stop", BULB) == {"light.bulb": {**SENT, "detail": "readback_failed"}}


async def test_a_dimstop_error_rejects_the_target(hass, setup_production):
    call_rpc = dimmable_bulb(hass)
    call_rpc.side_effect = ConnectionError("device unreachable")

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "stop", BULB)

    assert raised.value.translation_key == "targets_failed"


async def test_a_relay_shown_as_a_light_is_not_dimmable(hass, setup_production):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(
        hass, entry, "light.relay", "switch:0", state="on", attributes={"supported_color_modes": ["onoff"]}
    )

    assert await refusal(hass, "stop", {"entity_id": "light.relay"}) == "not_dimmable"
    assert not call_rpc.await_args_list


async def test_gen1_is_refused(hass, setup_production):
    gen1, _ = shelly_device(hass, gen1=True, mac="112233445566")
    add_shelly_entity(hass, gen1, "light.old_bulb", "light_0", state="on")

    assert await refusal(hass, "stop", {"entity_id": "light.old_bulb"}) == "gen1_unsupported"


@pytest.mark.parametrize(("key", "component"), OTHER_LIGHT_COMPONENTS)
async def test_other_light_components_are_experimental(hass, setup_production, key, component):
    entry, call_rpc = shelly_device(hass, status={"output": True, "brightness": 40})
    add_shelly_entity(hass, entry, "light.lamp", key, state="on")

    assert await refusal(hass, "stop", {"entity_id": "light.lamp"}) == "experimental_off"
    assert not call_rpc.await_args_list

    allow_experimental(hass)
    assert await call(hass, "stop", {"entity_id": "light.lamp"}) == {"light.lamp": CONFIRMED}
    assert call_rpc.await_args_list == [
        rpc_call(f"{component}.DimStop", {"id": 0}),
        rpc_call(f"{component}.GetStatus", {"id": 0}),
    ]


def test_scope():
    scope = ShellyStop.scope
    assert not scope.experimental
    assert scope.confirmable
    assert scope.capabilities == ShellyRaiseBrightness.scope.capabilities
