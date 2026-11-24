"""Matter addressing: what refuses a target before anything is sent, for every action, and the unique_id and
client lookups."""

import sys
from types import SimpleNamespace

import pytest

from custom_components.deviceside.integrations.matter.addressing import (
    color_feature_map_path,
    color_features,
    color_path,
    has_level,
    level_path,
    make_command,
    matter_client,
    node_id_from_unique_id,
    on_level_path,
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


def test_attribute_paths_are_endpoint_cluster_attribute():
    assert level_path(1) == "1/8/0"
    assert level_path(2, 0x0011) == "2/8/17"
    assert on_level_path(1) == "1/8/17"
    assert color_path(1, 0x0000) == "1/768/0"
    assert color_path(1, 0x0001) == "1/768/1"
    assert color_path(1, 0x0003) == "1/768/3"
    assert color_path(1, 0x0004) == "1/768/4"
    assert color_path(3, 0x0007) == "3/768/7"
    assert color_feature_map_path(1) == "1/768/65532"


def _node(attributes):
    return SimpleNamespace(node_data=SimpleNamespace(attributes=attributes))


def test_has_level_is_the_endpoints_current_level_in_the_cache():
    node = _node({"1/8/0": 128, "2/6/0": True})

    assert has_level(node, 1) is True
    assert has_level(node, 2) is False
    assert has_level(_node({}), 1) is False


def test_color_features_reads_the_feature_map_or_is_zero():
    node = _node({"1/768/65532": 0x1F, "2/768/65532": "bad"})

    assert color_features(node, 1) == 0x1F
    assert color_features(node, 2) == 0
    assert color_features(node, 3) == 0


@pytest.mark.parametrize(
    ("cluster", "command", "fields"),
    [
        ("LevelControl", "MoveToLevel", {"level": 10, "transitionTime": 5, "optionsMask": 1, "optionsOverride": 1}),
        ("LevelControl", "Stop", {"optionsMask": 1, "optionsOverride": 1}),
        (
            "ColorControl",
            "MoveToHueAndSaturation",
            {"hue": 1, "saturation": 2, "transitionTime": 3, "optionsMask": 1, "optionsOverride": 1},
        ),
        ("ColorControl", "MoveToColorTemperature", {"colorTemperatureMireds": 300, "transitionTime": 0}),
        ("ColorControl", "EnhancedMoveHue", {"moveMode": 1, "rate": 20, "optionsMask": 1, "optionsOverride": 1}),
    ],
)
def test_make_command_builds_the_chip_command_with_the_exact_fields(monkeypatch, cluster, command, fields):
    def factory(**kwargs):
        return SimpleNamespace(**kwargs)

    commands = SimpleNamespace(**{command: factory})
    objects = SimpleNamespace(**{cluster: SimpleNamespace(Commands=commands)})
    chip_clusters = SimpleNamespace(Objects=objects)
    monkeypatch.setitem(sys.modules, "chip", SimpleNamespace(clusters=chip_clusters))
    monkeypatch.setitem(sys.modules, "chip.clusters", chip_clusters)

    assert vars(make_command(cluster, command, **fields)) == fields
