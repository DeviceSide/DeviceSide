"""The wire trace: each call a transport sends to a device, fired as the HA event `deviceside_wire` while the logger
`custom_components.deviceside.wire` is at DEBUG, so a test rig can see the calls an action made.

The event's data names the target by its entity_id and carries the payload alone: never the device's addressing (an
IEEE, a Hue resource ID, a Shelly component ID, an MQTT device topic), so a trace reads the same on any household.
Reads are not traced.
"""

import copy
import logging
from typing import Any

from homeassistant.core import HomeAssistant

WIRE_EVENT = "deviceside_wire"
WIRE_LOGGER = logging.getLogger("custom_components.deviceside.wire")


def wire_enabled() -> bool:
    """Whether the trace is on, for a caller that must look something up to name the entity: off, it costs nothing."""
    return WIRE_LOGGER.isEnabledFor(logging.DEBUG)


def wire_trace(hass: HomeAssistant, entity_id: str | None, transport: str, command: str, params: Any) -> None:
    """Fire the trace of one call, before it is sent, when the wire logger is at DEBUG; else do nothing.

    `transport` is the wire (zcl, clip, rpc, mqtt, matter, or ha for an HA action an adapter calls), `command` the
    call within it, and `params` its JSON-serializable payload. A call to a device with no entity is not traced.
    """
    if entity_id is None or not wire_enabled():
        return
    # A copy: an adapter may pass a shared constant, which a listener must not be able to change.
    data = {"entity_id": entity_id, "transport": transport, "command": command, "params": copy.deepcopy(params)}
    WIRE_LOGGER.debug("%s", data)
    hass.bus.async_fire(WIRE_EVENT, data)
