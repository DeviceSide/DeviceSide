"""Zigbee2MQTT lower_hue: Z2M's hue_move, a cycle red to magenta to blue at a rate the bulb runs until a stop."""

import pytest

from .conftest import SENT, SET, call, commands, group, light

pytestmark = pytest.mark.usefixtures("setup_production", "clock")


async def test_a_cycle_in_the_sweep_time(hass, broker):
    entity_id = light(hass, broker)

    response = await call(hass, "lower_hue", {"entity_id": entity_id})

    assert response == {entity_id: SENT}
    assert commands(broker) == [(SET, {"hue_move": -51})]


async def test_a_group_is_one_publish_to_its_topic(hass, broker):
    room = group(hass, broker, one={"hs": (200.0, 40.0)}, two={"hs": (100.0, 80.0)})

    response = await call(hass, "lower_hue", {"entity_id": room})

    assert response == {room: SENT}
    assert commands(broker) == [("zigbee2mqtt/7/set", {"hue_move": -51})]
