"""Shelly set_attributes: one RGBCCT.Set without `on`, GetStatus read-back."""

import logging
from unittest.mock import call as rpc_call

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.shelly.addressing import COMPONENTS
from custom_components.deviceside.integrations.shelly.set_attributes import ShellySetAttributes

from .conftest import call
from ...conftest import allow_labs, refusal, result
from ...fixtures.shelly import MAC, add_shelly_entity, failing, shelly_device

KELVIN_RANGE = {"min_color_temp_kelvin": 2700, "max_color_temp_kelvin": 6500}
BULB = {"entity_id": "light.bulb"}
CONFIRMED = {"status": "confirmed", "integration": "shelly"}
CONFIRMED_DROPPED = result("shelly", "confirmed", detail="fields_dropped")
UNCHANGED_DROPPED = result("shelly", "unchanged", detail="fields_dropped")


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


async def test_a_relay_is_not_built(hass, setup_production):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "light.other", "switch:0")

    assert await refusal(hass, "set_attributes", {"entity_id": "light.other", "brightness": 40}) == "not_built"
    assert not call_rpc.await_args_list


@pytest.mark.parametrize(
    ("key", "component"), [("light:0", "Light"), ("cct:0", "CCT"), ("rgb:0", "RGB"), ("rgbw:0", "RGBW")]
)
async def test_other_light_components_are_documented(hass, setup_production, key, component):
    entry, call_rpc = shelly_device(hass, status={"output": False, "brightness": 40})
    add_shelly_entity(hass, entry, "light.other", key, attributes={"supported_color_modes": ["brightness"]})
    data = {"entity_id": "light.other", "brightness": 40}

    assert await call(hass, "set_attributes", data) == {"light.other": CONFIRMED}
    assert rpc_call(f"{component}.Set", {"id": 0, "brightness": 40}) in call_rpc.await_args_list


@pytest.mark.parametrize(
    ("key", "data", "sent", "expected"),
    [
        ("cct:0", {"color_temp_kelvin": 3000, "brightness": 40}, {"id": 0, "brightness": 40}, CONFIRMED_DROPPED),
        ("rgb:0", {"rgb_color": [255, 0, 0], "brightness": 40}, {"id": 0, "brightness": 40}, CONFIRMED_DROPPED),
        ("cct:0", {"color_temp_kelvin": 3000}, None, UNCHANGED_DROPPED),
    ],
)
async def test_color_and_ct_in_labs_are_dropped_on_cct_rgb_and_rgbw_while_labs_is_off(
    hass, setup_production, key, data, sent, expected
):
    entry, call_rpc = shelly_device(hass, status={"output": False, "brightness": 40})
    add_shelly_entity(hass, entry, "light.other", key, attributes={"supported_color_modes": ["color_temp", "rgb"]})

    assert await call(hass, "set_attributes", {"entity_id": "light.other", **data}) == {"light.other": expected}
    sets = [c for c in call_rpc.await_args_list if ".Set" in c.args[0]]
    assert sets == ([] if sent is None else [rpc_call(f"{key[:-2].upper()}.Set", sent)])


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


@pytest.mark.parametrize(
    ("key", "data", "sent"),
    [
        ("cct:0", {"color_temp_kelvin": 3000, "brightness": 40}, {"brightness": 40, "ct": 3000}),
        ("rgb:0", {"rgb_color": [255, 0, 10]}, {"rgb": [255, 0, 10]}),
        ("rgb:0", {"hs_color": [120, 100]}, {"rgb": [0, 255, 0]}),
        ("rgb:0", {"color_temp_kelvin": 3000}, {"rgb": [255, 177, 110]}),
        ("rgbw:0", {"rgb_color": [255, 0, 10], "brightness": 60}, {"brightness": 60, "rgb": [255, 0, 10], "white": 0}),
        ("rgbw:0", {"xy_color": [0.15, 0.06]}, {"rgb": [5, 0, 255], "white": 67}),
        ("rgbw:0", {"color_temp_kelvin": 3000}, {"rgb": [255, 118, 0], "white": 193}),
    ],
)
async def test_color_and_ct_in_labs_are_sent_and_read_back_when_labs_is_on(hass, setup_production, key, data, sent):
    allow_labs(hass)
    entry, call_rpc = shelly_device(hass, status={"output": False})
    add_shelly_entity(hass, entry, "light.strip", key, attributes=KELVIN_RANGE)
    component = COMPONENTS[key.split(":")[0]]

    response = await call(hass, "set_attributes", {"entity_id": "light.strip", **data})

    assert response == {"light.strip": CONFIRMED}
    assert call_rpc.await_args_list == [
        rpc_call(f"{component}.Set", {"id": 0, **sent}),
        rpc_call(f"{component}.GetStatus", {"id": 0}),
    ]


@pytest.mark.parametrize(
    ("key", "data", "kept"),
    [
        ("rgb:0", {"rgb_color": [255, 0, 10]}, {"rgb": [250, 0, 10]}),
        ("rgbw:0", {"rgb_color": [255, 0, 10]}, {"rgb": [255, 0, 10], "white": 5}),
        ("rgbw:0", {"rgb_color": [255, 0, 10]}, {"rgb": [255, 0, 12], "white": 0}),
        ("cct:0", {"color_temp_kelvin": 3000}, {"ct": 3100}),
    ],
)
async def test_a_color_or_ct_the_device_kept_differently_is_rejected_and_logged(
    hass, setup_production, caplog, key, data, kept
):
    allow_labs(hass)
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "light.strip", key, attributes=KELVIN_RANGE)
    respond = call_rpc.side_effect

    async def keeping_other(method, params):
        return respond(method, {**params, **kept} if method.endswith(".Set") else params)

    call_rpc.side_effect = keeping_other
    caplog.set_level(logging.DEBUG)

    with pytest.raises(HomeAssistantError, match="light.strip: not_stored"):
        await call(hass, "set_attributes", {"entity_id": "light.strip", **data})

    line = next(r.getMessage() for r in caplog.records if "not stored" in r.getMessage())
    assert line.startswith("light.strip: not stored: sent ")
    assert str(next(iter(kept.values()))) in line
    assert MAC not in caplog.text


async def test_the_rgb_an_rgbcct_reads_back_is_still_not_compared(hass, setup_production):
    call_rpc = await bulb(hass)
    respond = call_rpc.side_effect

    async def rounding(method, params):
        return respond(method, {**params, "rgb": [250, 0, 10]} if method == "RGBCCT.Set" else params)

    call_rpc.side_effect = rounding

    response = await call(hass, "set_attributes", {**BULB, "rgb_color": [255, 0, 10]})

    assert response == {"light.bulb": CONFIRMED}


def test_color_labs_is_set_on_the_scope():
    colors = frozenset({"color_temp_kelvin", "hs_color", "rgb_color", "xy_color"})
    assert ShellySetAttributes.scope.class_labs == {
        "RGB": colors,
        "RGBW": colors,
        "CCT": frozenset({"color_temp_kelvin"}),
    }


def test_rgbcct_is_verified_and_the_other_light_components_documented():
    assert dict(ShellySetAttributes.scope.capabilities) == {
        "RGBCCT": Level.VERIFIED,
        **dict.fromkeys(("Light", "CCT", "RGB", "RGBW"), Level.DOCUMENTED),
    }
