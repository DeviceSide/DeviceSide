"""Zigbee2MQTT addressing and detection: which device identifiers are addressable, and the edges no call reaches."""

from types import SimpleNamespace

import pytest

from custom_components.deviceside.integrations.zigbee2mqtt.addressing import is_z2m_group, topic, z2m_address
from custom_components.deviceside.integrations.zigbee2mqtt.detect import detect

from ...fixtures.zigbee2mqtt import IEEE


@pytest.mark.parametrize(
    ("identifier", "address"),
    [
        ("zigbee2mqtt_0x00124b0012345678", "0x00124b0012345678"),
        ("zigbee2mqtt_1234567_7", "1234567_7"),
        ("zigbee2mqtt_bridge_0x00124b0012345678", None),
        ("zigbee2mqtt_bridge", None),
    ],
)
def test_only_a_device_or_a_group_has_an_address(identifier, address):
    device = SimpleNamespace(identifiers={("mqtt", identifier)})

    assert z2m_address(device) == address  # type: ignore[arg-type]


def target(identifier: str | None) -> SimpleNamespace:
    """A target whose device carries this MQTT identifier, or one with no device."""
    return SimpleNamespace(device=None if identifier is None else SimpleNamespace(identifiers={("mqtt", identifier)}))


GROUP = "zigbee2mqtt_1221051039810110150109113116116_7"  # the literal Z2M writes, so this checks Z2M's scheme


@pytest.mark.parametrize(
    ("check", "expected"),
    [
        pytest.param(lambda: topic(target(None), "set"), None, id="topic_without_a_device"),
        pytest.param(lambda: topic(target("other_bridge_0x1234"), "set"), None, id="topic_of_a_non_z2m_identifier"),
        pytest.param(lambda: topic(target(GROUP), "set"), "zigbee2mqtt/7/set", id="topic_of_a_group_pinned"),
        pytest.param(lambda: is_z2m_group(None, target(GROUP)), True, id="group_on_the_default_base_topic"),
        pytest.param(lambda: is_z2m_group(None, target("zigbee2mqtt_12250109_7")), True, id="group_on_another"),
        pytest.param(lambda: is_z2m_group(None, target(f"zigbee2mqtt_{IEEE}")), False, id="a_device_is_no_group"),
        pytest.param(lambda: is_z2m_group(None, target(None)), False, id="no_device_is_no_group"),
        pytest.param(lambda: detect(None, None, None), False, id="detect_without_a_device"),
    ],
)
def test_the_edges_no_call_reaches(check, expected):
    assert check() == expected
