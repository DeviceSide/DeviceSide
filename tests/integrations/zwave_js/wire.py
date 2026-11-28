"""Z-Wave's wire boundary for the call transcripts (tests/transcripts.py).

zwave-js-server-python's `Endpoint.async_invoke_cc_api` is the one place a call reaches the node, through Z-Wave JS's
websocket: the command class, the CC API method (`get`, then the moves) and its arguments; its reply is the CC's
result (the `{currentValue, targetValue, duration}` of a Multilevel Switch `get`).

zwave_js_server isn't a dev dependency, so the boundary is the fake in tests/fixtures/zwave_js.py, a class whose method
takes what DeviceSide passes the endpoint and awaits each test's mock; no test replaces it on an instance. The instance,
the first arg, is dropped. The method calls neither itself nor another boundary, so nothing nests, and it is only ever
called directly through the class (`endpoint.async_invoke_cc_api(...)`), never through a reference captured before the
wrap."""

BOUNDARIES = [
    ("tests.fixtures.zwave_js", "ZwaveEndpoint.async_invoke_cc_api", 1),
]
