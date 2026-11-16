"""Matter addressing: what refuses a target before anything is sent, for every action, and the unique_id and
client lookups."""

import pytest

from custom_components.deviceside.integrations.matter.addressing import (
    matter_client,
    node_id_from_unique_id,
    onoff_endpoint,
)

from ...conftest import refusal
from ...fixtures.matter import add_matter_entity, matter_device

pytestmark = pytest.mark.usefixtures("mock_chip", "setup_production")

EP = 1


def _no_client(entry):
    del entry.runtime_data


def _node_lookup_raises(entry):
    entry.runtime_data.adapter.matter_client.get_node.side_effect = KeyError("node gone")


def _node_missing(entry):
    entry.runtime_data.adapter.matter_client.get_node.return_value = None


def _feature_map_unreported(entry):
    entry.runtime_data.adapter.matter_client.get_node.return_value.node_data.attributes = {}


@pytest.mark.parametrize(("action", "data"), [("get_attributes", {}), ("turn_on_for", {"duration": 5})])
@pytest.mark.parametrize(
    ("feature_map", "break_entry", "entity", "reason"),
    [
        pytest.param(0x0000, None, {"endpoint_id": EP}, "no_lt_feature", id="no_lt_feature"),
        # FeatureMap 0x2 is DeadFrontBehavior, not Lighting.
        pytest.param(0x0002, None, {"endpoint_id": EP}, "no_lt_feature", id="dead_front_bit_alone"),
        pytest.param(0x0001, _feature_map_unreported, {"endpoint_id": EP}, "no_lt_feature", id="featuremap_unreported"),
        pytest.param(0x0001, _no_client, {"endpoint_id": EP}, "not_addressable", id="no_client"),
        pytest.param(0x0001, _node_lookup_raises, {"endpoint_id": EP}, "not_addressable", id="node_lookup_raises"),
        pytest.param(0x0001, _node_missing, {"endpoint_id": EP}, "not_addressable", id="node_missing"),
        pytest.param(0x0001, None, {"unique_id": "bad-uid"}, "not_addressable", id="unparsable_unique_id"),
    ],
)
async def test_a_target_that_cant_take_the_timer_is_refused_before_anything_is_sent(
    hass, action, data, feature_map, break_entry, entity, reason
):
    entry, send_cmd, read_attr = matter_device(hass, endpoint_id=EP, feature_map=feature_map)
    if break_entry is not None:
        break_entry(entry)
    add_matter_entity(hass, entry, "switch.plug", **entity)

    assert await refusal(hass, action, {"entity_id": "switch.plug", **data}) == reason
    send_cmd.assert_not_awaited()
    read_attr.assert_not_awaited()


def test_non_numeric_unique_id_segment_is_unparsable():
    """Seven parts pass the length guard, but a non-numeric node or endpoint segment parses to None."""
    assert node_id_from_unique_id("00-zzzzzzzzzzzzzzzz-0-1-2-3-4") is None
    assert onoff_endpoint("00-0000000000000001-0-zz-6-6-0") is None


@pytest.mark.parametrize(
    ("unique_id", "endpoint"),
    [
        ("0000000000000001-0000000000000002-MatterNodeDevice-1-MatterPlug-6-0", 1),
        ("0000000000000001-0000000000000002-MatterNodeDevice-3-MatterLight-6-0", 3),
        # Another switch on the plug's endpoint: Eve's child lock, then the same cluster's other attribute.
        ("0000000000000001-0000000000000002-MatterNodeDevice-1-EveChildLock-319486977-319422481", None),
        ("0000000000000001-0000000000000002-MatterNodeDevice-1-MatterPlug-6-16385", None),
        ("0000000000000001-0000000000000002-MatterNodeDevice-1-MatterPlug-6-zz", None),
        ("bad-uid", None),
    ],
)
def test_only_an_onoff_unique_id_has_an_endpoint(unique_id, endpoint):
    assert onoff_endpoint(unique_id) == endpoint


def test_matter_client_without_entry_id_or_loaded_entry_is_none(hass):
    assert matter_client(hass) is None


def test_matter_client_without_entry_id_uses_first_loaded_entry(hass):
    entry, _, _ = matter_device(hass, endpoint_id=EP)

    assert matter_client(hass) is entry.runtime_data.adapter.matter_client
