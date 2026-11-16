"""Tuya on Zigbee2MQTT: the classes of Tuya firmware, whatever vendor's definition Z2M gives the device.

On Zigbee the call and the firmware family decide the result together (research/2026-11-14-timed-on-call-patterns.md),
and Tuya's departs most: Z2M has no `on_time` converter for it, so turn_on_for's call would leave a Tuya device on.
The classes split it by the call that would serve each: the countdown plugs get Tuya's countdown (countdown.py), and
the rest are refused there until theirs is built.

Two rule groups, as the integration places them apart (families/__init__.py): ZIGBEE_RULES, on the device's own
Zigbee strings and its definition, from bridge/devices, which alone show a Tuya device under another vendor's
definition; and REGISTRY_RULES, which stand in for them on what the registry shows until bridge/devices lists the
device. The Zigbee string patterns are the catalog's (zigbee/tuya.py), shared with ZHA.
"""

import re

from .countdown import COUNTDOWN
from ...rules import Rule
from .....core.scope import Family, FamilyScope, NotSupported, experimental, verified
from .....zigbee.tuya import (
    COUNTDOWN_HARMED_MANUFACTURER,
    COUNTDOWN_HARMED_MODEL,
    DATAPOINT_MANUFACTURER,
    DATAPOINT_MODEL,
    ZCL_MANUFACTURER,
    ZCL_MODEL,
)

# A Tuya device on the Zigbee On/Off cluster (TS011F, TS000x and white labels): its timer is Tuya's countdown.
TUYA_ZCL = "tuya_zcl"
# The TS011F plug, a Tuya ZCL device whose failure of turn_on_for's call is measured (Decision 16), matched by its
# model so every firmware inherits the refusal: a TS011F that isn't on Tuya's countdown below.
TUYA_TS011F = "tuya_ts011f"
# A TS011F plug Zigbee2MQTT drives by Tuya's countdown (research/2026-11-14-tuya-countdown.md, §1, converter A): its
# definition exposes `countdown`, and isn't the datapoint ZOT60. turn_on_for sends it that call (countdown.py).
TUYA_COUNTDOWN = "tuya_countdown"
# The maker strings on Tuya's countdown with a record of their own (plan Decision 35: a string is Verified only by its
# own evidence), each a class of its own, so the coverage check asks each for its record (string_class).
VERIFIED_STRINGS = ("_TZ3000_0zfrhq4i", "_TZ3000_typdpbpg", "_TZ3000_gznh2xla", "_TZ3000_okaz9tjs")
# The catalog's COUNTDOWN_HARMED_MANUFACTURER, on Tuya's countdown, reported failing it with harm (Z2M #30493): not
# yet supported, as Tuya's inching would plausibly serve it (plan Decision 41).
TUYA_COUNTDOWN_HARMED = "tuya_countdown_harmed"
# A Tuya datapoint device (TS0601): no Zigbee On/Off cluster, so no raw ZCL read or write reaches it (Decision 12).
TUYA_MCU = "tuya_mcu"


def string_class(string: str) -> str:
    """The class of a maker string on Tuya's countdown with a record of its own: `tuya_countdown_tz3000_0zfrhq4i`."""
    return TUYA_COUNTDOWN + string.lower()


VERIFIED_COUNTDOWNS = tuple(string_class(string) for string in VERIFIED_STRINGS)
# Every class on Tuya's countdown that turn_on_for serves, each sent that call.
COUNTDOWNS = (TUYA_COUNTDOWN, *VERIFIED_COUNTDOWNS)
# Every plug on converter A's countdown, served or not: its OnTime is the countdown last set, not the time left.
COUNTDOWN_PLUGS = frozenset({*COUNTDOWNS, TUYA_COUNTDOWN_HARMED})
# Tuya's TS011F plugs, on its countdown or not, take the rest of the actions' calls as any Tuya ZCL device does.
_TS011F = (TUYA_TS011F, *COUNTDOWNS, TUYA_COUNTDOWN_HARMED)
# Every Tuya class, in the order the cards list them (scripts/gen_compat.py reads a scope's classes in its order).
_ALL = (TUYA_ZCL, *_TS011F, TUYA_MCU)
CLASSES = frozenset(_ALL)

_TS011F_MODEL = "TS011F"  # the plug's Zigbee model, and the stem of its Z2M definitions (`TS011F_plug_1`)
# Tuya's countdown, converter A, on a TS011F: the definition exposes `countdown` for the whole device (Z2M's own
# statement that it takes the key; a multi-gang one exposes one per endpoint, `countdown_l1`, so isn't matched) and
# isn't the ZOT60, whose `countdown` is a datapoint, converter B (research/2026-11-14-tuya-countdown.md, §1, The
# expose doesn't tell A from B).
_COUNTDOWN = {"zigbee_model": _TS011F_MODEL, "exposes": "countdown", "definition_model": "(?!ZOT60$).*"}

# The Zigbee strings, from bridge/devices. The models go first: a TS011F's manufacturer (`_TZ3000_…`) matches
# `tuya_zcl`'s, and a TS0601's model matches `tuya_zcl`'s `TS` and four digits. The TS011F's go in this order: the
# string reported harmed, then each Verified string's and `tuya_countdown` (both on converter A's definition, read
# from bridge/devices), then `tuya_ts011f`, which every TS011F matches.
ZIGBEE_RULES = (
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
    Rule(TUYA_MCU, {"zigbee_model": DATAPOINT_MODEL}),
    Rule(TUYA_MCU, {"zigbee_manufacturer": DATAPOINT_MANUFACTURER}),
    Rule(TUYA_ZCL, {"zigbee_manufacturer": ZCL_MANUFACTURER}),
    Rule(TUYA_ZCL, {"zigbee_model": ZCL_MODEL}),
)
# The registry, for a Tuya device bridge/devices doesn't show yet: Z2M's definition (`TS011F_plug_1`) and vendor. The
# models go before the vendor `Tuya` and the catch-all `TS.*`, which a `TS011F_…` or `TS0601_…` definition also
# matches.
REGISTRY_RULES = (
    Rule(TUYA_TS011F, {"model_id": _TS011F_MODEL + "(_.*)?"}),
    Rule(TUYA_MCU, {"model_id": DATAPOINT_MODEL + "(_.*)?"}),
    Rule(TUYA_ZCL, {"manufacturer": "Tuya"}),
    Rule(TUYA_ZCL, {"model_id": "TS.*"}),
)

# The levels (index.md, Device classes): untested on every action but the two below.
_UNTESTED = FamilyScope(capabilities=experimental(*_ALL))
# Raw ZCL reads and writes, which a datapoint device can't take, so `tuya_mcu` is left out.
_RAW_ZCL = FamilyScope(capabilities=experimental(TUYA_ZCL, *_TS011F))

# turn_on_for. The classes off Tuya's countdown are not yet supported, and harmed by today's call (plan Decisions 20,
# 70 and 71): Z2M has no `on_time` converter for a definition built with `onOffCountdown`, or for a datapoint device,
# so it sends a plain On and the device stays on. Each has a call that would work, Z2M's `countdown`, which isn't built
# for them: converter A's for a TS011F Z2M shows no `countdown` for and the TS011F's kin (v0.1.0 builds it for the
# countdown plugs alone, plan Decision 72), the datapoint one for TS0601 devices (v0.1.x,
# docs/plans/2026-11-15-tuya-datapoint-countdown.md). `harms`, so the dispatcher refuses a device not yet placed as
# well, which could be one of them (plan Decision 26).
_RESEARCH = "https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zigbee2mqtt/research/"
# What the user reads after core's "can't take this action yet" (errors.py, the not_supported key).
_STAYS_ON = "Zigbee2MQTT would turn it on with no timer, so it would stay on"
TURN_ON_FOR_NOT_SUPPORTED = {
    # Measured (Decision 16), and matched by its model so every firmware inherits the refusal.
    TUYA_TS011F: NotSupported(reason=_STAYS_ON, source=_RESEARCH + "2026-11-14-lab-probe.md", harms=True),
    TUYA_ZCL: NotSupported(reason=_STAYS_ON, source=_RESEARCH + "2026-11-14-timed-on-call-patterns.md", harms=True),
    # The harm today: a datapoint device's definition has no `on_time` converter either, so it gets a plain On
    # (timed-on call patterns); the call that would serve it is the datapoint countdown (its research note).
    TUYA_MCU: NotSupported(reason=_STAYS_ON, source=_RESEARCH + "2026-11-14-timed-on-call-patterns.md", harms=True),
    # Reported failing the countdown with harm (plan Decisions 35 and 41).
    TUYA_COUNTDOWN_HARMED: NotSupported(
        reason="its maker string is reported to restart its timer at random, so it could stay on",
        source="https://github.com/Koenkk/zigbee2mqtt/issues/30493",
        harms=True,
    ),
}
_TURN_ON_FOR = FamilyScope(
    # Tuya's countdown plugs get that call: each maker string with a record of its own Verified, on switches alone, as
    # Z2M shows a plug, and the rest untested (plan Decision 35).
    capabilities=verified(*VERIFIED_COUNTDOWNS, domains=("switch",)) | experimental(TUYA_COUNTDOWN),
    not_supported=TURN_ON_FOR_NOT_SUPPORTED,
    # Each takes the countdown, which a Z2M group's call isn't, so a group with one falls back to its members.
    own_calls=dict.fromkeys(COUNTDOWNS, COUNTDOWN),
)

FAMILY = Family(
    key="tuya",
    maintainers=(),
    classes=CLASSES,
    scopes={
        "raise_brightness": _UNTESTED,
        "lower_brightness": _UNTESTED,
        "raise_hue": _UNTESTED,
        "lower_hue": _UNTESTED,
        "raise_saturation": _UNTESTED,
        "lower_saturation": _UNTESTED,
        "stop": _UNTESTED,
        "get_attributes": _RAW_ZCL,
        "set_attributes": _RAW_ZCL,
        "turn_on_for": _TURN_ON_FOR,
    },
)
