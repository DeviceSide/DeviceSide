"""Hue's wire boundary for the call transcripts (tests/transcripts.py).

`HueBridgeV2.request` (aiohue) is the one place a call reaches the bridge: every light, grouped_light and scene write
(`bridge.set_state`, `bridge.write_light` and `bridge.put` in DeviceSide, aiohue's `set_state` and scene recall under
them) ends in it, as the CLIP v2 method, the resource path and the JSON body. Its args are the wire call, its reply the
bridge's. The bridge's own state is read from aiohue's models, which send nothing, so no read is recorded.

The calls above it (`bridge.put`, `bridge.set_state`) are not listed: they reach this one with the body built, and
recording both would write each call twice. The tests replace `HueBridgeV2.request` on the class (`fake_request`, and
a test's own), never on an instance, so the wrapper lands around whatever they installed. It never calls itself, and
is only ever called directly (aiohue's controllers and `bridge.put` call it, never pass it on). The api instance is
dropped."""

BOUNDARIES = [
    ("aiohue.v2", "HueBridgeV2.request", 1),
]
