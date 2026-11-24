"""Matter raise and lower: brightness and saturation as one MoveTo with a TransitionTime for the distance left, from the
level the light reports (core.level_fade), and hue as a MoveHue or EnhancedMoveHue cycle the light runs until a stop.

A lower to 0 is the light's soft off, after which its start level goes back with ExecuteIfOff, so it stays off and its
next On comes up where it was, as on ZHA and Hue (plan Decisions 4 to 6; docs/integrations/matter/research/
2026-11-24-level-color.md)."""

import asyncio
import logging
from typing import ClassVar

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .addressing import (
    EXECUTE_IF_OFF,
    NO_OVERRIDE,
    color_features,
    color_path,
    level_path,
    light_reason,
    make_command,
    matter_client,
    node_for,
    node_id_from_unique_id,
    onoff_attr_path,
    onoff_endpoint,
)
from .classes import LIGHT_ACTIONS
from ...actions.ramp import RampRequest
from ...core.adapter import Adapter
from ...core.errors import Reason, describe
from ...core.fields import BRIGHTNESS_FIELD
from ...core.ha_watch import ALL, Call, Entries
from ...core.level_fade import LevelFade, Reading
from ...core.models import EntityResult, Status, Target
from ...core.runtime import Job, get_runtime
from ...core.scope import AdapterScope, DurationLimits, labs
from ...core.transition import SATURATION
from ...core.zcl import (
    CURRENT_LEVEL,
    CURRENT_SATURATION,
    ENHANCED_HUE,
    ENHANCED_HUE_STEPS,
    HUE_SATURATION,
    HUE_STEPS,
    MAX_TENTHS_S,
    MOVE_DOWN,
    MOVE_UP,
)
from ...core.zcl_fade import MIN_STEP, hue_cycle
from ...core.zcl_write import level

_LOGGER = logging.getLogger(__name__)

# TransitionTime is a uint16 in tenths (core/zcl.py): a full-range fade runs 0.1 s to MAX_TENTHS_S.
FADE_LIMITS = DurationLimits(min_s=0.1, max_s=MAX_TENTHS_S)
# The soft off's restore runs this long after the fade's end, so the light has reached off: ZHA's END_REFRESH_S, which
# its bulbs settle within (ZHA probe 13f). No Matter light has measured it (plan Decision 1).
RESTORE_AFTER_S = 1.0
# CurrentLevel and CurrentSaturation, 0-254 (Level and Color Control), per percent.
_STEPS_PER_PERCENT = 254 / 100


def soft_off_restores(hass: HomeAssistant) -> dict[str, object]:
    """The lights a soft off of ours will put back at their start level once it has run, each with the token its restore
    job holds: a later move, a stop or a light call from HA takes the entry, and the job then finds it isn't its own."""
    return get_runtime(hass).integration_state.setdefault("matter_restores", {})


def hue_moves(hass: HomeAssistant) -> set[str]:
    """The lights a hue move of ours is cycling: it runs until a stop."""
    return get_runtime(hass).integration_state.setdefault("matter_hue_moves", set())


def restore_key(entity_id: str) -> str:
    """The key a soft off's restore job is scheduled under."""
    return f"matter:restore:{entity_id}"


def cancel_restore(hass: HomeAssistant, entity_id: str) -> None:
    """Drop the light's pending soft-off restore, if any: a stop, or a light call from HA, replaces our fade."""
    soft_off_restores(hass).pop(entity_id, None)
    get_runtime(hass).schedule(hass, restore_key(entity_id), [])


def light_lock(hass: HomeAssistant, target: Target) -> asyncio.Lock:
    """One lock per light, held by a move from its read to its MoveTo (LevelFade.guard), so a stop that arrives during
    a move goes out after it rather than ahead of it."""
    locks = get_runtime(hass).integration_state.setdefault("matter_light_locks", {})
    return locks.setdefault(target.entity_id, asyncio.Lock())


class MatterCallResolver:
    """Drop a Matter light's pending soft-off restore when a light call from HA targets it, as on ZHA: the call replaces
    our fade. A call that sets a color or turns the light off ends its hue cycle. Our own commands go to the node, not
    through the light domain, so they pass the watch by."""

    def busy(self, hass: HomeAssistant) -> bool:
        return bool(soft_off_restores(hass) or hue_moves(hass))

    def forget(self, hass: HomeAssistant, call: Call, entries: Entries) -> None:
        cycling = hue_moves(hass)
        if entries is ALL:
            light_ids = list(soft_off_restores(hass)) + list(cycling)
        else:
            light_ids = [entry.entity_id for entry in entries if entry.domain == Platform.LIGHT]
        for light_id in light_ids:
            if light_id in soft_off_restores(hass):
                cancel_restore(hass, light_id)
            if call.ends_hue_cycle:
                cycling.discard(light_id)


def fade_scope(attribute: str) -> AdapterScope:
    """A raise or lower's scope: the light actions' classes, in Labs (plan Decision 2)."""
    return AdapterScope(domains=labs(Platform.LIGHT), fields=labs(attribute), capabilities=LIGHT_ACTIONS)


class _Light:
    """A target's node address, read from its unique ID and the client, which supports() has checked."""

    def __init__(self, hass: HomeAssistant, target: Target) -> None:
        self.node_id = node_id_from_unique_id(target.entry.unique_id)
        self.ep_id = onoff_endpoint(target.entry.unique_id)
        self.client = matter_client(hass, target.entry.config_entry_id)

    async def read(self, path: str) -> object:
        return (await self.client.read_attribute(node_id=self.node_id, attribute_path=path)).get(path)

    async def send(self, target: Target, cluster: str, command: str, **fields: int) -> None:
        _LOGGER.debug("%s: sending matter %s.%s %s", target.reported_id, cluster, command, fields)
        await self.client.send_device_command(
            node_id=self.node_id, endpoint_id=self.ep_id, command=make_command(cluster, command, **fields)
        )


def _percent(value: object) -> float:
    """A CurrentLevel or CurrentSaturation as a percent; a null one (a level the light doesn't know) as 0."""
    return value / _STEPS_PER_PERCENT if isinstance(value, int) and not isinstance(value, bool) else 0.0


def _tenths(seconds: float) -> int:
    return round(seconds * 10)


class MatterFade(LevelFade):
    """core.level_fade's read and set: OnOff and CurrentLevel (or CurrentSaturation) read live, then one MoveTo with a
    TransitionTime for the distance left. A live read, not the subscription's cache: the reference server interpolates
    mid-transition, and a subscription reports at most once per max(1 s, T/4) (plan Decision 4). heading_there is
    always False: the light reports where it is, so a move from there is right.

    Brightness: raising is MoveToLevelWithOnOff, which turns the light on; one that is off is first set to level 1 with
    MoveToLevel and ExecuteIfOff, so it fades in from the bottom rather than its stored level. Lowering to a limit is
    MoveToLevel. Lowering to 0 is MoveToLevelWithOnOff to 0, the light's soft off; RESTORE_AFTER_S after it has run, if
    the light reads off, MoveToLevel with ExecuteIfOff puts back the level it started from. A later move, a stop or a
    light call from HA drops that restore. Saturation is MoveToSaturation on a lit light (raises_from_off is False, so
    an off one is unchanged with off), and a light without the HS feature is unchanged with fields_dropped.
    """

    integration: ClassVar[str] = "matter"
    # BRIGHTNESS_FIELD or SATURATION: the attribute the action moves.
    attribute: ClassVar[str]
    fade_limits = FADE_LIMITS
    min_step: ClassVar[float] = MIN_STEP

    def __init__(self) -> None:
        # Each light's reading, from read() to fade_to(), which the light's lock (guard) holds together.
        self._readings: dict[str, Reading] = {}

    def supports(self, hass: HomeAssistant, request: RampRequest, target: Target) -> str | None:
        if (reason := super().supports(hass, request, target)) is not None or request.nothing_to_do():
            return reason
        return light_reason(hass, target)

    def unaddressable(self, target: Target) -> str | None:
        """The unique ID's part of the address; supports() checks the node, which needs hass."""
        return Reason.NOT_ADDRESSABLE if onoff_endpoint(target.entry.unique_id) is None else None

    def guard(self, hass: HomeAssistant, target: Target) -> asyncio.Lock:
        return light_lock(hass, target)

    async def execute(self, hass: HomeAssistant, request: RampRequest, targets: list[Target]) -> list[EntityResult]:
        if request.attribute != SATURATION:
            return await super().execute(hass, request, targets)

        def has_hs(target: Target) -> bool:
            node = node_for(hass, target)
            return node is not None and bool(
                color_features(node, onoff_endpoint(target.entry.unique_id)) & HUE_SATURATION
            )

        movers = [target for target in targets if has_hs(target)]
        dropped = [
            self.result(target, Status.UNCHANGED, detail="fields_dropped") for target in targets if target not in movers
        ]
        return [*dropped, *(await super().execute(hass, request, movers) if movers else [])]

    async def read(self, hass: HomeAssistant, target: Target, end: float) -> Reading:
        light = _Light(hass, target)
        on_off = await light.read(onoff_attr_path(light.ep_id))
        path = (
            level_path(light.ep_id, CURRENT_LEVEL)
            if self.attribute == BRIGHTNESS_FIELD
            else color_path(light.ep_id, CURRENT_SATURATION)
        )
        reading = Reading(on_off is True, _percent(await light.read(path)))
        self._readings[target.entity_id] = reading
        return reading

    async def fade_to(self, hass: HomeAssistant, target: Target, end: float, seconds: float) -> None:
        reading = self._readings.pop(target.entity_id)
        light = _Light(hass, target)
        tenths = _tenths(seconds)
        if self.attribute != BRIGHTNESS_FIELD:
            saturation = round(end * _STEPS_PER_PERCENT)
            await light.send(
                target, "ColorControl", "MoveToSaturation", saturation=saturation, transitionTime=tenths, **NO_OVERRIDE
            )
            hue_moves(hass).discard(target.entity_id)  # a color move ends the light's hue cycle
            return
        restores = soft_off_restores(hass)
        # A move of ours replaces the light's pending restore: taken before the send, so its job can't run during it.
        earlier = restores.pop(target.entity_id, None)
        mine = restores[target.entity_id] = object()
        soft_off = end == 0
        try:
            if end > reading.level or not reading.lit:
                if not reading.lit:
                    await light.send(target, "LevelControl", "MoveToLevel", level=1, transitionTime=0, **EXECUTE_IF_OFF)
                await light.send(
                    target,
                    "LevelControl",
                    "MoveToLevelWithOnOff",
                    level=level(end),
                    transitionTime=tenths,
                    **NO_OVERRIDE,
                )
            elif soft_off:
                await light.send(
                    target, "LevelControl", "MoveToLevelWithOnOff", level=0, transitionTime=tenths, **NO_OVERRIDE
                )
            else:
                await light.send(
                    target, "LevelControl", "MoveToLevel", level=level(end), transitionTime=tenths, **NO_OVERRIDE
                )
        except BaseException:
            # Nothing replaced the earlier restore, unless a light call from HA took the entry meanwhile.
            if restores.get(target.entity_id) is mine:
                if earlier is None:
                    del restores[target.entity_id]
                else:
                    restores[target.entity_id] = earlier
            else:
                cancel_restore(hass, target.entity_id)
            raise
        if soft_off and restores.get(target.entity_id) is mine:
            job = _restore_job(hass, target, reading.level, mine)
            get_runtime(hass).schedule(
                hass, restore_key(target.entity_id), [(seconds + RESTORE_AFTER_S, job)], must_run=True
            )
        else:
            if restores.get(target.entity_id) is mine:
                del restores[target.entity_id]
            get_runtime(hass).schedule(hass, restore_key(target.entity_id), [])


def _restore_job(hass: HomeAssistant, target: Target, start: float, token: object) -> Job:
    """Once a soft off has run: put the light's start level back with ExecuteIfOff, if the restore is still this one's
    and the light reads off, so its next On comes up where it was. A light that reads on (turned on elsewhere) keeps
    its level."""

    async def run() -> None:
        # Under the light's lock, so a move's read-to-send can't interleave with the restore's.
        async with light_lock(hass, target):
            restores = soft_off_restores(hass)
            if restores.get(target.entity_id) is not token:
                return
            try:
                light = _Light(hass, target)
                off = await light.read(onoff_attr_path(light.ep_id)) is False
                if restores.get(target.entity_id) is not token:  # a light call from HA took it during the read
                    return
                del restores[target.entity_id]
                if off:
                    _LOGGER.debug("Restoring %s to %.1f %% after a soft off", target.entity_id, start)
                    await light.send(
                        target, "LevelControl", "MoveToLevel", level=level(start), transitionTime=0, **EXECUTE_IF_OFF
                    )
            except Exception as err:  # noqa: BLE001 - the light stays off, and comes back on dim
                if restores.get(target.entity_id) is token:
                    del restores[target.entity_id]
                _LOGGER.warning(
                    "matter couldn't put back %s's level after a soft off: %s, so its next plain turn on comes up dim",
                    target.entity_id,
                    describe(err),
                )

    return run


class MatterHueMove(Adapter[RampRequest]):
    """Cycle hue up or down the wheel until a stop: EnhancedMoveHue where the light has the EHUE feature, else MoveHue,
    at the rate for the sweep_time (core.zcl_fade.hue_cycle), clamped to what the command's rate can carry, with
    clamped_to. A light without the HS feature is unchanged with fields_dropped, one that reads off with off. The
    lights cycling are in hue_moves, for a stop."""

    integration: ClassVar[str] = "matter"

    def supports(self, hass: HomeAssistant, request: RampRequest, target: Target) -> str | None:
        if (reason := super().supports(hass, request, target)) is not None or request.nothing_to_do():
            return reason
        return light_reason(hass, target)

    async def execute(self, hass: HomeAssistant, request: RampRequest, targets: list[Target]) -> list[EntityResult]:
        async def move(target: Target) -> EntityResult:
            light = _Light(hass, target)
            features = color_features(node_for(hass, target), light.ep_id)
            if not features & HUE_SATURATION:
                return self.result(target, Status.UNCHANGED, detail="fields_dropped")
            if await light.read(onoff_attr_path(light.ep_id)) is not True:
                return self.result(target, Status.UNCHANGED, detail="off")
            command, steps = (
                ("EnhancedMoveHue", ENHANCED_HUE_STEPS) if features & ENHANCED_HUE else ("MoveHue", HUE_STEPS)
            )
            rate, clamped_to = hue_cycle(request.sweep_time, steps, steps)
            mode = MOVE_UP if request.up else MOVE_DOWN
            await light.send(target, "ColorControl", command, moveMode=mode, rate=rate, **NO_OVERRIDE)
            hue_moves(hass).add(target.entity_id)
            return self.result(target, Status.SENT, clamped_to=clamped_to)

        return await self.gather(hass, targets, move, hold=lambda target: light_lock(hass, target))
