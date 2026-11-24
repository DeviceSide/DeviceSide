"""Read a registry device's identifiers by their first two parts.

Home Assistant types DeviceEntry.identifiers as (domain, value) pairs but stores any tuple, and one HomeKit device's has
three. Unpacking every identifier as a pair raised on that one device, wherever the registry is walked.
"""

from collections.abc import Iterator

from homeassistant.helpers import device_registry as dr


def identifier_values(device: dr.DeviceEntry, domain: str) -> Iterator[str]:
    """The device's identifier values under `domain`. Each identifier is read by its first two parts and skipped if it
    has fewer: HA types them as pairs but stores any tuple (one HomeKit device's has three)."""
    return (ident[1] for ident in device.identifiers if len(ident) >= 2 and ident[0] == domain)
