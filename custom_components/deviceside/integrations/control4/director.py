"""Which Director item a Control4 light entity drives, and the calls the adapters send to it.

The core control4 integration keeps one pyControl4 C4Director per config entry (runtime_data.director); the adapters
borrow it, so they add no connection and no credentials. Read from the registry and the config entry only, never from
pyControl4 or homeassistant.components.control4 at import time: importing either would make this module unavailable
wherever Control4 isn't installed. docs/integrations/control4/internals.md has the measurements cited below.
"""

import asyncio
import json
import logging
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from homeassistant.components.light import ATTR_SUPPORTED_COLOR_MODES, brightness_supported
from homeassistant.core import HomeAssistant

from ...core.errors import Reason
from ...core.models import Target
from ...core.runtime import get_runtime
from ...core.scope import DurationLimits

_LOGGER = logging.getLogger(__name__)
# Named here so a test can time the read-back's waits without touching asyncio's own sleep.
_sleep = asyncio.sleep

# The tested lights report "Brightness Percent" (0-100) and no LIGHT_LEVEL (Tested behavior). LIGHT_LEVEL is read
# only so a light that reports it alone shows in the log; it isn't parsed.
BRIGHTNESS_PERCENT = "Brightness Percent"
LIGHT_LEVEL = "LIGHT_LEVEL"
# Where a ramp in flight is heading; equal to the level at rest, lit or off (Tested behavior).
BRIGHTNESS_TARGET = "Brightness Target Percent"
LEVEL_VARIABLES = (BRIGHTNESS_PERCENT, LIGHT_LEVEL, BRIGHTNESS_TARGET)

# On or off. Core shows an item that reports this and no level as an on/off light.
LIGHT_STATE = "LIGHT_STATE"
# The color temperature the light is at, in kelvin, and its color mode: 1 is color temperature, the only
# mode measured (Tested behavior). An off light shows what it last had, bar a moment after a write.
CURRENT_CCT = "Current CCT"
# Where a lit light's color temperature is heading; it equals the current one at rest. Off, see CURRENT_CCT.
TARGET_CCT = "Target CCT"
TARGET_COLOR_MODE = "Target Color Mode"
COLOR_MODE = "Current Color Mode"
_MODE_CCT = 1
# The Director's color temperature variables hold tens of kelvin (Tested behavior).
_KELVIN_STEP = 10
# What the light itself can do, as the Director hands it over: {"DynamicCapabilities": {...}}.
CAPABILITIES = "Navigator Dynamic Capabilities"

# RAMP_TO_LEVEL's TIME is sent as whole milliseconds. A Zigbee bulb's driver caps a rate at 65535 ms; a group's takes
# far longer, but a call may reach either, so the bulb's ceiling bounds both (Tested behavior).
RAMP_LIMITS = DurationLimits(min_s=0.001, max_s=65.535)

# SET_BRIGHTNESS_STOP halts a ramp in flight, whichever way it runs, and changes nothing on a light at rest (Tested
# behavior). A light's own capabilities say whether it takes it (supports_brightness_stop). A button release halts a
# ramp too, but SET_BRIGHTNESS_STOP is the command made for it.
_STOP = "SET_BRIGHTNESS_STOP"

# The Director takes a command without waiting for the light. Over 20 stops timed from the moment each was sent
# (Tested behavior; the reply came 8-26 ms later in all but two): a read sent on the reply still showed the ramp in
# 15, the halt showed by a quarter of a second after the reply in 19, and one was not shown within 350 ms. So the
# first read waits, and later ones back off, a little over a second in all.
SETTLE_DELAYS_S = (0.1, 0.15, 0.3, 0.6)
# A move that halts a ramp first waits inside its concurrency slot, so it takes only the first two: a quarter of a
# second from the stop's reply, by when 19 of the 20 halts had shown.
MOVE_SETTLE_DELAYS_S = SETTLE_DELAYS_S[:2]

_LOCKS_KEY = "control4_item_locks"
_RAMP_KEY = "control4_ramp_ends"


@dataclass(frozen=True, slots=True)
class LightLevel:
    """What the Director holds for one light: its level, and where a ramp is taking it (None if it reports none)."""

    brightness: float
    target: float | None

    @property
    def on(self) -> bool:
        """Lit at any level. The level alone decides, so on and the level a ramp is sized from never disagree."""
        return self.brightness > 0

    @property
    def ramping(self) -> bool:
        """True while the level is still on its way to a target."""
        # The Director holds whole percents, so level and target are equal at rest (Tested behavior).
        return self.target is not None and self.target != self.brightness


def item_id(target: Target) -> int | None:
    """The Director item behind the entity: core's control4/entity.py sets the entity's unique_id to the item's id."""
    unique_id = str(target.entry.unique_id)
    return int(unique_id) if unique_id.isdecimal() else None


def director(target: Target) -> Any | None:
    """The pyControl4 C4Director the core integration holds for the entity's config entry."""
    return getattr(getattr(target.config_entry, "runtime_data", None), "director", None)


def unsupported_reason(target: Target) -> str | None:
    """Why this entity can't take a Director call at all, or None."""
    if director(target) is None or item_id(target) is None:
        return Reason.NOT_ADDRESSABLE
    return None


def dimmable(target: Target) -> bool:
    """False only for a light whose state says it has no brightness: core shows an item with LIGHT_STATE alone as an
    on/off light. A state that doesn't list its color modes says nothing, so the light counts as dimmable."""
    attributes = target.state.attributes if target.state is not None else {}
    modes = attributes.get(ATTR_SUPPORTED_COLOR_MODES)
    return modes is None or brightness_supported(modes)


def item_lock(hass: HomeAssistant, target: Target) -> asyncio.Lock:
    """One lock per Director item, passed to gather() as its `hold`, so it is taken before the concurrency slot and a
    call waiting on a busy light holds none. Held by a move from its read to its ramp (a halt of a ramp already running
    included) and by a stop for its halt, so a stop that arrives during a move is sent after the ramp that
    move starts instead of slipping in ahead of it."""
    locks = get_runtime(hass).integration_state.setdefault(_LOCKS_KEY, {})
    return locks.setdefault(_item_key(target), asyncio.Lock())


def _number(value: Any) -> float | None:
    """A variable's value as a number. The Director sends a number for most, and text ("0") for a light that has
    never reported, which is why core's own comparison of it fails."""
    try:
        return float(value)
    except TypeError, ValueError:
        return None


def parse_level(held: dict[str, Any]) -> LightLevel:
    """The light's level from the variables the Director holds for it. One the item lacks is absent; a level that
    can't be read raises, so the target is rejected instead of moved from a guess."""
    brightness = _number(held.get(BRIGHTNESS_PERCENT))
    # NaN fails the comparison too: a level outside 0-100 is nothing to size a ramp from.
    if brightness is None or not 0 <= brightness <= 100:
        raise ValueError(f"the Director reported no usable light level: {held!r}")
    target = _number(held.get(BRIGHTNESS_TARGET))
    if target is not None and not 0 <= target <= 100:
        # No place a ramp can be heading: read as a driver that reports none, so nothing is confirmed from it.
        target = None
    return LightLevel(brightness=brightness, target=target)


def _kelvin(value: Any) -> int | None:
    """A variable's value as a whole kelvin; None for one that is absent, zero or not a finite number."""
    number = _number(value)
    return round(number) if number and math.isfinite(number) else None


def color_temperature(held: dict[str, Any]) -> int | None:
    """The light's color temperature in kelvin, or None when it isn't in color temperature mode or reports none."""
    return _kelvin(held.get(CURRENT_CCT)) if _number(held.get(COLOR_MODE)) == _MODE_CCT else None


def heading_for(held: dict[str, Any], kelvin: int) -> bool:
    """Whether the light is at the kelvin or heading for it. The Director shows a new color temperature as the
    target within 0.2 s and as current most of a second later (Tested behavior), so the target is the first sign of
    the command. Whether a lit light that doesn't obey, as a bulb with no power, still shows it as its target is
    unmeasured. Either counts only in color temperature mode, so a light left in full color with an old target
    isn't taken for one that obeyed."""
    heading = _shows(_kelvin(held.get(TARGET_CCT)), kelvin) and _number(held.get(TARGET_COLOR_MODE)) == _MODE_CCT
    return heading or _shows(color_temperature(held), kelvin)


def _shows(reported: int | None, kelvin: int) -> bool:
    """Whether a kelvin the Director reports is the one sent. It reports a color temperature in tens of kelvin,
    rounded down: 2203 sent reads 2200, and 2956 reads 2950 (Tested behavior)."""
    return reported is not None and 0 <= kelvin - reported < _KELVIN_STEP


def kelvin_range(held: dict[str, Any]) -> tuple[int, int] | None:
    """The color temperatures the light takes, from its own capabilities variable; None when the light has no such
    variable or says it takes none. Core's light entity shows no color temperature, so only the device can say.
    Capabilities that can't be read, or that claim a color temperature with no real range, raise: that light is
    rejected, not passed off as one that lacks the field."""
    capabilities = held.get(CAPABILITIES)
    if capabilities is None:
        return None
    dynamic = capabilities.get("DynamicCapabilities") if isinstance(capabilities, dict) else None
    if not isinstance(dynamic, dict):
        raise ValueError(f"the Director reported capabilities that can't be read: {capabilities!r}")
    if dynamic.get("supports_color_correlated_temperature") is not True:
        return None
    low = _number(dynamic.get("color_correlated_temperature_min"))
    high = _number(dynamic.get("color_correlated_temperature_max"))
    if low is None or high is None or not 0 < low <= high < math.inf:
        raise ValueError(f"the Director reported no usable color temperature range: {low} to {high}")
    return round(low), round(high)


async def _call(hass: HomeAssistant, target: Target, method: str, *args: Any) -> Any:
    """One request on the Director core holds now. An expired token (BadToken) fails the call until core's own poll
    refreshes it, as for core's own commands."""
    return await getattr(director(target), method)(*args)


async def settle[HeldT](
    target: Target, read: Callable[[], Awaitable[HeldT]], settled: Callable[[HeldT], bool], *, brief: bool = False
) -> HeldT:
    """Read until `settled` rules the read shows the write, or the Director has had SETTLE_DELAYS_S (`brief`:
    MOVE_SETTLE_DELAYS_S); the last read either way. The waits sit before the reads, so a caller outside a
    concurrency slot whose `read` takes one holds none while waiting."""
    first, *later = MOVE_SETTLE_DELAYS_S if brief else SETTLE_DELAYS_S
    await _sleep(first)
    held = await read()
    for delay in later:
        if settled(held):
            break
        _LOGGER.debug("%s: director doesn't show the write yet; reading again", target.reported_id)
        await _sleep(delay)
        held = await read()
    return held


async def read_variables(hass: HomeAssistant, target: Target, names: tuple[str, ...]) -> dict[str, Any]:
    """The named variables as the Director holds them now, by name, logged as read; one the item lacks is absent.
    Only a row's name and value are kept: its item id is a device address. An error propagates."""
    uri = f"/api/v1/items/{item_id(target)}/variables?varnames={','.join(quote(name) for name in names)}"
    raw = await _call(hass, target, "send_get_request", uri)
    rows = json.loads(raw)
    held = {row["varName"]: row.get("value") for row in rows if row.get("varName") in names}
    _LOGGER.debug("%s: director reports %s", target.reported_id, held)
    return held


async def read_level(hass: HomeAssistant, target: Target) -> LightLevel:
    """The light's level as the Director holds it now; an error propagates."""
    return parse_level(await read_variables(hass, target, LEVEL_VARIABLES))


async def send(hass: HomeAssistant, target: Target, command: str, params: dict[str, Any]) -> None:
    """One command to the target's Director item, logged without its item id; an error propagates."""
    _LOGGER.debug("%s: sending director %s %s", target.reported_id, command, params)
    await _call(hass, target, "send_post_request", f"/api/v1/items/{item_id(target)}/commands", command, params)


def whole_percent(percent: float) -> int:
    """A brightness percent as the whole-percent level the adapter sends RAMP_TO_LEVEL. Only 0 is 0, which ends off:
    anything above it is at least 1, so a low limit never switches the light off."""
    return 0 if percent <= 0 else max(1, round(percent))


async def ramp_to_level(hass: HomeAssistant, target: Target, brightness: float, duration_s: float) -> None:
    """RAMP_TO_LEVEL: the light runs the ramp itself, from its current level, to a whole percent over whole
    milliseconds (the adapter's rounding). Level 0 ends off, as core's own turn-off sends it."""
    params = {"LEVEL": whole_percent(brightness), "TIME": round(duration_s * 1000)}
    await send(hass, target, "RAMP_TO_LEVEL", params)
    over_by = hass.loop.time() + params["TIME"] / 1000
    _ramp_ends(hass)[_item_key(target)] = (params["LEVEL"], over_by)


def _item_key(target: Target) -> tuple[str, int | None]:
    return target.config_entry.entry_id, item_id(target)


def _ramp_ends(hass: HomeAssistant) -> dict[tuple[str, int | None], tuple[int, float]]:
    return get_runtime(hass).integration_state.setdefault(_RAMP_KEY, {})


def own_ramp_end(hass: HomeAssistant, target: Target) -> int | None:
    """The level of DeviceSide's last RAMP_TO_LEVEL to the light, until its TIME has passed or a stop is sent."""
    level, over_by = _ramp_ends(hass).get(_item_key(target), (None, 0.0))
    if level is not None and hass.loop.time() >= over_by:
        _LOGGER.debug("%s: own ramp to %s ran its time; not taken for the one running", target.reported_id, level)
        del _ramp_ends(hass)[_item_key(target)]
        return None
    return level


async def set_color_temperature(hass: HomeAssistant, target: Target, kelvin: int) -> None:
    """SET_COLOR_TARGET in color temperature mode, as pyControl4 2.0.2's own set_color_temperature sends it. A light
    that is off stays off and comes on at it (Tested behavior)."""
    params = {"LIGHT_COLOR_TARGET_COLOR_CORRELATED_TEMPERATURE": kelvin, "LIGHT_COLOR_TARGET_MODE": _MODE_CCT}
    await send(hass, target, "SET_COLOR_TARGET", params)


async def stop_brightness(hass: HomeAssistant, target: Target) -> None:
    """SET_BRIGHTNESS_STOP: halts a ramp in flight where it is."""
    await send(hass, target, _STOP, {})
    _ramp_ends(hass).pop(_item_key(target), None)
