"""Matter's device classes: the rules on the node's attribute cache, the levels, and what each class runs."""

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.deviceside.core.models import Target
from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.matter import INTEGRATION
from custom_components.deviceside.integrations.matter.classes import (
    BRIDGED,
    MULTI_ENDPOINT,
    OTHER,
    UNCERTIFIED,
    WIZ_PLUG,
    capability,
    node_class,
)
from custom_components.deviceside.integrations.matter.get_attributes import MatterGetAttributes
from custom_components.deviceside.integrations.matter.turn_on_for import MatterTurnOnFor

from ...conftest import allow_labs, call, refusal
from ...fixtures.matter import WIZ_PRODUCT_ID, WIZ_VENDOR_ID, add_matter_entity, matter_device

WIZ = {"0/40/2": WIZ_VENDOR_ID, "0/40/4": WIZ_PRODUCT_ID}
# A bridge: endpoint 1 is the Aggregator (0x000E), endpoint 2 a bridged plug-in unit, as Home Assistant's fixtures
# record them (tests/components/matter/fixtures/nodes/mock_composed_bridge.json).
AGGREGATOR = {"1/29/0": [{"0": 14, "1": 1}], "2/29/0": [{"0": 19, "1": 1}, {"0": 266, "1": 1}]}


@pytest.mark.parametrize(
    ("attributes", "expected"),
    [
        (WIZ, WIZ_PLUG),
        ({"0/40/2": WIZ_VENDOR_ID, "0/40/4": 1}, OTHER),  # another Signify product: its own firmware
        ({"0/40/2": 4874, "0/40/4": 80}, OTHER),  # a certified plug from another vendor
        ({"0/40/2": 0xFFF1, "0/40/4": 0x8000}, UNCERTIFIED),
        ({"0/40/2": 0xFFF4}, UNCERTIFIED),
        ({"0/40/2": 0xFFF5}, OTHER),  # past the test range
        ({"0/40/2": 4757} | AGGREGATOR, BRIDGED),
        (WIZ | AGGREGATOR, BRIDGED),  # a bridge's software answers, whoever made it
        ({"0/40/2": 0xFFF1} | AGGREGATOR, UNCERTIFIED),  # a test VendorID marks it untested first
        ({"0/40/2": 4874, "1/29/0": [{"0": 266, "1": 1}]}, OTHER),  # a device type that isn't the Aggregator
        # Any sign of a bridge, or a DeviceTypeList that can't be read, fails closed to `bridged`.
        ({"0/40/2": 4874, "2/29/0": [{"0": 19, "1": 1}]}, BRIDGED),  # a Bridged Node, no Aggregator
        ({"0/40/2": 4874, "2/57/5": "a name"}, BRIDGED),  # Bridged Device Basic Information
        ({"0/40/2": 4874, "1/29/0": [266]}, BRIDGED),
        ({"0/40/2": 4874, "1/29/0": None}, BRIDGED),
        # Certification tests one On/Off endpoint, so a device with more is untested beyond it.
        ({"0/40/2": 4874, "1/6/65532": 1}, OTHER),
        ({"0/40/2": 4874, "1/6/65532": 1, "2/6/65532": 1}, MULTI_ENDPOINT),
        (WIZ | {"1/6/65532": 1, "2/6/65532": 1}, WIZ_PLUG),  # a measured product's own record covers it
        ({"0/40/2": 4757, "1/6/65532": 1, "2/6/65532": 1} | AGGREGATOR, BRIDGED),
        ({}, None),  # no VendorID yet: no class to name
        ({"0/40/2": "4874"}, None),
    ],
)
def test_node_class(attributes, expected):
    assert node_class(attributes) == expected


@pytest.mark.usefixtures("setup_production")
async def test_capability_is_none_without_a_vendor_id(hass):
    """A node that hasn't reported its VendorID has no class to name, not even `uncertified`, which needs one."""
    entry, _, _ = matter_device(hass, vendor_id=None, product_id=None)
    add_matter_entity(hass, entry, "switch.plug")
    target = _target(hass, "switch.plug")

    found = capability(hass, target)

    assert found is None


@pytest.mark.usefixtures("mock_chip", "setup_production")
async def test_a_node_with_no_vendor_id_is_class_unknown_until_it_reports(hass):
    """No class to name: refused as class_unknown even with Labs on, until it reports a VendorID."""
    entry, send_cmd, _ = matter_device(hass, vendor_id=None, product_id=None)
    add_matter_entity(hass, entry, "switch.plug")
    allow_labs(hass)

    assert await refusal(hass, "turn_on_for", {"entity_id": "switch.plug", "duration": 5}) == "class_unknown"
    send_cmd.assert_not_awaited()


@pytest.mark.usefixtures("setup_production")
async def test_capability_is_none_without_a_node(hass):
    entry, _, _ = matter_device(hass)
    add_matter_entity(hass, entry, "switch.plug", unique_id="not-a-matter-id")

    assert capability(hass, _target(hass, "switch.plug")) is None


@pytest.mark.usefixtures("setup_production")
async def test_capability_is_none_when_the_node_lookup_raises(hass):
    entry, _, _ = matter_device(hass)
    entry.runtime_data.adapter.matter_client.get_node.side_effect = KeyError("gone")
    add_matter_entity(hass, entry, "switch.plug")

    assert capability(hass, _target(hass, "switch.plug")) is None


def test_levels():
    """Both actions: the WiZ plug Verified by its records, `other` Documented by certification of the reads and, for the
    timer call, in Labs (plan Decision 75). Bridges, multi-endpoint and uncertified nodes not built on both
    (docs/evidence.md, In Labs)."""
    for adapter in (MatterTurnOnFor, MatterGetAttributes):
        held = adapter.scope.capabilities
        assert held.keys() == {WIZ_PLUG, OTHER}
        assert INTEGRATION.classes.keys() - held.keys() == {BRIDGED, UNCERTIFIED, MULTI_ENDPOINT}
        assert not adapter.scope.no_known_method
    # turn_on_for's failure harms, so its three unserved classes carry entries, which make core refuse a node with no
    # class yet; get_attributes never harms, so needs none.
    assert MatterTurnOnFor.scope.not_built.keys() == {BRIDGED, UNCERTIFIED, MULTI_ENDPOINT}
    assert not MatterGetAttributes.scope.not_built
    assert MatterTurnOnFor.scope.capabilities[WIZ_PLUG] is Level.VERIFIED
    assert MatterTurnOnFor.scope.capabilities[OTHER] is Level.LABS
    assert MatterTurnOnFor.scope.level("switch", [WIZ_PLUG]) is Level.VERIFIED
    assert MatterGetAttributes.scope.capabilities[WIZ_PLUG] is Level.VERIFIED
    assert MatterGetAttributes.scope.capabilities[OTHER] is Level.DOCUMENTED
    assert MatterGetAttributes.scope.level("switch", [WIZ_PLUG]) is Level.VERIFIED
    assert MatterGetAttributes.scope.level("light", [OTHER]) is Level.DOCUMENTED


@pytest.mark.usefixtures("mock_chip", "setup_production")
@pytest.mark.parametrize(
    ("node", "expected"),
    [({}, WIZ_PLUG), ({"vendor_id": 4874, "product_id": 80}, OTHER)],
    ids=["wiz_plug", "other"],
)
@pytest.mark.parametrize("entity_id", ["switch.plug", "light.bulb"])
async def test_certified_reads_with_labs_off(hass, node, expected, entity_id):
    entry, _, read_attr = matter_device(hass, **node)
    add_matter_entity(hass, entry, entity_id)

    response = await call(hass, "get_attributes", _data("get_attributes", entity_id))

    assert response[entity_id]["capability"] == expected
    assert read_attr.await_count == 2


UNCERTIFIED_NODE = {"vendor_id": 0xFFF1}
BRIDGE_NODE = {"vendor_id": 4757, "attributes": AGGREGATOR}


@pytest.mark.usefixtures("mock_chip", "setup_production")
@pytest.mark.parametrize(
    ("node", "action"),
    [
        (UNCERTIFIED_NODE, "get_attributes"),
        (BRIDGE_NODE, "get_attributes"),
        # A second On/Off endpoint beside the fixture's endpoint 1.
        ({"vendor_id": 4874, "product_id": 80, "attributes": {"2/6/65532": 1}}, "get_attributes"),
        (UNCERTIFIED_NODE, "turn_on_for"),
        (BRIDGE_NODE, "turn_on_for"),
        ({"vendor_id": 4874, "product_id": 80, "attributes": {"2/6/65532": 1}}, "turn_on_for"),
    ],
    ids=["uncertified-read", "bridged-read", "multi_endpoint-read", "uncertified", "bridged", "multi_endpoint"],
)
async def test_classes_with_no_pass_or_research_are_not_built(hass, node, action):
    """No pass or research predicts they take the call (docs/evidence.md, In Labs): refused even with Labs
    features on."""
    entry, send_cmd, read_attr = matter_device(hass, **node)
    add_matter_entity(hass, entry, "switch.plug")
    allow_labs(hass)

    assert await refusal(hass, action, _data(action, "switch.plug")) == "not_built"
    send_cmd.assert_not_awaited()
    read_attr.assert_not_awaited()


@pytest.mark.usefixtures("mock_chip", "setup_production")
async def test_the_timer_waits_for_labs_on_other(hass):
    """Certification sends OnWithTimedOff, with another OffWaitTime (plan Decision 75): in Labs."""
    entry, send_cmd, read_attr = matter_device(hass, vendor_id=4874, product_id=80)
    add_matter_entity(hass, entry, "switch.plug")
    data = _data("turn_on_for", "switch.plug")

    assert await refusal(hass, "turn_on_for", data) == "labs_off"
    send_cmd.assert_not_awaited()
    allow_labs(hass)
    response = await call(hass, "turn_on_for", data)

    assert response["switch.plug"]["capability"] == OTHER
    # It sends once and reads back its two paths.
    assert (send_cmd.await_count, read_attr.await_count) == (1, 2)


def _data(action, entity_id):
    return {"entity_id": entity_id} | ({"duration": 5} if action == "turn_on_for" else {})


def _target(hass, entity_id):
    entry = er.async_get(hass).async_get(entity_id)
    return Target(entity_id, "switch", "matter", entry, dr.async_get(hass).async_get(entry.device_id), None, None)
