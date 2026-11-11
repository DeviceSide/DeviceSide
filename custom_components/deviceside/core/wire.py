"""The wire trace: each call a transport sends to a device, fired as the HA event `deviceside_wire` while the logger
`custom_components.deviceside.wire` is at DEBUG, so a test rig can see the calls an action made.

The event's data names the target by its entity_id and carries the payload alone: never the device's addressing (an
IEEE, a Hue resource ID, a Shelly component ID, an MQTT device topic), so a trace reads the same on any household.
A transport setting that changes how the call is encoded rides the event as `options`, apart from `params`; addressing
never does. Z2M stamps its `hue_native_control` this way on every set, since the same payload sends different Zigbee
commands with it on and off, and a rig comparing traces must not read two such runs as one. Reads are not traced.

The same logger gates the scope trace, `deviceside_scope`: one event per target the dispatcher runs, past the
Experimental gate, naming what `AdapterScope.level()` weighed for it (its domain, the capability the adapter named,
null when none, and the fields the call carries after drops). A rig unions it over the cases a run passed into its
record's `Covers:` line, which `check_release.py --records` holds against the adapter's Verified scope. The target is
named by the entity_id results are keyed on.
"""

import copy
import logging
from typing import Any

from homeassistant.core import HomeAssistant

WIRE_EVENT = "deviceside_wire"
SCOPE_EVENT = "deviceside_scope"
WIRE_LOGGER = logging.getLogger("custom_components.deviceside.wire")


def wire_enabled() -> bool:
    """Whether the trace is on, for a caller that must look something up to name the entity: off, it costs nothing."""
    return WIRE_LOGGER.isEnabledFor(logging.DEBUG)


def wire_trace(
    hass: HomeAssistant,
    entity_id: str | None,
    transport: str,
    command: str,
    params: Any,
    options: dict | None = None,
) -> None:
    """Fire the trace of one call, before it is sent, when the wire logger is at DEBUG; else do nothing.

    `transport` is the wire (zcl, clip, rpc, mqtt, matter, or ha for an HA action an adapter calls), `command` the
    call within it, and `params` its JSON-serializable payload. A call to a device with no entity is not traced.

    `options` is the transport's own settings that change how it encodes this call (Z2M entity options), never
    addressing; the event gains an `options` key when given. Other transports pass nothing, and their events are
    unchanged.
    """
    if entity_id is None or not wire_enabled():
        return
    # A copy: an adapter may pass a shared constant, which a listener must not be able to change.
    data = {"entity_id": entity_id, "transport": transport, "command": command, "params": copy.deepcopy(params)}
    if options is not None:
        data["options"] = copy.deepcopy(options)
    WIRE_LOGGER.debug("%s", data)
    hass.bus.async_fire(WIRE_EVENT, data)


def scope_trace(
    hass: HomeAssistant,
    entity_id: str,
    action: str,
    integration: str,
    domain: str,
    capability: str | None,
    fields: frozenset[str],
) -> None:
    """Fire the scope trace of one target about to run, when the wire logger is at DEBUG; else do nothing."""
    if not wire_enabled():
        return
    data = {
        "entity_id": entity_id,
        "action": action,
        "integration": integration,
        "domain": domain,
        "capability": capability,
        "fields": sorted(fields),
    }
    WIRE_LOGGER.debug("%s", data)
    hass.bus.async_fire(SCOPE_EVENT, data)
