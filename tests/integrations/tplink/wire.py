"""TP-Link's wire boundary for the call transcripts (tests/transcripts.py).

`Protocol.query` (python-kasa's device protocol, `device.protocol.query`) is the one place a call reaches the device:
every raw call DeviceSide sends goes through it as the request (IOT's dict of namespace, command and params, or SMART's
method and params), and its reply is the device's answer (or the error). A SMART strip or hub child's protocol wraps the
call in `control_child` itself, and an IOT outlet's request names its `context` and `child_ids`.

python-kasa isn't a dev dependency, so the boundary is the fake in tests/fixtures/tplink.py, a class whose `query`
method takes what DeviceSide passes python-kasa and awaits each test's mock; no test replaces it on an instance. The
instance, the first arg, is dropped. It is only ever called directly.
"""

BOUNDARIES = [
    ("tests.fixtures.tplink", "Protocol.query", 1),
]
