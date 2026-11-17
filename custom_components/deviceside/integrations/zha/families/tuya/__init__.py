"""Tuya on ZHA: its datapoint devices, which their quirk answers for, and its devices on the Zigbee On/Off cluster,
whose timer is Tuya's countdown or unprobed (internals.md, `classes`).

A Tuya datapoint quirk routes On/Off itself and answers OnWithTimedOff with UNSUP_CLUSTER_COMMAND, sending nothing, so
there the quirk decides: `tuya_mcu` keys on it (the On/Off cluster's `command` comes from zha-quirks' Tuya package),
and on the datapoint strings for a device whose quirk is missing. Every other rule reads the Zigbee manufacturer and
model, by the catalog both Zigbee stacks share (zigbee/tuya.py): its patterns as they are, its literal strings
escaped."""

import re

from .....core.rules import Rule
from .....core.scope import Family, FamilyScope, experimental
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

# The package whose On/Off clusters route commands themselves: zhaquirks.tuya.mcu's TuyaOnOff and TuyaOnOffNM, and
# zhaquirks.tuya's older TuyaOnOff.
_QUIRKS = "zhaquirks.tuya"
# The models whose timer is Tuya's countdown.
_COUNTDOWN_MODELS = re.escape(strings.TS011F_MODEL) + r"|TS000[1-4]|TS0011|TS0726"

# The quirk rule goes first: some datapoint devices carry a `_TZ3000_…` or `_TZ3210_…` string and a model of their
# own, which only the quirk shows.
DATAPOINT_RULES = (
    Rule(TUYA_MCU, {"quirk": re.escape(_QUIRKS) + r"(\..*)?"}),
    Rule(TUYA_MCU, {"model": re.escape(strings.DATAPOINT_MODEL)}),
    Rule(TUYA_MCU, {"manufacturer": strings.DATAPOINT_MANUFACTURER_PATTERN}),
)
# The reported string goes before the countdown models, which hold its model; those go before the rest of Tuya's ZCL
# strings, which their manufacturers match too.
ZCL_RULES = (
    # A ban that names both strings (docs/evidence.md, Contrary evidence).
    Rule(
        TUYA_COUNTDOWN_HARMED,
        {
            "manufacturer": re.escape(strings.COUNTDOWN_HARMED_MANUFACTURER),
            "model": re.escape(strings.COUNTDOWN_HARMED_MODEL),
        },
    ),
    Rule(TUYA_COUNTDOWN, {"model": _COUNTDOWN_MODELS}),
    Rule(TUYA_ZCL, {"manufacturer": strings.ZCL_MANUFACTURER_PATTERN}),
    Rule(TUYA_ZCL, {"model": strings.ZCL_MODEL_PATTERN}),
)

# The ZCL classes untested on every action but turn_on_for, whose call harms every Tuya class: the integration refuses
# them there (refusals.py). The countdown models are plugs and switches, so the actions for lights alone hold only
# `tuya_zcl`, as the registry checks (core/registry.py, check_classes). `tuya_mcu` is in no scope at all: its quirk
# answers what DeviceSide sends itself (reads from its cache, a Level move without its transition), so it needs a
# datapoint call nobody has built (not built yet).
_UNTESTED = FamilyScope(capabilities=experimental(TUYA_ZCL))
# get_attributes reads only what another action serves (core/registry.py, check_queries): `tuya_zcl` as a light. No
# action serves a Tuya plug or switch yet, the countdown models included, so none is read (plan Decision 25); when
# turn_on_for serves the countdown models, their OnTime reads in whole seconds (internals.md, "Tuya's recipe, parked").
_READ = FamilyScope(capabilities=experimental(TUYA_ZCL, domains=("light",), only=True))

FAMILY = Family(
    key="tuya",
    maintainers=(),
    # Each class's domains (IntegrationInfo.classes): the countdown models are plugs and switch modules; the rest of
    # Tuya's ZCL devices, and its datapoint ones, include bulbs and dimmers too.
    classes={
        TUYA_COUNTDOWN: frozenset({"switch"}),
        TUYA_COUNTDOWN_HARMED: frozenset({"switch"}),
        TUYA_ZCL: frozenset({"light", "switch"}),
        TUYA_MCU: frozenset({"light", "switch"}),
    },
    scopes={
        "get_attributes": _READ,
        "lower_brightness": _UNTESTED,
        "lower_hue": _UNTESTED,
        "lower_saturation": _UNTESTED,
        "raise_brightness": _UNTESTED,
        "raise_hue": _UNTESTED,
        "raise_saturation": _UNTESTED,
        "set_attributes": _UNTESTED,
        "stop": _UNTESTED,
    },
)
