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
        ({}, OTHER),
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

    assert isinstance(found, Unplaced) and found == OTHER


@pytest.mark.usefixtures("setup_production")
async def test_capability_is_none_without_a_node(hass):
    entry, _, _ = matter_device(hass)
    add_matter_entity(hass, entry, "switch.plug", unique_id="not-a-matter-id")

    assert capability(hass, _target(hass, "switch.plug")) is None


def test_levels():
    """WiZ plug: Verified on the read its record ran, Documented on the new timed call until its rerun; `other`
    Documented by certification; bridges and uncertified nodes untested."""
    for adapter in (MatterTurnOnFor, MatterGetAttributes):
        held = adapter.scope.capabilities
        assert held.keys() == INTEGRATION.classes
        assert held[OTHER] is Level.DOCUMENTED
        assert held[BRIDGED] is held[UNCERTIFIED] is Level.EXPERIMENTAL
        assert not adapter.scope.doesnt_work
    assert MatterTurnOnFor.scope.capabilities[WIZ_PLUG] is Level.DOCUMENTED
    assert MatterGetAttributes.scope.capabilities[WIZ_PLUG] is Level.VERIFIED


@pytest.mark.usefixtures("mock_chip", "setup_production")
@pytest.mark.parametrize(
    ("node", "expected"),
    [({}, WIZ_PLUG), ({"vendor_id": 4874, "product_id": 80}, OTHER)],
    ids=["wiz_plug", "other"],
)
async def test_certified_runs_with_experimental_off(hass, node, expected):
    entry, send_cmd, _ = matter_device(hass, **node)
    add_matter_entity(hass, entry, "switch.plug")

    response = await call(hass, "turn_on_for", {"entity_id": "switch.plug", "duration": 5})

    assert response["switch.plug"]["capability"] == expected
    send_cmd.assert_awaited_once()


@pytest.mark.usefixtures("mock_chip", "setup_production")
@pytest.mark.parametrize(
    "node",
    [{"vendor_id": 0xFFF1}, {"vendor_id": 4757, "attributes": AGGREGATOR}],
    ids=["uncertified", "bridged"],
)
@pytest.mark.parametrize("action", ["turn_on_for", "get_attributes"])
async def test_untested_classes_wait_for_experimental(hass, node, action):
    """No Matter class is harmed by a call, so an untested one runs once Experimental features is on."""
    entry, send_cmd, read_attr = matter_device(hass, **node)
    add_matter_entity(hass, entry, "switch.plug")
    data = {"entity_id": "switch.plug"} | ({"duration": 5} if action == "turn_on_for" else {})

    assert await refusal(hass, action, data) == "experimental_off"
    allow_experimental(hass)
    await call(hass, action, data)

    assert (send_cmd if action == "turn_on_for" else read_attr).await_count >= 1


def _target(hass, entity_id):
    entry = er.async_get(hass).async_get(entity_id)
    return Target(entity_id, "switch", "matter", entry, dr.async_get(hass).async_get(entry.device_id), None, None)
