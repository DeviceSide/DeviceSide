"""Fade planning shared by the Zigbee integrations: ZHA and Zigbee2MQTT plan a brightness or saturation fade, and a hue
cycle's rate, from here, so the two can't drift. Each keeps its own commands, payloads, sending and recording."""

from dataclasses import dataclass
from statistics import mean
from typing import TYPE_CHECKING

from .models import Target
from .transition import SATURATION, TransitionCache, hs_color, light_brightness, lit

if TYPE_CHECKING:  # core doesn't import actions at run time
    from ..actions.ramp import RampRequest

# The smallest brightness or saturation step a bulb makes (1/254), in percent.
MIN_STEP = 100 / 254
# A ZCL transition is a uint16 in tenths of a second; 0xFFFF means the bulb's default.
MAX_TRANSITION_S = 0xFFFE / 10
# A hue cycle takes at least this long.
MIN_CYCLE_S = 1.0


@dataclass(frozen=True, slots=True)
class Leg:
    """One attribute's planned move, before an integration builds its call."""

    movers: list[Target]
    lit: list[Target]
    starts: dict[str, float]  # the movers' starts
    limit: float
    duration: float  # at most MAX_TRANSITION_S
    clamped_to: float | None = None  # the sweep_time the duration stands for, where the cap applied


def fade_seconds(distance: float, sweep_time: float) -> tuple[float, float | None]:
    """How long a fade over `distance` percent takes at the sweep_time's speed, and the sweep_time used where that had
    to be clamped.

    Clamped, not refused: a fade longer than the longest ZCL transition (MAX_TRANSITION_S, docs/internals.md, Fades)
    runs at that, faster, as an out-of-range duration does; the sweep_time that gives it is reported.
    """
    seconds = distance / 100 * sweep_time
    if seconds <= MAX_TRANSITION_S:
        return seconds, None
    return MAX_TRANSITION_S, round(MAX_TRANSITION_S * 100 / distance, 1)


def brightness_leg(cache: TransitionCache, request: RampRequest, lights: list[Target]) -> Leg | str:
    """The brightness fade toward the limit; "off" lowering with nothing lit, "at_limit" when there is none left to
    make. Raising moves every light (the off ones fade in from the bottom), lowering the lit ones."""
    up, limit = request.up, request.end()
    starts = {light.entity_id: light_brightness(cache, light) for light in lights}
    lit_lights = lit(cache, lights)
    if not up and not lit_lights:
        return "off"
    movers = lights if up else lit_lights
    current = mean(starts[light.entity_id] for light in lit_lights or lights)
    if (limit - current if up else current - limit) < MIN_STEP:
        return "at_limit"
    duration, clamped_to = fade_seconds(abs(limit - current), request.sweep_time)
    starts = {light.entity_id: starts[light.entity_id] for light in movers}
    return Leg(movers, lit_lights, starts, limit, duration, clamped_to)


def saturation_leg(cache: TransitionCache, request: RampRequest, lights: list[Target]) -> Leg | str:
    """The saturation fade toward the limit, on the lit lights with a color; "off" with none, "at_limit" when there is
    none left to make."""
    if not (movers := [light for light in lit(cache, lights) if hs_color(light) is not None]):
        return "off"
    up, limit = request.up, request.end()
    starts = {light.entity_id: cache.value(light.entity_id, SATURATION, hs_color(light)[1]) for light in movers}
    current = mean(starts.values())
    if (limit - current if up else current - limit) < MIN_STEP:
        return "at_limit"
    duration, clamped_to = fade_seconds(abs(limit - current), request.sweep_time)
    return Leg(movers, movers, starts, limit, duration, clamped_to)


def hue_cycle(sweep_time: float, steps: int, max_cycle: float) -> tuple[int, float | None]:
    """A hue cycle's unsigned rate, in `steps` per cycle per second, for the sweep_time, and the sweep_time used where
    it had to be clamped to 1 to max_cycle seconds.

    Clamped, not refused: the call's value lies outside what the bulb can do, as an out-of-range duration does. Rounding
    the rate inside the range isn't reported.
    """
    cycle = min(max(sweep_time, MIN_CYCLE_S), max_cycle)
    rate = min(max(round(steps / cycle), 1), steps)
    return rate, (cycle if cycle != sweep_time else None)
