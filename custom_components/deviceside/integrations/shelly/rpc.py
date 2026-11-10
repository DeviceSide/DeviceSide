"""The RPC calls the Shelly adapters send: a <Component>.Set with a flip-back timer or a fade, DimStop, and the
persistent auto-off / auto-on setting in <Component>.SetConfig, each with a read-back."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from homeassistant.core import HomeAssistant, State
from homeassistant.util.color import color_hs_to_RGB, color_xy_to_RGB

from .addressing import address, rpc_device
from ...core.adapter import Adapter
from ...core.models import EntityResult, LightFields, Status, Target
from ...core.scope import DurationLimits
from ...core.wire import wire_trace

_LOGGER = logging.getLogger(__name__)

# The device's own bounds (Switch.Set error -103: "should be > 0 and <= 604800"); it keeps 0.01 s steps.
# Durations arrive rounded to 10 ms and floored at 50 ms (core/duration.py), so only the ceiling can bite here.
TIMER_LIMITS = DurationLimits(min_s=0, max_s=604800)

# auto_off_delay / auto_on_delay bounds. Not yet verified on a device: TIMER_LIMITS until the rig's SetConfig error
# text says otherwise.
AUTO_DELAY_LIMITS = DurationLimits(min_s=0, max_s=604800)

# The device keeps the delays to 0.01 s.
_DELAY_DIGITS = 2

# A Set's transition_duration: core's floor (shelly/const.py RPC_MIN_TRANSITION_TIME_SEC) and the device's ceiling
# (rig, 8 Nov: 0.5 to 10800 s, 0 refused with error -103).
TRANSITION_LIMITS = DurationLimits(min_s=0.5, max_s=10800)


def whole_percent(percent: float) -> int:
    """A brightness percent as the device's whole-percent level, never 0 (0 would switch the light off)."""
    return max(1, round(percent))


def light_params(light: LightFields, component: str, state: State | None) -> dict[str, Any]:
    """light.turn_on fields as <Component>.Set params, translated as shelly/light.py does bar brightness.

    Brightness is a percent on both sides, so it goes straight to the device's whole-percent level.
    """
    params: dict[str, Any] = {}
    if light.brightness is not None:
        params["brightness"] = whole_percent(light.brightness)
    if light.transition is not None:
        params["transition_duration"] = min(max(light.transition, TRANSITION_LIMITS.min_s), TRANSITION_LIMITS.max_s)
    if light.color_temp_kelvin is not None:
        kelvin = light.color_temp_kelvin
        if state is not None:
            low = state.attributes.get("min_color_temp_kelvin", kelvin)
            high = state.attributes.get("max_color_temp_kelvin", kelvin)
            kelvin = min(max(kelvin, low), high)
        params["ct"] = kelvin
    # Core's light.turn_on sends hs and xy to a light without those modes as rgb, at full value, whatever mode the
    # light is in: light/helper.py process_turn_on_params. The schema allows one color per call.
    if light.rgb_color is not None:
        params["rgb"] = list(light.rgb_color)
    elif light.hs_color is not None:
        params["rgb"] = list(color_hs_to_RGB(*light.hs_color))
    elif light.xy_color is not None:
        params["rgb"] = list(color_xy_to_RGB(*light.xy_color))
    if component == "RGBCCT" and ("ct" in params or "rgb" in params):
        params["mode"] = "cct" if "ct" in params else "rgb"
    return params


async def send(hass: HomeAssistant, target: Target, method: str, params: dict[str, Any]) -> None:
    """One write RPC, <Component>.<method>, to the target's component, traced; an error propagates."""
    rpc, device = address(target), rpc_device(target)
    wire_trace(hass, target.reported_id, "rpc", f"{rpc.component}.{method}", params)
    await device.call_rpc(f"{rpc.component}.{method}", {"id": rpc.id, **params})


async def get_status(target: Target) -> dict[str, Any]:
    """The target's <Component>.GetStatus; an error propagates."""
    rpc = address(target)
    return await rpc_device(target).call_rpc(f"{rpc.component}.GetStatus", {"id": rpc.id})


async def read_back(
    adapter: Adapter,
    target: Target,
    read: Callable[[Target], Awaitable[dict[str, Any]]],
    judge: Callable[[dict[str, Any]], EntityResult],
) -> EntityResult:
    """Read what the device kept after an accepted write and let `judge` rule on it.

    A failed read-back reports SENT: the device accepted the write.
    """
    try:
        held = await read(target)
    except Exception as err:  # noqa: BLE001 - aioshelly's errors can't be imported here; see addressing.py
        _LOGGER.debug("%s read-back failed for %s: %s", adapter.action, target.entity_id, err)
        return adapter.result(target, Status.SENT, detail="readback_failed")
    return judge(held)


async def set_and_read_back(
    hass: HomeAssistant,
    adapter: Adapter,
    target: Target,
    params: dict[str, Any],
    judge: Callable[[dict[str, Any]], EntityResult],
) -> EntityResult:
    """Send the Set (an error propagates, so gather() reports it rejected), then GetStatus and let `judge` rule."""
    await send(hass, target, "Set", params)
    return await read_back(adapter, target, get_status, judge)


async def set_with_timer(hass: HomeAssistant, adapter: Adapter, target: Target, params: dict[str, Any]) -> EntityResult:
    """Send the Set, then confirm the timer is running for the duration asked: timer_duration is the full duration,
    not the time left, so it reads back the toggle_after sent."""

    def judge(status: dict[str, Any]) -> EntityResult:
        if status.get("output") == params["on"] and same_delay(status.get("timer_duration"), params["toggle_after"]):
            return adapter.result(target, Status.CONFIRMED)
        return adapter.result(target, Status.SENT, detail="timer_not_reported")

    return await set_and_read_back(hass, adapter, target, params, judge)


async def set_fade(hass: HomeAssistant, target: Target, brightness: float, duration_s: float) -> None:
    """One <Component>.Set fading to `brightness` percent over `duration_s`; an error propagates.

    The device runs the fade from its current level, mid-fade included, and from 1 % when off. Fading to 0 is
    on: false with the transition, the device's own soft off: it ends off and keeps its stored level for the next on
    (brightness 0 would leave it on at 0 %). Brightness always goes with on: true, or the device restores its stored
    level. Rig, 8 Nov.
    """
    params = {"on": False} if brightness == 0 else {"on": True, "brightness": whole_percent(brightness)}
    await send(hass, target, "Set", {**params, "transition_duration": duration_s})


async def dim_stop(hass: HomeAssistant, target: Target) -> None:
    """<Component>.DimStop: halts a Set's fade as well as a DimUp/DimDown ramp, within ~0.1 s, and changes nothing
    when no fade runs (rig, 8 Nov). An error propagates."""
    await send(hass, target, "DimStop", {})


async def get_config(target: Target) -> dict[str, Any]:
    """The target's <Component>.GetConfig; an error propagates."""
    rpc = address(target)
    return await rpc_device(target).call_rpc(f"{rpc.component}.GetConfig", {"id": rpc.id})


def _auto_config(which: Literal["off", "on"], duration_s: float | None) -> dict[str, Any]:
    """The SetConfig config for a set (a duration) or a clear (None). A clear leaves the stored delay alone."""
    if duration_s is None:
        return {f"auto_{which}": False}
    return {f"auto_{which}": True, f"auto_{which}_delay": duration_s}


def same_delay(held: Any, value: float) -> bool:
    """Whether a delay the device reports is the one sent: it may come back as an int (the clamp's ceiling is one) and
    is kept to 0.01 s."""
    return (
        isinstance(held, int | float)
        and not isinstance(held, bool)
        and round(held, _DELAY_DIGITS) == round(value, _DELAY_DIGITS)
    )


def _auto_matches(config: dict[str, Any], wanted: dict[str, Any]) -> bool:
    for key, value in wanted.items():
        held = config.get(key)
        if isinstance(value, bool):
            if held is not value:
                return False
        elif not same_delay(held, value):
            return False
    return True


async def write_auto(
    hass: HomeAssistant, adapter: Adapter, target: Target, which: Literal["off", "on"], duration_s: float | None
) -> EntityResult:
    """Set (a duration) or clear (None) the persistent auto-off or auto-on, writing only on a difference.

    SetConfig writes flash and makes core reload the Shelly entry, so a call that changes nothing sends nothing. The
    first GetConfig and the SetConfig raise on error, so gather() reports the target rejected; a failed or
    inconclusive read-back still reports SENT, as set_with_timer does.
    """
    wanted = _auto_config(which, duration_s)
    if _auto_matches(await get_config(target), wanted):
        return adapter.result(target, Status.UNCHANGED, detail="already_clear" if duration_s is None else "already_set")
    await send(hass, target, "SetConfig", {"config": wanted})

    def judge(config: dict[str, Any]) -> EntityResult:
        if _auto_matches(config, wanted):
            return adapter.result(target, Status.CONFIRMED)
        return adapter.result(target, Status.SENT, detail="config_not_reported")

    return await read_back(adapter, target, get_config, judge)
