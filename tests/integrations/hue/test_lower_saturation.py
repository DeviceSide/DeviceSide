"""Hue lower_saturation: an xy fade toward white at the light's hue, and what a stop or a refused write leaves the next
move to start from."""

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.color import color_hs_to_xy, color_xy_to_hs

from .conftest import SENT, STOP, color_lamp, hs_xy, xy_halt, xy_put
from ...conftest import call

pytestmark = pytest.mark.usefixtures("setup_production")

HUE, SATURATION_PCT = color_xy_to_hs(*hs_xy(200.0, 90.0))


async def test_lower_fades_toward_white_at_the_lights_hue(hass, bridge, clock):
    entity_id = await color_lamp(hass, bridge, (200.0, 90.0))

    response = await call(hass, "lower_saturation", {"entity_id": entity_id, "sweep_time": 10, "limit": 20})

    assert response == {entity_id: SENT}
    duration_ms = round((SATURATION_PCT - 20) * 100)
    assert bridge.puts == [("light/light-1", xy_put(color_hs_to_xy(HUE, 20), duration_ms))]


async def test_lowering_below_the_limit_is_at_limit(hass, bridge):
    entity_id = await color_lamp(hass, bridge, (200.0, 10.0))

    response = await call(hass, "lower_saturation", {"entity_id": entity_id, "limit": 30})

    assert response[entity_id]["detail"] == "at_limit"
    assert bridge.puts == []


async def test_a_move_after_a_stop_starts_from_the_halt(hass, bridge, clock):
    # The bridge reported the end xy at once; the halt and the next move come from the straight line.
    entity_id = await color_lamp(hass, bridge, (200.0, 90.0))
    await call(hass, "lower_saturation", {"entity_id": entity_id, "sweep_time": 10, "limit": 0})
    start, end = hs_xy(200.0, 90.0), color_hs_to_xy(HUE, 0)
    bridge.api.lights["light-1"].color.xy.x, bridge.api.lights["light-1"].color.xy.y = end
    clock.now += SATURATION_PCT / 10 / 4  # a quarter of the way

    await call(hass, "stop", {"entity_id": entity_id})
    halt = tuple(a + (b - a) / 4 for a, b in zip(start, end, strict=True))
    clock.now += 5
    await call(hass, "lower_saturation", {"entity_id": entity_id, "sweep_time": 10, "limit": 0})

    assert bridge.puts[1] == ("light/light-1", STOP | xy_halt(halt))
    # From the predicted 3/4 of the start's saturation, not the end the bridge reported.
    assert bridge.puts[2] == ("light/light-1", xy_put(end, round(SATURATION_PCT * 0.75 * 1000 / 10)))


async def test_a_refused_move_leaves_the_light_where_the_bridge_says(hass, bridge, clock):
    entity_id = await color_lamp(hass, bridge, (200.0, 90.0))
    bridge.failing.add("light-1")

    with pytest.raises(HomeAssistantError):
        await call(hass, "lower_saturation", {"entity_id": entity_id, "sweep_time": 10})
    bridge.failing.clear()
    clock.now += 2
    read = await call(hass, "get_attributes", {"entity_id": entity_id})

    assert read[entity_id]["xy_color"] == pytest.approx(list(hs_xy(200.0, 90.0)), abs=1e-4)
