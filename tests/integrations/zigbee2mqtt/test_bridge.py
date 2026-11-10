"""Zigbee2MQTT bridge: publishing."""

from custom_components.deviceside.integrations.zigbee2mqtt import bridge


async def test_publish_goes_straight_to_mqtt_as_json(hass, monkeypatch):
    sent: list[tuple] = []

    async def async_publish(hass, topic, payload, *args, **kwargs):
        sent.append((topic, payload, args, kwargs))

    monkeypatch.setattr(bridge.mqtt, "async_publish", async_publish)

    await bridge.publish(hass, "zigbee2mqtt/0x01/set", {"state": "ON", "on_time": 6.0})

    assert sent == [("zigbee2mqtt/0x01/set", '{"state": "ON", "on_time": 6.0}', (), {})]
