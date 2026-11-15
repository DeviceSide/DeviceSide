"""ZHA's device classes (docs/evidence.md, Device classes): which firmware family a target's device is, and so which
call it takes.

What decides the outcome on ZHA (internals.md, `classes`, which cites the source): every adapter sends standard ZCL
through the cluster object a device's quirk puts on its endpoint. A quirk that keeps the standard command (Tuya's ZCL
quirks, Sonoff's; Hue bulbs and the Sengled have none) puts the same frame on the air for every device, so the
firmware decides the result, and the device's own Zigbee strings name the firmware. A Tuya datapoint quirk routes
On/Off itself and answers OnWithTimedOff with UNSUP_CLUSTER_COMMAND, sending nothing, so there the quirk decides:
`tuya_mcu` keys on it (the On/Off cluster's `command` comes from zha-quirks' Tuya package), and on the datapoint
strings for a device whose quirk is missing. Every other rule reads the Zigbee manufacturer and model.

Both come from zigpy's device (zcl.zigpy_device), never the registry: ZHA writes the registry from its own device's
`manufacturer` and `model`, which a v2 quirk's friendly name replaces (zha-quirks zhaquirks/builder/device.py), so a
Tuya device could show there under another maker. Reading the gateway is sync, with no I/O.

RULES is ordered, the first match winning, and `other`, the default class, takes a device none places. The order
matters in four places: the datapoint rules go before the ZCL ones (a TS0601's model matches `tuya_zcl`'s `TS` and
four digits, and some datapoint devices carry a `_TZ3000_…` or `_TZ3210_…` string, which the quirk rule catches); the
reported string goes before the countdown models; those go before the rest of Tuya's ZCL strings; and every Tuya rule
goes before `sengled`, so a Tuya device sold under Sengled's name keeps its Tuya class. `hue` reads a manufacturer no
Tuya device carries.

A ZHA device is never Unplaced: zigpy reads its strings and picks its quirk once, in the interview, before ZHA makes
its entities, and nothing reports them later, so the class is final when a target first exists. A device whose
interview couldn't read a string, or that the gateway doesn't hold, gets None, as no rule can place it until it is
reconfigured; where a call harms a class, core refuses None as class_unknown. A group is no device of its own: the
dispatcher classes its members (groups.expand_group).
"""

import re

from homeassistant.core import HomeAssistant

from . import zcl
from .addressing import address
from ...core.models import Target
from ...core.scope import DoesntWork, NotSupported, documented, experimental, verified

HUE = "hue"
# Tuya's ZCL plugs and switches whose timer is Tuya's countdown, in whole seconds, which Tuya's recipe drives (parked
# until after v0.1.0, plan Decision 74): the models Zigbee2MQTT drives that way (zigbee2mqtt/research/2026-11-14-
# timed-on-call-patterns.md, §3, Tuya ZCL row) and the lab probe ran.
TUYA_COUNTDOWN = "tuya_countdown"
# A countdown plug reported harmed on the recipe's own frame (plan Decision 35, amended; docs/evidence.md, Contrary
# evidence): the TS011F `_TZ3000_gjnozsaz`, whose time left jumps back at random (Z2M #30493, on Z2M's converter A,
# whose frame the recipe sends).
TUYA_COUNTDOWN_HARMED = "tuya_countdown_harmed"
# Every other Tuya device on the Zigbee On/Off cluster (bulbs, dimmers, white labels), whose timer nobody has probed:
# the spec's tenths may be read as seconds, as the countdown models do, and the recipe as a bulb's tenths.
TUYA_ZCL = "tuya_zcl"
# A Tuya datapoint device (TS0601), whose quirk turns On/Off into Tuya datapoints and answers the rest itself.
TUYA_MCU = "tuya_mcu"
SENGLED = "sengled"
# Sonoff's SWV water valve, which reads OnWithTimedOff's on_time as whole seconds (research, §3, Sonoff row).
SONOFF_SWV = "sonoff_swv"
OTHER = "other"  # the default class, never Verified (IntegrationInfo.default_class)
CLASSES = frozenset({HUE, TUYA_COUNTDOWN, TUYA_COUNTDOWN_HARMED, TUYA_ZCL, TUYA_MCU, SENGLED, SONOFF_SWV, OTHER})

# Tuya's Zigbee manufacturer strings, as Zigbee2MQTT's rules read them (zigbee2mqtt/classes.py): `_TZE…` for
# datapoint devices, `_TZ3000_…`, `_TZ3210_…` and `_TYZB01_…` for ZCL ones.
_TUYA_MCU_MANUFACTURER = r"_TZE\d{3}_.*"
_TUYA_ZCL_MANUFACTURER = r"_TZ\d{4}_.*|_TYZB\d{2}_.*"
# The package whose On/Off clusters route commands themselves: zhaquirks.tuya.mcu's TuyaOnOff and TuyaOnOffNM, and
# zhaquirks.tuya's older TuyaOnOff.
_TUYA_QUIRKS = "zhaquirks.tuya"

# (class, field, a regex the field must fully match), first match winning. `quirk` is the module that defines the
# On/Off cluster's `command`; `identity` is `manufacturer/model`, for a ban that names both (docs/evidence.md, Contrary
# evidence).
RULES: tuple[tuple[str, str, str], ...] = (
    # Hue bulbs' own manufacturer strings, older and newer (zha-quirks zhaquirks/philips/__init__.py, PHILIPS and
    # SIGNIFY); the lab's read `Signify Netherlands B.V.`.
    (HUE, "manufacturer", r"Signify Netherlands B\.V\.|Philips"),
    (TUYA_MCU, "quirk", re.escape(_TUYA_QUIRKS) + r"(\..*)?"),
    (TUYA_MCU, "model", "TS0601"),
    (TUYA_MCU, "manufacturer", _TUYA_MCU_MANUFACTURER),
    (TUYA_COUNTDOWN_HARMED, "identity", r"_TZ3000_gjnozsaz/TS011F"),
    (TUYA_COUNTDOWN, "model", r"TS011F|TS000[1-4]|TS0011|TS0726"),
    (TUYA_ZCL, "manufacturer", _TUYA_ZCL_MANUFACTURER),
    (TUYA_ZCL, "model", r"TS\d{4}.*"),
    # The lab's E11-G13 reads `sengled`.
    (SENGLED, "manufacturer", "(?i:sengled)"),
    # zha-quirks matches it as `SONOFF` / `SWV` (zhaquirks/sonoff/swv.py).
    (SONOFF_SWV, "model", "SWV"),
)

# The levels each adapter's scope holds (index.md, Device classes): Verified on Hue, whose bulbs every record ran on;
# `other` Documented where it gets the Verified call and no known class departs, else untested; the Tuya ZCL, Sengled
# and Sonoff classes untested, or refused on turn_on_for. `tuya_mcu` is in none but turn_on_for's doesnt_work: its
# quirk answers what DeviceSide sends itself (reads from its cache, a Level move without its transition), so it needs
# a datapoint call that isn't built (not yet supported).
_UNTESTED = experimental(TUYA_COUNTDOWN, TUYA_COUNTDOWN_HARMED, TUYA_ZCL, SENGLED, SONOFF_SWV)
# lower_brightness and stop: the Level and Color commands a Hue bulb gets, sent alike to every light (fade.py), and no
# class known to depart (the Sengled, which drops a level while off, is its own).
LOWER_BRIGHTNESS = STOP = verified(HUE) | documented(OTHER) | _UNTESTED
# raise_brightness from off turns a Hue bulb on by Signify's own multiColor, and any other light by MoveToLevel with
# ExecuteIfOff, a call no record has run; the color fades rest on how each firmware renders its moves.
RAISE_BRIGHTNESS = FADE_COLOR = verified(HUE) | experimental(OTHER) | _UNTESTED
# Reads and writes: other brands depart (a bulb without OnTime, one that comes on at full when written while off).
READ_WRITE = verified(HUE) | experimental(OTHER) | _UNTESTED
# turn_on_for: the spec's call, untested on all but Hue.
TURN_ON_FOR = verified(HUE) | experimental(OTHER)

# turn_on_for's call harms each of these (docs/evidence.md, When today's call harms a class): it ends on with no timer,
# or on or off long after it was asked, unwatched. `harms`, so core also refuses a target it can't class.
_INTERNALS = "https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zha/internals.md"
_RESEARCH = "https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zigbee2mqtt/research/"
# No known call works on it: it fails the very call (Tuya's recipe, Z2M's converter A) that serves its siblings.
TURN_ON_FOR_DOESNT_WORK = {
    TUYA_COUNTDOWN_HARMED: DoesntWork(
        what="Reported Tuya plugs",
        reason="Its timer is reported to jump back at random, so it may not turn off when asked",
        source="https://github.com/Koenkk/zigbee2mqtt/issues/30493",
        harms=True,
    ),
}
# A call that would work is known or plausible, but isn't built (plan Decisions 70 and 74).
TURN_ON_FOR_NOT_SUPPORTED = {
    # Tuya's recipe works on the lab plug (research/2026-11-14-lab-probe.md, §2, C5), parked until after v0.1.0;
    # today's tenths from off switched a TS011F on 106 s after a 10 s request and left it on (C1).
    TUYA_COUNTDOWN: NotSupported(
        reason="ZHA's timer can turn it on long after the time asked and leave it on",
        source=_RESEARCH + "2026-11-14-lab-probe.md",
        harms=True,
    ),
    # The recipe or a countdown is plausible; the spec's tenths may be read as seconds, as the countdown models do.
    TUYA_ZCL: NotSupported(
        reason="ZHA's timer can turn it on or off long after the time asked",
        source=_RESEARCH + "2026-11-14-timed-on-call-patterns.md",
        harms=True,
    ),
    # A datapoint countdown is plausible; the quirk refuses 0x42, and with fields the light.turn_on before it stays on.
    TUYA_MCU: NotSupported(
        reason="ZHA refuses its timer, so with brightness or a color temperature it would turn on and stay on",
        source=_INTERNALS + "#classes",
        harms=True,
    ),
    # A host-side off would serve it; it refuses 0x42 by unicast and misses it by groupcast (Tested behavior).
    SENGLED: NotSupported(
        reason="It refuses the timer, so with brightness, a color temperature or in a group it would stay on",
        source=_INTERNALS + "#tested-behavior",
        harms=True,
    ),
    # Z2M's call in whole seconds (on_off_fixed_on_time) works on it; ZHA's tenths would run ten times as long.
    SONOFF_SWV: NotSupported(
        reason="It reads ZHA's timer in seconds, so it would stay open about ten times longer than asked",
        source=_RESEARCH + "2026-11-14-tuya-countdown.md",
        harms=True,
    ),
}


def device_class(manufacturer: str | None, model: str | None, quirk: str | None = None) -> str | None:
    """The class of a device with these Zigbee strings and On/Off `quirk` module: the first rule they match, else the
    default; None when the interview didn't read a string, as no rule can place it."""
    if not manufacturer or not model:
        return None
    fields = {"manufacturer": manufacturer, "model": model, "quirk": quirk or "", "identity": f"{manufacturer}/{model}"}
    return next((cls for cls, name, pattern in RULES if re.fullmatch(pattern, fields[name])), OTHER)


def capability(hass: HomeAssistant, target: Target) -> str | None:
    """ZHA's IntegrationInfo.capability: the class of the target's zigpy device, by its Zigbee strings and the quirk on
    its On/Off cluster; None for a target with no address, or one the gateway doesn't hold."""
    if (addr := address(target.entry.unique_id)) is None or (device := zcl.zigpy_device(hass, addr.ieee)) is None:
        return None
    return device_class(device.manufacturer, device.model, _command_module(device, addr.endpoint_id))


def _command_module(device, endpoint_id: int) -> str | None:
    """The module that defines the `command` of the On/Off cluster on the target's endpoint: zigpy's for a standard
    cluster, the quirk's where it routes commands itself. None without one."""
    endpoint = device.endpoints.get(endpoint_id)
    if (cluster := endpoint.in_clusters.get(zcl.ON_OFF_CLUSTER) if endpoint is not None else None) is None:
        return None
    owner = next((cls for cls in type(cluster).__mro__ if "command" in vars(cls)), None)
    return owner.__module__ if owner is not None else None
