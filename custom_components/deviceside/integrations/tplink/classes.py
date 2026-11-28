"""TP-Link's device classes (docs/evidence.md, Device classes): which of python-kasa's device objects a target is,
and so which countdown call it takes.

The class is read from the core tplink config entry's device object (`entry.runtime_data.parent_coordinator.device` and
its `children`, tplink/__init__.py) by name: python-kasa's `device_type` (an enum, read by its `.name`) and the module
its device class lives in (`kasa.iot` or `kasa.smart`). Neither `kasa` nor
`homeassistant.components.tplink` (importing it loads python-kasa) is imported, so the module loads where TP-Link
isn't installed.
The rules, by the device's type (docs/plans/2026-11-28-tplink-integration.md, Classes):

- IOT `Plug` and `WallSwitch`: `iot_plug`. `StripSocket`: `iot_strip_outlet`.
- SMART `Plug` and `WallSwitch`: `smart_plug` with no parent, `smart_strip_child` under a `Strip`,
  `smart_hub_child` under a `Hub`.
- SMART `Bulb`, `Dimmer` and `LightStrip`, parent or child (a KS240's dimmer is a child): `smart_light`.
- IOT `Bulb`, `Dimmer` and `LightStrip`: `iot_light`, not built (its `count_down` namespace is unsourced).

Any other device (a strip parent, a hub, a fan, a thermostat) has no class and no entity DeviceSide addresses
(addressing.unsupported_reason).
"""

from typing import Any

from homeassistant.const import Platform

from ...const import DOCS_URL
from ...core.scope import NotBuilt

IOT_PLUG = "iot_plug"
IOT_STRIP_OUTLET = "iot_strip_outlet"
SMART_PLUG = "smart_plug"
SMART_STRIP_CHILD = "smart_strip_child"
SMART_HUB_CHILD = "smart_hub_child"
SMART_LIGHT = "smart_light"
IOT_LIGHT = "iot_light"

_SWITCH = frozenset({Platform.SWITCH})
_LIGHT = frozenset({Platform.LIGHT})
# Each class's domains (IntegrationInfo.classes).
CLASSES = {
    IOT_PLUG: _SWITCH,
    IOT_STRIP_OUTLET: _SWITCH,
    SMART_PLUG: _SWITCH,
    SMART_STRIP_CHILD: _SWITCH,
    SMART_HUB_CHILD: _SWITCH,
    SMART_LIGHT: _LIGHT,
    IOT_LIGHT: _LIGHT,
}

# python-kasa's DeviceType names (kasa/device_type.py) the rules read.
_SWITCHES = frozenset({"Plug", "WallSwitch"})
_LIGHTS = frozenset({"Bulb", "Dimmer", "LightStrip"})

# The adapters whose failure harms refuse the class they can't serve, so a device not yet loaded (no class) is
# class_unknown and this one is not_built, never a call: turn_on_for and turn_off_for's scopes hold it
# (docs/evidence.md, Not built yet).
IOT_LIGHT_NOT_BUILT = NotBuilt(
    reason="Its countdown namespace isn't known: python-kasa's own module queries one a KP115 doesn't serve, and no "
    "source or probe covers a Kasa bulb or dimmer",
    source=DOCS_URL + "docs/integrations/tplink/internals.md",
)


def family(device: Any) -> str:
    """`iot` or `smart`: the python-kasa package (`kasa.iot`, `kasa.smart`) the device's class is defined in."""
    parts = type(device).__module__.split(".")
    return parts[1] if len(parts) > 1 and parts[0] == "kasa" else ""


def device_type(device: Any) -> str:
    return getattr(device.device_type, "name", "")


def classify(device: Any) -> str | None:
    """The class of one python-kasa device object, by the rules above; None for a device with none."""
    kind, name = family(device), device_type(device)
    parent = getattr(device, "parent", None)
    if kind == "iot":
        if name in _SWITCHES:
            return IOT_PLUG
        if name == "StripSocket":
            return IOT_STRIP_OUTLET
        return IOT_LIGHT if name in _LIGHTS else None
    if kind != "smart":
        return None
    if name in _LIGHTS:
        return SMART_LIGHT
    if name in _SWITCHES:
        if parent is None:
            return SMART_PLUG
        return {"Strip": SMART_STRIP_CHILD, "Hub": SMART_HUB_CHILD}.get(device_type(parent))
    return None
