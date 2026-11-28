"""Which python-kasa device a TP-Link entity is, from the registry and the config entry's device object alone.

Never from kasa or homeassistant.components.tplink, whose import would make this adapter module unavailable wherever
TP-Link isn't installed (classes.py).
"""

from typing import Any

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .classes import classify, device_type, family
from ...core.errors import Reason
from ...core.models import Target


def legacy_device_id(device: Any) -> str:
    """Core's `legacy_device_id` (tplink/__init__.py): python-kasa's plug ids are prefixed with the mac
    (`<mac>_<id>`), and the unique_id of the primary `state` entity, the switch, is the part after it
    (tplink/entity.py, `_get_feature_unique_id`)."""
    device_id: str = device.device_id
    if "_" not in device_id:
        return device_id
    return device_id.split("_")[1]


def _light_unique_id(device: Any) -> str:
    """The unique_id of a device's light entity (tplink/light.py, `_get_backwards_compatible_light_unique_id`): the
    legacy device id for an IOT dimmer and any device with a parent or children, else its mac, upper case, no colons."""
    if (family(device) == "iot" and device_type(device) == "Dimmer") or device.parent or device.children:
        return legacy_device_id(device)
    return str(device.mac).replace(":", "").upper()


def _unique_id(device: Any, domain: str) -> str:
    return _light_unique_id(device) if domain == Platform.LIGHT else legacy_device_id(device)


def parent_coordinator(target: Target) -> Any | None:
    """The entry's parent coordinator (its `.device` the python-kasa device, `async_request_refresh` its refresh),
    or None while the entry hasn't loaded."""
    return getattr(getattr(target.config_entry, "runtime_data", None), "parent_coordinator", None)


def device_for(target: Target) -> Any | None:
    """The python-kasa device the entity is the primary entity of, the entry's device or one of its children; None
    for any other entity (a feature entity, a strip parent's) or an entry that hasn't loaded."""
    if (coordinator := parent_coordinator(target)) is None:
        return None
    parent = coordinator.device
    for device in (parent, *parent.children):
        if target.entry.unique_id == _unique_id(device, target.domain) and classify(device) is not None:
            return device
    return None


def capability(hass: HomeAssistant, target: Target) -> str | None:
    """TP-Link's IntegrationInfo.capability: the class of the device the entity is, None while the entry hasn't loaded
    or for an entity that is none (unsupported_reason refuses it first)."""
    return classify(device) if (device := device_for(target)) is not None else None


def unsupported_reason(target: Target) -> str | None:
    """Why this entity can't take a countdown at all, or None. An entry that hasn't loaded gives None: it has no class
    (class_unknown), which the dispatcher refuses where the call harms. The dispatcher then checks the class."""
    if parent_coordinator(target) is None:
        return None
    return Reason.NOT_ADDRESSABLE if device_for(target) is None else None
