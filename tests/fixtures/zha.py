"""Fabricate ZHA entities and groups the way the zha library registers them."""

from types import SimpleNamespace

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

IEEE = "00:17:88:01:02:03:04:05"
# A Hue bulb's Zigbee strings (research/2026-11-14-lab-probe.md, §1), which place a device in the `hue` class.
HUE = ("Signify Netherlands B.V.", "LTA009")
# Where add_zha_entity keeps the zigpy devices it fabricates, by IEEE, for zigpy_devices to answer from.
_ZIGPY = "test_zha_zigpy_devices"


class StandardOnOff:
    """An On/Off cluster as zigpy defines it: `command` from zigpy, as a quirk keeping the standard frame leaves it."""

    command = None


StandardOnOff.__module__ = "zigpy.zcl"


def quirk_on_off(module: str) -> type:
    """An On/Off cluster whose quirk, in `module`, defines its own `command`, as a Tuya datapoint quirk does."""
    return type("QuirkOnOff", (StandardOnOff,), {"command": None, "__module__": module})


def zigpy_device(strings: tuple[str | None, str | None], endpoint: int, on_off: type = StandardOnOff):
    """A zigpy device: its raw manufacturer and model, and an On/Off cluster of type `on_off` on `endpoint`."""
    manufacturer, model = strings
    clusters = {0x0006: on_off()}
    return SimpleNamespace(
        manufacturer=manufacturer,
        model=model,
        endpoints={endpoint: SimpleNamespace(in_clusters=clusters)},
    )


def zigpy_devices(hass: HomeAssistant) -> dict:
    """The zigpy devices add_zha_entity fabricated, by IEEE, for a fake zcl.zigpy_device to answer from."""
    return hass.data.setdefault(_ZIGPY, {})


def zha_entry(hass: HomeAssistant) -> MockConfigEntry:
    """The one loaded ZHA config entry every ZHA device shares."""
    entry = MockConfigEntry(domain="zha")
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    return entry


def add_zha_entity(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    entity_id: str,
    ieee: str = IEEE,
    unique_id: str | None = None,
    state: str = "off",
    attributes: dict | None = None,
    strings: tuple[str | None, str | None] = HUE,
    on_off: type = StandardOnOff,
) -> str:
    """Register a ZHA entity; a light's unique_id is "{ieee}-{endpoint_id}" unless one is given. Its zigpy device has
    the Zigbee manufacturer and model `strings`, a Hue bulb's unless given, which the registry device shows too, and an
    On/Off cluster of type `on_off` on the entity's endpoint."""
    domain, object_id = entity_id.split(".")
    manufacturer, model = strings
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("zha", ieee)}, manufacturer=manufacturer, model=model
    )
    tail = (unique_id or f"{ieee}-11").removeprefix(f"{ieee}-")
    endpoint = int(tail) if tail.isdigit() else 11
    zigpy_devices(hass)[ieee] = zigpy_device(strings, endpoint, on_off)
    er.async_get(hass).async_get_or_create(
        domain,
        "zha",
        unique_id or f"{ieee}-11",
        suggested_object_id=object_id,
        config_entry=entry,
        device_id=device.id,
    )
    hass.states.async_set(entity_id, state, attributes)
    return entity_id


def zha_group(*members: tuple[str, int], coordinator: str | None = None, unknown: int = 0) -> SimpleNamespace:
    """A zha library Group: members as (ieee, endpoint_id), the way GroupMember exposes them, plus the `coordinator`
    (an IEEE) when it is one, and `unknown` members zigpy holds that ZHA doesn't, which Group.members leaves out."""
    listed = [(ieee, endpoint, False) for ieee, endpoint in members]
    if coordinator is not None:
        listed.append((coordinator, 1, True))
    zha_members = [
        SimpleNamespace(device=SimpleNamespace(ieee=ieee, is_coordinator=is_coordinator), endpoint_id=endpoint)
        for ieee, endpoint, is_coordinator in listed
    ]
    zigpy_members = {(ieee, endpoint): None for ieee, endpoint, _ in listed}
    zigpy_members |= {(f"ff:ff:ff:ff:ff:ff:ff:{n:02x}", 1): None for n in range(unknown)}
    return SimpleNamespace(members=zha_members, zigpy_group=SimpleNamespace(members=zigpy_members))
