"""Z-Wave's device classes (docs/evidence.md, Device classes): whose Multilevel Switch firmware answers the call.

Z-Wave JS gives every vendor's dimmer the same Multilevel Switch CC API, so one package serves all, with no families
(docs/integrations/zwave_js/internals.md). A class is the node's identity or the CC version the endpoint reports, the
first rule that matches:

1. `lzw42`: Inovelli's LZW42 bulb, manufacturer 0x031e, product type 0x0005, product ID 0x0001 (Z-Wave JS's config
   database, `packages/config/config/devices/0x031e/lzw42.json` at
   zwave-js/zwave-js@473703662970725e75fcf8d6f2d226c48dc4f3ba). Its Start Level Change V3 jumps to the end level,
   and V2 works (docs/research/2026-11-27-zwave-call-patterns.md, section 9), so a move that would start one runs
   as a Set.
2. `v1`: the endpoint's Multilevel Switch CC is version 1, which has no duration: Set and Start Level Change take
   none, so no move can be timed.
3. `other`, the default: any other Multilevel Switch endpoint (V2 and later), including every vendor's not named here.

A class is read from the node and endpoint in the client's cache, sync and with no I/O, as Matter's is. A target with no
node or endpoint has none (None; addressing.unsupported_reason refuses it first, as not_addressable).
"""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .addressing import endpoint_for, multilevel_switch_version, node_for
from ...core.models import Target
from ...core.scope import OTHER, documented

LZW42 = "lzw42"
V1 = "v1"
# Every class is a light: the package serves dimmers and bulbs, and no switch or plug entity addresses a level.
CLASSES = {name: frozenset({Platform.LIGHT}) for name in (LZW42, V1, OTHER)}

_INOVELLI = 0x031E
_LZW42 = (_INOVELLI, 0x0005, 0x0001)  # (manufacturer ID, product type, product ID)

# get_attributes is Documented where the call is the one HA's own `refresh_value` and polling send through Z-Wave JS to
# every brand, Multilevel Switch Get (docs/evidence.md, Levels: a read an integration passes through to every device).
# The read is the same on every version of the CC, so it is the same call on `other` and `lzw42`. `v1` is left out:
# a query serves only what another of the integration's actions serves (core/registry.check_queries), and no move is
# built for a V1 dimmer, which can't carry a duration. (check_queries compares nothing until a move adapter exists.)
GET_ATTRIBUTES = documented(OTHER, LZW42)


def node_class(node, endpoint) -> str:
    """The class of a node's endpoint, by the rules above."""
    if (node.manufacturer_id, node.product_type, node.product_id) == _LZW42:
        return LZW42
    return V1 if multilevel_switch_version(endpoint) == 1 else OTHER


def capability(hass: HomeAssistant, target: Target) -> str | None:
    """Z-Wave's IntegrationInfo.capability: the class of the target's endpoint; None for a target with no node or
    endpoint."""
    if (endpoint := endpoint_for(hass, target)) is None:
        return None
    return node_class(node_for(hass, target), endpoint)
