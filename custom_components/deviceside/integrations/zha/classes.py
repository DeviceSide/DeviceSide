"""ZHA's device classes (docs/evidence.md, Device classes): which firmware family a target's device is, and so which
call it takes. The vendor classes, the rules that place a device in them and their levels are each family's
(families/<family>/); the default class `other`, its levels and reading the device are the integration's, here, as
are the classes an action refuses with a reason (refusals.py).

What decides the outcome on ZHA (internals.md, `classes`, which cites the source): every adapter sends standard ZCL
through the cluster object a device's quirk puts on its endpoint. A quirk that keeps the standard command (Tuya's ZCL
quirks, Sonoff's; Hue bulbs and the Sengled have none) puts the same frame on the air for every device, so the
firmware decides the result, and the device's own Zigbee strings name the firmware. Where the quirk routes On/Off
itself, the quirk decides, so a rule can read it too (families/tuya).

Both come from zigpy's device (zcl.zigpy_device), never the registry: ZHA writes the registry from its own device's
`manufacturer` and `model`, which a v2 quirk's friendly name replaces (zha-quirks zhaquirks/builder/device.py), so a
Tuya device could show there under another maker. A v2 quirk leaves zigpy's strings; a v1 quirk's `replacement` can
rewrite them (BaseCustomDevice's set_device_attr), which no Tuya quirk does at the pinned commit (internals.md). Reading
the gateway is sync, with no I/O.

The rules run in the families' order (families/__init__.py), the first match winning, and `other`, the default class,
takes a device none places.

A ZHA device is never Unplaced: zigpy reads its strings and picks its quirk once, in the interview, before ZHA makes
its entities, and nothing reports them later, so the class is final when a target first exists. A device whose
interview couldn't read a string, or that the gateway doesn't hold, gets None, as no rule can place it until it is
reconfigured; where a call harms a class, core refuses None as class_unknown. A group is no device of its own: the
dispatcher classes its members (groups.expand_group).
"""

from collections.abc import Mapping
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from . import rules, zcl
from .addressing import address
from .families import FAMILIES, RULES
from .refusals import REFUSALS
from ...core import scope
from ...core.identifiers import identifier_values
from ...core.models import Target
from ...core.rules import match
from ...core.scope import OTHER, ClassDomains, ClassLevel, labs

# Every class with its domains (IntegrationInfo.classes): `other`, any brand's light, plug or switch, and the families'.
CLASSES: ClassDomains = {OTHER: frozenset({Platform.LIGHT, Platform.SWITCH})} | {
    name: domains for family in FAMILIES for name, domains in family.classes.items()
}

# `other`'s level in each adapter's scope (index.md, Device classes; docs/evidence.md, In Labs): in Labs only where
# research predicts most of it accepts the call, and not built elsewhere (an empty mapping). It spans vendors, so a
# Hue bulb's pass makes it neither Documented nor in Labs.
_NOT_BUILT: Mapping[str, ClassLevel] = {}
OTHER_LEVELS: Mapping[str, Mapping[str, ClassLevel]] = {
    # Brightness fades and stop: Level Control's Move, MoveToLevel and Stop, which a Zigbee 3.0 dimmable light must
    # take (docs/internals.md, Shared). raise_brightness from off sends MoveToLevel with ExecuteIfOff (fade.py).
    "lower_brightness": labs(OTHER),
    "raise_brightness": labs(OTHER),
    "stop": labs(OTHER),
    # Hue and saturation moves, reads and writes: no research predicts how other firmware takes them, and other
    # brands depart on reads and writes (a bulb without OnTime, one that comes on at full when written while off).
    "lower_hue": _NOT_BUILT,
    "lower_saturation": _NOT_BUILT,
    "raise_hue": _NOT_BUILT,
    "raise_saturation": _NOT_BUILT,
    "get_attributes": _NOT_BUILT,
    "set_attributes": _NOT_BUILT,
    # turn_on_for: its call harms some lights and most plugs, so the integration refuses `other` there (refusals.py).
    "turn_on_for": _NOT_BUILT,
}


def class_scope(action: str) -> dict[str, Any]:
    """An adapter's AdapterScope fields that are held by class, for its action (core/scope.py, class_scope): `other`
    at its own level, the families' classes and own calls, and the integration's refusal entries (refusals.py)."""
    return scope.class_scope(action, families=FAMILIES, default_levels=OTHER_LEVELS, refusals=REFUSALS)


def device_class(manufacturer: str | None, model: str | None, quirk: str | None = None) -> str | None:
    """The class of a device with these Zigbee strings and On/Off `quirk` module: the first rule they match, else the
    default; None when the interview didn't read a string, as no rule can place it."""
    if not manufacturer or not model:
        return None
    return match(RULES, rules.read(manufacturer, model, quirk)) or OTHER


def capability(hass: HomeAssistant, target: Target) -> str | None:
    """ZHA's IntegrationInfo.capability: the class of the target's zigpy device, by its Zigbee strings and the quirk on
    its On/Off cluster; None for a target with no address, or one the gateway doesn't hold."""
    if (addr := address(target.entry.unique_id)) is None or (device := zcl.zigpy_device(hass, addr.ieee)) is None:
        return None
    return device_class(device.manufacturer, device.model, _command_module(device, addr.endpoint_id))


def zigbee_manufacturer(hass: HomeAssistant, device: dr.DeviceEntry) -> str | None:
    """ZHA's IntegrationInfo.zigbee_manufacturer: the raw Zigbee manufacturer string of the zigpy device behind a
    registry device, the one the rules read; None for a device ZHA didn't register or the gateway doesn't hold. ZHA
    registers a device by identifier ("zha", its IEEE) (HA core homeassistant/components/zha/helpers.py,
    ZHADeviceProxy.device_info)."""
    ieee = next(identifier_values(device, "zha"), None)
    if ieee is None or (zigpy := zcl.zigpy_device(hass, ieee)) is None:
        return None
    return zigpy.manufacturer if isinstance(zigpy.manufacturer, str) and zigpy.manufacturer else None


def _command_module(device, endpoint_id: int) -> str | None:
    """The module that defines the `command` of the On/Off cluster on the target's endpoint: zigpy's for a standard
    cluster, the quirk's where it routes commands itself. None without one."""
    endpoint = device.endpoints.get(endpoint_id)
    if (cluster := endpoint.in_clusters.get(zcl.ON_OFF_CLUSTER) if endpoint is not None else None) is None:
        return None
    # Every zigpy Cluster defines `command`, so some class in the MRO does.
    return next(cls for cls in type(cluster).__mro__ if "command" in vars(cls)).__module__
