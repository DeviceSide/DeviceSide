"""ZHA raise and lower: brightness and saturation sent as an end point with a transition, hue as an EnhancedMoveHue
rate, through zha.issue_zigbee_cluster_command (or one zha.issue_zigbee_group_command for a ZHA group's members). Each
action's adapter is a ZHARamp."""

import asyncio
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from statistics import mean
from typing import Any, ClassVar

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import Unauthorized
from homeassistant.util.color import color_hs_to_xy

from . import zcl
from .addressing import address, group_id, unsupported_reason, via_zha_group
from .groups import light_members
from ...actions.ramp import HUE, RampRequest
from ...core import transition
from ...core.adapter import Adapter, DeadlinePassed
from ...core.ha_watch import ALL, Call, Entries
from ...core.models import EntityResult, Status, Target
from ...core.runtime import Job, get_runtime
from ...core.scope import AdapterScope, verified
from ...core.transition import BRIGHTNESS, SATURATION, TransitionCache, hs_color, light_brightness, lit

_LOGGER = logging.getLogger(__name__)

# A refresh after a fade or a stop reads the bulb's real value, so a prediction is needed only until then.
SETTLE_SECONDS = 2.0
# The smallest brightness or saturation step a bulb makes (1/254), in percent.
MIN_STEP = 100 / 254
# EnhancedMoveHue's rate is in steps of 1/65536 of the cycle per second, 1 to 65535, so a cycle takes 1 to 65535 s.
MIN_CYCLE_S, MAX_CYCLE_S = 1.0, 65535.0
# The end refresh and the soft off's restore, after the fade has run: the bulb reads its end within it (probe 13f).
END_REFRESH_S = 1.0
# The fit's deadband: how late a bulb may start its ramp, plus one level step. The lab's Hue bulbs start 0.05 to
# 0.08 s after the send, so every read lands behind schedule and fits a start a few percent off (3 Nov lab rerun);
# a read within this much of the ramp's own speed of the prediction leaves the prediction alone.
FIT_LAG_S = 0.15
# A ZCL transition is a uint16 in tenths of a second; 0xFFFF means the bulb's default.
_MAX_TENTHS = 0xFFFE
_MOVE_UP, _MOVE_DOWN = 0x01, 0x03
_COLOR_MODES = frozenset({"xy", "hs"})

type Command = tuple[int, int, dict[str, Any]]  # cluster, command, params in the command's positional order


def transition_cache(hass: HomeAssistant) -> TransitionCache:
    return transition.transition_cache(hass, "zha", lambda: TransitionCache(SETTLE_SECONDS))


def hue_moves(hass: HomeAssistant) -> set[str]:
    """The lights a hue move of ours is cycling: it runs until a stop, so it has no transition to predict."""
    return get_runtime(hass).integration_state.setdefault("zha_hue_moves", set())


def soft_off_restores(hass: HomeAssistant) -> set[str]:
    """The lights a soft off of ours will put back at their start level once it has run. A light call from HA drops a
    light from it: the call replaces our fade."""
    return get_runtime(hass).integration_state.setdefault("zha_restores", set())


class ZHACallResolver:
    """Forget the ZHA lights a light call from HA targets, as on Hue: the bulb then goes where the call sends it, and
    its next move or stop starts from HA's state. A pending soft-off restore is dropped too, and a call that sets a
    color or turns the light off ends the bulb's hue cycle. The end refresh still runs. Our own commands go through
    the zha domain, so they pass the watch by."""

    def busy(self, hass: HomeAssistant) -> bool:
        return bool(transition_cache(hass).resource_ids() or soft_off_restores(hass) or hue_moves(hass))

    def forget(self, hass: HomeAssistant, call: Call, entries: Entries) -> None:
        cache, pending, cycling = transition_cache(hass), soft_off_restores(hass), hue_moves(hass)
        if entries is ALL:
            cache.clear()
            pending.clear()
            if call.ends_hue_cycle:
                cycling.clear()
            return
        for entry in entries:
            if entry.domain != "light":
                continue
            gid = group_id(entry.unique_id)
            for light_id in light_members(hass, gid) if gid is not None else (entry.entity_id,):
                cache.forget(light_id)
                pending.discard(light_id)
                if call.ends_hue_cycle:
                    cycling.discard(light_id)


def end_key(light: Target, attribute: str) -> str:
    """The key an attribute's end refresh (and a soft off's restore) is scheduled under, which the attribute's next
    move, or a stop, replaces."""
    return f"zha:ramp:{light.entity_id}:{attribute}"


def units(hass: HomeAssistant, targets: list[Target]) -> list[tuple[int | None, list[Target]]]:
    """The targets as one unit per ZHA group they were expanded from, with its Zigbee group ID, then one per other
    target, with None."""
    groups: dict[int, list[Target]] = {}
    singles: list[tuple[int | None, list[Target]]] = []
    for target in targets:
        if (gid := via_zha_group(hass, target)) is not None:
            groups.setdefault(gid, []).append(target)
        else:
            singles.append((None, [target]))
    return [*groups.items(), *singles]


def has_color(light: Target) -> bool:
    modes = light.state.attributes.get("supported_color_modes") if light.state else None
    return bool(set(modes or ()) & _COLOR_MODES)


def drops_while_off(light: Target) -> bool:
    return light.device is not None and light.device.model in zcl.DROPS_WHILE_OFF


async def send(
    hass: HomeAssistant, gid: int | None, movers: list[Target], command: Command, context: Context | None
) -> None:
    """One groupcast when the movers are every light the group holds, so they move in lockstep; else one command each.

    A groupcast reaches every member, so one that isn't moving (off, on a move that passes it by) gets its own command
    instead: a soft off sent to an off light would still drop its stored level.
    """
    cluster_id, command_id, params = command
    if gid is not None and light_members(hass, gid) <= {light.entity_id for light in movers}:
        await zcl.group_command(hass, gid, cluster_id, command_id, list(params.values()), context)
        return
    for light in movers:
        await zcl.command(
            hass, address(light.entry.unique_id), cluster_id, command_id, params, context, entity_id=light.reported_id
        )


async def send_each(
    hass: HomeAssistant, gid: int | None, movers: list[Target], commands: dict[str, Command], context: Context | None
) -> dict[str, Exception]:
    """send() for a fade, which can fail one light and run on the rest: each mover's command, keyed by entity ID, and
    the movers it failed for, with why.

    One groupcast when the movers are every light the group holds and all get the same command, failing them all if it
    fails; else one command each, sent together. A cancel or other BaseException is raised.
    """
    shared = next(iter(commands.values()))
    if (
        gid is not None
        and all(command == shared for command in commands.values())
        and light_members(hass, gid) <= {light.entity_id for light in movers}
    ):
        cluster_id, command_id, params = shared
        try:
            await zcl.group_command(hass, gid, cluster_id, command_id, list(params.values()), context)
        except Exception as err:  # noqa: BLE001 - the callers report it per light
            return dict.fromkeys(commands, err)
        return {}

    async def one(light: Target) -> None:
        cluster_id, command_id, params = commands[light.entity_id]
        await zcl.command(
            hass, address(light.entry.unique_id), cluster_id, command_id, params, context, entity_id=light.reported_id
        )

    return failures(movers, await asyncio.gather(*(one(light) for light in movers), return_exceptions=True))


async def preset_each(hass: HomeAssistant, presets: list[Target], context: Context | None) -> dict[str, Exception]:
    """Put each light that is off at the bottom before a raise turns it on, unicast as each concerns one light's own
    stored level: a Hue bulb turned on there by Hue's own command, any other set there with ExecuteIfOff. The lights
    it failed for, with why."""

    async def one(light: Target) -> None:
        addr = address(light.entry.unique_id)
        if not await zcl.hue_turn_on(hass, addr, 1, context, entity_id=light.reported_id):
            bottom = {"level": 1, **zcl.execute_if_off(0)}
            await zcl.command(
                hass, addr, zcl.LEVEL_CLUSTER, zcl.MOVE_TO_LEVEL, bottom, context, entity_id=light.reported_id
            )

    return failures(presets, await asyncio.gather(*(one(light) for light in presets), return_exceptions=True))


def failures(lights: list[Target], outcomes: list[Any]) -> dict[str, Exception]:
    """The lights whose gathered send raised, with why; a cancel or other BaseException is raised."""
    for outcome in outcomes:
        if isinstance(outcome, BaseException) and not isinstance(outcome, Exception):
            raise outcome
    return {light.entity_id: err for light, err in zip(lights, outcomes, strict=True) if isinstance(err, Exception)}


async def refresh(hass: HomeAssistant, light: Target, context: Context | None) -> None:
    try:
        await hass.services.async_call(
            "homeassistant", "update_entity", {"entity_id": light.entity_id}, blocking=True, context=context
        )
    except Exception as err:  # noqa: BLE001 - a failed refresh leaves HA's state stale, nothing more
        _LOGGER.debug("update_entity for %s failed: %r", light.entity_id, err)


@dataclass(frozen=True, slots=True)
class Fade:
    """One attribute's fade: each moving light's command, start and end, and how long it runs; the lights to put at
    the bottom first, and the level each soft-off light gets back once it reads off."""

    attribute: str
    commands: dict[str, Command]
    movers: list[Target]
    starts: dict[str, float]
    ends: dict[str, float]
    duration: float
    presets: list[Target] = field(default_factory=list)
    restores: frozenset[str] = frozenset()  # the soft-off lights whose start level goes back, from starts


@dataclass(frozen=True, slots=True)
class HueMove:
    command: Command
    movers: list[Target]
    clamped_to: float | None  # the sweep_time used, where it had to be clamped


def ramp_scope(attribute: str, *, experimental: bool) -> AdapterScope:
    return AdapterScope(
        experimental=experimental, domains=verified("light"), fields=verified(attribute), max_concurrency=2
    )


class ZHARamp(Adapter[RampRequest]):
    """Send the limit (or range end) with a transition for the distance left; the bulb runs the fade.

    Brightness and saturation fades are separate calls, each with its own transition: the bulb runs them
    independently. Predictions live per light and attribute (the core transition cache), so a move after a stop
    continues from where the light halted. The dispatcher expands a ZHA group into its members; those from one group
    get one groupcast, so they fade together, each recorded from its own start, and the group's start is the mean of
    its lit members.

    Raising brightness is MoveToLevelWithOnOff, which turns the light on; a light that is off is first set to level 1,
    so it fades in from the bottom rather than its stored level: a Hue bulb turned on there by Hue's own command
    (zcl.hue_turn_on), any other light set there with ExecuteIfOff. Lowering to a limit is MoveToLevel,
    which a light that is off ignores. Lowering to 0 is MoveToLevelWithOnOff to 0, which leaves the bulb at level 1;
    once it reads off, its start level goes back with ExecuteIfOff, so it stays off and comes back at its old level, as
    on Hue. Models that drop a level while off (zcl.DROPS_WHILE_OFF) get neither: they start a raise at their stored
    level, and come back on dim.

    Saturation is MoveToColor, the xy of each light's current hue at the end saturation, on lit lights in color: group
    members at different hues each get their own, so the group's lights are sent one each. Hue is
    EnhancedMoveHue, a cycle the bulb runs until a stop, on lit lights whose ColorCapabilities report enhanced hue; a
    sweep_time outside 1-65535 s is clamped, with clamped_to. A group is unchanged with fields_dropped for hue if any
    member lacks it. A move with nothing left to make is unchanged with at_limit; one with only lights that are off to
    move is unchanged with off. A hue move whose ColorCapabilities read fails is rejected with error.

    A command that fails rejects only the lights it was for (admin_required, or error), each keeping the prediction
    and soft off restore it had; the rest run on. A light whose bottom preset failed gets no fade, so a groupcast
    becomes one command each for the rest.

    Once a fade has run, each light is refreshed with update_entity: ZHA applies the bulb's brightness reports but never
    its color ones.
    """

    integration: ClassVar[str] = "zha"

    def supports(self, hass: HomeAssistant, request: RampRequest, target: Target) -> str | None:
        return super().supports(hass, request, target) or unsupported_reason(target)

    async def execute(self, hass: HomeAssistant, request: RampRequest, targets: list[Target]) -> list[EntityResult]:
        cache = transition_cache(hass)
        runs = [self._unit(hass, request, cache, gid, lights) for gid, lights in units(hass, targets)]
        return [result for batch in await asyncio.gather(*runs) for result in batch]

    async def _unit(
        self, hass: HomeAssistant, request: RampRequest, cache: TransitionCache, gid: int | None, lights: list[Target]
    ) -> list[EntityResult]:
        def each(status: Status, **kwargs) -> list[EntityResult]:
            return [self.result(light, status, **kwargs) for light in lights]

        try:
            lacking = await lacks_hue(hass, request, lights)
        except Exception as err:  # noqa: BLE001 - zha and zigpy errors can't be imported here; read_attributes says why
            _LOGGER.warning("%s on zha failed for %s: ColorCapabilities not read: %r", self.action, names(lights), err)
            return each(Status.REJECTED, detail="error")
        if lacking:
            return each(Status.UNCHANGED, detail="fields_dropped")
        outcome = plan(cache, request, lights)
        if (
            isinstance(outcome, str)
            and request.attribute == BRIGHTNESS
            and any(cache.tracks(light.entity_id, BRIGHTNESS) for light in lights)
        ):
            # Nothing to do by the prediction, which a change made elsewhere can leave stale: ZHA applies the bulb's
            # brightness reports, so its state is right then. Plan again from it.
            for light in lights:
                cache.forget(light.entity_id, BRIGHTNESS)
            outcome = plan(cache, request, lights)
        if isinstance(outcome, str):
            return each(Status.UNCHANGED, detail=outcome)
        try:
            async with self.slot(hass):
                clamped_to, failed = await start(hass, request.context, cache, gid, outcome)
        except DeadlinePassed:
            _LOGGER.warning("%s on zha timed out for %s", self.action, names(lights))
            return each(Status.REJECTED, detail="timeout")
        except Exception as err:  # noqa: BLE001 - as in gather(): one group's failure must not abort the room
            _LOGGER.warning("%s on zha failed for %s: %r", self.action, names(lights), err)
            return each(Status.REJECTED, detail="error")
        if errors := {light_id: err for light_id, err in failed.items() if not isinstance(err, Unauthorized)}:
            why = ", ".join(f"{light_id}: {err!r}" for light_id, err in errors.items())
            _LOGGER.warning("%s on zha failed for %s", self.action, why)
        moved = {light.entity_id for light in outcome.movers}
        return [self._result(light, moved, failed, clamped_to) for light in lights]

    def _result(
        self, light: Target, moved: set[str], failed: dict[str, Exception], clamped_to: float | None
    ) -> EntityResult:
        if (err := failed.get(light.entity_id)) is not None:
            return self.result(
                light, Status.REJECTED, detail="admin_required" if isinstance(err, Unauthorized) else "error"
            )
        if light.entity_id in moved:
            return self.result(light, Status.SENT, clamped_to=clamped_to)
        return self.result(light, Status.UNCHANGED, detail="off")


def names(lights: list[Target]) -> str:
    return ", ".join(light.entity_id for light in lights)


def plan(cache: TransitionCache, request: RampRequest, lights: list[Target]) -> Fade | HueMove | str:
    """The attribute's fade or hue move, or why it has none to make."""
    if request.attribute == BRIGHTNESS:
        return brightness_fade(cache, request, lights)
    if request.attribute == SATURATION:
        return saturation_fade(cache, request, lights)
    return hue_move(request, movers) if (movers := lit(cache, lights)) else "off"


async def start(
    hass: HomeAssistant, context: Context | None, cache: TransitionCache, gid: int | None, outcome: Fade | HueMove
) -> tuple[float | None, dict[str, Exception]]:
    """Send the fade, recording it, and schedule each light's end refresh, or send the hue move; the clamped
    sweep_time, and the lights it failed for, with why.

    A light that fails gets back the prediction and soft off restore it had, and no end job; the rest run on. A cancel
    puts every light back and is raised.
    """
    if isinstance(outcome, HueMove):
        commands = {light.entity_id: outcome.command for light in outcome.movers}
        failed = await send_each(hass, gid, outcome.movers, commands, context)
        hue_moves(hass).update(light_id for light_id in commands if light_id not in failed)
        return outcome.clamped_to, failed
    marks = Marks.take(hass, cache, outcome)
    try:
        failed = await preset_each(hass, outcome.presets, context)
        if movers := [light for light in outcome.movers if light.entity_id not in failed]:
            # A light whose preset failed drops out, so a groupcast, which would reach it, gives way to unicasts.
            commands = {light.entity_id: outcome.commands[light.entity_id] for light in movers}
            failed |= await send_each(hass, gid, movers, commands, context)
    except BaseException:
        marks.put_back(outcome.starts)
        raise
    marks.put_back(failed)
    for light in outcome.movers:
        if light.entity_id not in failed:
            run_on(hass, cache, context, outcome, light, marks.recorded[light.entity_id])
    return None, failed


@dataclass(frozen=True, slots=True)
class Marks:
    """What a fade records before its send, and what each light held before it, to put back for one the send fails.

    The soft off marks go on before the send, so a light call from HA during it cancels the restore. This fade's end
    jobs replace the movers' earlier ones, restores included. A light the send fails for schedules none and replaces
    nothing, so its mark is taken back and an earlier soft off's (in kept) is put back for that one's end job.
    """

    cache: TransitionCache
    pending: set[str]
    fade: Fade
    before: dict[str, dict[tuple[str, str], transition.Transition]]
    recorded: dict[str, transition.Transition]
    kept: frozenset[str]

    @classmethod
    def take(cls, hass: HomeAssistant, cache: TransitionCache, fade: Fade) -> Marks:
        before = {light_id: cache.forget(light_id, fade.attribute) for light_id in fade.starts}
        recorded = {
            light_id: cache.moving(light_id, fade.attribute, begin, fade.ends[light_id], fade.duration)
            for light_id, begin in fade.starts.items()
        }
        pending = soft_off_restores(hass)
        kept: frozenset[str] = frozenset()
        if fade.attribute == BRIGHTNESS:
            kept = frozenset(pending & fade.starts.keys())
            pending.difference_update(fade.starts)
            pending.update(fade.restores)
        return cls(cache, pending, fade, before, recorded, kept)

    def put_back(self, light_ids: Iterable[str]) -> None:
        attribute = self.fade.attribute
        for light_id in light_ids:
            if self.cache.live(light_id, attribute) is self.recorded[light_id]:
                self.cache.forget(light_id, attribute)
                self.cache.restore(self.before[light_id])
            if light_id in self.fade.restores:
                self.pending.discard(light_id)
            if light_id in self.kept:
                self.pending.add(light_id)


def run_on(
    hass: HomeAssistant,
    cache: TransitionCache,
    context: Context | None,
    fade: Fade,
    light: Target,
    recorded: transition.Transition,
) -> None:
    """After a light's fade was sent: end its hue cycle for a color write, or fit its ramp for brightness, and
    schedule its end job."""
    if fade.attribute == SATURATION:
        hue_moves(hass).discard(light.entity_id)  # a color write ends the bulb's hue cycle
    else:
        hass.async_create_task(sync_to_bulb(hass, cache, light, fade, recorded))
    restore = fade.starts if light.entity_id in fade.restores else None
    job = end_job(hass, light, restore, context)
    # Replaces the attribute's pending refresh and restore: those of the light's other attribute run on.
    get_runtime(hass).schedule(
        hass, end_key(light, fade.attribute), [(fade.duration + END_REFRESH_S, job)], must_run=restore is not None
    )


async def lacks_hue(hass: HomeAssistant, request: RampRequest, lights: list[Target]) -> bool:
    """Whether a hue move meets a light whose ColorCapabilities lack enhanced hue; raises when one isn't read. The
    dispatcher already dropped saturation and hue from lights without color."""
    if request.attribute != HUE:
        return False
    reads = await asyncio.gather(*(zcl.enhanced_hue(hass, address(light.entry.unique_id)) for light in lights))
    return not all(reads)


def fade_seconds(distance: float, sweep_time: float) -> float:
    """How long a fade over `distance` percent takes at the sweep_time's speed, at most the longest ZCL transition: a
    longer fade runs at that, faster."""
    return min(distance / 100 * sweep_time, _MAX_TENTHS / 10)


def transition_tenths(duration: float) -> int:
    return round(duration * 10)


def brightness_fade(cache: TransitionCache, request: RampRequest, lights: list[Target]) -> Fade | str:
    """The brightness fade toward the limit; off lowering with nothing lit, at_limit when there is none left to make."""
    up, limit = request.up, request.end()
    starts = {light.entity_id: light_brightness(cache, light) for light in lights}
    lit_lights = lit(cache, lights)
    if not up and not lit_lights:
        return "off"
    # Raising turns every light on, so the off ones fade in from the bottom; lowering passes them by.
    movers = lights if up else lit_lights
    current = mean(starts[light.entity_id] for light in lit_lights or lights)
    if (limit - current if up else current - limit) < MIN_STEP:
        return "at_limit"
    duration = fade_seconds(abs(limit - current), request.sweep_time)
    tenths = transition_tenths(duration)
    presets: list[Target] = []
    restores: frozenset[str] = frozenset()
    if up:
        command_id, level = zcl.MOVE_TO_LEVEL_WITH_ON_OFF, zcl.level(limit)
        lit_ids = {light.entity_id for light in lit_lights}
        presets = [light for light in lights if light.entity_id not in lit_ids and not drops_while_off(light)]
    elif limit == 0:
        command_id, level = zcl.MOVE_TO_LEVEL_WITH_ON_OFF, 0
        restores = frozenset(light.entity_id for light in movers if not drops_while_off(light))
    else:
        command_id, level = zcl.MOVE_TO_LEVEL, zcl.level(limit)
    command = (zcl.LEVEL_CLUSTER, command_id, {"level": level, "transition_time": tenths})
    moving_starts = {light.entity_id: starts[light.entity_id] for light in movers}
    return Fade(
        BRIGHTNESS,
        dict.fromkeys(moving_starts, command),
        movers,
        moving_starts,
        dict.fromkeys(moving_starts, limit),
        duration,
        presets,
        restores,
    )


def saturation_fade(cache: TransitionCache, request: RampRequest, lights: list[Target]) -> Fade | str:
    """The saturation fade toward the limit at each light's own hue, as an xy fade; off with no lit light in color,
    at_limit when there is none left to make. Group members at different hues each get their own command, so none
    takes another's hue; members at one hue share one, which a groupcast can carry."""
    if not (movers := [light for light in lit(cache, lights) if hs_color(light) is not None]):
        return "off"
    up, limit = request.up, request.end()
    starts = {light.entity_id: cache.value(light.entity_id, SATURATION, hs_color(light)[1]) for light in movers}
    current = mean(starts.values())
    if (limit - current if up else current - limit) < MIN_STEP:
        return "at_limit"
    duration = fade_seconds(abs(limit - current), request.sweep_time)

    def command(light: Target) -> Command:
        x, y = color_hs_to_xy(hs_color(light)[0], limit)
        params = {"color_x": round(x * 65535), "color_y": round(y * 65535)}
        return zcl.COLOR_CLUSTER, zcl.MOVE_TO_COLOR, params | {"transition_time": transition_tenths(duration)}

    commands = {light.entity_id: command(light) for light in movers}
    return Fade(SATURATION, commands, movers, starts, dict.fromkeys(starts, limit), duration)


def hue_move(request: RampRequest, movers: list[Target]) -> HueMove:
    """EnhancedMoveHue at the rate for the sweep_time, a full cycle, and the sweep_time used where it had to be clamped.

    Clamped, not refused: the call's value lies outside what the bulb can do, as an out-of-range duration does. Rounding
    the rate inside the range isn't reported.
    """
    cycle = min(max(request.sweep_time, MIN_CYCLE_S), MAX_CYCLE_S)
    rate = min(max(round(65535 / cycle), 1), 65535)
    mode = _MOVE_UP if request.up else _MOVE_DOWN
    command = (zcl.COLOR_CLUSTER, zcl.ENHANCED_MOVE_HUE, {"move_mode": mode, "rate": rate})
    return HueMove(command, movers, cycle if cycle != request.sweep_time else None)


async def sync_to_bulb(
    hass: HomeAssistant, cache: TransitionCache, light: Target, fade: Fade, recorded: transition.Transition
) -> None:
    """Fit the recorded ramp to a CurrentLevel read taken just after the fade was sent.

    The bulb fades from its real level, which a change made elsewhere (one ZHA can't tell from the bulb's own reports)
    leaves the prediction blind to. The read is timed at the middle of its round trip and lies on the bulb's ramp, which
    ends at the sent end point at the sent end time, so the ramp's real start is solved for and the fade re-recorded
    from it: the next move, a stop and the soft off's restore then start from where the bulb really is. Sent first and
    read after, so a move starts with no added latency; a read after the fade's end, or after a newer move or a stop
    took over, changes nothing. Nor does a read within the deadband of the prediction (FIT_LAG_S of the ramp, plus a
    level step): the bulb starts a little after the send, and fitting that lag would move a right start.
    """
    try:
        before = cache.clock()
        read = await zcl.read_attributes(hass, address(light.entry.unique_id), zcl.LEVEL_CLUSTER, (zcl.CURRENT_LEVEL,))
        after = cache.clock()
        at = (before + after) / 2
        level = read[zcl.CURRENT_LEVEL] * 100 / 254
    except Exception as err:  # noqa: BLE001 - the prediction stands, as on the other integrations
        _LOGGER.debug("Level read after a fade was sent failed for %s: %r", light.entity_id, err)
        return
    elapsed = (at - recorded.started_at) / recorded.duration if recorded.duration > 0 else 1.0
    if elapsed >= 1 or cache.live(light.entity_id, BRIGHTNESS) is not recorded:
        _LOGGER.debug(
            "Fit skipped for %s: read %.1f %% at f=%.3f, or a newer move or stop", light.entity_id, level, elapsed
        )
        return
    predicted = recorded.value(at)
    deadband = abs(recorded.target - recorded.start) / recorded.duration * FIT_LAG_S + MIN_STEP
    start = min(max((level - recorded.target * elapsed) / (1 - elapsed), 0.0), 100.0)
    kept = abs(level - predicted) <= deadband
    # Every term of the fit, so a restore that lands off can be traced to the read's timing.
    _LOGGER.debug(
        "Fit for %s: read %.1f %% in a %.3f s round trip at f=%.3f of %.1f s; ramp %.1f -> %.1f %%, predicted "
        "%.1f ± %.1f; %s",
        light.entity_id,
        level,
        after - before,
        elapsed,
        recorded.duration,
        recorded.start,
        recorded.target,
        predicted,
        deadband,
        "kept" if kept else f"fitted start {start:.1f}",
    )
    if kept:
        return
    fade.starts[light.entity_id] = start
    cache.moving(light.entity_id, BRIGHTNESS, start, recorded.target, recorded.duration, started_at=recorded.started_at)


def end_job(hass: HomeAssistant, light: Target, restore: dict[str, float] | None, context: Context | None) -> Job:
    """Once a fade has run: a soft off's restore of the light's start level (in restore, as last fitted), if the light
    reads off and a light call from HA hasn't since replaced the fade, then a refresh."""

    async def run() -> None:
        pending = soft_off_restores(hass)
        if restore is not None and light.entity_id in pending:
            pending.discard(light.entity_id)
            try:
                addr = address(light.entry.unique_id)
                read = await zcl.read_attributes(hass, addr, zcl.ON_OFF_CLUSTER, (zcl.ON_OFF,))
                if not read[zcl.ON_OFF]:
                    _LOGGER.debug("Restoring %s to %.1f %% after a soft off", light.entity_id, restore[light.entity_id])
                    params = {"level": zcl.level(restore[light.entity_id]), **zcl.execute_if_off(0)}
                    await zcl.command(
                        hass, addr, zcl.LEVEL_CLUSTER, zcl.MOVE_TO_LEVEL, params, context, entity_id=light.reported_id
                    )
            except Exception as err:  # noqa: BLE001 - the light stays off, and comes back on dim
                _LOGGER.warning("Restoring %s's level after a soft off failed: %r", light.entity_id, err)
        await refresh(hass, light, context)

    return run
