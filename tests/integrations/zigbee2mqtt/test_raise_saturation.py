"""Zigbee2MQTT raise_saturation: a color with the end saturation and no hue (MoveToSaturation), and its color brought
in line."""

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside.core.transition import SATURATION
from custom_components.deviceside.integrations.zigbee2mqtt.fade import hue_moves, transition_cache

from .conftest import GET, SENT, SET, call, commands, group, light
from ...conftest import advance, wall_clock_now

pytestmark = pytest.mark.usefixtures("setup_production", "clock")


@pytest.mark.parametrize(
    ("data", "payload"),
    [
        pytest.param({}, {"color": {"saturation": 100.0}, "transition": 2.0}, id="without_a_hue"),
        pytest.param(
            {"limit": 80, "sweep_time": 10},
            {"color": {"saturation": 80.0}, "transition": 2.0},
            id="to_a_limit",
        ),
    ],
)
async def test_publishes_the_end_point_with_the_time_left(hass, broker, data, payload):
    entity_id = light(hass, broker)

    response = await call(hass, "raise_saturation", {"entity_id": entity_id, **data})

    assert response == {entity_id: SENT}
    assert commands(broker) == [(SET, payload)]


async def test_a_fade_longer_than_a_zcl_transition_is_reported_clamped(hass, broker):
    entity_id = light(hass, broker)

    response = await call(hass, "raise_saturation", {"entity_id": entity_id, "sweep_time": 100_000})

    assert response == {entity_id: {**SENT, "clamped_to": 16383.5}}
    assert commands(broker)[0][1]["transition"] == 6553.4


async def test_a_group_records_each_lit_member(hass, broker, clock):
    room = group(hass, broker, one={"hs": (200.0, 40.0)}, two={"hs": (200.0, 80.0)})

    await call(hass, "raise_saturation", {"entity_id": room})

    payload = {"color": {"saturation": 100.0}, "transition": 2.0}
    assert commands(broker) == [("zigbee2mqtt/7/set", payload)]
    cache = transition_cache(hass)
    assert cache.value("light.one", SATURATION, 0) == 40.0
    assert cache.value("light.two", SATURATION, 0) == 80.0


async def test_a_group_at_different_hues_is_one_publish_without_a_hue(hass, broker):
    room = group(hass, broker, one={"hs": (200.0, 40.0)}, two={"hs": (100.0, 40.0)})

    await call(hass, "raise_saturation", {"entity_id": room})

    assert commands(broker) == [("zigbee2mqtt/7/set", {"color": {"saturation": 100.0}, "transition": 3.0})]


async def test_a_light_in_color_temperature_fades_at_its_current_hue(hass, broker):
    entity_id = light(hass, broker, color_mode="color_temp")

    await call(hass, "raise_saturation", {"entity_id": entity_id})

    assert commands(broker) == [(SET, {"color": {"hue": 200.0, "saturation": 100.0}, "transition": 2.0})]


async def test_one_member_in_color_temperature_sends_the_group_the_hue_too(hass, broker):
    room = group(hass, broker, one={"hs": (200.0, 40.0)}, two={"hs": (200.0, 40.0), "color_mode": "color_temp"})

    await call(hass, "raise_saturation", {"entity_id": room})

    payload = {"color": {"hue": 200.0, "saturation": 100.0}, "transition": 3.0}
    assert commands(broker) == [("zigbee2mqtt/7/set", payload)]


async def test_the_color_is_brought_in_line_at_its_end(hass, broker):
    entity_id = light(hass, broker, color={"colorMode": 1})
    start = wall_clock_now()
    await call(hass, "raise_saturation", {"entity_id": entity_id})

    await advance(hass, start, 3.5)
    assert commands(broker)[1:] == [(GET, {"color": ""})]


async def test_a_failed_publish_leaves_the_hue_cycle_running(hass, broker):
    entity_id = light(hass, broker)
    hue_moves(hass).add(entity_id)

    def refuse(service):
        raise RuntimeError("broker gone")

    hass.services.async_register("mqtt", "publish", refuse)
    with pytest.raises(HomeAssistantError):
        await call(hass, "raise_saturation", {"entity_id": entity_id})

    assert hue_moves(hass) == {entity_id}
