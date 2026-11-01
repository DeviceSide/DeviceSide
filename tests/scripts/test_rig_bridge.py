"""The rig's HueBridge against a local stub of the bridge's CLIP v2 API."""

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from tests.rig.bridge import BridgeError, HueBridge


async def serve(received: list, status: int = 200, reply: dict | None = None) -> TestServer:
    async def put(request: web.Request) -> web.Response:
        received.append((request.path, request.headers.get("hue-application-key"), await request.json()))
        return web.json_response(reply if reply is not None else {"data": [{"rid": "x"}], "errors": []}, status=status)

    app = web.Application()
    app.router.add_put("/clip/v2/resource/{kind}/{rid}", put)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    return server


def bridge_for(server: TestServer) -> HueBridge:
    bridge = HueBridge(f"{server.host}:{server.port}", "key")
    bridge.base = f"http://{server.host}:{server.port}/clip/v2/resource"
    return bridge


async def test_put_sends_the_body_to_the_resource_with_the_app_key(socket_enabled):
    received: list = []
    server = await serve(received)
    bridge = bridge_for(server)
    try:
        await bridge.put("light", "abc", {"on": {"on": True}})
    finally:
        await bridge.close()
        await server.close()
    assert received == [("/clip/v2/resource/light/abc", "key", {"on": {"on": True}})]


@pytest.mark.parametrize(
    ("status", "reply", "message"),
    [
        (200, {"errors": [{"description": "invalid body"}]}, "got 200: invalid body"),
        (403, {"errors": [{"description": "unauthorized user"}]}, "got 403: unauthorized user"),
        (500, {}, "got 500"),
    ],
)
async def test_put_raises_on_an_http_error_or_a_listed_error(socket_enabled, status, reply, message):
    server = await serve([], status, reply)
    bridge = bridge_for(server)
    try:
        with pytest.raises(BridgeError, match=message):
            await bridge.put("light", "abc", {})
    finally:
        await bridge.close()
        await server.close()


async def test_put_raises_when_the_bridge_cannot_be_reached(socket_enabled):
    server = await serve([])
    bridge = bridge_for(server)
    await server.close()
    try:
        with pytest.raises(BridgeError, match="PUT light/abc"):
            await bridge.put("light", "abc", {})
    finally:
        await bridge.close()


async def serve_any(received: list, reply: dict | None = None) -> TestServer:
    async def handle(request: web.Request) -> web.Response:
        body = await request.json() if request.can_read_body else None
        received.append((request.method, request.path, body))
        return web.json_response(reply if reply is not None else {"data": [{"id": "x"}], "errors": []})

    app = web.Application()
    app.router.add_route("*", "/clip/v2/resource/{tail:.*}", handle)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    return server


async def test_get_post_and_delete_use_the_resource_path_and_return_the_data(socket_enabled):
    received: list = []
    server = await serve_any(received)
    bridge = bridge_for(server)
    try:
        assert await bridge.get("device") == [{"id": "x"}]
        assert await bridge.get("device", "abc") == [{"id": "x"}]
        assert await bridge.post("zigbee_device_discovery", {"action": {"action_type": "search"}}) == [{"id": "x"}]
        await bridge.delete("device", "abc")
    finally:
        await bridge.close()
        await server.close()
    assert received == [
        ("GET", "/clip/v2/resource/device", None),
        ("GET", "/clip/v2/resource/device/abc", None),
        ("POST", "/clip/v2/resource/zigbee_device_discovery", {"action": {"action_type": "search"}}),
        ("DELETE", "/clip/v2/resource/device/abc", None),
    ]


async def test_delete_raises_on_a_listed_error(socket_enabled):
    server = await serve_any([], {"errors": [{"description": "not found"}]})
    bridge = bridge_for(server)
    try:
        with pytest.raises(BridgeError, match="DELETE device/abc got 200: not found"):
            await bridge.delete("device", "abc")
    finally:
        await bridge.close()
        await server.close()


@pytest.mark.parametrize(
    ("spelling", "found"),
    [
        ("0x001788010abcdef0", "dev-1"),
        ("00:17:88:01:0A:BC:DE:F0", "dev-1"),
        ("0x0000000000000000", None),
    ],
)
async def test_device_id_by_ieee_reads_zigbee_connectivity_in_any_spelling(socket_enabled, spelling, found):
    reply = {"data": [{"mac_address": "00:17:88:01:0a:bc:de:f0", "owner": {"rid": "dev-1", "rtype": "device"}}]}
    server = await serve_any([], reply)
    bridge = bridge_for(server)
    try:
        assert await bridge.device_id_by_ieee(spelling) == found
    finally:
        await bridge.close()
        await server.close()
