"""Zigbee2MQTT raise and lower: brightness and saturation published as an end point with a transition, hue as a rate
move. Each action's adapter is a Z2MRamp.

Saturation is a color with no hue, which zigbee-herdsman-converters' light_color sends as MoveToSaturation: the stop of
an xy (MoveToColor) saturation fade visibly jumps, and a MoveToSaturation one halted by StopMoveStep doesn't
(docs/integrations/zigbee2mqtt/internals.md, Tested behavior).

A lower to the lowest level goes raw where every light it reaches is of a class that declares its bottom level
(RAW_BOTTOM: Hue and Aqara 1, families/hue and families/aqara; standard lights 2, zigbee/standard_lights.py), a group
of them included, at the highest level any of them declares: the converter sends level 1 as 2 where every light's
definition has turnsOffAtBrightness1 (a group only when all its members' do), and a Hue bulb holds 1; it sends it as
moveToLevelWithOnOff, which switched an unflagged Aqara bulb off, and every standard light is unflagged. A group with
any other light keeps the converter. The raw call is a moveToLevel, not the converter's moveToLevelWithOnOff, which
turns a light off at the minimum (rig probe 2026-11-25); below a light's MinLevel a moveToLevel clamps there and leaves
it lit. It publishes no state, which the end read-back makes up. A raise from off keeps the converter's bottom, level
2, which the fade up hides (internals.md, `fade`)."""

import logging
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any, ClassVar

from homeassistant.components.light import COLOR_MODES_COLOR
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .adapter import Z2MAdapter
from .addressing import known_base, not_addressable, topic, z2m_address
from .bridge import LEVEL_CLUSTER, has_feature, publish, publish_set, raw_command
from .classes import capability, class_scope
from .color_refresh import refresh_color
from .families.aqara import RAW_BOTTOM as AQARA_RAW_BOTTOM
from .families.hue import NEED
from .families.hue import RAW_BOTTOM as HUE_RAW_BOTTOM
from .members import member_lights, unaddressable
from .native_control import native_control
from .set_check import checked
from ...actions.ramp import RampRequest
from ...core import transition
from ...core.errors import Reason, describe
from ...core.fields import BRIGHTNESS_FIELD
from ...core.ha_watch import ALL, Call, Entries
from ...core.models import EntityResult, Status, Target
from ...core.resolver import resolve
from ...core.runtime import Job, get_runtime
from ...core.scope import AdapterScope, verified
from ...core.transition import (
    SATURATION,
    Transition,
    TransitionCache,
    color_mode,
    hs_color,
    lit,
)
from ...core.zcl import HUE_STEPS
from ...core.zcl_fade import brightness_leg, hue_cycle, saturation_leg
from ...zigbee.standard_lights import BOTTOM_LEVEL as STANDARD_BOTTOM_LEVEL
from ...zigbee.standard_lights import STANDARD_LIGHT

_LOGGER = logging.getLogger(__name__)

# The classes a lower to the lowest level sends a raw moveToLevel, each with its level, declared by its owner with its
# evidence; set_attributes uses Hue's alone.
RAW_BOTTOM: dict[str, int] = {**HUE_RAW_BOTTOM, **AQARA_RAW_BOTTOM, STANDARD_LIGHT: STANDARD_BOTTOM_LEVEL}

# Z2M reads a light back within 0.7 s of a stop, and once a fade has run its published end value is right.
SETTLE_SECONDS = 2.0
# The end read-back, after the fade has run: a live read mid-fade may have overwritten Z2M's published end value.
END_READ_S = 1.0
COLOR_HS = "color_hs"  # the Z2M feature a hue or saturation move needs
# An off light keeps its level, and a fade from off starts there: it is turned on at the bottom first.
AT_THE_BOTTOM = {"state": "ON", "brightness": 1, "transition": 0}


def transition_cache(hass: HomeAssistant) -> TransitionCache:
    return transition.transition_cache(hass, "zigbee2mqtt", lambda: TransitionCache(SETTLE_SECONDS))


type Source = tuple[Transition | None, float]  # the last published move under a planned fade, else the bulb's level


def waiting(hass: HomeAssistant) -> dict[int, Source]:
    """By id, each recorded fade still waiting for Z2M's option, and where the bulb really is under it: a stop in the
    window halts there (start)."""
    return get_runtime(hass).integration_state.setdefault("zigbee2mqtt_waiting_fades", {})


def hue_moves(hass: HomeAssistant) -> set[str]:
    """The lights a hue move of ours is cycling: it runs until a stop, so it has no transition to predict."""
    return get_runtime(hass).integration_state.setdefault("zigbee2mqtt_hue_moves", set())


class Z2MCallResolver:
    """Forget the Z2M lights a light call from HA targets: the bulb then goes where the call sends it, and its next move
    or stop starts from HA's state. A call that sets a color or turns the light off ends the bulb's hue cycle. The end
    read-back stays: it reads the bulb.

    A group's members come only from Z2M's retained bridge/groups message, so a call to a group resolves in a task;
    the dispatcher waits for it (ha_watch.settled) before a move plans.
    """

    def busy(self, hass: HomeAssistant) -> bool:
        return bool(transition_cache(hass).resource_ids() or hue_moves(hass))

    def forget(self, hass: HomeAssistant, call: Call, entries: Entries) -> Coroutine[Any, Any, None] | None:
        if entries is ALL:
            transition_cache(hass).clear()
            if call.ends_hue_cycle:
                hue_moves(hass).clear()
            return None
        targets = _z2m_lights(hass, entries)
        _drop(hass, call, [target.entity_id for target in targets])
        if not (groups := [target for target in targets if target.is_group]):
            return None

        async def members() -> None:
            for group in groups:
                _drop(hass, call, [light.entity_id for light in await member_lights(hass, group)])

        return members()


def _drop(hass: HomeAssistant, call: Call, light_ids: list[str]) -> None:
    cache, cycling = transition_cache(hass), hue_moves(hass)
    for light_id in light_ids:
        cache.forget(light_id)
        if call.ends_hue_cycle:
            cycling.discard(light_id)


def _z2m_lights(hass: HomeAssistant, entries: list[er.RegistryEntry]) -> list[Target]:
    """The Z2M light and group targets among the entries, which may hold any MQTT entity."""
    registry = get_runtime(hass).registry
    targets = [resolve(hass, registry, entry.entity_id) for entry in entries if entry.domain == Platform.LIGHT]
    return [t for t in targets if not isinstance(t, str) and t.integration == "zigbee2mqtt"]


def read_back_key(target: Target, attribute: str) -> str:
    """The key an attribute's end read-back is scheduled under, which the attribute's next move, or a stop, replaces."""
    return f"zigbee2mqtt:ramp:{target.entity_id}:{attribute}"


async def lights_of(hass: HomeAssistant, target: Target) -> list[Target]:
    return await member_lights(hass, target) if target.is_group else [target]


@dataclass(frozen=True, slots=True)
class Fade:
    """One attribute's fade: the payload published, each moving light's start and end, and how long it runs; first, any
    publishes that put a light at the fade's start."""

    attribute: str
    payload: dict
    starts: dict[str, float]
    ends: dict[str, float]
    duration: float
    before: tuple[tuple[Target, dict], ...] = ()
    clamped_to: float | None = None  # the sweep_time used, where it had to be clamped


def ramp_scope(action: str, attribute: str) -> AdapterScope:
    """A ramp's scope: its classes as classes.class_scope holds them for the action, a brightness fade's as stop's
    are, a hue or saturation fade's apart."""
    return AdapterScope(
        domains=verified(Platform.LIGHT), **class_scope(action), fields=verified(attribute), native_groups=True
    )


class Z2MRamp(Z2MAdapter[RampRequest]):
    """Publish the limit (or range end) with a transition for the distance left; the bulb runs the fade.

    Brightness and saturation fades are separate calls, each with its own transition: the bulb runs them
    independently. Predictions live per light and attribute (the core transition cache), so a move after a stop
    continues from where the light halted. A group gets one publish to its group topic, so its members fade together;
    each member's transition is recorded from its own start, and the group's start is the mean of its lit members.

    Raising brightness turns the light on. Lowering it to 0 % is Z2M's soft off, state OFF with the transition, which
    keeps the level for the next plain on. Saturation is written as a color with the end saturation and no hue, so each
    bulb keeps its own and a group is one publish, on lit lights showing a color (hs or xy); else as the light's
    current hue with the end saturation, in xy. It moves only lit lights. Hue is Z2M's hue_move, a cycle at a rate the
    bulb runs until a stop; a sweep_time outside 1-254 s is clamped, with clamped_to, as is a brightness or saturation
    fade's, which the longest ZCL transition caps (core.zcl_fade.fade_seconds). A light whose Z2M definition lacks
    color_hs is unchanged with fields_dropped for hue and saturation. A move with nothing left to make is unchanged with
    at_limit; one with only lights that are off to move is unchanged with off.

    Z2M publishes the end value at once. Once a fade has run, its attribute is read back, and a saturation fade's color
    refreshed (color_refresh), so HA ends right even after a live read mid-fade.
    """

    integration: ClassVar[str] = "zigbee2mqtt"

    def supports(self, hass: HomeAssistant, request: RampRequest, target: Target) -> str | None:
        if (reason := super().supports(hass, request, target)) is not None:
            return reason
        return not_addressable(hass, target) or unaddressable(hass, target, every=True)

    async def execute(self, hass: HomeAssistant, request: RampRequest, targets: list[Target]) -> list[EntityResult]:
        cache = transition_cache(hass)

        async def send(target: Target) -> EntityResult:
            if not (lights := await lights_of(hass, target)):
                return self.result(target, Status.UNSUPPORTED, detail=Reason.EMPTY_GROUP)
            if await lacks_color(hass, request, lights):
                return self.result(target, Status.UNCHANGED, detail="fields_dropped")
            if isinstance(outcome := plan(hass, cache, request, target, lights), str):
                return self.result(target, Status.UNCHANGED, detail=outcome)
            try:
                await start(hass, cache, target, lights, outcome, NEED.get(self.action))
            except Stopped:
                return self.result(target, Status.UNCHANGED, detail="stopped")
            clamped_to = outcome.clamped_to if isinstance(outcome, Fade) else outcome[1]
            return self.result(target, Status.SENT, clamped_to=clamped_to)

        return await checked(self, hass, targets, send)


type HueMove = tuple[int, float | None]  # hue_move's signed rate, and the sweep_time used where it was clamped


def plan(
    hass: HomeAssistant, cache: TransitionCache, request: RampRequest, target: Target, lights: list[Target]
) -> Fade | HueMove | str:
    """The attribute's fade or hue move, or why it has none to make."""
    if request.attribute == BRIGHTNESS_FIELD:
        return brightness_fade(hass, cache, request, target, lights)
    if request.attribute == SATURATION:
        return saturation_fade(cache, request, target, lights)
    return hue_rate(request) if lit(cache, lights) else "off"


class Stopped(Exception):
    """A stop reached the fade's lights while it waited for Z2M's option: it publishes nothing. Its arg maps each light
    the stop halted to its halt."""


async def start(
    hass: HomeAssistant,
    cache: TransitionCache,
    target: Target,
    lights: list[Target],
    outcome: Fade | HueMove,
    need: bool | None,
) -> None:
    """Publish the fade, recording it, and schedule its end read-back, or publish the hue move. Z2M's
    hue_native_control is held at need for the publishes (native_control.py).

    A fade is recorded before the option is taken, which can wait on an earlier action's restore, so a stop in that
    window finds the fade and halts it; the fade then raises Stopped and publishes nothing, and the stop stands, moved
    to where the bulb is. A hue move needs no option, so it has no such window."""
    if not isinstance(outcome, Fade):
        async with native_control(hass, target, need):
            await publish_set(hass, target, {"hue_move": outcome[0]})
        hue_moves(hass).update(light.entity_id for light in lights)
        return
    attribute = outcome.attribute
    await _publish_fade(hass, cache, target, outcome, need)
    if attribute == SATURATION:
        hue_moves(hass).difference_update(outcome.starts)  # a color write ends the bulb's hue cycle
    read = end_read(hass, target, lights, attribute)
    get_runtime(hass).schedule(hass, read_back_key(target, attribute), [(outcome.duration + END_READ_S, read)])


def _sources(hass: HomeAssistant, cache: TransitionCache, outcome: Fade) -> dict[str, Source]:
    """Where each of the fade's bulbs really is: under a fade that never published, where that one's source puts it."""
    pending = waiting(hass)
    sources: dict[str, Source] = {}
    for light_id, begin in outcome.starts.items():
        prior = cache.live(light_id, outcome.attribute)
        sources[light_id] = pending.get(id(prior), (prior, begin)) if prior is not None else (None, begin)
    return sources


async def _publish_fade(
    hass: HomeAssistant, cache: TransitionCache, target: Target, outcome: Fade, need: bool | None
) -> None:
    """Record the fade, take the option and publish, unless a stop halted it meanwhile (start)."""
    attribute, pending, sources = outcome.attribute, waiting(hass), _sources(hass, cache, outcome)
    planned: dict[str, Transition] = {}
    try:
        async with cache.recording((light_id, attribute) for light_id in outcome.starts):
            for light_id, begin in outcome.starts.items():
                planned[light_id] = cache.moving(light_id, attribute, begin, outcome.ends[light_id], outcome.duration)
                pending[id(planned[light_id])] = sources[light_id]
            async with native_control(hass, target, need):
                if halts := {
                    light_id: halt
                    for light_id, transition in planned.items()
                    if cache.halted(light_id, attribute) and (halt := cache.live(light_id, attribute)) is not transition
                }:
                    raise Stopped(halts)
                # Recorded again inside the option's window, so the prediction starts at the publish.
                for light_id, begin in outcome.starts.items():
                    cache.moving(light_id, attribute, begin, outcome.ends[light_id], outcome.duration)
                for light, payload in outcome.before:
                    await publish_set(hass, light, payload)
                await publish_set(hass, target, outcome.payload)
    except Stopped as stop:
        # The stop halted at the unpublished fade's prediction; the bulb halted where its source put it at the stop (0 %
        # from off), so a raise right after still lights it from the bottom.
        for light_id, halt in stop.args[0].items():
            move, level = sources[light_id]
            value = move.value(halt.started_at) if move is not None else level
            cache.moving(light_id, attribute, value, value, 0.0, started_at=halt.started_at)
        raise
    finally:
        for transition in planned.values():
            pending.pop(id(transition), None)


async def lacks_color(hass: HomeAssistant, request: RampRequest, lights: list[Target]) -> bool:
    """Whether a hue or saturation move meets a light whose Z2M definition lacks color_hs."""
    if request.attribute == BRIGHTNESS_FIELD:
        return False
    return not await has_feature(
        hass, known_base(hass, lights[0]), [z2m_address(light.device) for light in lights], COLOR_HS
    )


def brightness_fade(
    hass: HomeAssistant, cache: TransitionCache, request: RampRequest, target: Target, lights: list[Target]
) -> Fade | str:
    """The brightness fade toward the limit, or why it has none to make (core.zcl_fade.brightness_leg); a lower to
    the lowest level raw where every light it reaches is of a class with a bottom level (raw_bottom)."""
    if isinstance(leg := brightness_leg(cache, request, lights), str):
        return leg
    up, limit, lit_lights = request.up, leg.limit, leg.lit
    transition_s = round(leg.duration, 1)
    if limit == 0:
        payload = {"state": "OFF", "transition": transition_s}
    else:
        payload = {"brightness": max(1, round(limit / 100 * 254)), "transition": transition_s}
        payload = {"state": "ON", **payload} if up else payload
    off = [light for light in lights if light not in lit_lights] if up else []
    # One publish to the group when it is all off, so its members light together; else each off member's own.
    before = tuple((light, AT_THE_BOTTOM) for light in ([target] if off == lights else off))
    if not up and payload.get("brightness") == 1 and (level := bottom_level(hass, lights)) is not None:
        payload = raw_bottom(payload, level)
    return Fade(
        BRIGHTNESS_FIELD, payload, leg.starts, dict.fromkeys(leg.starts, limit), leg.duration, before, leg.clamped_to
    )


def bottom_level(hass: HomeAssistant, reached: list[Target]) -> int | None:
    """The level a lower to the lowest level sends raw to the lights it reaches: the highest any of their classes
    declares (RAW_BOTTOM), so every one stays lit, or None where one's class declares none, which keeps the converter.
    A group reaches its members."""
    levels = [RAW_BOTTOM.get(capability(hass, light)) for light in reached]
    return None if None in levels else max(levels)


def raw_bottom(payload: dict, level: int) -> dict:
    """A lower's publish to the lowest level as a raw moveToLevel to the level, with the converter's transtime and
    options: the converter's moveToLevelWithOnOff would turn the light off at the minimum."""
    transtime = round(payload["transition"] * 10)  # the converter's: transition in tenths
    return raw_command(
        LEVEL_CLUSTER,
        "moveToLevel",
        {"level": level, "transtime": transtime, "optionsMask": 0, "optionsOverride": 0},
    )


def saturation_fade(cache: TransitionCache, request: RampRequest, target: Target, lights: list[Target]) -> Fade | str:
    """The saturation fade toward the limit; off with no lit light in color, at_limit when there is none left to make.

    A color with no hue where every moving light shows a color: Z2M sends MoveToSaturation (hue_native_control off,
    which NEED holds), so each bulb keeps its own hue and a group is one publish. Else, a light in color temperature
    (its stored hue may be stale, untested) makes it the current hue with the end saturation, as an xy fade. Z2M
    publishes the end, which HA takes.
    """
    if isinstance(leg := saturation_leg(cache, request, lights), str):
        return leg
    movers, limit = leg.movers, leg.limit
    color = {"saturation": round(limit, 1)}
    if not all(color_mode(light) in COLOR_MODES_COLOR for light in movers):
        color["hue"] = round((hs_color(target) or hs_color(movers[0]))[0], 1)
    payload = {"color": color, "transition": round(leg.duration, 1)}
    return Fade(
        SATURATION, payload, leg.starts, dict.fromkeys(leg.starts, limit), leg.duration, clamped_to=leg.clamped_to
    )


def hue_rate(request: RampRequest) -> HueMove:
    """hue_move's signed rate for the sweep_time, a full cycle, and the sweep_time used where it had to be clamped.

    Clamped, not refused: the call's value lies outside what the bulb can do, as an out-of-range duration does. Rounding
    the rate inside the range isn't reported.
    """
    rate, clamped_to = hue_cycle(request.sweep_time, HUE_STEPS, HUE_STEPS)
    return (rate if request.up else -rate), clamped_to


def end_read(hass: HomeAssistant, target: Target, lights: list[Target], attribute: str) -> Job:
    """The read-back once a fade has run: each light's state and brightness, or the target's color refreshed."""

    async def read() -> None:
        if attribute == SATURATION:
            await refresh_color(hass, target, silent=True)
            return
        for light in lights:
            try:
                await publish(hass, topic(hass, light, "get"), {"state": "", "brightness": ""})
            except Exception as err:  # noqa: BLE001 - a failed read leaves HA's state stale, nothing more
                _LOGGER.debug("End read-back for %s failed: %s", light.entity_id, describe(err))

    return read
