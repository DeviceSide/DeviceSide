"""Shelly's wire boundary for the call transcripts (tests/transcripts.py).

`RpcDevice.call_rpc` (aioshelly) is the one place a call reaches the device: every Set, SetConfig, DimStop, GetStatus
and GetConfig DeviceSide sends goes through `rpc.send`, `rpc.get_status` or `rpc.get_config` into it, as the RPC method
(`<Component>.<Verb>`) and its params. Its reply is the device's result (or the error). Gen1 devices get no call: they
are refused before one is sent.

aioshelly isn't a dev dependency, so the boundary is the fake in tests/fixtures/shelly.py, a class whose `call_rpc`
method takes what DeviceSide passes aioshelly and awaits each test's mock; no test replaces it on an instance. The
instance, the first arg, is dropped. The calls above it (`rpc.send` and the readers) are not listed, as they would
record each call twice. It never calls itself, and is only ever called directly."""

BOUNDARIES = [
    ("tests.fixtures.shelly", "RpcDevice.call_rpc", 1),
]
