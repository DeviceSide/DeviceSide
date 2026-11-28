"""Fabricate TP-Link entities the way the core tplink integration registers them, with python-kasa device objects faked.

python-kasa stays out of the test environment: the integration must load without it. DeviceSide reads a device's class
from its `device_type` name and the `kasa` package its class is defined in (integrations/tplink/classes.py), so each
fake sets its `__module__` to where python-kasa defines the real one.
"""

from enum import Enum
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

MAC = "AA:BB:CC:DD:EE:FF"
# A SMART device's id is 40 hex characters; an IOT plug's is "<mac>_<id>" (python-kasa), which core's
# legacy_device_id shortens to the part after the underscore.
SMART_ID = "80228C0A1B2C3D4E5F60718293A4B5C6D7E8F901"
IOT_ID = "8006A1B2C3D4E5F60718293A4B5C6D7E8F901234"


class DeviceType(Enum):
    """The names of python-kasa's DeviceType (kasa/device_type.py) the rules read; DeviceSide reads `.name`."""

    Plug = "plug"
    WallSwitch = "wallswitch"
    Strip = "strip"
    StripSocket = "stripsocket"
    Bulb = "bulb"
    Dimmer = "dimmer"
    LightStrip = "lightstrip"
    Hub = "hub"
    Fan = "fan"


class Protocol:
    """Stands in for python-kasa's device protocol: `query` is the one method DeviceSide calls, a method on the class
    (the wire boundary tests/integrations/tplink/wire.py wraps) that awaits the test's mock, so a test sets
    `side_effect` and reads the calls there."""

    def __init__(self, query: AsyncMock) -> None:
        self.mock = query

    async def query(self, request: dict | str, retry_count: int = 3) -> dict:
        return await self.mock(request)


class Device:
    """The attributes of python-kasa's Device that DeviceSide reads."""

    def __init__(self, device_type: DeviceType, device_id: str, query: AsyncMock, parent: Device | None = None):
        self.device_type = device_type
        self.device_id = device_id
        self.mac = MAC
        self.parent = parent
        self.children: list[Device] = []
        self.protocol = Protocol(query)
        if parent is not None:
            parent.children.append(self)


# python-kasa defines IOT devices under kasa.iot and SMART ones (children included) under kasa.smart.
class IotDevice(Device):
    __module__ = "kasa.iot.iotdevice"


class SmartDevice(Device):
    __module__ = "kasa.smart.smartdevice"


def iot_device(device_type: DeviceType, query: AsyncMock, device_id: str = "", parent: Device | None = None) -> Device:
    return IotDevice(device_type, device_id or f"{MAC}_{IOT_ID}", query, parent)


def smart_device(
    device_type: DeviceType, query: AsyncMock, device_id: str = SMART_ID, parent: Device | None = None
) -> Device:
    return SmartDevice(device_type, device_id, query, parent)


def tplink_entry(hass: HomeAssistant, device: Device, loaded: bool = True) -> tuple[MockConfigEntry, AsyncMock]:
    """A config entry whose runtime_data.parent_coordinator holds `device`; also the refresh mock. `loaded` False gives
    an entry whose setup hasn't run (no runtime_data)."""
    refresh = AsyncMock()
    entry = MockConfigEntry(domain="tplink", unique_id=device.mac)
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    if loaded:
        coordinator = SimpleNamespace(device=device, async_request_refresh=refresh)
        entry.runtime_data = SimpleNamespace(parent_coordinator=coordinator)
    return entry, refresh


def add_tplink_entity(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    entity_id: str,
    unique_id: str,
    state: str = "off",
    attributes: dict | None = None,
) -> str:
    """Register an entity under `unique_id`, the one core's tplink gives it (integrations/tplink/addressing.py)."""
    domain, object_id = entity_id.split(".")
    device = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, identifiers={("tplink", unique_id)})
    er.async_get(hass).async_get_or_create(
        domain, "tplink", unique_id, suggested_object_id=object_id, config_entry=entry, device_id=device.id
    )
    hass.states.async_set(entity_id, state, attributes or {})
    return entity_id
