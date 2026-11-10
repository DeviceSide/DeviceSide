"""Zigbee2MQTT addressing: which device identifiers are addressable."""

from types import SimpleNamespace

import pytest

from custom_components.deviceside.integrations.zigbee2mqtt.addressing import z2m_address


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
