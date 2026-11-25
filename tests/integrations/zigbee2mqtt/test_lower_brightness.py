"""Zigbee2MQTT lower_brightness: the end point with the time left, or a soft off at 0 %%."""

import pytest

from custom_components.deviceside.core.fields import BRIGHTNESS_FIELD
from custom_components.deviceside.integrations.zigbee2mqtt.fade import transition_cache

from .conftest import SENT, SET, bottom_target, call, commands, group, light, move_to_level
from ...conftest import result

pytestmark = pytest.mark.usefixtures("setup_production", "clock")


@pytest.mark.parametrize(
    ("data", "payload"),
    [
        pytest.param({}, {"state": "OFF", "transition": 3.0}, id="to_zero_is_a_soft_off"),
        pytest.param({"limit": 20}, {"brightness": 51, "transition": 2.0}, id="to_a_limit"),
    ],
)
async def test_publishes_the_end_point_with_the_time_left(hass, broker, data, payload):
    entity_id = light(hass, broker)

    response = await call(hass, "lower_brightness", {"entity_id": entity_id, **data})

    assert response == {entity_id: SENT}
    assert commands(broker) == [(SET, payload)]


@pytest.mark.parametrize(
    ("options", "data", "detail"),
    [
        pytest.param({"brightness": 51}, {"limit": 20}, "at_limit", id="at_the_limit"),
        pytest.param({"state": "off"}, {}, "off", id="an_off_light"),
    ],
)
async def test_nothing_left_to_move_is_unchanged(hass, broker, options, data, detail):
    entity_id = light(hass, broker, **options)

    response = await call(hass, "lower_brightness", {"entity_id": entity_id, **data})

    assert response == {entity_id: result("zigbee2mqtt", "unchanged", detail=detail)}
    assert commands(broker) == []


async def test_a_group_gets_one_publish_and_a_prediction_per_member(hass, broker, clock):
    room = group(hass, broker, one={"brightness": 255}, two={"brightness": 51})

    response = await call(hass, "lower_brightness", {"entity_id": room})

    assert response == {room: SENT}
    # From the members' mean, 60 %, to off over a 5 s sweep.
    assert commands(broker) == [("zigbee2mqtt/7/set", {"state": "OFF", "transition": 3.0})]
    cache = transition_cache(hass)
    clock.now += 1.5
    assert cache.value("light.one", BRIGHTNESS_FIELD, 0) == pytest.approx(50.0)
    assert cache.value("light.two", BRIGHTNESS_FIELD, 0) == pytest.approx(10.0)


@pytest.mark.parametrize(
    ("kind", "payload"),
    [
        pytest.param("hue_light", move_to_level(1, 30), id="hue_light"),
        pytest.param("hue_group", move_to_level(1, 30), id="all_hue_group"),
        pytest.param("aqara_light", move_to_level(1, 30), id="aqara_light"),
        pytest.param("aqara_hue_group", move_to_level(1, 30), id="aqara_and_hue_group"),
        # A standard light's bottom is level 2 (zigbee/standard_lights.py), and a group's the highest any member's.
        pytest.param("standard_light", move_to_level(2, 30), id="standard_light"),
        pytest.param("standard_hue_group", move_to_level(2, 30), id="standard_and_hue_group"),
        pytest.param("mixed_group", {"brightness": 1, "transition": 3.0}, id="hue_and_another_brand_group"),
        pytest.param("aqara_other_group", {"brightness": 1, "transition": 3.0}, id="aqara_and_another_brand_group"),
        pytest.param(
            "standard_other_group", {"brightness": 1, "transition": 3.0}, id="standard_and_another_brand_group"
        ),
        pytest.param("other_light", {"brightness": 1, "transition": 3.0}, id="another_brand"),
    ],
)
async def test_to_the_bottom_goes_raw_to_hue_aqara_and_standard_lights_alone(hass, broker, kind, payload):
    # From 60 % to 0.4 % of a 5 s sweep: 3 s, transtime 30.
    entity_id, to = bottom_target(hass, broker, kind)

    response = await call(hass, "lower_brightness", {"entity_id": entity_id, "limit": 0.4})

    assert response == {entity_id: SENT}
    assert commands(broker) == [(to, payload)]


@pytest.mark.parametrize(
    ("kind", "limit", "payload"),
    [
        # At or below a standard light's bottom, level 2: raw to 2. Above Hue's, level 1: the converter.
        # From 60 % to 0.8 % (brightness 2) of a 5 s sweep: 3 s, transtime 30.
        pytest.param("standard_light", 0.8, move_to_level(2, 30), id="standard_light"),
        pytest.param("hue_light", 0.8, {"brightness": 2, "transition": 3.0}, id="hue_light"),
        # Just above a standard light's bottom, 1.2 % (brightness 3): the converter, 2.94 s.
        pytest.param("standard_light", 1.2, {"brightness": 3, "transition": 2.9}, id="standard_above"),
    ],
)
async def test_goes_raw_at_or_below_the_bottom_level_alone(hass, broker, kind, limit, payload):
    entity_id, to = bottom_target(hass, broker, kind)

    response = await call(hass, "lower_brightness", {"entity_id": entity_id, "limit": limit})

    assert response == {entity_id: SENT}
    assert commands(broker) == [(to, payload)]


async def test_to_the_bottom_on_a_hue_group_leaves_an_off_member_off(hass, broker):
    # moveToLevel has no On/Off, so the off member ignores it: only the lit ones are lowered (core.zcl_fade).
    room = group(hass, broker, one={}, two={"state": "off"})

    response = await call(hass, "lower_brightness", {"entity_id": room, "limit": 0.4})

    assert response == {room: SENT}
    # From the lit member's 60 % to 0.4 % of a 5 s sweep: 3 s, transtime 30.
    assert commands(broker) == [("zigbee2mqtt/7/set", move_to_level(1, 30))]
