"""Sonoff's inching on Zigbee2MQTT: the call set_auto_off and clear_auto_off send, one publish of `inching_control_set`.

Z2M's converter writes cluster 0xFC11's `protocolData` (research/sonoff/2026-11-24-inching.md, §1). Both fields it reads
are always sent, with `inching_mode` too: ZHC sets mode ON (auto-on, which switches the relay on at once) unless the
value reads `"OFF"`, so a write without it would turn the relay on (ZHC#13383). `set_auto_off` arms it, mode OFF, for
the duration, half seconds from 0.5 to 3599.5 (ZHC writes a 16-bit time, so the 86399.5 s models can't take more than
32767.5 s through it; one limit keeps one class). `clear_auto_off` sends DISABLE with the least time, as the field is
required.

No read: the converter has none, and the state Z2M holds is the last write's echo, which the device may disagree with
(Z2M #31604), so the result is `sent` (a set Z2M logs as failed is `rejected`, set_check.py).
"""

from homeassistant.core import HomeAssistant

from ...bridge import publish_set
from .....core.adapter import Adapter
from .....core.models import EntityResult, Request, Status, Target, TimedRequest
from .....core.scope import DurationLimits, OwnCall

# The time field's range and resolution, in seconds: ZHC's `inching_time` expose (min 0.5, step 0.5, max 3599.5).
_MIN_S = 0.5
INCHING_LIMITS = DurationLimits(min_s=_MIN_S, max_s=3599.5, step_s=0.5)


async def _set(adapter: Adapter, hass: HomeAssistant, request: TimedRequest, target: Target) -> EntityResult:
    # supports() refused the targets it can't address.
    inching = {"inching_control": "ENABLE", "inching_time": request.duration_s, "inching_mode": "OFF"}
    await publish_set(hass, target, {"inching_control_set": inching})
    return adapter.result(target, Status.SENT)


async def _clear(adapter: Adapter, hass: HomeAssistant, request: Request, target: Target) -> EntityResult:
    inching = {"inching_control": "DISABLE", "inching_time": _MIN_S, "inching_mode": "OFF"}
    await publish_set(hass, target, {"inching_control_set": inching})
    return adapter.result(target, Status.SENT)


SET_AUTO_OFF = OwnCall(_set, INCHING_LIMITS)
CLEAR_AUTO_OFF = OwnCall(_clear)
