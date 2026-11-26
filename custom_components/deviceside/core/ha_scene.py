"""Home Assistant scenes: which entity IDs are one, and what each light in one asks for.

A scene is an entity in the `homeassistant` scene platform, found as core's `entities_in_scene` finds it, not through
the entity registry: a YAML scene with no `id` has no registry entry. Its states are read from the live entity on each
call, so an edit or reload applies, and a scene removed meanwhile reads as gone. `scene_config` is core-internal, so the
read is guarded as in `ha_entity`: a rename in HA reads as no scene, never an exception.

A light's state becomes the request core's `light/reproduce_state.py` would send, minus what `set_attributes` has no
field for (`effect`, `transition`), as Hue's `set_scene` skips effects.

The route (route): each light held on is a `set_attributes` target, indirect, through the scene as its group, so each is
planned, gated and sent as that action's, by its adapters; a light held off is turned off by core's `light.turn_off`, as
Hue's `set_scene` sends `on: false`. The scene gets one result, in Hue's `set_scene` vocabulary
(`integrations/hue/set_scene.py`); a light that can't take its write is skipped and logged, as a group's member is.
"""

import asyncio
import logging
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Final

from homeassistant.components.homeassistant.scene import DATA_PLATFORM
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_XY_COLOR,
    ColorMode,
)
from homeassistant.components.light.reproduce_state import COLOR_MODE_TO_ATTRIBUTE
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, STATE_OFF, STATE_ON, Platform
from homeassistant.core import DOMAIN as HA_DOMAIN
from homeassistant.core import HomeAssistant, State

from .action import Routed
from .dispatcher import Run, rank, skip
from .errors import describe
from .groups import expand_ha_groups
from .models import EntityResult, LightFields, Request, Skip, Status
from .resolver import resolve
from ..actions.set_attributes import SetAttributes, SetAttributesRequest
from ..const import ADAPTER_BACKSTOP_S, ADAPTER_TIMEOUT_S

if TYPE_CHECKING:
    from .dispatcher import Dispatcher

_LOGGER = logging.getLogger(__name__)

OFF: Final = "off"  # a light the scene holds off: turned off, not written
SKIPPED: Final = "skipped"  # a light whose state can't be read (its mode's color is missing): nothing is sent
# A SKIPPED light's skip reason, in the skipped-targets warning.
COLOR_MISSING: Final = "color_missing"
# A named scene's skip reason when each of its lights was left out as unavailable, in the skipped-targets warning.
LIGHTS_UNAVAILABLE: Final = "lights_unavailable"
LIGHTS: Final = frozenset({Platform.LIGHT})
LightWrite = SetAttributesRequest | str | None  # a request, OFF, SKIPPED, or None: on, nothing to write (unchanged)

_unreadable: set[str] = set()  # what of a scene HA no longer keeps as expected, already logged

# For a state with no color mode: core's COLOR_GROUP order (hs, color_temp, rgb, rgbw, rgbww, xy) less the two
# modes `set_attributes` can't write; an rgbw or rgbww state holds hs_color too, which comes first.
_COLORS = (ATTR_HS_COLOR, ATTR_COLOR_TEMP_KELVIN, ATTR_RGB_COLOR, ATTR_XY_COLOR)
# Modes whose own attribute `set_attributes` has no field for: they take the state's hs_color. White is not one: core's
# white is a brightness, and a white-mode state holds no color.
_HS_MODES = frozenset({ColorMode.RGBW, ColorMode.RGBWW})


def _scene_states(hass: HomeAssistant, entity_id: str) -> dict[str, State] | None:
    """The scene's states, or None if no such scene is loaded."""
    if (platform := hass.data.get(DATA_PLATFORM)) is None:
        return None
    if not isinstance(entities := getattr(platform, "entities", None), dict):
        _log_unreadable("EntityPlatform.entities")
        return None
    if (entity := entities.get(entity_id)) is None:
        return None
    states = getattr(getattr(entity, "scene_config", None), "states", None)
    if not isinstance(states, dict):
        _log_unreadable(f"{type(entity).__qualname__}.scene_config.states")
        return None
    return states


def _log_unreadable(what: str) -> None:
    if what not in _unreadable:
        _unreadable.add(what)
        _LOGGER.warning("%s is not what Home Assistant's scene platform held, so its scenes can't be read", what)


def is_ha_scene(hass: HomeAssistant, entity_id: str) -> bool:
    """Whether entity_id is a Home Assistant scene loaded now."""
    return _scene_states(hass, entity_id) is not None


def scene_lights(hass: HomeAssistant, entity_id: str) -> dict[str, LightWrite] | None:
    """What each light in the scene asks for, by entity_id, or None if the scene is gone.

    A non-light member (a switch, a cover) is left out at DEBUG: it isn't a fault. So is a light whose state is neither
    on nor off, as core's reproduce_state ignores it. A light that can't be read is SKIPPED, for the caller to count.
    """
    if (states := _scene_states(hass, entity_id)) is None:
        return None
    lights: dict[str, LightWrite] = {}
    for member, state in states.items():
        if member.partition(".")[0] != Platform.LIGHT:
            _LOGGER.debug("Scene %s: skipping %s, not a light", entity_id, member)
        elif state.state not in (STATE_ON, STATE_OFF):
            _LOGGER.debug("Scene %s: skipping %s, state %s is neither on nor off", entity_id, member, state.state)
        else:
            lights[member] = light_write(state)
    return lights


def light_write(state: State) -> LightWrite:
    """One light's scene state as OFF, a SetAttributesRequest, SKIPPED, or None when it is on with nothing to write."""
    if state.state == STATE_OFF:
        return OFF
    attributes = state.attributes
    brightness = attributes.get(ATTR_BRIGHTNESS)  # ha-255: HA state reports a byte
    if (light := _color(state)) is None:
        return SKIPPED
    request = SetAttributesRequest(
        light=light,
        # Level 1 is 0.4 %: no floor is raised. 0 is no level (core would turn the light off), so it writes nothing.
        brightness=brightness / 255 * 100 if brightness else None,  # ha-255: converts HA's byte to a percent
    )
    return None if request.nothing_to_do() else request


def _color(state: State) -> LightFields | None:
    """The state's one color, empty when it has none to write, None when its mode names a color it lacks."""
    attributes = state.attributes
    mode = attributes.get(ATTR_COLOR_MODE, ColorMode.UNKNOWN)
    if mode == ColorMode.UNKNOWN:  # a scene from before color modes: the first color present, as core does
        name = next((name for name in _COLORS if attributes.get(name) is not None), None)
    elif mode in _HS_MODES:
        name = ATTR_HS_COLOR
    elif mode == ColorMode.WHITE or mode not in COLOR_MODE_TO_ATTRIBUTE:  # white, onoff, brightness: no color
        name = None
    else:
        name = COLOR_MODE_TO_ATTRIBUTE[mode].parameter
    if name is None:
        return LightFields()
    value = attributes.get(name)
    if value is None:
        _LOGGER.warning("Skipping %s: its scene state names color mode %s but holds no %s", state.entity_id, mode, name)
        return None
    return LightFields.from_data({name: _typed(name, value)})


def _typed(name: str, value: Any) -> Any:
    """The value as LightFields holds it: YAML scenes give lists, where a light's own state gives tuples."""
    if name == ATTR_COLOR_TEMP_KELVIN:
        return int(value)
    if name == ATTR_RGB_COLOR:
        return tuple(int(part) for part in value)
    return tuple(float(part) for part in value)


# The route


@dataclass(slots=True)
class _Planned:
    """One scene, planned (_plan): the set_attributes runs, the lights to turn off, the results of the lights left
    nothing to write (`unchanged`, and `idle`: those ha_scene found so, which carry no result), and the integrations
    of the lights that carry no result (`unresolved`: turned off or idle)."""

    entity_id: str
    runs: list[Run] = field(default_factory=list)
    off: list[str] = field(default_factory=list)
    unchanged: list[EntityResult] = field(default_factory=list)
    idle: list[str] = field(default_factory=list)
    unresolved: set[str] = field(default_factory=set)


def route(hass: HomeAssistant, request: Request, claimed: dict[str, bool], dispatcher: Dispatcher) -> Routed:
    """Plan each scene claimed (each entity_id to whether the caller named it), as Action.route says, and send them
    concurrently by the Routed's run."""
    results: list[EntityResult] = []
    planned = [
        scene
        for entity_id, named in claimed.items()
        if (scene := _plan(hass, request, entity_id, named, dispatcher, results))
    ]

    async def run() -> list[EntityResult]:
        sent: list[EntityResult] = []
        for scene_results in await asyncio.gather(*(_run(hass, request, scene, dispatcher) for scene in planned)):
            sent += scene_results
        return sent

    return Routed(results, run)


def _plan(
    hass: HomeAssistant,
    request: Request,
    entity_id: str,
    named: bool,
    dispatcher: Dispatcher,
    results: list[EntityResult],
) -> _Planned | None:
    """One scene's plan, or None when it has nothing to send; its skips, and a result it has without sending, go in
    results. Lights held on with the same write are planned as one set_attributes call on them, HA groups expanded
    and each light indirect, through the scene. A scene none of whose lights can run is refused with their ranked
    reason (rank), raised if named with that light's refusal text; one whose lights were each left out as
    unavailable gets no result, and is logged as skipped if named, as core logs a named target it can't find."""
    if (lights := scene_lights(hass, entity_id)) is None:  # removed since the call began
        results.append(EntityResult(entity_id, Status.REJECTED, integration=HA_DOMAIN, detail="scene_not_found"))
        return None
    scene = _Planned(entity_id)
    skipped: list[EntityResult] = []
    by_write = _sort(request, lights, scene, skipped)
    for write, ids in by_write.items():
        write = replace(write, context=request.context)
        members, _ = expand_ha_groups(hass, ids)
        unresolved, targets, _ = dispatcher.resolve_targets(
            LIGHTS, set(), {member: via or entity_id for member, via in members.items()}
        )
        planned, runs = dispatcher.plan_adapters(SetAttributes.key, write, targets)
        skipped += unresolved
        for result in planned:
            (skipped if result.status is Status.UNSUPPORTED else scene.unchanged).append(result)
        scene.runs += runs
    scene.unresolved = _integrations(hass, dispatcher, [*scene.off, *scene.idle])
    results += skipped
    _LOGGER.debug(
        "set_scene %s: %d set_attributes runs, %d lights to turn off, %d skipped",
        entity_id,
        len(scene.runs),
        len(scene.off),
        len(skipped),
    )
    if scene.runs or scene.off or scene.unchanged or scene.idle or not lights:
        return scene
    # No light could run: refused with the most useful light's reason and refusal text.
    if best := min((r for r in skipped if r.detail), key=lambda r: rank(r.detail), default=None):
        why, title = (best.why, best.title) if isinstance(best, Skip) else (None, None)
        results += skip(entity_id, named, best.detail, HA_DOMAIN, why, title)
    elif named:  # each light left out as unavailable
        results.append(EntityResult(entity_id, Status.UNSUPPORTED, integration=HA_DOMAIN, detail=LIGHTS_UNAVAILABLE))
    return None


def _integrations(hass: HomeAssistant, dispatcher: Dispatcher, lights: list[str]) -> set[str]:
    """The integrations of the lights (HA groups expanded) that DeviceSide resolves, for the scene's `integration`."""
    members, _ = expand_ha_groups(hass, lights)
    return {
        target.integration
        for member in members
        if not isinstance(target := resolve(hass, dispatcher.registry, member), str)
    }


def _sort(
    request: Request, lights: dict[str, LightWrite], scene: _Planned, skipped: list[EntityResult]
) -> dict[SetAttributesRequest, list[str]]:
    """The lights held on with something to write, grouped by their write; the rest go to
    the scene's off lights, its idle count, or `skipped`."""
    by_write: dict[SetAttributesRequest, list[str]] = {}
    for light, write in lights.items():
        if isinstance(write, SetAttributesRequest):  # ha_scene's writes carry no context, so they hash
            by_write.setdefault(write, []).append(light)
        elif write == OFF:
            scene.off.append(light)
        elif write == SKIPPED:
            skipped.append(EntityResult(light, Status.UNSUPPORTED, detail=COLOR_MISSING))
        else:
            scene.idle.append(light)
    return by_write


async def _run(hass: HomeAssistant, request: Request, scene: _Planned, dispatcher: Dispatcher) -> list[EntityResult]:
    """Send one scene's runs and turn its off lights off, concurrently, then fold the lights' results into the scene's
    (_fold). A light an adapter skipped while running (an empty group) is no failure: its result is kept beside the
    scene's, for the skipped-targets warning."""
    written, off_failed = await asyncio.gather(dispatcher.run_planned(scene.runs), _turn_off(hass, request, scene))
    skipped = [result for result in written if result.status is Status.UNSUPPORTED]
    reached = [result for result in written if result.status is not Status.UNSUPPORTED]
    return [_fold(scene, reached, off_failed), *skipped]


def _fold(scene: _Planned, reached: list[EntityResult], off_failed: int) -> EntityResult:
    """The scene's result: rejected if any light failed (error if each written or turned off did), sent if any was
    written or turned off, else unchanged. Its integration is its lights' when they share one, else homeassistant;
    `member_classes` maps each light the call reached to its class, as a native group's entry does."""
    integrations = {r.integration for r in (*reached, *scene.unchanged) if r.integration} | scene.unresolved
    integration = integrations.pop() if len(integrations) == 1 else HA_DOMAIN
    if failed := sum(result.status is Status.REJECTED for result in reached) + off_failed:
        detail = "error" if failed == len(reached) + len(scene.off) else "some_lights_failed"
        return EntityResult(scene.entity_id, Status.REJECTED, integration=integration, detail=detail)
    classes: dict[str, str] = {}
    for result in (*reached, *scene.unchanged):
        if isinstance(result.classes, str):
            classes[result.entity_id] = result.classes
        classes |= result.member_classes or {}
    folded = EntityResult(scene.entity_id, Status.UNCHANGED, integration=integration, detail="nothing_to_set")
    if scene.off or any(result.status is not Status.UNCHANGED for result in reached):
        folded = EntityResult(scene.entity_id, Status.SENT, integration=integration)
    folded.member_classes = dict(sorted(classes.items())) or None
    return folded


async def _turn_off(hass: HomeAssistant, request: Request, scene: _Planned) -> int:
    """Turn the scene's off lights off with the caller's context, in one blocking call bounded as an adapter's run
    is: how many failed."""
    if not scene.off:
        return 0
    _LOGGER.debug("set_scene %s: light.turn_off %s", scene.entity_id, ", ".join(scene.off))
    try:
        async with asyncio.timeout(ADAPTER_TIMEOUT_S + ADAPTER_BACKSTOP_S):
            await hass.services.async_call(
                Platform.LIGHT, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: scene.off}, blocking=True, context=request.context
            )
    except TimeoutError:
        _LOGGER.warning(
            "set_scene %s: turning off %s timed out after %ss, so they may stay on",
            scene.entity_id,
            ", ".join(scene.off),
            ADAPTER_TIMEOUT_S + ADAPTER_BACKSTOP_S,
        )
        return len(scene.off)
    except Exception as err:  # noqa: BLE001 - the scene's other lights still get their writes and a result
        _LOGGER.warning(
            "set_scene %s: turning off %s failed: %s, so they may stay on",
            scene.entity_id,
            ", ".join(scene.off),
            describe(err),
        )
        return len(scene.off)
    return 0
