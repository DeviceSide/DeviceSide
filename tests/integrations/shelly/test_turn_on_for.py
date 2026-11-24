"""Shelly turn_on_for: one <Component>.Set with toggle_after, GetStatus read-back."""

import dataclasses
from unittest.mock import call as rpc_call

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside.core.models import LightFields
from custom_components.deviceside.core.scope import Level, verified
from custom_components.deviceside.integrations.shelly.addressing import COLOR_LABS, COMPONENTS
from custom_components.deviceside.integrations.shelly.rpc import light_params
from custom_components.deviceside.integrations.shelly.turn_on_for import ShellyTurnOnFor

from .conftest import call
from ...conftest import allow_labs, refusal
from ...fixtures.fake import add_switch_as_x
from ...fixtures.shelly import add_shelly_entity, shelly_device

CONFIRMED = {"status": "confirmed", "integration": "shelly"}


async def test_switch_one_set_then_read_back(hass, setup_production):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "switch.porch", "switch:1")

    response = await call(hass, "turn_on_for", {"entity_id": "switch.porch", "duration": 5})

    assert response == {"switch.porch": CONFIRMED}
    assert call_rpc.await_args_list == [
        rpc_call("Switch.Set", {"id": 1, "on": True, "toggle_after": 5.0}),
        rpc_call("Switch.GetStatus", {"id": 1}),
    ]


@pytest.mark.parametrize(
    ("key", "data", "expected"),
    [
        # Brightness percent to the device's whole percent, never 0; transition floored at 0.5 s, as shelly/light.py.
        ("light:0", {"brightness": 50, "transition": 0.2}, {"brightness": 50, "transition_duration": 0.5}),
        ("light:0", {"brightness": 0.4}, {"brightness": 1}),
        ("cct:0", {"brightness": 50, "transition": 1}, {"brightness": 50, "transition_duration": 1.0}),
        ("rgb:0", {"brightness": 100, "transition": 2}, {"brightness": 100, "transition_duration": 2.0}),
        ("rgbw:0", {"brightness": 25.4}, {"brightness": 25}),
    ],
)
async def test_documented_components_take_the_same_set(hass, setup_production, key, data, expected):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "light.lamp", key)

    response = await call(hass, "turn_on_for", {"entity_id": "light.lamp", "duration": 5, **data})

    assert response == {"light.lamp": CONFIRMED}
    component = COMPONENTS[key.split(":")[0]]
    assert call_rpc.await_args_list == [
        rpc_call(f"{component}.Set", {"id": 0, "on": True, "toggle_after": 5.0, **expected}),
        rpc_call(f"{component}.GetStatus", {"id": 0}),
    ]


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"color_temp_kelvin": 9000}, {"ct": 6500, "mode": "cct"}),
        ({"color_temp_kelvin": 1500}, {"ct": 2700, "mode": "cct"}),
        ({"rgb_color": [255, 0, 10]}, {"rgb": [255, 0, 10], "mode": "rgb"}),
        # As core converts them for a light with no hs or xy mode: at full value, whatever mode the bulb is in.
        ({"hs_color": [120, 100]}, {"rgb": [0, 255, 0], "mode": "rgb"}),
        ({"xy_color": [0.15, 0.06]}, {"rgb": [57, 53, 255], "mode": "rgb"}),
    ],
)
async def test_rgbcct_sets_mode_and_clamps_kelvin_to_the_entity_range(hass, setup_production, data, expected):
    entry, call_rpc = shelly_device(hass)
    kelvin_range = {"min_color_temp_kelvin": 2700, "max_color_temp_kelvin": 6500}
    add_shelly_entity(hass, entry, "light.bulb", "rgbcct:0", attributes=kelvin_range)

    response = await call(hass, "turn_on_for", {"entity_id": "light.bulb", "duration": 5, **data})

    assert response == {"light.bulb": CONFIRMED}
    assert call_rpc.await_args_list[0] == rpc_call("RGBCCT.Set", {"id": 0, "on": True, "toggle_after": 5.0, **expected})


async def test_switch_drops_light_fields(hass, setup_production):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "switch.porch", "switch:0")

    response = await call(hass, "turn_on_for", {"entity_id": "switch.porch", "duration": 5, "brightness": 10})

    # The dispatcher drops brightness for a switch domain; the timer still runs.
    assert response == {"switch.porch": {**CONFIRMED, "detail": "fields_dropped"}}
    assert call_rpc.await_args_list[0] == rpc_call("Switch.Set", {"id": 0, "on": True, "toggle_after": 5.0})


async def test_switch_as_x_light_sends_the_switch_call(hass, setup_production):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "switch.porch", "switch:0")
    add_switch_as_x(hass, "light.porch", "switch.porch")

    response = await call(hass, "turn_on_for", {"entity_id": "light.porch", "duration": 5})

    assert response == {"light.porch": CONFIRMED}
    assert call_rpc.await_args_list[0] == rpc_call("Switch.Set", {"id": 0, "on": True, "toggle_after": 5.0})


@pytest.mark.parametrize(
    ("entity_id", "key", "data"),
    [
        ("light.relay", "switch:0", {"brightness": 10}),  # relay shown as a light is on/off
        ("light.dimmer", "light:0", {"color_temp_kelvin": 3000}),
        # A CCT takes ct alone: the device's word.
        ("light.cct", "cct:0", {"rgb_color": [1, 2, 3]}),
        ("light.cct", "cct:0", {"hs_color": [30, 50]}),
    ],
)
async def test_component_fields_not_in_component_are_dropped(hass, setup_production, entity_id, key, data):
    # A field the component can't take is dropped; the timer still runs.
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, entity_id, key)

    response = await call(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5, **data})

    assert response[entity_id] == {**CONFIRMED, "detail": "fields_dropped"}
    component = COMPONENTS[key.split(":")[0]]
    assert call_rpc.await_args_list[0] == rpc_call(f"{component}.Set", {"id": 0, "on": True, "toggle_after": 5.0})


@pytest.mark.parametrize(
    ("key", "data"),
    [
        ("cct:0", {"color_temp_kelvin": 3000}),
        ("rgb:0", {"rgb_color": [1, 2, 3]}),
        ("rgb:0", {"color_temp_kelvin": 3000}),
        ("rgbw:0", {"hs_color": [30, 50]}),
        ("rgbw:0", {"xy_color": [0.3, 0.3]}),
    ],
)
async def test_color_in_labs_on_cct_rgb_and_rgbw_is_dropped_while_labs_is_off(hass, setup_production, key, data):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "light.strip", key)

    response = await call(hass, "turn_on_for", {"entity_id": "light.strip", "duration": 5, **data})

    assert response["light.strip"] == {**CONFIRMED, "detail": "fields_dropped"}
    component = COMPONENTS[key.split(":")[0]]
    assert call_rpc.await_args_list[0] == rpc_call(f"{component}.Set", {"id": 0, "on": True, "toggle_after": 5.0})


@pytest.mark.parametrize(
    ("key", "data", "expected"),
    [
        ("cct:0", {"color_temp_kelvin": 3000}, {"ct": 3000}),  # no mode: CCT.Set {ct}
        ("cct:0", {"color_temp_kelvin": 9000}, {"ct": 6500}),  # clamped to the entity's range
        ("rgb:0", {"rgb_color": [255, 0, 10]}, {"rgb": [255, 0, 10]}),
        ("rgb:0", {"hs_color": [120, 100]}, {"rgb": [0, 255, 0]}),
        ("rgb:0", {"xy_color": [0.15, 0.06]}, {"rgb": [57, 53, 255]}),
        ("rgb:0", {"color_temp_kelvin": 3000}, {"rgb": [255, 177, 110]}),
        ("rgbw:0", {"rgb_color": [255, 0, 10]}, {"rgb": [255, 0, 10], "white": 0}),
        ("rgbw:0", {"hs_color": [30, 50]}, {"rgb": [253, 126, 0], "white": 255}),
        ("rgbw:0", {"xy_color": [0.15, 0.06]}, {"rgb": [5, 0, 255], "white": 67}),
        ("rgbw:0", {"color_temp_kelvin": 3000}, {"rgb": [255, 118, 0], "white": 193}),
    ],
)
async def test_color_in_labs_is_sent_when_labs_is_on(hass, setup_production, key, data, expected):
    allow_labs(hass)
    entry, call_rpc = shelly_device(hass)
    kelvin_range = {"min_color_temp_kelvin": 2700, "max_color_temp_kelvin": 6500}
    add_shelly_entity(hass, entry, "light.strip", key, attributes=kelvin_range)

    response = await call(hass, "turn_on_for", {"entity_id": "light.strip", "duration": 5, **data})

    assert response == {"light.strip": CONFIRMED}
    component = COMPONENTS[key.split(":")[0]]
    assert call_rpc.await_args_list[0] == rpc_call(
        f"{component}.Set", {"id": 0, "on": True, "toggle_after": 5.0, **expected}
    )


@pytest.mark.parametrize(
    ("component", "light", "expected"),
    [
        ("RGB", {"rgb_color": (255, 0, 10)}, {"rgb": [255, 0, 10]}),
        ("RGB", {"color_temp_kelvin": 6500}, {"rgb": [255, 254, 250]}),
        ("RGB", {"color_temp_kelvin": 1500}, {"rgb": [255, 108, 0]}),  # unclamped, as core
        ("RGBW", {"rgb_color": (1, 2, 3)}, {"rgb": [0, 2, 3], "white": 2}),
        ("RGBW", {"rgb_color": (255, 255, 255)}, {"rgb": [0, 0, 0], "white": 255}),
        ("RGBW", {"color_temp_kelvin": 6500}, {"rgb": [5, 4, 0], "white": 255}),
        ("CCT", {"color_temp_kelvin": 3000}, {"ct": 3000}),
        ("RGBCCT", {"color_temp_kelvin": 3000}, {"ct": 3000, "mode": "cct"}),
        ("RGBCCT", {"rgb_color": (1, 2, 3)}, {"rgb": [1, 2, 3], "mode": "rgb"}),
    ],
)
def test_light_params_convert_color_per_component(component, light, expected):
    assert light_params(LightFields(**light), component, None) == expected


def test_color_labs_names_the_classes_and_fields():
    assert {name: sorted(fields) for name, fields in COLOR_LABS.items()} == {
        "RGB": ["color_temp_kelvin", "hs_color", "rgb_color", "xy_color"],
        "RGBW": ["color_temp_kelvin", "hs_color", "rgb_color", "xy_color"],
        "CCT": ["color_temp_kelvin"],
    }
    assert ShellyTurnOnFor.scope.class_labs == COLOR_LABS


async def test_capability_out_of_scope_is_refused(hass, setup_production, monkeypatch):
    monkeypatch.setattr(
        ShellyTurnOnFor,
        "scope",
        dataclasses.replace(ShellyTurnOnFor.scope, capabilities=verified("Switch"), class_labs={}),
    )
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "light.dimmer", "light:0")

    assert await refusal(hass, "turn_on_for", {"entity_id": "light.dimmer", "duration": 5}) == "not_built"
    assert not call_rpc.await_args_list


async def test_set_error_rejects_only_that_target(hass, setup_production):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "switch.porch", "switch:0")
    call_rpc.side_effect = ConnectionError("device unreachable")

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "turn_on_for", {"entity_id": "switch.porch", "duration": 5})

    assert raised.value.translation_key == "targets_failed"
    assert raised.value.translation_placeholders == {"summary": "switch.porch: error"}


@pytest.mark.parametrize(
    ("status", "detail"),
    [
        (ConnectionError("gone"), "readback_failed"),
        ({"id": 0, "output": True}, "timer_not_reported"),  # timer fields absent
        ({"id": 0, "output": False, "timer_duration": 5.0}, "timer_not_reported"),  # output not what we sent
        ({"id": 0, "output": True, "timer_duration": 3.0}, "timer_not_reported"),  # another timer's duration
        ({"id": 0, "output": True, "timer_duration": 5.02}, "timer_not_reported"),  # off by more than 0.01 s
    ],
)
async def test_inconclusive_read_back_reports_sent(hass, setup_production, status, detail):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "switch.porch", "switch:0")
    call_rpc.side_effect = [{"was_on": False}, status]

    response = await call(hass, "turn_on_for", {"entity_id": "switch.porch", "duration": 5})

    assert response == {"switch.porch": {"status": "sent", "integration": "shelly", "detail": detail}}


async def test_duration_beyond_the_limit_is_clamped(hass, setup_production):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "switch.porch", "switch:0")

    response = await call(hass, "turn_on_for", {"entity_id": "switch.porch", "duration": {"days": 8}})

    assert response == {"switch.porch": {**CONFIRMED, "clamped_to": 604800}}
    assert call_rpc.await_args_list[0].args[1]["toggle_after"] == 604800


async def test_fractional_duration_passes_through_unrounded(hass, setup_production):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "switch.porch", "switch:0")

    response = await call(hass, "turn_on_for", {"entity_id": "switch.porch", "duration": {"milliseconds": 50}})

    assert response == {"switch.porch": CONFIRMED}
    assert call_rpc.await_args_list[0].args[1]["toggle_after"] == 0.05


async def test_duration_under_50ms_is_floored_and_reported(hass, setup_production):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "switch.porch", "switch:0")

    response = await call(hass, "turn_on_for", {"entity_id": "switch.porch", "duration": {"milliseconds": 20}})

    assert response == {"switch.porch": {**CONFIRMED, "clamped_to": 0.05}}
    assert call_rpc.await_args_list[0].args[1]["toggle_after"] == 0.05


@pytest.mark.parametrize(
    ("component", "level"),
    [("Switch", Level.VERIFIED), ("RGBCCT", Level.VERIFIED), ("Light", Level.DOCUMENTED), ("RGBW", Level.DOCUMENTED)],
)
def test_component_levels(component, level):
    assert ShellyTurnOnFor.scope.level("light", (component,)) is level


def test_color_makes_an_led_controller_call_labs_and_leaves_rgbcct_verified():
    scope = ShellyTurnOnFor.scope
    assert scope.level("light", ("RGBW",), ("rgb_color",)) is Level.LABS
    assert scope.level("light", ("CCT",), ("color_temp_kelvin",)) is Level.LABS
    assert scope.level("light", ("RGBW",), ("brightness",)) is Level.DOCUMENTED
    assert scope.level("light", ("RGBCCT",), ("rgb_color",)) is Level.VERIFIED


@pytest.mark.parametrize(("transition", "sent"), [(0.2, 0.5), (3, 3), (20000, 10800)])
def test_transition_is_held_to_the_devices_bounds(transition, sent):
    assert light_params(LightFields(transition=transition), "RGBCCT", None) == {"transition_duration": sent}
