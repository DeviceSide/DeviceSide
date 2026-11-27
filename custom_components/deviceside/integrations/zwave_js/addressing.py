"""Parse a Z-Wave light's node and endpoint from its unique_id, and reach the node through the config entry.

No imports from homeassistant.components.zwave_js, and zwave_js_server only inside multilevel_switch_cc: the adapter
must import cleanly where neither is installed (the test environment, a Home Assistant without Z-Wave). Everything
Z-Wave-specific is read from hass.config_entries or a deferred import, as the Matter integration does.
"""

import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant

from ...core.errors import Reason
from ...core.models import Target

_LOGGER = logging.getLogger(__name__)

_ZWAVE_JS_DOMAIN = "zwave_js"
MULTILEVEL_SWITCH = 38  # Multilevel Switch command class (CC 0x26)

# A Z-Wave JS entity's unique_id is "{home_id}.{value_id}" (HA/helpers.py#L230-L232, get_unique_id; set from the
# entity's primary value at HA/entity.py#L103, home-assistant/core@66e9f19b16aa03edd174127b65cc80d066b8a39e), and a
# value_id is "{node_id}-{command_class}-{endpoint}-{property}[-{property_key}]" (zwave-js-server-python
# zwave_js_server/model/value.py#L139-L153 at 6ddab45f8fc93c45c47e866dc5909be21a7a1511). The home_id leads, so a
# unique_id with no "." never matches. The root endpoint is 0.
_VALUE_ID = re.compile(r"\d+\.(\d+)-\d+-(\d+)-")


def node_and_endpoint(unique_id: str) -> tuple[int, int] | None:
    """The (node_id, endpoint index) of a Z-Wave JS entity's primary value, or None for a unique_id of another shape."""
    if (found := _VALUE_ID.match(unique_id)) is None:
        return None
    return int(found.group(1)), int(found.group(2))


def zwave_client(hass: HomeAssistant, config_entry_id: str | None = None):
    """The ZwaveClient of a config entry, or None.

    When config_entry_id is supplied, that entry's client is returned; when omitted, the first loaded Z-Wave JS entry's
    (production: there is one). Reads hass.config_entries directly: in production entry.runtime_data is a ZwaveJSData
    whose .client is the zwave-js-server-python client (HA/models.py#L31-L35); in tests the fixture provides a stand-in.
    """
    if config_entry_id is not None:
        entry = hass.config_entries.async_get_entry(config_entry_id)
        if entry is None or not hasattr(entry, "runtime_data"):
            return None
        return entry.runtime_data.client

    entries = hass.config_entries.async_loaded_entries(_ZWAVE_JS_DOMAIN)
    if not entries or not hasattr(entries[0], "runtime_data"):
        return None
    return entries[0].runtime_data.client


def node_for(hass: HomeAssistant, target: Target):
    """The target's Node from the client's cache, sync and with no I/O, or None: an unparsable unique ID, no loaded
    Z-Wave JS entry, a client with no driver yet (not connected), or a node the controller doesn't hold."""
    if (found := node_and_endpoint(target.entry.unique_id)) is None:
        return None
    if (client := zwave_client(hass, target.entry.config_entry_id)) is None:
        return None
    if (driver := client.driver) is None:
        return None
    return driver.controller.nodes.get(found[0])


def endpoint_for(hass: HomeAssistant, target: Target):
    """The target's Endpoint, sync and with no I/O, or None where node_for finds no node or the node has no such
    endpoint."""
    if (node := node_for(hass, target)) is None:
        return None
    return node.endpoints.get(node_and_endpoint(target.entry.unique_id)[1])


def multilevel_switch_version(endpoint) -> int | None:
    """The endpoint's Multilevel Switch CC version, or None when it has no such CC (it isn't dimmable). Sync, no I/O:
    the endpoint's command_classes come from the node's interview."""
    return next((cc.version for cc in endpoint.command_classes if cc.id == MULTILEVEL_SWITCH), None)


def unsupported_reason(hass: HomeAssistant, target: Target) -> str | None:
    """Why DeviceSide can't address this entity's endpoint, or None: it needs a unique_id of a Z-Wave JS value and the
    node and endpoint it names, both in the client's cache."""
    return None if endpoint_for(hass, target) is not None else Reason.NOT_ADDRESSABLE


def light_reason(hass: HomeAssistant, target: Target) -> str | None:
    """Why a light action can't run on this entity, or None: unsupported_reason's, then not_dimmable for an endpoint
    with no Multilevel Switch CC, whose level Get, Set and Start Level Change are all calls of."""
    if reason := unsupported_reason(hass, target):
        return reason
    # unsupported_reason found the endpoint.
    return None if multilevel_switch_version(endpoint_for(hass, target)) is not None else "not_dimmable"


def multilevel_switch_cc():
    """zwave_js_server's CommandClass.SWITCH_MULTILEVEL (CC 38), the command class async_invoke_cc_api takes. Imported
    here, as the library isn't a dependency of the adapter's module."""
    from zwave_js_server.const import CommandClass  # noqa: PLC0415

    return CommandClass.SWITCH_MULTILEVEL


async def invoke_multilevel_switch(target: Target, endpoint, method: str, *args: Any) -> Any:
    """One Multilevel Switch CC API call on the endpoint (`get`, then the moves), and what it returns, the way
    Z-Wave JS's own light does for HA: through Endpoint.async_invoke_cc_api (zwave-js-server-python
    zwave_js_server/model/endpoint.py#L214-L236), which raises NotFoundError for a CC the endpoint lacks and returns
    the CC's result. Logs the per-call DEBUG line (docs/logging.md); the node isn't named, as its ID is an address."""
    _LOGGER.debug("%s: sending zwave_js MultilevelSwitch.%s %s", target.reported_id, method, args)
    return await endpoint.async_invoke_cc_api(multilevel_switch_cc(), method, *args)
