"""Matter's device classes (docs/evidence.md, Device classes): whose On/Off server answers a target's endpoint.

Neither Home Assistant nor the Matter server picks the call: DeviceSide sends OnWithTimedOff to the endpoint as it is,
so the endpoint's own On/Off server decides the outcome (internals.md, What decides the call). That is the device's
firmware, named by its VendorID and ProductID, or, on a bridge, the bridge's software, which runs the timer or forwards
it. Certification tests the call on every certified device with the Lighting feature (TC-OO-2.3), which a test
VendorID marks as missing. So the classes, first match winning:

1. `uncertified`: the node reports a test VendorID (0xFFF1 to 0xFFF4), which certified products never carry.
2. `bridged`: the node is a bridge (an Aggregator endpoint), so the bridge's software answers the call.
3. `wiz_plug`: the WiZ Smart Plug, VendorID 4107 and ProductID 8979, the one product a record covers (plan Decision 47:
   firmware is per product, so a record covers its VID and PID alone).
4. `other`, the default: a certified device that is no bridge, from any other product.

The rules read the node's attribute cache, as addressing.lt_feature does: sync, no I/O. A node holds every attribute
from its interview on, so a missing VendorID means a node not fully reported, answered as its class Unplaced. No
Matter scope holds a harmful doesnt_work entry, so Unplaced changes no refusal today; it keeps the flag honest for when
one does. A target with no node is None (addressing.unsupported_reason refuses it first, as not_addressable).
"""

from collections.abc import Mapping

from homeassistant.core import HomeAssistant

from .addressing import node_for
from ...core.models import Target
from ...core.scope import Unplaced, documented, experimental, verified

UNCERTIFIED = "uncertified"
BRIDGED = "bridged"
WIZ_PLUG = "wiz_plug"
OTHER = "other"  # the default class, never Verified (IntegrationInfo.default_class)
CLASSES = frozenset({UNCERTIFIED, BRIDGED, WIZ_PLUG, OTHER})

# Basic Information (cluster 0x0028) on the root endpoint, and the Descriptor's DeviceTypeList (0x001D/0x0000).
_VENDOR_ID = "0/40/2"
_PRODUCT_ID = "0/40/4"
_DEVICE_TYPE_LIST = 29, 0
_AGGREGATOR = 0x000E  # the device type a bridge's aggregating endpoint carries
# Test VendorIDs (connectedhomeip src/lib/core/CHIPVendorIdentifiers.hpp, IsTestVendorId): no certified product has one.
_TEST_VENDOR_IDS = range(0xFFF1, 0xFFF4 + 1)
# Measured products, by (VendorID, ProductID): Signify's WiZ Smart Plug (zigbee2mqtt/research/2026-11-14-lab-probe.md).
_PRODUCTS = {(4107, 8979): WIZ_PLUG}


# The levels each adapter's scope holds (index.md, Device classes; plan Decisions 46 to 48). `other` is Documented as
# certification tests the call (docs/evidence.md, Levels): TC-OO-2.3 sends OnWithTimedOff with a non-zero OffWaitTime,
# as turn_on_for does, and checks the device turns off; and it reads OnTime and OnOff, as get_attributes does. A bridge
# or an uncertified node answers with software nothing has tested, so both are untested. The WiZ plug is Verified on
# the read its record ran; on turn_on_for its record ran OffWaitTime 0, so the new call is Documented on it, as on
# `other`, until its lab rerun (plan, step 9).
TURN_ON_FOR = documented(WIZ_PLUG, OTHER) | experimental(BRIDGED, UNCERTIFIED)
GET_ATTRIBUTES = verified(WIZ_PLUG) | documented(OTHER) | experimental(BRIDGED, UNCERTIFIED)


def _is_bridge(attributes: Mapping[str, object]) -> bool:
    """Whether any endpoint's DeviceTypeList holds the Aggregator: Matter's bridge, as the Matter server marks it."""
    cluster, attribute = _DEVICE_TYPE_LIST
    return any(
        isinstance(types, list) and any(isinstance(item, dict) and item.get("0") == _AGGREGATOR for item in types)
        for path, types in attributes.items()
        if path.split("/")[1:] == [str(cluster), str(attribute)]
    )


def node_class(attributes: Mapping[str, object]) -> str:
    """The class of a node from its attribute cache, by the rules above."""
    vendor = attributes.get(_VENDOR_ID)
    if isinstance(vendor, int) and vendor in _TEST_VENDOR_IDS:
        return UNCERTIFIED
    if _is_bridge(attributes):
        return BRIDGED
    return _PRODUCTS.get((vendor, attributes.get(_PRODUCT_ID)), OTHER)


def capability(hass: HomeAssistant, target: Target) -> str | None:
    """Matter's IntegrationInfo.capability: the class of the target's node, Unplaced while it reports no VendorID;
    None for a target with no node."""
    if (node := node_for(hass, target)) is None:
        return None
    attributes = node.node_data.attributes
    found = node_class(attributes)
    return found if isinstance(attributes.get(_VENDOR_ID), int) else Unplaced(found)
