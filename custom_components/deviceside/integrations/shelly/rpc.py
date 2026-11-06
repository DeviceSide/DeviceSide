"""The RPC calls the Shelly adapters send: a <Component>.Set with a flip-back timer, and the persistent auto-off /
auto-on setting in <Component>.SetConfig, each with a read-back."""

import logging
from typing import Any, Literal

from homeassistant.core import State
from homeassistant.util.color import color_hs_to_RGB, color_xy_to_RGB

from .addressing import address, rpc_device
from ...core.adapter import Adapter
from ...core.models import EntityResult, LightFields, Status, Target
from ...core.scope import DurationLimits

_LOGGER = logging.getLogger(__name__)

# The device's own bounds (Switch.Set error -103: "should be > 0 and <= 604800"); it keeps 0.01 s steps.
# Durations arrive rounded to 10 ms and floored at 50 ms (core/duration.py), so only the ceiling can bite here.
TIMER_LIMITS = DurationLimits(min_s=0, max_s=604800)

# auto_off_delay / auto_on_delay bounds. Not yet verified on a device: TIMER_LIMITS until the rig's SetConfig error
# text says otherwise.
AUTO_DELAY_LIMITS = DurationLimits(min_s=0, max_s=604800)

# The device keeps the delays to 0.01 s.
_DELAY_DIGITS = 2

# Core's floor for an RPC transition (shelly/const.py RPC_MIN_TRANSITION_TIME_SEC).
_MIN_TRANSITION_S = 0.5


def light_params(light: LightFields, component: str, state: State | None) -> dict[str, Any]:
    """light.turn_on fields as <Component>.Set params, translated as shelly/light.py does bar brightness.

    Brightness is a percent on both sides, so it goes straight to the device's whole-percent level, never 0.
    """
    params: dict[str, Any] = {}
    if light.brightness is not None:
        params["brightness"] = max(1, round(light.brightness))
    if light.transition is not None:
        params["transition_duration"] = max(light.transition, _MIN_TRANSITION_S)
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


async def get_status(target: Target) -> dict[str, Any]:
    """The target's <Component>.GetStatus; an error propagates."""
    rpc = address(target)
    return await rpc_device(target).call_rpc(f"{rpc.component}.GetStatus", {"id": rpc.id})


async def set_with_timer(adapter: Adapter, target: Target, params: dict[str, Any]) -> EntityResult:
    """Send the Set (an error propagates, so gather() reports it rejected), then confirm the timer is running.

    A failed or inconclusive read-back still reports SENT: the device accepted the Set.
    """
    device, rpc = rpc_device(target), address(target)
    await device.call_rpc(f"{rpc.component}.Set", {"id": rpc.id, **params})
    try:
        status = await get_status(target)
    except Exception as err:  # noqa: BLE001 - aioshelly's errors can't be imported here; see addressing.py
        _LOGGER.debug("%s read-back failed for %s: %s", adapter.action, target.entity_id, err)
        return adapter.result(target, Status.SENT, detail="readback_failed")
    if status.get("output") == params["on"] and "timer_duration" in status:
        return adapter.result(target, Status.CONFIRMED)
    return adapter.result(target, Status.SENT, detail="timer_not_reported")


async def get_config(target: Target) -> dict[str, Any]:
    """The target's <Component>.GetConfig; an error propagates."""
    rpc = address(target)
    return await rpc_device(target).call_rpc(f"{rpc.component}.GetConfig", {"id": rpc.id})


def _auto_config(which: Literal["off", "on"], duration_s: float | None) -> dict[str, Any]:
    """The SetConfig config for a set (a duration) or a clear (None). A clear leaves the stored delay alone."""
    if duration_s is None:
        return {f"auto_{which}": False}
    return {f"auto_{which}": True, f"auto_{which}_delay": duration_s}


def _auto_matches(config: dict[str, Any], wanted: dict[str, Any]) -> bool:
    for key, value in wanted.items():
        held = config.get(key)
        if isinstance(value, bool):
            if held is not value:
                return False
        # The delay may come back as an int (the clamp's ceiling is one) and is stored to 0.01 s.
        elif not isinstance(held, int | float) or round(held, _DELAY_DIGITS) != round(value, _DELAY_DIGITS):
            return False
    return True


async def write_auto(
    adapter: Adapter, target: Target, which: Literal["off", "on"], duration_s: float | None
) -> EntityResult:
    """Set (a duration) or clear (None) the persistent auto-off or auto-on, writing only on a difference.

    SetConfig writes flash and makes core reload the Shelly entry, so a call that changes nothing sends nothing. The
    first GetConfig and the SetConfig raise on error, so gather() reports the target rejected; a failed or
    inconclusive read-back still reports SENT, as set_with_timer does.
    """
    wanted = _auto_config(which, duration_s)
    if _auto_matches(await get_config(target), wanted):
        return adapter.result(target, Status.UNCHANGED, detail="already_clear" if duration_s is None else "already_set")
    device, rpc = rpc_device(target), address(target)
    await device.call_rpc(f"{rpc.component}.SetConfig", {"id": rpc.id, "config": wanted})
    try:
        config = await get_config(target)
    except Exception as err:  # noqa: BLE001 - aioshelly's errors can't be imported here; see addressing.py
        _LOGGER.debug("%s read-back failed for %s: %s", adapter.action, target.entity_id, err)
        return adapter.result(target, Status.SENT, detail="readback_failed")
    if _auto_matches(config, wanted):
        return adapter.result(target, Status.CONFIRMED)
    return adapter.result(target, Status.SENT, detail="config_not_reported")
