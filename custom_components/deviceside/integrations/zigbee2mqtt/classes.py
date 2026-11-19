"""Zigbee2MQTT's device classes (docs/evidence.md, Device classes): which firmware family a target's device is.

On Zigbee the call and the firmware family decide the result together, so one call proves nothing across vendors
(research/2026-11-14-timed-on-call-patterns.md). Each vendor's classes, rules and levels are its family's
(families/<family>/); a class is named by the families' rules in the integration's order (families/__init__.py, the
home for the rule order), the first match winning, and `other`, the default class, for a device none places. This
module holds what is the integration's: `other` and its levels, `capability`, and when a device is placed.

The registry fallback's limit: until bridge/devices arrives after a connect, for a device it doesn't list yet, or for
one it lists without its strings (mid-interview), the Tuya rules on the Zigbee strings can't match, so the registry
rules place what the registry can show: vendor `Tuya`, or a definition model that starts `TS`. A Tuya device under
another vendor's definition shows neither: Lidl's `HG06337` lands in `other`, and Gledopto's GL-SPI-206P in
`gledopto`, until the strings arrive. `capability` answers that case with the class as core's Unplaced, by one rule
(`placed`): a device is placed once bridge/devices lists it with `interview_completed` true and both Zigbee strings
(Z2M's bridge/devices, https://www.zigbee2mqtt.io/guide/usage/mqtt_topics_and_messages.html), or when the registry
puts it in a class no Zigbee-string rule can override (families.REGISTRY_PLACED: `hue`). So a registry Tuya class
waits too (refused either way), a rule added before the Zigbee-string rules can't become final by accident, and a
class a later call serves (part 3's countdown) still waits for the full strings. An Unplaced class is that class to
every adapter but one whose call harms a class (turn_on_for's, with refusals.py's Tuya entries), where
the dispatcher refuses it as class_unknown (plan Decisions 23 and 26; docs/evidence.md, where a call is known to harm, a
class not yet known is refused). A group is no device of its own: the dispatcher classes its members
(members.expand_group), and falls back to them when one isn't placed. A device whose interview never completes stays
Unplaced until it is paired again, so its groups fall back for good, one call per member (index.md, Device classes).
`capability` logs, at DEBUG, what an Unplaced device is waiting for.

Each adapter's scope holds the families' levels, `other`'s below and the refusal entries in refusals.py
(`class_scope`); why each class sits where it does is in index.md (Device classes) and the step 5 PR body.
"""

import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from . import bridge_cache, rules
from .addressing import z2m_address
from .families import FAMILIES, REGISTRY_PLACED, RULES
from .refusals import REFUSALS
from .rules import ZIGBEE, definition_fields, zigbee_strings
from ...core import scope
from ...core.models import Target
from ...core.rules import match
from ...core.scope import OTHER, ClassDomains, ClassLevel, Unplaced, labs

_LOGGER = logging.getLogger(__name__)

# Every class with its domains (IntegrationInfo.classes): `other`, any brand's light, plug or switch, and the families'.
CLASSES: ClassDomains = {OTHER: frozenset({Platform.LIGHT, Platform.SWITCH})} | {
    name: domains for family in FAMILIES for name, domains in family.classes.items()
}

# `other`'s level in each adapter's scope (index.md, Device classes; docs/evidence.md, In Labs): in Labs only where
# research predicts most of it accepts the call, and not built elsewhere (an empty mapping). It spans vendors, so a
# Hue bulb's pass makes it neither Documented nor in Labs.
# Brightness fades and stop: Level Control's Move, MoveToLevel and Stop, which a Zigbee 3.0 dimmable light must take
# (docs/internals.md, Shared); native_control.py turns Philips' own off for a brightness fade.
_CERTIFIED = labs(OTHER)
_NOT_BUILT: Mapping[str, ClassLevel] = {}
OTHER_LEVELS: Mapping[str, Mapping[str, ClassLevel]] = {
    "raise_brightness": _CERTIFIED,
    "lower_brightness": _CERTIFIED,
    "stop": _CERTIFIED,
    # Hue and saturation moves: no research predicts how other firmware takes them.
    "raise_hue": _NOT_BUILT,
    "lower_hue": _NOT_BUILT,
    "raise_saturation": _NOT_BUILT,
    "lower_saturation": _NOT_BUILT,
    # Raw ZCL reads and writes: other brands depart (a bulb without `onTime` can fail the read, and some come on, or at
    # full, when written while off).
    "get_attributes": _NOT_BUILT,
    "set_attributes": _NOT_BUILT,
    # turn_on_for: its call harms some lights and most plugs, so the integration refuses `other` there (refusals.py).
    "turn_on_for": _NOT_BUILT,
}


def class_scope(action: str) -> dict[str, Any]:
    """An adapter's AdapterScope fields that are held by class, for its action (core/scope.py, class_scope): `other`
    at its own level, the families' classes and own calls, and the integration's refusal entries (refusals.py)."""
    return scope.class_scope(action, families=FAMILIES, default_levels=OTHER_LEVELS, refusals=REFUSALS)


def _listed(hass: HomeAssistant, device: dr.DeviceEntry) -> dict | None:
    """The device's entry in the held bridge/devices; None while none is held, or for a device it doesn't list."""
    if (ieee := z2m_address(device)) is None or (cache := bridge_cache.get(hass)) is None:
        return None
    return cache.device(ieee)


def zigbee_manufacturer(hass: HomeAssistant, device: dr.DeviceEntry) -> str | None:
    """Zigbee2MQTT's IntegrationInfo.zigbee_manufacturer: the device's own Zigbee manufacturer string from the held
    bridge/devices, where the registry holds the definition's vendor; None until bridge/devices lists it with one."""
    return zigbee_strings(_listed(hass, device)).get("zigbee_manufacturer")


def placed(found: str, entry: Mapping | None, zigbee: Mapping[str, str]) -> bool:
    """Whether a device of class `found` is placed: its bridge/devices entry (`_listed`) has it interviewed
    (`interview_completed`) with both Zigbee strings (`zigbee`, as zigbee_strings reads them), or its class is one the
    registry alone places."""
    # A class the registry alone places (`hue`), which no Zigbee-string rule can override: every rule up to its own
    # reads the registry alone, so a device is in it exactly when its registry shows it (families/__init__.py
    # declares and checks it).
    if found in REGISTRY_PLACED:
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
    return match(RULES, rules.read(device, bridge)) or OTHER


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
