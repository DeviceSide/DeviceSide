"""Signify's own cluster on Hue bulbs, whose multiColor command sets on, brightness and fade time in one; Z2M sends it
with hue_native_control on (zigbee-herdsman-converters src/lib/philips.ts). Keyed on the cluster, not the class: a
light without it gets nothing, and the adapter its standard call."""

import logging
import struct

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from ... import zcl
from ...addressing import Address

_LOGGER = logging.getLogger(__name__)

CLUSTER = 0xFC03
MULTI_COLOR = 0x00
SIGNIFY = 0x100B
# multiColor's payload: flags, then each flagged field in Hue's wire order: on (1 byte), brightness (1 byte, 1-254),
# fade time (2 bytes, tenths).
_ON_BRIGHTNESS_FADE = 0x0013


async def turn_on(hass: HomeAssistant, addr: Address, level: int, context: Context | None, *, entity_id: str) -> bool:
    """Turn a Hue bulb on at `level`, with no fade, in one multiColor command; False, with nothing sent, for a light
    without Hue's cluster.

    A Hue bulb on ZHA ignores a level sent just before it is turned on, by MoveToLevel with ExecuteIfOff or by
    MoveToLevelWithOnOff, and fades from its stored one; turned on this way it starts at `level`, as on Z2M with
    hue_native_control. zha has no action for a command its cluster doesn't define, so it goes to zigpy, behind zha's
    admin check. Raises on a delivery failure or a non-success status, as zcl.command does.
    """
    from zigpy.types import EUI64, SerializableBytes, Struct

    if (device := zcl.gateway(hass).get_device(EUI64.convert(addr.ieee))) is None:
        raise LookupError(f"ZHA device of {entity_id} not found")
    try:
        cluster = device.async_get_cluster(addr.endpoint_id, CLUSTER, cluster_type="in")
    except KeyError:
        return False
    await zcl.require_admin(hass, context)

    class MultiColor(Struct):
        data: SerializableBytes

    payload = struct.pack("<HBBH", _ON_BRIGHTNESS_FADE, 1, max(1, min(level, 254)), 0)
    _LOGGER.debug("%s: sending zcl %s %s", entity_id, zcl.command_name(CLUSTER, MULTI_COLOR), payload.hex())
    response = await cluster.request(False, MULTI_COLOR, MultiColor, payload, manufacturer=SIGNIFY)
    if (status := getattr(response, "status", 0)) != 0:
        raise HomeAssistantError(f"multiColor to {entity_id} answered {status}")
    return True
