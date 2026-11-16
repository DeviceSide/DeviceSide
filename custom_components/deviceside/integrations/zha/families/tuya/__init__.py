"""Tuya on ZHA: its datapoint devices, which their quirk answers for, and its devices on the Zigbee On/Off cluster,
whose timer is Tuya's countdown or unprobed (internals.md, `classes`).

A Tuya datapoint quirk routes On/Off itself and answers OnWithTimedOff with UNSUP_CLUSTER_COMMAND, sending nothing, so
there the quirk decides: `tuya_mcu` keys on it (the On/Off cluster's `command` comes from zha-quirks' Tuya package),
and on the datapoint strings for a device whose quirk is missing. Every other rule reads the Zigbee manufacturer and
model, whose patterns both Zigbee stacks share (zigbee/tuya.py)."""

import re

from ...rules import Group, Rule
from .....core.scope import Family, FamilyScope, NotBuilt, experimental
from .....zigbee import tuya as strings

# Tuya's ZCL plugs and switches whose timer is Tuya's countdown, in whole seconds (internals.md, `classes`; Tuya's
# recipe for them is parked: internals.md, "Tuya's recipe, parked", and plan Decision 74).
TUYA_COUNTDOWN = "tuya_countdown"
# A countdown plug reported harmed on the recipe's own frame, the TS011F `_TZ3000_gjnozsaz` (plan Decision 35;
# docs/evidence.md, Contrary evidence).
TUYA_COUNTDOWN_HARMED = "tuya_countdown_harmed"
# Every other Tuya device on the Zigbee On/Off cluster (bulbs, dimmers, white labels), whose timer nobody has probed:
# the spec's tenths may be read as seconds, as the countdown models do, and the recipe as a bulb's tenths.
TUYA_ZCL = "tuya_zcl"
# A Tuya datapoint device (TS0601), whose quirk turns On/Off into Tuya datapoints and answers the rest itself.
TUYA_MCU = "tuya_mcu"
# The classes whose OnTime counts Tuya's countdown, in whole seconds, not the spec's tenths (get_attributes).
COUNTS_SECONDS = frozenset({TUYA_COUNTDOWN, TUYA_COUNTDOWN_HARMED})

# The package whose On/Off clusters route commands themselves: zhaquirks.tuya.mcu's TuyaOnOff and TuyaOnOffNM, and
# zhaquirks.tuya's older TuyaOnOff.
_QUIRKS = "zhaquirks.tuya"
# The models whose timer is Tuya's countdown.
_COUNTDOWN_MODELS = r"TS011F|TS000[1-4]|TS0011|TS0726"

# The quirk rule goes first: some datapoint devices carry a `_TZ3000_…` or `_TZ3210_…` string and a model of their
# own, which only the quirk shows.
DATAPOINT_RULES: Group = (
    Rule(TUYA_MCU, "quirk", re.escape(_QUIRKS) + r"(\..*)?"),
    Rule(TUYA_MCU, "model", strings.DATAPOINT_MODEL),
    Rule(TUYA_MCU, "manufacturer", strings.DATAPOINT_MANUFACTURER),
)
# The reported string goes before the countdown models, which hold its model; those go before the rest of Tuya's ZCL
# strings, which their manufacturers match too.
ZCL_RULES: Group = (
    Rule(
        TUYA_COUNTDOWN_HARMED,
        "identity",
        re.escape(f"{strings.COUNTDOWN_HARMED_MANUFACTURER}/{strings.COUNTDOWN_HARMED_MODEL}"),
    ),
    Rule(TUYA_COUNTDOWN, "model", _COUNTDOWN_MODELS),
    Rule(TUYA_ZCL, "manufacturer", strings.ZCL_MANUFACTURER),
    Rule(TUYA_ZCL, "model", strings.ZCL_MODEL),
)

# The ZCL classes untested on every action but turn_on_for, which refuses them. `tuya_mcu` is in no scope but
# turn_on_for's not_built: its quirk answers what DeviceSide sends itself (reads from its cache, a Level move
# without its transition), so it needs a datapoint call nobody has built (not built yet).
_UNTESTED = FamilyScope(capabilities=experimental(TUYA_COUNTDOWN, TUYA_COUNTDOWN_HARMED, TUYA_ZCL))

# turn_on_for's call harms each of these (docs/evidence.md, When today's call harms a class): it ends on with no timer,
# or on or off long after it was asked, unwatched. `harms`, so core also refuses a target it can't class.
_INTERNALS = "https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zha/internals.md"
_RESEARCH = "https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zigbee2mqtt/research/"
# A call that would work is known or plausible, but isn't built (plan Decisions 70, 74 and 41): every class the call
# harms, so none has no known method.
_TURN_ON_FOR = FamilyScope(
    not_built={
        # The countdown misbehaves on this string (Z2M #30493: the time left jumps back at random), and Tuya's inching
        # (cluster 0xE000, command 0xFB), which would plausibly serve it, isn't built (plan Decision 41).
        TUYA_COUNTDOWN_HARMED: NotBuilt(
            reason="Tuya's own timer is reported to jump back at random on it, so it may not turn off when asked, and "
            "the timer that would serve it isn't built",
            source="https://github.com/Koenkk/zigbee2mqtt/issues/30493",
            harms=True,
        ),
        # Tuya's recipe would serve it, parked (internals.md, "Tuya's recipe, parked"); today's tenths harm it (Tested
        # behavior, the TS011F).
        TUYA_COUNTDOWN: NotBuilt(
            reason="ZHA's timer can turn it on long after the time asked and leave it on",
            source=_RESEARCH + "2026-11-14-lab-probe.md",
            harms=True,
        ),
        # The recipe or a countdown is plausible; the spec's tenths may be read as seconds, as the countdown models do.
        TUYA_ZCL: NotBuilt(
            reason="ZHA's timer can turn it on or off long after the time asked",
            source=_RESEARCH + "2026-11-14-timed-on-call-patterns.md",
            harms=True,
        ),
        # A datapoint countdown is plausible; the quirk refuses 0x42, and with fields the light.turn_on before it stays
        # on.
        TUYA_MCU: NotBuilt(
            reason="ZHA refuses its timer, so with brightness or a color temperature it would turn on and stay on",
            source=_INTERNALS + "#classes",
            harms=True,
        ),
    }
)

FAMILY = Family(
    key="tuya",
    maintainers=(),
    classes=frozenset({TUYA_COUNTDOWN, TUYA_COUNTDOWN_HARMED, TUYA_ZCL, TUYA_MCU}),
    scopes={
        "get_attributes": _UNTESTED,
        "lower_brightness": _UNTESTED,
        "lower_hue": _UNTESTED,
        "lower_saturation": _UNTESTED,
        "raise_brightness": _UNTESTED,
        "raise_hue": _UNTESTED,
        "raise_saturation": _UNTESTED,
        "set_attributes": _UNTESTED,
        "stop": _UNTESTED,
        "turn_on_for": _TURN_ON_FOR,
    },
)
