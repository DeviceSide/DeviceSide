"""Zigbee2MQTT's wire boundaries for the call transcripts (tests/transcripts.py).

Every call reaches Zigbee2MQTT through HA's `mqtt` integration, by two functions DeviceSide looks up at call time
(`mqtt.async_publish`, `mqtt.async_subscribe`), so they are the last calls before the network:

- `async_publish`: a topic and its payload (the JSON text, as sent). Every set, read, `bridge/request/...` options
  request and timer is one. Its reply is None. `hass` is dropped.
- `async_subscribe`: a topic and, at index 2, the callback that gets its messages. The replies are not the call's
  return value but messages delivered to that callback, so the boundary records the subscription (`hass` and the
  callback dropped, no reply) and each message its callback gets as `mqtt.async_subscribe.callback` (the topic, the
  payload and `retain`), in the segment open when it arrives. A run's wire reads as the conversation it had: what it
  sent, what it listened on, what Z2M answered, so the reply handling (a bridge response, a state publish, a log line)
  is pinned along with the request.

Limits: a subscription made while no segment is open, such as the bridge cache's at set up, isn't wrapped (the
callback is wrapped at the subscribe call), so what it hears isn't in the wire; the run's result shows its effect.
A message delivered to a callback after its segment has closed, or from a context with no segment, isn't recorded.

mqtt isn't set up in the unit tests, so tests/fixtures/zigbee2mqtt.py's `Broker` and the conftest stand where the
client does: `async_publish` forwards to a registered `mqtt.publish` service (the broker, or a test's refusal) and
`async_subscribe` is `Broker.subscribe`, each set on the module with `monkeypatch.setattr`, never on an instance.
That service call is the fake's plumbing and not recorded (tests/transcripts.py). Neither function calls the other
or itself, and each is only called directly through `mqtt.`, never through a reference captured before the wrap
(`bridge.publish` and the like look it up at call time).

The options request's `transaction` is a `uuid4().hex` in production; the conftest numbers it per test, so the bytes
`bridge.py` builds stay in the segment.
"""

BOUNDARIES = [
    ("homeassistant.components.mqtt", "async_publish", 1),
    ("homeassistant.components.mqtt", "async_subscribe", 1, 2),
]
