"""Tuya on Zigbee2MQTT: the classes of Tuya firmware, whatever vendor's definition Z2M gives the device.

On Zigbee the call and the firmware family decide the result together (research/2026-11-14-timed-on-call-patterns.md),
and Tuya's departs most: Z2M has no `on_time` converter for it, so turn_on_for's call would leave a Tuya device on.
The classes split it by the call that would serve each: the countdown plugs get Tuya's countdown (countdown.py), the
single-endpoint datapoint devices research names Tuya's datapoint countdown (datapoint.py), and the other classes are
refused there until theirs is built (the integration's refusals.py holds those entries, and
why).

Two rule groups, as the integration places them apart (families/__init__.py): ZIGBEE_RULES, on the device's own
Zigbee strings and its definition, from bridge/devices, which alone show a Tuya device under another vendor's
definition; and REGISTRY_RULES, which stand in for them on what the registry shows until bridge/devices lists the
device. The Zigbee strings are the catalog's (zigbee/tuya.py), shared with ZHA: its patterns as they are, its
literal strings escaped.
"""

import re

from homeassistant.const import Platform

from .countdown import COUNTDOWN
from .datapoint import DATAPOINT_CALLS, DATAPOINT_CLASSES, DATAPOINT_RULES
from .inching import CLEAR_AUTO_OFF, SET_AUTO_OFF
from .....core.rules import Rule
from .....core.scope import Family, FamilyScope, labs, verified
from .....zigbee.tuya import (
    COUNTDOWN_HARMED_MANUFACTURER,
    COUNTDOWN_HARMED_MODEL,
    DATAPOINT_MANUFACTURER_PATTERN,
    DATAPOINT_MODEL,
    INCHING_MW781Z_MANUFACTURER,
    INCHING_WHD02_MANUFACTURER,
    TS011F_MODEL,
    ZCL_MANUFACTURER_PATTERN,
    ZCL_MODEL_PATTERN,
)

# A Tuya device on the Zigbee On/Off cluster (TS011F, TS000x and white labels): its timer is Tuya's countdown.
TUYA_ZCL = "tuya_zcl"
# The single-endpoint Tuya switches whose inching, a persistent auto-off, has a time measured on the device
# (inching.py): set_auto_off and clear_auto_off serve them in Labs. Every other action leaves them as `tuya_zcl`.
TUYA_INCHING = "tuya_inching"
# The TS011F plug, a Tuya ZCL device whose failure of turn_on_for's call is measured (Decision 16), matched by its
# model so every firmware inherits the refusal: a TS011F that isn't on Tuya's countdown below.
TUYA_TS011F = "tuya_ts011f"
# A TS011F plug Zigbee2MQTT drives by Tuya's countdown (research/2026-11-14-tuya-countdown.md, §1, converter A): its
# definition exposes `countdown`, and isn't the datapoint ZOT60 (datapoint.py). turn_on_for sends it that call
# (countdown.py).
TUYA_COUNTDOWN = "tuya_countdown"
# The maker strings on Tuya's countdown with a record of their own (plan Decision 35: a string is Verified only by its
# own evidence), each a class of its own, so the coverage check asks each for its record (string_class).
VERIFIED_STRINGS = ("_TZ3000_0zfrhq4i", "_TZ3000_typdpbpg", "_TZ3000_gznh2xla", "_TZ3000_okaz9tjs")
# The catalog's COUNTDOWN_HARMED_MANUFACTURER, on Tuya's countdown, reported failing it with harm (Z2M #30493): not
# built yet, as Tuya's inching would plausibly serve it (plan Decision 41).
TUYA_COUNTDOWN_HARMED = "tuya_countdown_harmed"
# A Tuya datapoint device (TS0601): no Zigbee On/Off cluster, so no raw ZCL read or write reaches it (Decision 12).
# The single-endpoint definitions on Tuya's datapoint countdown that research names have classes of their own
# (datapoint.py); this is the rest.
TUYA_MCU = "tuya_mcu"


def string_class(string: str) -> str:
    """The class of a maker string on Tuya's countdown with a record of its own: `tuya_countdown_tz3000_0zfrhq4i`."""
    return TUYA_COUNTDOWN + string.lower()


VERIFIED_COUNTDOWNS = tuple(string_class(string) for string in VERIFIED_STRINGS)
# Every class on Tuya's countdown, converter A's: the Verified maker strings, which turn_on_for sends that call, and the
# rest, which it runs in Labs.
COUNTDOWNS = (TUYA_COUNTDOWN, *VERIFIED_COUNTDOWNS)
# Tuya's TS011F plugs, on its countdown or not.
_TS011F = (TUYA_TS011F, *COUNTDOWNS, TUYA_COUNTDOWN_HARMED)
# Every Tuya class, in the order the cards list them (scripts/gen_compat.py reads a scope's classes in its order).
_ALL = (TUYA_ZCL, TUYA_INCHING, *_TS011F, *DATAPOINT_CLASSES, TUYA_MCU)
# The classes that can be lights: Tuya's ZCL and datapoint devices include bulbs, dimmers and LED controllers
# (TS0501B, TS110E, TS0601 dimmers), as well as plugs and switches.
_LIGHTS = (TUYA_ZCL, *DATAPOINT_CLASSES, TUYA_MCU)
# Each class's domains (IntegrationInfo.classes): a TS011F is a plug, so a switch, which no action for lights alone
# reaches. Zigbee2MQTT can be set to show one as a light, on/off alone; it stays a switch here (docs/evidence.md, "A
# class names its domains"), as none of those actions has anything to do on it but stop.
CLASSES = {
    name: frozenset({Platform.LIGHT, Platform.SWITCH}) if name in _LIGHTS else frozenset({Platform.SWITCH})
    for name in _ALL
}

# The catalog's literal models, as the patterns the rules below test.
_TS011F_MODEL = re.escape(TS011F_MODEL)
_DATAPOINT_MODEL = re.escape(DATAPOINT_MODEL)
# Tuya's countdown, converter A, on a TS011F: the definition exposes `countdown` for the whole device (Z2M's own
# statement that it takes the key; a multi-gang one exposes one per endpoint, `countdown_l1`, so isn't matched). The
# ZOT60, a TS011F whose `countdown` is a datapoint, converter B (research/2026-11-14-tuya-countdown.md, §1, The
# expose doesn't tell A from B), is the datapoint rules', which run first.
_COUNTDOWN = {"zigbee_model": _TS011F_MODEL, "exposes": "countdown"}

# Inching: the two measured maker strings, whose definition exposes the composite for the whole device (ZHC enables the
# WHD02's on its `TS0001` model alone, so its `TS000F` variant exposes none and stays `tuya_zcl`).
_INCHING = {
    "zigbee_manufacturer": "|".join(map(re.escape, (INCHING_WHD02_MANUFACTURER, INCHING_MW781Z_MANUFACTURER))),
    "exposes": "inching_control_set",
}

# The Zigbee strings and the definition, from bridge/devices. The datapoint countdown's definitions go first
# (datapoint.py): the ZOT60 is a TS011F with converter A's expose, and the rest TS0601s or `_TZE…` strings, which the
# `tuya_mcu` rules match. Then the models: a TS011F's manufacturer (`_TZ3000_…`) matches `tuya_zcl`'s, and a TS0601's
# model matches `tuya_zcl`'s `TS` and four digits. The TS011F's go in this order: the string reported harmed, then
# each Verified string's and `tuya_countdown` (both on converter A's definition, read from bridge/devices), then
# `tuya_ts011f`, which every TS011F matches.
ZIGBEE_RULES = (
    *DATAPOINT_RULES,
    Rule(
        TUYA_COUNTDOWN_HARMED,
        {
            "zigbee_model": re.escape(COUNTDOWN_HARMED_MODEL),
            "zigbee_manufacturer": re.escape(COUNTDOWN_HARMED_MANUFACTURER),
        },
    ),
    *(
        Rule(string_class(string), _COUNTDOWN | {"zigbee_manufacturer": re.escape(string)})
        for string in VERIFIED_STRINGS
    ),
    Rule(TUYA_COUNTDOWN, _COUNTDOWN),
    Rule(TUYA_TS011F, {"zigbee_model": _TS011F_MODEL}),
    Rule(TUYA_MCU, {"zigbee_model": _DATAPOINT_MODEL}),
    Rule(TUYA_MCU, {"zigbee_manufacturer": DATAPOINT_MANUFACTURER_PATTERN}),
    # Before the rules that class these strings today: the WHD02's `_TZ3000_…` string (`tuya_zcl`'s manufacturer rule)
    # and the MW781Z's `TS0726` model (its `_TZ300A_…` string matches no pattern here).
    Rule(TUYA_INCHING, _INCHING),
    Rule(TUYA_ZCL, {"zigbee_manufacturer": ZCL_MANUFACTURER_PATTERN}),
    Rule(TUYA_ZCL, {"zigbee_model": ZCL_MODEL_PATTERN}),
)
# The registry, for a Tuya device bridge/devices doesn't show yet: Z2M's definition (`TS011F_plug_1`) and vendor. The
# models go before the vendor `Tuya` and the catch-all `TS.*`, which a `TS011F_…` or `TS0601_…` definition also
# matches.
REGISTRY_RULES = (
    Rule(TUYA_TS011F, {"model_id": _TS011F_MODEL + "(_.*)?"}),
    Rule(TUYA_MCU, {"model_id": _DATAPOINT_MODEL + "(_.*)?"}),
    Rule(TUYA_ZCL, {"manufacturer": "Tuya"}),
    Rule(TUYA_ZCL, {"model_id": "TS.*"}),
)

# turn_on_for, which serves every Tuya class an action serves (index.md, Device classes): each countdown maker string
# with a record of its own, Verified, and the rest of the countdown plugs (`tuya_countdown`), in Labs on their kin's
# pass of the same call (docs/evidence.md, In Labs). Switches alone, as Z2M shows a plug, sent Tuya's countdown, which a
# Z2M group's call isn't, so a group with one falls back to its members. The datapoint countdown's classes, on lights
# and switches, in Labs on research (plan 2026-11-24-tuya-datapoint-single-endpoint.md, Decision 1), each sent its own
# call (datapoint.py), so a group with one falls back too. The classes off the countdown are left out, and the
# integration refuses them there, as today's call would harm them (refusals.py). Every other action but turn_off_for
# (below) leaves every Tuya class out: no pass or research admits Tuya's firmware there, and get_attributes reads only
# what another action serves (core/registry.py, check_queries; a countdown plug's read is refused, refusals.py).
_TURN_ON_FOR = FamilyScope(
    capabilities=verified(*VERIFIED_COUNTDOWNS, domains=(Platform.SWITCH,))
    | labs(TUYA_COUNTDOWN, domains=(Platform.SWITCH,))
    | labs(*DATAPOINT_CLASSES),
    own_calls={**dict.fromkeys(COUNTDOWNS, COUNTDOWN), **DATAPOINT_CALLS},
)

# turn_off_for: the datapoint countdown's classes alone, on lights and switches, in Labs on research (as turn_on_for),
# each sent its own call (datapoint.py), the one call any Zigbee device has for it.
_TURN_OFF_FOR = FamilyScope(capabilities=labs(*DATAPOINT_CLASSES), own_calls=DATAPOINT_CALLS)

# set_auto_off and clear_auto_off: the inching class alone, in Labs on research, each sent its own call (inching.py), so
# a group with one falls back to its members. Switches, as both strings are single-endpoint switches.
_AUTO_OFF = {
    "set_auto_off": FamilyScope(
        capabilities=labs(TUYA_INCHING, domains=(Platform.SWITCH,)), own_calls={TUYA_INCHING: SET_AUTO_OFF}
    ),
    "clear_auto_off": FamilyScope(
        capabilities=labs(TUYA_INCHING, domains=(Platform.SWITCH,)), own_calls={TUYA_INCHING: CLEAR_AUTO_OFF}
    ),
}

FAMILY = Family(
    key="tuya",
    maintainers=(),
    classes=CLASSES,
    scopes={"turn_on_for": _TURN_ON_FOR, "turn_off_for": _TURN_OFF_FOR, **_AUTO_OFF},
)
