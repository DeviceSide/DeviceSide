"""Zigbee2MQTT lower_saturation: a color with the end saturation and no hue (MoveToSaturation)."""

import pytest

from .conftest import SENT, SET, call, commands, group, light
from ...conftest import result

pytestmark = pytest.mark.usefixtures("setup_production", "clock")


@pytest.mark.parametrize(
    ("data", "payload"),
    [
        pytest.param({}, {"color": {"saturation": 0.0}, "transition": 3.0}, id="to_white"),
        pytest.param(
            {"limit": 20, "sweep_time": 10},
            {"color": {"saturation": 20.0}, "transition": 4.0},
            id="to_a_limit",
        ),
    ],
)
async def test_publishes_the_end_point_with_the_time_left(hass, broker, data, payload):
    entity_id = light(hass, broker)

    response = await call(hass, "lower_saturation", {"entity_id": entity_id, **data})

    assert response == {entity_id: SENT}
    assert commands(broker) == [(SET, payload)]


async def test_at_the_limit_is_unchanged(hass, broker):
    entity_id = light(hass, broker, hs=(200.0, 20.0))

    response = await call(hass, "lower_saturation", {"entity_id": entity_id, "limit": 20})

    assert response == {entity_id: result("zigbee2mqtt", "unchanged", detail="at_limit")}
    assert commands(broker) == []


async def test_a_group_is_one_publish_timed_from_its_members_mean(hass, broker):
    room = group(hass, broker, one={"hs": (200.0, 40.0)}, two={"hs": (200.0, 80.0)})

    response = await call(hass, "lower_saturation", {"entity_id": room})

    assert response == {room: SENT}
    assert commands(broker) == [("zigbee2mqtt/7/set", {"color": {"saturation": 0.0}, "transition": 3.0})]
