"""Zigbee2MQTT's device classes (docs/evidence.md, Device classes): which firmware family a target's device is.

On Zigbee the call and the firmware family decide the result together, so one call proves nothing across vendors
(research/2026-11-14-timed-on-call-patterns.md). A class is named by RULES: an ordered list of (class, conditions), the
first match winning, and `other`, the default class, for a device none places. A lab probe changes the rules' data,
never this structure.

A rule reads two sources, both sync and with no I/O:

- The registry device, which Z2M fills from its definition at discovery: the vendor as manufacturer, the definition's
  model as `model_id` (research/2026-11-14-lab-probe.md, §1). Enough for Hue, Sengled and Gledopto.
- The device's Zigbee strings, its own manufacturer and model, and its definition's model and exposes, from the
  bridge cache's bridge/devices (bridge_cache.py, the one members.py lists groups from). Only they show a Tuya device
  under another vendor's definition (`_TZ3000_…`, `_TZE…`), which the registry doesn't (plan Decision 18): one that
  fell into `other` would take turn_on_for's call with Experimental features on, and Zigbee2MQTT would leave it on.
  Only the definition shows which TS011F plugs take Tuya's countdown (internals.md, `turn_on_for`).

The rule order, the one home for it (internals.md points here). It matters in three places; elsewhere no device can
match two rules (`hue`'s vendor is Z2M's own Philips string, which no Tuya rule matches):

1. Among the Tuya rules on the Zigbee strings, the models go first: a TS011F's manufacturer (`_TZ3000_…`) matches
   `tuya_zcl`'s, and a TS0601's model matches `tuya_zcl`'s `TS` and four digits. The TS011F's go in this order: the
   string reported harmed, then each Verified string's and `tuya_countdown` (both on converter A's definition, read
   from bridge/devices), then `tuya_ts011f`, which every TS011F matches.
2. Every Tuya rule on the Zigbee strings goes before the vendor rules (`sengled`, `gledopto`), so a Tuya device sold
   under another vendor's definition (Gledopto's GL-SPI-206P runs Tuya datapoints) takes its Tuya class.
3. Among the Tuya rules on the registry, the models go before the vendor `Tuya` and the catch-all `TS.*`, which a
   `TS011F_…` or `TS0601_…` definition also matches; all of them go last, as they only stand in for the Zigbee strings.

The registry fallback's limit: until bridge/devices arrives after a connect, for a device it doesn't list yet, or for
one it lists without its strings (mid-interview), the Tuya rules on the Zigbee strings can't match, so the registry
rules place what the registry can show: vendor `Tuya`, or a definition model that starts `TS`. A Tuya device under
another vendor's definition shows neither: Lidl's `HG06337` lands in `other`, and Gledopto's GL-SPI-206P in
`gledopto`, until the strings arrive. `capability` answers that case with the class as core's Unplaced, by one rule
(`placed`): a device is placed once bridge/devices lists it with `interview_completed` true and both Zigbee strings
(Z2M's bridge/devices, https://www.zigbee2mqtt.io/guide/usage/mqtt_topics_and_messages.html), or when the registry
puts it in `hue`, which no Zigbee-string rule can override. So a registry Tuya class waits too (refused either way),
a rule added before the Zigbee-string rules can't become final by accident, and a class a later call serves (part
3's countdown) still waits for the full strings. An Unplaced class is that class to every adapter but one whose call
harms a class (the Tuya entries' NotSupported.harms, turn_on_for's), where the dispatcher refuses it as class_unknown
(plan Decisions 23 and 26; docs/evidence.md, where a call is known to harm, a class not yet known is refused). A
group is no device of its own: the dispatcher classes its members (members.expand_group), and falls back to them
when one isn't placed. A device whose interview never completes stays Unplaced until it is paired again, so its
groups fall back for good, one call per member (index.md, Device classes). `capability` logs, at DEBUG, what an
Unplaced device is waiting for.

Each adapter's scope holds the levels below; why each class sits where it does is in index.md (Device classes) and
the step 5 PR body (`other`'s Documented actions).
"""

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from . import bridge_cache
from .addressing import z2m_address
from ...core.models import Target
from ...core.scope import NotSupported, Unplaced, documented, experimental, verified

_LOGGER = logging.getLogger(__name__)

# Z2M's vendor string for Hue, which HA's device registry shows as the manufacturer; native_control.py reads it too.
HUE_MANUFACTURER = "Philips"

HUE = "hue"
# A Tuya device on the Zigbee On/Off cluster (TS011F, TS000x and white labels): its timer is Tuya's countdown.
TUYA_ZCL = "tuya_zcl"
# The TS011F plug, a Tuya ZCL device whose failure of turn_on_for's call is measured (Decision 16), matched by its
# model so every firmware inherits the refusal: a TS011F that isn't on Tuya's countdown below.
TUYA_TS011F = "tuya_ts011f"
# A TS011F plug Zigbee2MQTT drives by Tuya's countdown (research/2026-11-14-tuya-countdown.md, §1, converter A): its
# definition exposes `countdown`, and isn't the datapoint ZOT60. turn_on_for sends it that call (turn_on_for.py).
TUYA_COUNTDOWN = "tuya_countdown"
# The maker strings on Tuya's countdown with a record of their own (plan Decision 35: a string is Verified only by its
# own evidence), each a class of its own, so the coverage check asks each for its record (string_class).
VERIFIED_STRINGS = ("_TZ3000_0zfrhq4i", "_TZ3000_typdpbpg", "_TZ3000_gznh2xla", "_TZ3000_okaz9tjs")
# `_TZ3000_gjnozsaz`, on Tuya's countdown, reported failing it with harm (Z2M #30493): not yet supported, as Tuya's
# inching would plausibly serve it (plan Decision 41).
TUYA_COUNTDOWN_HARMED = "tuya_countdown_harmed"
_HARMED_STRING = "_TZ3000_gjnozsaz"
# A Tuya datapoint device (TS0601): no Zigbee On/Off cluster, so no raw ZCL read or write reaches it (Decision 12).
TUYA_MCU = "tuya_mcu"
SENGLED = "sengled"
# Gledopto's controllers and bulbs: its converter departs from the standard calls (research/2026-11-14-timed-on-call-
# patterns.md, §3), so `other`'s Documented actions don't cover it (plan Decision 24).
GLEDOPTO = "gledopto"
OTHER = "other"  # the default class, never Verified (IntegrationInfo.default_class)


def string_class(string: str) -> str:
    """The class of a maker string on Tuya's countdown with a record of its own: `tuya_countdown_tz3000_0zfrhq4i`."""
    return TUYA_COUNTDOWN + string.lower()


VERIFIED_COUNTDOWNS = tuple(string_class(string) for string in VERIFIED_STRINGS)
# Every class on Tuya's countdown that turn_on_for serves, each sent that call.
COUNTDOWNS = (TUYA_COUNTDOWN, *VERIFIED_COUNTDOWNS)
# Every plug on converter A's countdown, served or not: its OnTime is the countdown last set, not the time left.
COUNTDOWN_PLUGS = frozenset({*COUNTDOWNS, TUYA_COUNTDOWN_HARMED})
CLASSES = frozenset(
    {HUE, TUYA_ZCL, TUYA_TS011F, *COUNTDOWNS, TUYA_COUNTDOWN_HARMED, TUYA_MCU, SENGLED, GLEDOPTO, OTHER}
)

# The fields a rule may test: the registry device's; the Zigbee manufacturer and model bridge/devices holds; and from
# its definition there, Z2M's model and the properties of its device-wide top-level exposes (DEFINITION).
REGISTRY = frozenset({"manufacturer", "model", "model_id"})
ZIGBEE = {"zigbee_manufacturer": "manufacturer", "zigbee_model": "model_id"}  # rule field: bridge/devices key
DEFINITION = frozenset({"definition_model", "exposes"})


@dataclass(frozen=True, slots=True)
class Rule:
    """A class and the fields that place a device in it, each a regex the field must fully match; every condition
    must hold, and there is at least one."""

    capability: str
    conditions: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.capability not in CLASSES - {OTHER}:
            raise ValueError(f"a rule names {self.capability!r}, no class but the default's")
        if not self.conditions:
            raise ValueError(f"a rule for {self.capability!r} tests nothing")
        if unknown := self.conditions.keys() - REGISTRY - ZIGBEE.keys() - DEFINITION:
            raise ValueError(f"a rule tests {sorted(unknown)}, which neither the registry nor bridge/devices holds")

    def matches(self, strings: Mapping[str, str | frozenset[str] | None]) -> bool:
        """Whether every condition holds: a string field fully matches its pattern, a set (`exposes`) has a member
        that does."""
        return all(
            any(re.fullmatch(pattern, value) for value in values)
            if isinstance(values := strings.get(name), frozenset)
            else isinstance(values, str) and re.fullmatch(pattern, values)
            for name, pattern in self.conditions.items()
        )


# Tuya's Zigbee manufacturer strings (research/2026-11-14-timed-on-call-patterns.md, §4): `_TZE…` for datapoint
# devices, `_TZ3000_…`, `_TZ3210_…` and `_TYZB01_…` for ZCL ones. Only the TS011F's are measured; the rest are Tuya's
# naming, from the converters and quirks.
_TUYA_MCU_MANUFACTURER = r"_TZE\d{3}_.*"
_TUYA_ZCL_MANUFACTURER = r"_TZ\d{4}_.*|_TYZB\d{2}_.*"

# Tuya's countdown, converter A, on a TS011F: the definition exposes `countdown` for the whole device (Z2M's own
# statement that it takes the key; a multi-gang one exposes one per endpoint, `countdown_l1`, so isn't matched) and
# isn't the ZOT60, whose `countdown` is a datapoint, converter B (research/2026-11-14-tuya-countdown.md, §1, The
# expose doesn't tell A from B).
_COUNTDOWN = {"zigbee_model": "TS011F", "exposes": "countdown", "definition_model": "(?!ZOT60$).*"}

RULES: tuple[Rule, ...] = (
    Rule(HUE, {"manufacturer": re.escape(HUE_MANUFACTURER)}),
    # The Zigbee strings, from bridge/devices.
    Rule(TUYA_COUNTDOWN_HARMED, {"zigbee_model": "TS011F", "zigbee_manufacturer": re.escape(_HARMED_STRING)}),
    *(
        Rule(string_class(string), _COUNTDOWN | {"zigbee_manufacturer": re.escape(string)})
        for string in VERIFIED_STRINGS
    ),
    Rule(TUYA_COUNTDOWN, _COUNTDOWN),
    Rule(TUYA_TS011F, {"zigbee_model": "TS011F"}),
    Rule(TUYA_MCU, {"zigbee_model": "TS0601"}),
    Rule(TUYA_MCU, {"zigbee_manufacturer": _TUYA_MCU_MANUFACTURER}),
    Rule(TUYA_ZCL, {"zigbee_manufacturer": _TUYA_ZCL_MANUFACTURER}),
    Rule(TUYA_ZCL, {"zigbee_model": r"TS\d{4}.*"}),
    Rule(SENGLED, {"manufacturer": "Sengled"}),
    # The registry manufacturer: Z2M's vendor `Gledopto`, in any case, as the devices' own Zigbee string is
    # `GLEDOPTO` (zigbee-herdsman-converters src/devices/gledopto.ts, at the research file's commit).
    Rule(GLEDOPTO, {"manufacturer": "(?i:gledopto)"}),
    # The registry, for a Tuya device bridge/devices doesn't show yet: Z2M's definition (`TS011F_plug_1`) and vendor.
    Rule(TUYA_TS011F, {"model_id": "TS011F(_.*)?"}),
    Rule(TUYA_MCU, {"model_id": "TS0601(_.*)?"}),
    Rule(TUYA_ZCL, {"manufacturer": "Tuya"}),
    Rule(TUYA_ZCL, {"model_id": "TS.*"}),
)

# The levels each adapter's scope holds (index.md, Device classes): Verified on Hue, whose bulbs every record ran on;
# `other` Documented where the call is the Verified one and no known class departs, else untested; the Tuya, Sengled
# and Gledopto classes untested, or left out where they're not yet supported.
# Tuya's TS011F plugs, on its countdown or not, take the rest of the actions' calls as any Tuya ZCL device does.
_TS011F = (TUYA_TS011F, *COUNTDOWNS, TUYA_COUNTDOWN_HARMED)
_UNTESTED = experimental(TUYA_ZCL, *_TS011F, TUYA_MCU, SENGLED, GLEDOPTO)
# Brightness fades and stop: the ZCL Level and Color commands Hue's are (native_control turns Philips' own off for a
# brightness fade), and no class known to depart from them.
FADE_BRIGHTNESS = STOP = verified(HUE) | documented(OTHER) | _UNTESTED
# Hue and saturation fades: a saturation fade is MoveToSaturation with Philips' own command held off, which holds a
# Hue bulb's hue; nothing shows other firmware does.
FADE_COLOR = verified(HUE) | experimental(OTHER) | _UNTESTED
# Raw ZCL reads and writes, which a datapoint device can't take. Other brands depart: a bulb without `onTime` can fail
# the read, and some come on, or at full, when written while off.
READ_WRITE = verified(HUE) | experimental(OTHER, TUYA_ZCL, *_TS011F, SENGLED, GLEDOPTO)
# turn_on_for: Hue on lights alone, as every record ran on a bulb, so a Hue plug (a switch) is untested. The Sengled
# needs a host-side off, which isn't built, so it is not yet supported; every other brand may depart (some never switch
# off), so `other` and `gledopto` are untested. Tuya's countdown plugs get that call (turn_on_for.py): each maker
# string with a record of its own Verified, on switches alone, as Z2M shows a plug, and the rest untested (plan
# Decision 35). The other Tuya classes are not yet supported, with an entry each, as today's call harms them.
TURN_ON_FOR = (
    verified(HUE, domains=("light",))
    | verified(*VERIFIED_COUNTDOWNS, domains=("switch",))
    | experimental(OTHER, GLEDOPTO, TUYA_COUNTDOWN)
)
# The other Tuya classes are not yet supported, and harmed by today's call (plan Decisions 20, 70 and 71): Z2M has no
# `on_time` converter for a definition built with `onOffCountdown`, or for a datapoint device, so it sends a plain On
# and the device stays on. Each has a call that would work, Z2M's `countdown`, which isn't built for them: converter
# A's for a TS011F Z2M shows no `countdown` for and the TS011F's kin (v0.1.0 builds it for the countdown plugs alone,
# plan Decision 72), the datapoint one for TS0601 devices (v0.1.x, docs/plans/2026-11-15-tuya-datapoint-countdown.md).
# `harms`, so the dispatcher refuses a device not yet placed as well, which could be one of them (plan Decision 26).
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


def _listed(hass: HomeAssistant, device: dr.DeviceEntry) -> dict | None:
    """The device's entry in the held bridge/devices; None while none is held, or for a device it doesn't list."""
    if (ieee := z2m_address(device)) is None or (cache := bridge_cache.get(hass)) is None:
        return None
    return cache.device(ieee)


def zigbee_strings(entry: Mapping | None) -> dict[str, str]:
    """The Zigbee manufacturer and model in a device's bridge/devices entry (`_listed`), as rule fields, each only
    when it is a non-empty string (Z2M holds null until the interview reads it); empty with no entry."""
    if entry is None:
        return {}
    return {name: value for name, key in ZIGBEE.items() if isinstance(value := entry.get(key), str) and value}


def definition_fields(entry: Mapping | None) -> dict[str, str | frozenset[str]]:
    """The rule fields from the definition in a device's bridge/devices entry: Z2M's model (`definition_model`), and
    the properties of its top-level exposes for the whole device, none for an endpoint (`exposes`), each only when the
    entry holds it (Z2M holds a null definition for a device it doesn't support); empty with no entry."""
    definition = entry.get("definition") if entry is not None else None
    if not isinstance(definition, Mapping):
        return {}
    fields: dict[str, str | frozenset[str]] = {}
    if isinstance(model := definition.get("model"), str) and model:
        fields["definition_model"] = model
    if isinstance(exposes := definition.get("exposes"), list):
        # By property, and the device's own alone: a per-endpoint copy keeps the name and suffixes the property
        # (`countdown_l1`, with `endpoint` set: ZHC's `withEndpoint`).
        fields["exposes"] = frozenset(
            prop
            for expose in exposes
            if isinstance(expose, Mapping)
            and expose.get("endpoint") is None
            and isinstance(prop := expose.get("property"), str)
        )
    return fields


def zigbee_manufacturer(hass: HomeAssistant, device: dr.DeviceEntry) -> str | None:
    """Zigbee2MQTT's IntegrationInfo.zigbee_manufacturer: the device's own Zigbee manufacturer string from the held
    bridge/devices, where the registry holds the definition's vendor; None until bridge/devices lists it with one."""
    return zigbee_strings(_listed(hass, device)).get("zigbee_manufacturer")


def placed(found: str, entry: Mapping | None, zigbee: Mapping[str, str]) -> bool:
    """Whether a device of class `found` is placed: its bridge/devices entry (`_listed`) has it interviewed
    (`interview_completed`) with both Zigbee strings (`zigbee`, as zigbee_strings reads them), or its class is `hue`."""
    # `hue` is the one class no Zigbee-string rule can override: its rule comes first, reads the registry alone, and is
    # the only one naming `hue`, so a device's class is `hue` exactly when its registry shows it (test_classes pins it).
    if found == HUE:
        return True
    return entry is not None and entry.get("interview_completed") is True and zigbee.keys() == ZIGBEE.keys()


def _why_unplaced(hass: HomeAssistant, entry: Mapping | None, zigbee: Mapping[str, str]) -> str:
    """Why `placed` said no, for the DEBUG line: what DeviceSide is still waiting for."""
    if (cache := bridge_cache.get(hass)) is None:
        return "no bridge cache"
    if entry is None:
        return "no bridge/devices yet" if cache.parsed("devices") is None else "bridge/devices doesn't list it"
    if entry.get("interview_completed") is not True:
        return "not interviewed"
    return "no Zigbee " + " or ".join(key for name, key in ZIGBEE.items() if name not in zigbee)


def device_class(device: dr.DeviceEntry, bridge: Mapping[str, str | frozenset[str] | None] | None = None) -> str:
    """The class of a device Z2M registered: the first rule its registry and bridge/devices fields (`bridge`: the
    Zigbee strings and the definition's) match, else the default."""
    strings = {name: getattr(device, name) for name in REGISTRY} | dict(bridge or {})
    return next((rule.capability for rule in RULES if rule.matches(strings)), OTHER)


def capability(hass: HomeAssistant, target: Target) -> str | None:
    """Zigbee2MQTT's IntegrationInfo.capability: the target's device's class, Unplaced until it is `placed`; None for
    a target with no device, which no rule can place and no adapter can address."""
    if target.device is None:
        return None
    entry = _listed(hass, target.device)
    zigbee = zigbee_strings(entry)
    found = device_class(target.device, zigbee | definition_fields(entry))
    if placed(found, entry, zigbee):
        return found
    if _LOGGER.isEnabledFor(logging.DEBUG):
        _LOGGER.debug(
            "%s: class %s is provisional until Zigbee2MQTT reports the device (%s)",
            target.entity_id,
            found,
            _why_unplaced(hass, entry, zigbee),
        )
    return Unplaced(found)
