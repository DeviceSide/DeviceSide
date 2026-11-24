"""Tuya's inching on Zigbee2MQTT: the call set_auto_off and clear_auto_off send a single-endpoint Tuya switch, one
publish of `inching_control_set`.

Z2M's converter writes cluster 0xE000's attribute 0xD003, a base64 table of gangs, one record per gang
(research/tuya/2026-11-24-inching.md, §1 and §2). The fields for gang 1 are `inching_control_1` and `inching_time_1`,
both always sent: ZHC skips a gang missing either and sends an empty payload (ZHC src/lib/tuya.ts L2905).
`set_auto_off` arms it for whole seconds, 1 to 65535 (the wire is a uint16 of seconds, so no sub-second);
`clear_auto_off` sends DISABLE with the least time. Tuya has no auto-on here, so no mode is sent.

No read: ZHC has no `convertGet` for it, and Z2M publishes the value last written, so the result is `sent` (a set Z2M
logs as failed is `rejected`, set_check.py).
"""

from homeassistant.core import HomeAssistant

from ...bridge import INCHING_COMPOSITE, publish_set
from .....core.adapter import Adapter
from .....core.models import EntityResult, Request, Status, Target, TimedRequest
from .....core.scope import DurationLimits, OwnCall

# The time field's range and resolution, in seconds: ZHC's `inching_time_1` expose (min 1, max 65535, step 1).
_MIN_S = 1
INCHING_LIMITS = DurationLimits(min_s=_MIN_S, max_s=65535, step_s=1)


async def _set(adapter: Adapter, hass: HomeAssistant, request: TimedRequest, target: Target) -> EntityResult:
    # supports() refused the targets it can't address.
    inching = {"inching_control_1": "ENABLE", "inching_time_1": int(request.duration_s)}
    await publish_set(hass, target, {INCHING_COMPOSITE: inching})
    return adapter.result(target, Status.SENT)


async def _clear(adapter: Adapter, hass: HomeAssistant, request: Request, target: Target) -> EntityResult:
    inching = {"inching_control_1": "DISABLE", "inching_time_1": _MIN_S}
    await publish_set(hass, target, {INCHING_COMPOSITE: inching})
    return adapter.result(target, Status.SENT)


SET_AUTO_OFF = OwnCall(_set, INCHING_LIMITS)
CLEAR_AUTO_OFF = OwnCall(_clear)
