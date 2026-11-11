"""Shelly set_attributes: one RGBCCT.Set without `on`, GetStatus read-back."""

from unittest.mock import call as rpc_call

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.shelly.set_attributes import ShellySetAttributes

from ...conftest import call, refusal, result
from ...fixtures.shelly import add_shelly_entity, failing, shelly_device

KELVIN_RANGE = {"min_color_temp_kelvin": 2700, "max_color_temp_kelvin": 6500}
BULB = {"entity_id": "light.bulb"}
CONFIRMED = {"status": "confirmed", "integration": "shelly"}


def _output(call_rpc) -> bool:
    """The bulb's output as the device would report it now."""
    return call_rpc.side_effect("RGBCCT.GetStatus", {"id": 0})["output"]


async def bulb(hass, status: dict | None = None, state: str = "off"):
    entry, call_rpc = shelly_device(hass, status=status)
    add_shelly_entity(hass, entry, "light.bulb", "rgbcct:0", state=state, attributes=KELVIN_RANGE)
    return call_rpc


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"brightness": 40}, {"brightness": 40}),
        ({"brightness": 0.4}, {"brightness": 1}),
        ({"color_temp_kelvin": 3000}, {"ct": 3000, "mode": "cct"}),
        ({"color_temp_kelvin": 9000}, {"ct": 6500, "mode": "cct"}),  # clamped to the entity's range
        ({"brightness": 60, "rgb_color": [255, 0, 10]}, {"brightness": 60, "rgb": [255, 0, 10], "mode": "rgb"}),
        ({"hs_color": [120, 100]}, {"rgb": [0, 255, 0], "mode": "rgb"}),
        ({"xy_color": [0.15, 0.06]}, {"rgb": [57, 53, 255], "mode": "rgb"}),
    ],
)
async def test_one_set_without_on_then_read_back(hass, setup_production, data, expected):
    call_rpc = await bulb(hass)

    response = await call(hass, "set_attributes", {**BULB, **data})

    assert response == {"light.bulb": CONFIRMED}
    assert call_rpc.await_args_list == [
        rpc_call("RGBCCT.Set", {"id": 0, **expected}),
        rpc_call("RGBCCT.GetStatus", {"id": 0}),
    ]


async def test_a_bulb_that_is_off_stays_off(hass, setup_production):
    call_rpc = await bulb(hass, status={"output": False})

    await call(hass, "set_attributes", {**BULB, "brightness": 40})

    assert all("on" not in c.args[1] for c in call_rpc.await_args_list)
    assert _output(call_rpc) is False


async def test_values_the_device_did_not_keep_are_rejected(hass, setup_production):
    call_rpc = await bulb(hass)
    respond = call_rpc.side_effect

    async def ignoring_set(method, params):
        return None if method == "RGBCCT.Set" else respond(method, params)

    call_rpc.side_effect = ignoring_set

    with pytest.raises(HomeAssistantError, match="light.bulb: not_stored"):
        await call(hass, "set_attributes", {**BULB, "color_temp_kelvin": 3000})


async def test_a_mode_that_did_not_switch_is_rejected(hass, setup_production):
    call_rpc = await bulb(hass, status={"mode": "cct"})
    respond = call_rpc.side_effect

    async def keeping_mode(method, params):
        return respond(method, {k: v for k, v in params.items() if k != "mode"} if method == "RGBCCT.Set" else params)

    call_rpc.side_effect = keeping_mode

    with pytest.raises(HomeAssistantError, match="light.bulb: not_stored"):
        await call(hass, "set_attributes", {**BULB, "rgb_color": [1, 2, 3]})


async def test_a_failed_read_back_still_reports_sent(hass, setup_production):
    call_rpc = await bulb(hass)
    failing(call_rpc, "GetStatus")

    response = await call(hass, "set_attributes", {**BULB, "brightness": 40})

    assert response == {"light.bulb": {"status": "sent", "integration": "shelly", "detail": "readback_failed"}}


async def test_a_failed_set_fails_the_call(hass, setup_production):
    call_rpc = await bulb(hass)
    failing(call_rpc, "Set")

    with pytest.raises(HomeAssistantError):
        await call(hass, "set_attributes", {**BULB, "brightness": 40})


@pytest.mark.parametrize("key", ["light:0", "cct:0", "rgb:0", "rgbw:0", "switch:0"])
async def test_other_components_are_refused(hass, setup_production, key):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "light.other", key)

    assert await refusal(hass, "set_attributes", {"entity_id": "light.other", "brightness": 40}) == (
        "capability_not_tested"
    )
    assert not call_rpc.await_args_list


async def test_gen1_is_refused(hass, setup_production):
    entry, call_rpc = shelly_device(hass, gen1=True)
    add_shelly_entity(hass, entry, "light.old", "rgbcct:0")

    assert await refusal(hass, "set_attributes", {"entity_id": "light.old", "brightness": 40}) == "gen1_unsupported"


@pytest.mark.parametrize(
    ("stored", "data", "expected"),
    [
        (10, {"min_brightness": 30}, 30),
        (90, {"max_brightness": 60}, 60),
        (50, {"min_brightness": 30, "max_brightness": 60}, None),  # within the limits: nothing sent
        (10, {"min_brightness": 0.4}, None),
        (10, {"min_brightness": 30, "brightness": 20}, 20),  # an explicit brightness wins
    ],
)
async def test_limits_clamp_the_stored_brightness(hass, setup_production, stored, data, expected):
    call_rpc = await bulb(hass, status={"brightness": stored})

    response = await call(hass, "set_attributes", {**BULB, **data})

    if expected is None:
        assert response == {"light.bulb": result("shelly", "unchanged", detail="within_limits")}
        assert all(".Set" not in c.args[0] for c in call_rpc.await_args_list)
        return
    assert response == {"light.bulb": CONFIRMED}
    assert rpc_call("RGBCCT.Set", {"id": 0, "brightness": expected}) in call_rpc.await_args_list


async def test_limits_work_while_the_bulb_is_off(hass, setup_production):
    call_rpc = await bulb(hass, status={"output": False, "brightness": 10})

    await call(hass, "set_attributes", {**BULB, "min_brightness": 30})

    assert rpc_call("RGBCCT.Set", {"id": 0, "brightness": 30}) in call_rpc.await_args_list
    assert all("on" not in c.args[1] for c in call_rpc.await_args_list)
    assert _output(call_rpc) is False


async def test_limits_with_a_color_still_send_the_color(hass, setup_production):
    call_rpc = await bulb(hass, status={"brightness": 50})

    await call(hass, "set_attributes", {**BULB, "min_brightness": 30, "color_temp_kelvin": 3000})

    assert rpc_call("RGBCCT.Set", {"id": 0, "ct": 3000, "mode": "cct"}) in call_rpc.await_args_list


def test_rgbcct_is_the_only_capability_in_scope():
    assert dict(ShellySetAttributes.scope.capabilities) == {"RGBCCT": Level.VERIFIED}
