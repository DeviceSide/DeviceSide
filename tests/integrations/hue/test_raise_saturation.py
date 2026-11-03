"""Hue raise_saturation: an xy fade toward the light's own hue at the limit, on lit color lights only."""

import pytest
from homeassistant.util.color import color_hs_to_xy, color_xy_to_hs

from custom_components.device_side.core.transition import SATURATION
from custom_components.device_side.integrations.hue.transition_cache import transition_cache

from .conftest import SENT, color_lamp, color_room, hs_xy, xy_put
from ...conftest import call

pytestmark = pytest.mark.usefixtures("setup_production")

# What HA reads back from the bulb's xy for hs (200, 50): xy is kept to 3 places, so not quite (200, 50).
HUE, SATURATION_PCT = color_xy_to_hs(*hs_xy(200.0, 50.0))
# A gamut with no blue reach: (0.15, 0.06) is outside it, and saturated blues with it.
NARROW = {"red": {"x": 0.6, "y": 0.35}, "green": {"x": 0.3, "y": 0.6}, "blue": {"x": 0.25, "y": 0.2}}


async def test_raise_fades_to_the_limit_at_the_lights_hue(hass, bridge, clock):
    entity_id = await color_lamp(hass, bridge)

    response = await call(hass, "raise_saturation", {"entity_id": entity_id, "sweep_time": 10, "limit": 80})

    assert response == {entity_id: SENT}
    duration_ms = round((80 - SATURATION_PCT) * 100)
    assert bridge.puts == [("light/light-1", xy_put(color_hs_to_xy(HUE, 80), duration_ms))]
    assert transition_cache(hass).running("light-1", SATURATION).target == 80


async def test_the_end_is_clamped_to_the_lights_gamut(hass, bridge, clock):
    entity_id = await color_lamp(hass, bridge, (240.0, 50.0), gamut=NARROW)

    await call(hass, "raise_saturation", {"entity_id": entity_id})

    (x, y) = (bridge.puts[0][1]["color"]["xy"][key] for key in ("x", "y"))
    hue = color_xy_to_hs(*hs_xy(240.0, 50.0))[0]
    assert (x, y) != pytest.approx(color_hs_to_xy(hue, 100))
    assert (x, y) == pytest.approx((0.25, 0.2), abs=0.03)  # on the gamut's edge, by its blue corner


@pytest.mark.parametrize(
    ("light", "detail"),
    [
        pytest.param({"state": "off"}, "off", id="off_light"),
        pytest.param({"hs": (200.0, 100.0)}, "at_limit", id="already_at_100"),
    ],
)
async def test_nothing_to_make_sends_nothing(hass, bridge, light, detail):
    entity_id = await color_lamp(hass, bridge, **light)

    response = await call(hass, "raise_saturation", {"entity_id": entity_id})

    assert response == {entity_id: {"status": "unchanged", "integration": "hue", "detail": detail}}
    assert bridge.puts == []


async def test_a_light_without_color_drops_saturation(hass, bridge):
    # Its state lists no color modes here, so the adapter, not the dispatcher, finds it lacks color.
    entity_id = await color_lamp(hass, bridge)
    bridge.api.lights["light-1"].color = None

    response = await call(hass, "raise_saturation", {"entity_id": entity_id})

    assert response == {entity_id: {"status": "unchanged", "integration": "hue", "detail": "fields_dropped"}}
    assert bridge.puts == []


async def test_a_white_light_raises_toward_its_own_tint(hass, bridge, clock):
    # A warm color temperature white: its xy has a hue, so it deepens toward amber.
    entity_id = await color_lamp(hass, bridge, (30.0, 20.0))

    await call(hass, "raise_saturation", {"entity_id": entity_id, "limit": 60})

    hue = color_xy_to_hs(*hs_xy(30.0, 20.0))[0]
    assert bridge.puts[0][1]["color"]["xy"] == pytest.approx(dict(zip("xy", color_hs_to_xy(hue, 60), strict=True)))


async def test_a_room_is_one_write_at_its_mean_hue_passing_white_lights_by(hass, bridge, clock):
    entity_id = await color_room(hass, bridge, {"one": (200.0, 90.0), "two": (220.0, 50.0), "white": None})

    response = await call(hass, "raise_saturation", {"entity_id": entity_id, "sweep_time": 10})

    one, two = (color_xy_to_hs(*hs_xy(*hs)) for hs in ((200.0, 90.0), (220.0, 50.0)))
    mean_xy = [(a + b) / 2 for a, b in zip(hs_xy(200.0, 90.0), hs_xy(220.0, 50.0), strict=True)]
    hue = color_xy_to_hs(*mean_xy)[0]
    duration_ms = round((100 - (one[1] + two[1]) / 2) * 100)
    assert response == {entity_id: SENT}
    assert bridge.puts == [("grouped_light/grouped-1", xy_put(color_hs_to_xy(hue, 100), duration_ms))]
    cache = transition_cache(hass)
    assert cache.running("one", SATURATION).start == pytest.approx(one[1])
    assert cache.running("two", SATURATION).start == pytest.approx(two[1])
    assert not cache.tracks("white", SATURATION)


@pytest.mark.parametrize(
    ("colors", "detail"),
    [
        pytest.param({"one": None, "two": None}, "fields_dropped", id="no_color_light"),
        pytest.param({"one": (200.0, 50.0), "two": None}, "off", id="all_off"),
    ],
)
async def test_a_room_with_no_lit_color_light_sends_nothing(hass, bridge, colors, detail):
    entity_id = await color_room(hass, bridge, colors, on=detail != "off")

    response = await call(hass, "raise_saturation", {"entity_id": entity_id})

    assert response == {entity_id: {"status": "unchanged", "integration": "hue", "detail": detail}}
    assert bridge.puts == []
