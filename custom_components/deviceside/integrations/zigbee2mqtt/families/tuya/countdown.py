"""Tuya's countdown on Zigbee2MQTT: the call turn_on_for sends a countdown plug, one publish with `countdown`.

Tuya's countdown plugs with a record of their own (VERIFIED_COUNTDOWNS, in this family) get `{"state": "ON",
"countdown": N}`, whole seconds, 1 to 43200: Z2M's converter A sends a plain On, then 0x42 `{0, N, N}`, which the plug
runs as a toggle at expiry, so from on it ends off (internals.md, Tuya's countdown). One publish, not a state check
first: 0x42 alone on an off plug turns it on at N for good (probe P1b), and converter A sends 0x42 only once the On's
send has resolved, so a lost On sends nothing more and Z2M logs the set as failed (set_check.py makes it `rejected`).
Neither the reads nor `on_time` are sent to it: it reports its state at expiry, and the time left can't be read (probe
P6), so the result is `sent`.
"""

from homeassistant.core import HomeAssistant

from ...bridge import publish_set
from .....actions.turn_on_for import TurnOnForRequest
from .....core.adapter import Adapter
from .....core.models import EntityResult, Status, Target
from .....core.scope import DurationLimits, OwnCall

# Tuya's countdown: whole seconds, 1 to 43200, both reaching the plug; Z2M refuses anything else before sending
# (probe P7, internals.md).
COUNTDOWN_LIMITS = DurationLimits(min_s=1, max_s=43200, step_s=1)


async def _countdown(adapter: Adapter, hass: HomeAssistant, request: TurnOnForRequest, target: Target) -> EntityResult:
    # A plug has no light fields to apply. supports() refused the targets it can't address.
    await publish_set(hass, target, {"state": "ON", "countdown": int(request.duration_s)})
    return adapter.result(target, Status.SENT)


# The countdown plugs' own call (module docstring), which the dispatcher hands execute_own for a run it planned on a
# countdown class: no fresh capability() there, which could differ if bridge/devices moved the plug in between.
COUNTDOWN = OwnCall(_countdown, COUNTDOWN_LIMITS)
