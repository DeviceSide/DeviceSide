"""Matter's device classes: the rules on the node's attribute cache, the levels, and what each class runs."""

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.deviceside.core.models import Target
from custom_components.deviceside.core.scope import Level, Unplaced
from custom_components.deviceside.integrations.matter import INTEGRATION
from custom_components.deviceside.integrations.matter.classes import (
    BRIDGED,
    OTHER,
    UNCERTIFIED,
    WIZ_PLUG,
    capability,
    node_class,
)
from custom_components.deviceside.integrations.matter.get_attributes import MatterGetAttributes
from custom_components.deviceside.integrations.matter.turn_on_for import MatterTurnOnFor

from ...conftest import allow_experimental, call, refusal
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
        ({}, UNCERTIFIED),  # no VendorID yet: the cautious class
        ({"0/40/2": "4874"}, UNCERTIFIED),
    ],
)
def test_node_class(attributes, expected):
    assert node_class(attributes) == expected


@pytest.mark.usefixtures("setup_production")
async def test_capability_is_unplaced_without_a_vendor_id(hass):
    """A node that hasn't reported its VendorID can't yet be told from an uncertified one: Unplaced."""
    entry, _, _ = matter_device(hass, vendor_id=None, product_id=None)
    add_matter_entity(hass, entry, "switch.plug")
    target = _target(hass, "switch.plug")

    found = capability(hass, target)

    assert isinstance(found, Unplaced) and found == UNCERTIFIED


@pytest.mark.usefixtures("mock_chip", "setup_production")
async def test_an_unplaced_node_waits_for_experimental_and_isnt_reported(hass):
    """Unplaced as `uncertified`: untested, so refused while Experimental features is off; with them on it runs, and
    the response leaves out its provisional class."""
    entry, send_cmd, _ = matter_device(hass, vendor_id=None, product_id=None)
    add_matter_entity(hass, entry, "switch.plug")
    data = {"entity_id": "switch.plug", "duration": 5}

    assert await refusal(hass, "turn_on_for", data) == "experimental_off"
    allow_experimental(hass)
    response = await call(hass, "turn_on_for", data)

    assert "capability" not in response["switch.plug"]
    send_cmd.assert_awaited_once()


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
    """get_attributes: the WiZ plug Verified by its record, `other` Documented by certification of the reads. The timer
    call untested on every class until the plug's rerun on it (plan Decision 75). Bridges and uncertified nodes
    untested on both."""
    for adapter in (MatterTurnOnFor, MatterGetAttributes):
        held = adapter.scope.capabilities
        assert held.keys() == INTEGRATION.classes
        assert held[BRIDGED] is held[UNCERTIFIED] is Level.EXPERIMENTAL
        assert not adapter.scope.doesnt_work
    assert set(MatterTurnOnFor.scope.capabilities.values()) == {Level.EXPERIMENTAL}
    assert MatterGetAttributes.scope.capabilities[WIZ_PLUG] is Level.VERIFIED
    assert MatterGetAttributes.scope.capabilities[OTHER] is Level.DOCUMENTED
    assert MatterGetAttributes.scope.level("switch", [WIZ_PLUG]) is Level.VERIFIED
    assert MatterGetAttributes.scope.level("light", [OTHER]) is Level.DOCUMENTED
    assert MatterGetAttributes.scope.level("light", [BRIDGED]) is Level.EXPERIMENTAL


@pytest.mark.usefixtures("mock_chip", "setup_production")
@pytest.mark.parametrize(
    ("node", "expected"),
    [({}, WIZ_PLUG), ({"vendor_id": 4874, "product_id": 80}, OTHER)],
    ids=["wiz_plug", "other"],
)
@pytest.mark.parametrize("entity_id", ["switch.plug", "light.bulb"])
async def test_certified_reads_with_experimental_off(hass, node, expected, entity_id):
    entry, _, read_attr = matter_device(hass, **node)
    add_matter_entity(hass, entry, entity_id)

    response = await call(hass, "get_attributes", _data("get_attributes", entity_id))

    assert response[entity_id]["capability"] == expected
    assert read_attr.await_count == 2


UNCERTIFIED_NODE = {"vendor_id": 0xFFF1}
BRIDGE_NODE = {"vendor_id": 4757, "attributes": AGGREGATOR}


@pytest.mark.usefixtures("mock_chip", "setup_production")
@pytest.mark.parametrize(
    ("node", "expected", "action"),
    [
        (UNCERTIFIED_NODE, UNCERTIFIED, "get_attributes"),
        (BRIDGE_NODE, BRIDGED, "get_attributes"),
        # The timer call is untested on every class until the WiZ plug's rerun (plan Decision 75).
        (UNCERTIFIED_NODE, UNCERTIFIED, "turn_on_for"),
        (BRIDGE_NODE, BRIDGED, "turn_on_for"),
        ({}, WIZ_PLUG, "turn_on_for"),
        ({"vendor_id": 4874, "product_id": 80}, OTHER, "turn_on_for"),
    ],
    ids=["uncertified-read", "bridged-read", "uncertified", "bridged", "wiz_plug", "other"],
)
async def test_untested_classes_wait_for_experimental(hass, node, expected, action):
    """No Matter class is harmed by a call, so an untested one runs once Experimental features is on."""
    entry, send_cmd, read_attr = matter_device(hass, **node)
    add_matter_entity(hass, entry, "switch.plug")
    data = _data(action, "switch.plug")

    assert await refusal(hass, action, data) == "experimental_off"
    send_cmd.assert_not_awaited()
    read_attr.assert_not_awaited()
    allow_experimental(hass)
    response = await call(hass, action, data)

    assert response["switch.plug"]["capability"] == expected
    # turn_on_for sends once and reads back its two paths; get_attributes reads the two paths
    assert (send_cmd.await_count, read_attr.await_count) == ((1, 2) if action == "turn_on_for" else (0, 2))


def _data(action, entity_id):
    return {"entity_id": entity_id} | ({"duration": 5} if action == "turn_on_for" else {})


def _target(hass, entity_id):
    entry = er.async_get(hass).async_get(entity_id)
    return Target(entity_id, "switch", "matter", entry, dr.async_get(hass).async_get(entry.device_id), None, None)
