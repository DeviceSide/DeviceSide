"""Matter's device classes (docs/evidence.md, Device classes): whose On/Off server answers a target's endpoint.

Nobody routes the call: DeviceSide sends OnWithTimedOff to the endpoint as it is, so its own On/Off server decides the
outcome (internals.md, What decides the call): the device's firmware, named by its VendorID and ProductID, or on a
bridge the bridge's software. The rules, first match winning:

1. `uncertified`: a test VendorID (0xFFF1 to 0xFFF4), which no certified product carries, or none reported yet.
2. `bridged`: any sign of a bridge (an Aggregator or Bridged Node endpoint, Bridged Device Basic Information, or a
   DeviceTypeList this can't read), as the bridge's software answers the call. Failing closed: a bridge read as
   native would run at `other`'s level; a hub's own native light gets the bridge's, the cautious side.
3. `wiz_plug`: VendorID 4107 and ProductID 8979, the one product a record covers (plan Decision 47).
4. `multi_endpoint`: more than one endpoint with the On/Off cluster (a multi-gang plug, say). Certification runs its
   On/Off test on one configured endpoint, and nothing found says every other one is tested too (internals.md).
5. `other`, the default: a real VendorID on a node with one On/Off endpoint and no sign of a bridge. A real VendorID
   is the proxy for certification, which tests the timer reads (docs/evidence.md, Levels): every certified product
   has one, and the known uncertified sources (development kits, apps that share devices on Matter) report a test one
   by default.

The rules read the node's attribute cache, as addressing.lt_feature does: sync, no I/O. A node holds every attribute
from its interview on, so one with no VendorID isn't fully reported: it is `uncertified`, Unplaced, the cautious class
until it reports. No Matter scope holds a `harms` entry, so Unplaced refuses nothing today. A target with
no node is None (addressing.unsupported_reason refuses it first, as not_addressable).
"""

from collections.abc import Mapping

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .addressing import node_for
from ...core.models import Target
from ...core.scope import Unplaced, documented, experimental, verified

UNCERTIFIED = "uncertified"
BRIDGED = "bridged"
WIZ_PLUG = "wiz_plug"
MULTI_ENDPOINT = "multi_endpoint"
OTHER = "other"  # the default class, never Verified (IntegrationInfo.default_class)
# Each class's domains (IntegrationInfo.classes): the WiZ Smart Plug is a switch; any other may be a light or a plug.
CLASSES = {
    name: frozenset({Platform.SWITCH}) if name == WIZ_PLUG else frozenset({Platform.LIGHT, Platform.SWITCH})
    for name in (UNCERTIFIED, BRIDGED, WIZ_PLUG, MULTI_ENDPOINT, OTHER)
}

# Basic Information (cluster 0x0028) on the root endpoint, and the Descriptor's DeviceTypeList (0x001D/0x0000).
_VENDOR_ID = "0/40/2"
_PRODUCT_ID = "0/40/4"
_DESCRIPTOR = "29"
_DEVICE_TYPE_LIST = "0"
_BRIDGED_INFO = "57"
_ON_OFF, _FEATURE_MAP = "6", "65532"  # Bridged Device Basic Information, on a bridged endpoint only
_BRIDGE_TYPES = {0x000E, 0x0013}  # Aggregator, Bridged Node
# Test VendorIDs (connectedhomeip src/lib/core/CHIPVendorIdentifiers.hpp, IsTestVendorId): no certified product has one.
_TEST_VENDOR_IDS = range(0xFFF1, 0xFFF4 + 1)
# Measured products, by (VendorID, ProductID): Signify's WiZ Smart Plug (zigbee2mqtt/research/2026-11-14-lab-probe.md).
_PRODUCTS = {(4107, 8979): WIZ_PLUG}


# The levels each adapter's scope holds (index.md, Device classes; plan Decisions 46 to 48 and 75): get_attributes's
# reads Documented on `other` by certification (docs/evidence.md, Levels), Verified on the WiZ plug by its record; the
# timer call untested on every class, as certification sends another OffWaitTime and the WiZ plug's record ran 0, until
# the plug's rerun on the call makes it Verified there.
TURN_ON_FOR = experimental(WIZ_PLUG, OTHER, MULTI_ENDPOINT, BRIDGED, UNCERTIFIED)
GET_ATTRIBUTES = verified(WIZ_PLUG) | documented(OTHER) | experimental(MULTI_ENDPOINT, BRIDGED, UNCERTIFIED)


def _bridge_type(item: object) -> bool:
    """Whether a DeviceTypeList entry names a bridge type; True for one this can't read, failing closed."""
    return not isinstance(item, dict) or item.get("0") in _BRIDGE_TYPES


def _is_bridge(attributes: Mapping[str, object]) -> bool:
    """Whether any endpoint shows a bridge: rule 2 above."""
    for path, value in attributes.items():
        cluster, attribute = path.split("/")[1:3]
        if cluster == _BRIDGED_INFO:
            return True
        if cluster == _DESCRIPTOR and attribute == _DEVICE_TYPE_LIST:
            if not isinstance(value, list) or any(_bridge_type(item) for item in value):
                return True
    return False


def node_class(attributes: Mapping[str, object]) -> str:
    """The class of a node from its attribute cache, by the rules above."""
    vendor = attributes.get(_VENDOR_ID)
    if not isinstance(vendor, int) or vendor in _TEST_VENDOR_IDS:
        return UNCERTIFIED
    if _is_bridge(attributes):
        return BRIDGED
    if (product := _PRODUCTS.get((vendor, attributes.get(_PRODUCT_ID)))) is not None:
        return product
    return MULTI_ENDPOINT if _on_off_endpoints(attributes) > 1 else OTHER


def _on_off_endpoints(attributes: Mapping[str, object]) -> int:
    """How many endpoints hold the On/Off cluster, by its FeatureMap, a global attribute every cluster reports."""
    return sum(1 for path in attributes if path.split("/")[1:] == [_ON_OFF, _FEATURE_MAP])


def capability(hass: HomeAssistant, target: Target) -> str | None:
    """Matter's IntegrationInfo.capability: the class of the target's node, Unplaced (as `uncertified`) while it
    reports no VendorID; None for a target with no node."""
    if (node := node_for(hass, target)) is None:
        return None
    attributes = node.node_data.attributes
    found = node_class(attributes)
    return found if isinstance(attributes.get(_VENDOR_ID), int) else Unplaced(found)
