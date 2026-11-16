"""The Zigbee integrations' shared fade planning: what a fade moves, from where, how long it runs and what it leaves
alone."""

from types import SimpleNamespace

import pytest

from custom_components.deviceside.actions.ramp import RampRequest
from custom_components.deviceside.core.transition import BRIGHTNESS, SATURATION, TransitionCache
from custom_components.deviceside.core.zcl_fade import (
    MAX_TRANSITION_S,
    brightness_leg,
    fade_seconds,
    hue_cycle,
    saturation_leg,
)


def light(name: str, on: bool = True, brightness: int | None = None, hs: tuple[float, float] | None = None):
    attributes = {"brightness": brightness, "hs_color": hs}
    return SimpleNamespace(
        entity_id=f"light.{name}", state=SimpleNamespace(state="on" if on else "off", attributes=attributes)
    )


def ramp(attribute: str, up: bool, sweep_time: float = 10.0, limit: float | None = None) -> RampRequest:
    return RampRequest(attribute=attribute, up=up, sweep_time=sweep_time, limit=limit)


@pytest.fixture
def cache():
    return TransitionCache(2.0, lambda: 0.0)


def test_lowering_with_nothing_lit_is_off(cache):
    assert brightness_leg(cache, ramp(BRIGHTNESS, False), [light("a", on=False)]) == "off"


@pytest.mark.parametrize(("up", "brightness"), [(True, 255), (False, 0)])
def test_a_light_at_the_limit_has_nothing_to_make(cache, up, brightness):
    lights = [light("a", brightness=brightness or None, on=bool(brightness))]
    expected = "at_limit" if brightness else "off"
    assert brightness_leg(cache, ramp(BRIGHTNESS, up), lights) == expected


def test_raising_moves_every_light_from_the_mean_of_the_lit_ones(cache):
    lit_a, lit_b, dark = light("a", brightness=51), light("b", brightness=153), light("c", on=False)

    leg = brightness_leg(cache, ramp(BRIGHTNESS, True), [lit_a, lit_b, dark])

    assert leg.movers == [lit_a, lit_b, dark]
    assert leg.lit == [lit_a, lit_b]
    assert leg.starts == {"light.a": pytest.approx(20), "light.b": pytest.approx(60), "light.c": 0.0}
    assert leg.limit == 100.0
    assert leg.duration == pytest.approx(6.0)  # from the mean, 40 %, over a sweep_time of 10 s


def test_lowering_moves_the_lit_lights_and_passes_the_off_ones_by(cache):
    lit_a, dark = light("a", brightness=255), light("b", on=False)

    leg = brightness_leg(cache, ramp(BRIGHTNESS, False, limit=20.0), [lit_a, dark])

    assert leg.movers == [lit_a]
    assert list(leg.starts) == ["light.a"]
    assert leg.duration == pytest.approx(8.0)


def test_raising_all_off_lights_averages_every_start(cache):
    lights = [light("a", on=False), light("b", on=False)]

    leg = brightness_leg(cache, ramp(BRIGHTNESS, True), lights)

    assert leg.lit == []
    assert leg.duration == pytest.approx(10.0)


def test_a_prediction_replaces_the_reported_start(cache):
    cache.moving("light.a", BRIGHTNESS, 0.0, 50.0, 10.0, started_at=0.0)

    leg = brightness_leg(cache, ramp(BRIGHTNESS, True), [light("a", brightness=255)])

    assert leg.starts == {"light.a": 0.0}


def test_a_fade_is_capped_at_the_longest_zcl_transition(cache):
    leg = brightness_leg(cache, ramp(BRIGHTNESS, True, sweep_time=100_000.0), [light("a", on=False)])

    assert leg.duration == MAX_TRANSITION_S == 6553.4


def test_fade_seconds_is_the_distance_at_the_sweep_speed_until_the_cap():
    assert fade_seconds(50, 10) == 5
    assert fade_seconds(100, 1e9) == MAX_TRANSITION_S


@pytest.mark.parametrize(
    ("lights", "up", "expected"),
    [
        pytest.param([light("a", on=False, hs=(10.0, 50.0))], True, "off", id="off"),
        pytest.param([light("a", hs=None)], True, "off", id="no_color"),
        pytest.param([light("a", hs=(10.0, 100.0))], True, "at_limit", id="at_the_top"),
        pytest.param([light("a", hs=(10.0, 0.0))], False, "at_limit", id="at_white"),
    ],
)
def test_saturation_with_nothing_to_make(cache, lights, up, expected):
    assert saturation_leg(cache, ramp(SATURATION, up), lights) == expected


def test_saturation_moves_the_lit_lights_in_color_from_their_mean(cache):
    colored = [light("a", hs=(10.0, 20.0)), light("b", hs=(200.0, 40.0))]
    leg = saturation_leg(cache, ramp(SATURATION, True), [*colored, light("c"), light("d", on=False, hs=(0.0, 0.0))])

    assert leg.movers == colored
    assert leg.starts == {"light.a": 20.0, "light.b": 40.0}
    assert leg.limit == 100.0
    assert leg.duration == pytest.approx(7.0)  # 70 % left of a 10 s sweep


def test_saturation_is_capped_too(cache):
    leg = saturation_leg(cache, ramp(SATURATION, True, sweep_time=1e9), [light("a", hs=(10.0, 0.0))])

    assert leg.duration == MAX_TRANSITION_S


@pytest.mark.parametrize(
    ("sweep_time", "steps", "max_cycle", "expected"),
    [
        pytest.param(10, 65535, 65535, (6554, None), id="enhanced_in_range"),
        pytest.param(0.1, 65535, 65535, (65535, 1.0), id="enhanced_too_fast"),
        pytest.param(1e6, 65535, 65535, (1, 65535.0), id="enhanced_too_slow"),
        pytest.param(5, 254, 254, (51, None), id="hue_move_in_range"),
        pytest.param(0.5, 254, 254, (254, 1.0), id="hue_move_too_fast"),
        pytest.param(1000, 254, 254, (1, 254.0), id="hue_move_too_slow"),
        pytest.param(254, 254, 254, (1, None), id="hue_move_slowest_unclamped"),
    ],
)
def test_hue_cycle_rate_and_clamp(sweep_time, steps, max_cycle, expected):
    assert hue_cycle(sweep_time, steps, max_cycle) == expected
