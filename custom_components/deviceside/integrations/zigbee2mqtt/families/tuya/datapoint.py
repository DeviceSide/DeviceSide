"""Tuya's datapoint countdown on Zigbee2MQTT: the single-endpoint definitions it is admitted on, their classes, and
the call they get.

A Tuya datapoint device (TS0601 and kin) has no Zigbee On/Off cluster; Zigbee2MQTT gives the ones here a `countdown`
key in seconds, a datapoint its `tz.datapoints` converter sends after the `state` one (converter B,
research/2026-11-24-tuya-datapoint-call.md). The countdown toggles at zero, so it serves turn_on_for and turn_off_for.
An allowlist, not an expose rule: docs/evidence.md (In Labs) admits only the identities research names, so a definition
ZHC adds later stays `tuya_mcu` until someone reads it. Each definition takes its own expose's `value_max`, and core
clamps by class (OwnCall.limits), so there is one class per limit.

The call: one publish, `{"state": "ON", "countdown": N}`, whole seconds, `state` first, as converter B sends a
message's keys in its order and a failed `state` throws before `countdown` goes out (research/
2026-11-24-tuya-datapoint-call.md, §1); Z2M logs that set as failed, and set_check.py makes it `rejected`. Light
fields on a dimmer go first by light.turn_on (light_turn_on.py). No reads: the time left isn't served, so the result
is `sent`.
"""

import re
from collections.abc import Mapping

from homeassistant.core import HomeAssistant

from ...bridge import publish_set
from ...light_turn_on import turn_on
from .....actions.turn_on_for import TurnOnForRequest
from .....core.adapter import Adapter
from .....core.models import EntityResult, Status, Target
from .....core.rules import Rule
from .....core.scope import DurationLimits, OwnCall

# The countdown's value_max, in seconds, as each definition's expose gives it
# (research/2026-11-24-tuya-datapoint-call.md, §3): ZHC's standard `tuya.exposes.countdown()`, 12 hours; a day; and
# AVATTO ZBS16's own.
STANDARD_MAX_S = 43200
DAY_MAX_S = 86400
ZBS16_MAX_S = 7210

# Zigbee2MQTT's definition model, as bridge/devices gives it, to its countdown's value_max. Each is a row of the
# datapoint note (research/2026-11-14-tuya-datapoint-countdown.md, Table, by #), confirmed at the ZHC Zigbee2MQTT 2.14.3
# ships, v26.125.0, and at v26.136.0 (research/2026-11-24-tuya-datapoint-call.md, §3).
DATAPOINT_DEFINITIONS: Mapping[str, int] = {
    "ZDMS16-1": STANDARD_MAX_S,  # 3, AVATTO dimmer
    "ZOT60": STANDARD_MAX_S,  # 6, AVATTO plug: a TS011F, yet a datapoint countdown
    "FK_V02": STANDARD_MAX_S,  # 7, FrankEver valve: "Countdown timer in seconds"
    "GL-SPI-206P": STANDARD_MAX_S,  # 9, Gledopto's definition, Tuya datapoint firmware
    "SFD02-Z": STANDARD_MAX_S,  # 24, Moes dimmer
    # 25, Moes dimmer. Added in ZHC v26.127.0, after the one Zigbee2MQTT 2.14.3 ships: it matches nothing until Z2M's
    # next release (research/2026-11-24-tuya-datapoint-call.md, §3).
    "SFD02-Z_2": STANDARD_MAX_S,
    "QADZ1LR": STANDARD_MAX_S,  # 35, QA dimmer
    "TS0601_dimmer_1_gang_1": STANDARD_MAX_S,  # 40, Tuya dimmer, 30 maker strings
    "TS0601_dimmer_1_gang_2": STANDARD_MAX_S,  # 41, Tuya dimmer
    "TS0601_dimmer_5": STANDARD_MAX_S,  # 45, Tuya dimmer
    "MG-ZG01W": STANDARD_MAX_S,  # 52, wall switch
    "_TZE28C1000000_jlbsptkl": STANDARD_MAX_S,  # 53, wall switch: "Switch 1 Countdown"
    "ZMS-206US-1": STANDARD_MAX_S,  # 75, Zemismart wall switch: "Countdown for switch 1"
    "TO-DM-W/B": DAY_MAX_S,  # 51, Nova Digital dimmer: "Countdown timer"
    "TS0601_multifunction_switch": DAY_MAX_S,  # 73, wall switch: "Countdown to turn off"
    # 33, Nous relay. Added in ZHC v26.126.0, after the one Zigbee2MQTT 2.14.3 ships: it matches nothing until Z2M's
    # next release (research/2026-11-24-tuya-datapoint-call.md, §3).
    "D1Z": DAY_MAX_S,
    # 32, Nous: its readback shows 0 while the timer runs, which doesn't matter, as no read is served.
    "D5Z": DAY_MAX_S,
    "ZBS16": ZBS16_MAX_S,  # 5, AVATTO relay: unit `seconds`, "Countdown to turn device off after a certain time"
}
# Left out, by the plan (docs/plans/2026-11-24-tuya-datapoint-single-endpoint.md, Decisions 2 and 6), each a row of
# the datapoint note:
# - LYAI-14 (58): its source says it ignores the countdown and uses its default 10 minutes.
# - ZBN-DJ-63 (36): a circuit breaker, where "on for N, then off" is the maintainers' call.
# - TS0601_fan_switch (60): "Max ON time in seconds", most likely a one-shot limit, not a timer.
# - TS0601_smart_temperature_switch (72): its auto mode also drives the output, which may override the timer.
# - FK-BV05 (8), ZVL-PRO (71), ZG-308Z (10): valves whose DP 11 may be a preset run time, not a live timer, so a
#   valve could be left open.
# - Timers in minutes, hours or an enum, or read-only: NAS-WV03B, NAS-WV03B2 (30, 31), TS0601_water_switch (59), TS0049
#   (57), GX03 (66), _TZE284_z5jz7wpo (68), RM28-LE (70); and EPJ-ZB (67), a motor timeout, and the garage opener
#   (56), with no `state`.
# - TS0601_power_monitoring_switch (74): unit `m`, minutes or a mislabel.
# - Every multi-gang definition, and every countdown named per endpoint (`countdown_l1`, `countdown_1`, even on one
#   gang: SFL02-Z-1, MG-AU01ZLMV01-XX), Manhot MH03 and Moes ZS-D among them: they need per-endpoint addressing.

# One class per limit, in the order the cards list them.
TUYA_DATAPOINT = "tuya_datapoint"
TUYA_DATAPOINT_24H = "tuya_datapoint_24h"
TUYA_DATAPOINT_2H = "tuya_datapoint_2h"
CLASS_MAX_S: Mapping[str, int] = {
    TUYA_DATAPOINT: STANDARD_MAX_S,
    TUYA_DATAPOINT_24H: DAY_MAX_S,
    TUYA_DATAPOINT_2H: ZBS16_MAX_S,
}
DATAPOINT_CLASSES = tuple(CLASS_MAX_S)


def _rule(name: str) -> Rule:
    """The class's rule: a definition of its limit (each model escaped), whose exposes hold `countdown` for the
    whole device. `exposes` holds endpoint-less properties alone (rules.definition_fields), so this is also the
    single-endpoint guard."""
    models = (model for model, max_s in DATAPOINT_DEFINITIONS.items() if max_s == CLASS_MAX_S[name])
    return Rule(name, {"definition_model": "|".join(map(re.escape, models)), "exposes": "countdown"})


# Read off the definition in bridge/devices alone: the registry can't show its exposes, so such a device stays
# Unplaced until bridge/devices lists it.
DATAPOINT_RULES = tuple(_rule(name) for name in DATAPOINT_CLASSES)


async def _countdown(adapter: Adapter, hass: HomeAssistant, request: TurnOnForRequest, target: Target) -> EntityResult:
    # A dimmer's light fields first, so the countdown starts once they have landed. supports() refused the targets it
    # can't address.
    if request.light.present():
        await turn_on(hass, target, request.light.as_turn_on_data())
    await publish_set(hass, target, {"state": "ON", "countdown": int(request.duration_s)})
    return adapter.result(target, Status.SENT)


# Each class's own call (module docstring): one per limit, as core clamps a run to its call's limits, sharing one send.
# The dispatcher hands execute_own the call of the class it planned the run on, so a bridge/devices republish in
# between can't send another class's call.
DATAPOINT_CALLS: Mapping[str, OwnCall] = {
    name: OwnCall(_countdown, DurationLimits(min_s=1, max_s=max_s, step_s=1)) for name, max_s in CLASS_MAX_S.items()
}
