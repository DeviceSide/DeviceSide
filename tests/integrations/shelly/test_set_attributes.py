"""Shelly set_attributes: one RGBCCT.Set without `on`, GetStatus read-back."""

from unittest.mock import call as rpc_call

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.shelly.set_attributes import ShellySetAttributes

from ...conftest import call, refusal
from ...fixtures.shelly import add_shelly_entity, shelly_device

KELVIN_RANGE = {"min_color_temp_kelvin": 2700, "max_color_temp_kelvin": 6500}
BULB = {"entity_id": "light.bulb"}
CONFIRMED = {"status": "confirmed", "integration": "shelly"}


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
    respond = call_rpc.side_effect

    async def no_status(method, params):
        if method.endswith(".GetStatus"):
            raise ConnectionError("device unreachable")
        return respond(method, params)

    call_rpc.side_effect = no_status

    response = await call(hass, "set_attributes", {**BULB, "brightness": 40})

    assert response == {"light.bulb": {"status": "sent", "integration": "shelly", "detail": "readback_failed"}}


async def test_a_failed_set_fails_the_call(hass, setup_production):
    call_rpc = await bulb(hass)
    call_rpc.side_effect = ConnectionError("device unreachable")

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


async def test_brightness_limits_are_out_of_scope(hass, setup_production):
    await bulb(hass)

    assert await refusal(hass, "set_attributes", {**BULB, "min_brightness": 20}) == "fields_not_tested"


def test_the_adapter_is_experimental_with_rgbcct_verified_only():
    scope = ShellySetAttributes.scope
    assert scope.experimental
    assert dict(scope.capabilities) == {"RGBCCT": Level.VERIFIED}
