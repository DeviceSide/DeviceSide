"""The rig's network helpers: HAClient's ZHA, Z2M and registry calls, on the wire and against FakeHA and FakeBridge."""

import json

import pytest
from aiohttp import WSMsgType, web
from aiohttp.test_utils import TestServer

from tests.rig.client import HAClient, HAError, device_ieee
from tests.scripts.rig_fakes import FakeBridge, FakeHA

IEEE = "0x001788010abcdef0"
ZHA_IEEE = "00:17:88:01:0a:bc:de:f0"
OTHER = "0x001788010abcdef1"


# --- on the wire: the exact commands HA's WebSocket API receives -------------------------------------------------


@pytest.fixture
async def wire(socket_enabled):
    """An HAClient on a stub that records each command and answers success, with a group id for zha/group/add."""
    seen: list[dict] = []

    async def websocket(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json({"type": "auth_required"})
        await ws.receive_json()
        await ws.send_json({"type": "auth_ok"})
        async for message in ws:
            if message.type != WSMsgType.TEXT:
                break
            msg = message.json()
            seen.append(msg)
            result = {"group_id": 4096} if msg["type"] == "zha/group/add" else None
            if msg["type"] == "config/device_registry/list":
                result = [{"id": "z", "identifiers": [["zha", ZHA_IEEE]]}, {"id": "m", "identifiers": [["mqtt", "x"]]}]
            await ws.send_json({"id": msg["id"], "type": "result", "success": True, "result": result})
        return ws

    app = web.Application()
    app.router.add_get("/api/websocket", websocket)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    ha = HAClient(str(server.make_url("")), "token")
    await ha.connect()
    seen.clear()
    yield ha, seen
    await ha.close()
    await server.close()


async def test_zha_commands_reach_the_wire(wire):
    ha, seen = wire
    await ha.zha_permit(120)
    await ha.zha_close()
    await ha.zha_remove(ZHA_IEEE)
    assert [(m["service"], m["service_data"]) for m in seen] == [
        ("permit", {"duration": 120}),
        ("permit", {"duration": 0}),
        ("remove", {"ieee": ZHA_IEEE}),
    ]


async def test_zha_groups_reach_the_wire(wire):
    ha, seen = wire
    group_id = await ha.zha_group_add("ds-rig-a", ((ZHA_IEEE, 11),))
    await ha.zha_group_remove(group_id)
    assert seen[0] == {
        "id": seen[0]["id"],
        "type": "zha/group/add",
        "group_name": "ds-rig-a",
        "members": [{"ieee": ZHA_IEEE, "endpoint_id": 11}],
    }
    assert seen[1]["group_ids"] == [4096]


async def test_registry_commands_reach_the_wire(wire):
    ha, seen = wire
    await ha.rename_entity("light.a", "light.b")
    await ha.remove_entity("light.b")
    assert [(m["type"], m["entity_id"]) for m in seen] == [
        ("config/entity_registry/update", "light.a"),
        ("config/entity_registry/remove", "light.b"),
    ]
    assert seen[0]["new_entity_id"] == "light.b"
    assert (await ha.device_by_ieee("zha", IEEE.upper()))["id"] == "z"


# --- against the fakes -------------------------------------------------------------------------------------------


def test_device_ieee_reads_each_integrations_identifier():
    assert device_ieee({"identifiers": [["zha", ZHA_IEEE]]}, "zha") == ZHA_IEEE
    assert device_ieee({"identifiers": [["mqtt", f"zigbee2mqtt_{IEEE}"]]}, "zigbee2mqtt") == IEEE
    assert device_ieee({"identifiers": [["mqtt", "zigbee2mqtt_bridge"]]}, "zigbee2mqtt") is None
    assert device_ieee({"identifiers": [["hue", "abc"]]}, "zha") is None
    # HomeKit Bridge registers a three-part identifier; the lab's first roam check crashed on one.
    homekit = ["homekit", "entry", "serial"]
    assert device_ieee({"identifiers": [homekit]}, "zha") is None
    assert device_ieee({"identifiers": [homekit, ["zha", ZHA_IEEE]]}, "zha") == ZHA_IEEE


async def test_device_by_ieee_finds_the_device_on_its_own_integration_only():
    ha = FakeHA({})
    ha.join("zha", ZHA_IEEE)
    ha.join("zigbee2mqtt", OTHER)
    assert (await ha.device_by_ieee("zha", IEEE))["identifiers"] == [["zha", ZHA_IEEE]]
    assert (await ha.device_by_ieee("zigbee2mqtt", OTHER.upper()))["identifiers"][0][0] == "mqtt"
    assert await ha.device_by_ieee("zigbee2mqtt", IEEE) is None


async def test_zha_joining_always_closes_the_window():
    ha = FakeHA({})
    with pytest.raises(RuntimeError):
        async with ha.zha_joining(120):
            assert ha.zha_open
            raise RuntimeError("bulb never joined")
    assert not ha.zha_open
    assert [c[2] for c in ha.calls] == [{"duration": 120}, {"duration": 0}]


async def test_zha_remove_drops_the_device_and_orphans_its_entity():
    ha = FakeHA({})
    ha.join("zha", ZHA_IEEE, "light.bulb")
    await ha.zha_remove(ZHA_IEEE)
    assert await ha.device_by_ieee("zha", IEEE) is None
    assert (await ha.command({"type": "config/entity_registry/get", "entity_id": "light.bulb"}))["device_id"] is None


async def test_z2m_permit_join_opens_closes_and_reads_back():
    ha = FakeHA({})
    assert not await ha.z2m_permit_join_open()
    await ha.z2m_permit_join(120)
    assert await ha.z2m_permit_join_open()
    await ha.z2m_permit_join(0)
    assert not await ha.z2m_permit_join_open()
    topic = "zigbee2mqtt/bridge/request/permit_join"
    assert [(c[2]["topic"], json.loads(c[2]["payload"])) for c in ha.calls] == [
        (topic, {"time": 120}),
        (topic, {"time": 0}),
    ]


async def test_z2m_remove_device_waits_for_bridge_devices_to_drop_it():
    ha = FakeHA({})
    ha.join("zigbee2mqtt", IEEE, "light.bulb")
    assert await ha.z2m_has_device(IEEE.upper())
    await ha.z2m_remove_device(IEEE)
    assert not await ha.z2m_has_device(IEEE)
    assert await ha.device_by_ieee("zigbee2mqtt", IEEE) is None


async def test_z2m_request_that_never_takes_effect_times_out(monkeypatch):
    monkeypatch.setattr("tests.rig.client.Z2M_REQUEST_TIMEOUT_S", 0.05)
    monkeypatch.setattr("tests.rig.client.Z2M_POLL_S", 0.01)
    ha = FakeHA({})
    ha.join("zigbee2mqtt", IEEE)
    ha.z2m_ignores.add("device/remove")
    with pytest.raises(TimeoutError, match=f"did not remove {IEEE}"):
        await ha.z2m_remove_device(IEEE)


async def test_z2m_groups_add_members_and_remove():
    ha = FakeHA({})
    assert await ha.z2m_group_members("ds-rig-g") is None
    await ha.z2m_group_add("ds-rig-g", (IEEE, OTHER))
    assert await ha.z2m_group_members("ds-rig-g") == [IEEE, OTHER]
    await ha.z2m_group_remove("ds-rig-g")
    assert await ha.z2m_group_members("ds-rig-g") is None


async def test_rename_entity_moves_the_registry_entry_and_state():
    ha = FakeHA({})
    ha.join("zha", ZHA_IEEE, "light.new_name")
    await ha.rename_entity("light.new_name", "light.fixed")
    assert ha.entity_devices.keys() == {"light.fixed"}
    assert await ha.get_state("light.fixed") is not None
    assert await ha.get_state("light.new_name") is None


async def test_rename_entity_into_a_taken_id_raises_until_the_stale_entry_is_removed():
    ha = FakeHA({})
    ha.join("zha", ZHA_IEEE, "light.fixed")
    await ha.zha_remove(ZHA_IEEE)  # leaves light.fixed orphaned
    ha.join("zha", ZHA_IEEE, "light.fixed_2")
    with pytest.raises(HAError, match="already registered"):
        await ha.rename_entity("light.fixed_2", "light.fixed")
    await ha.remove_entity("light.fixed")
    await ha.rename_entity("light.fixed_2", "light.fixed")
    assert ha.entity_devices.keys() == {"light.fixed"}


async def test_zha_group_add_and_remove_track_ids():
    ha = FakeHA({})
    group_id = await ha.zha_group_add("ds-rig-g", ((ZHA_IEEE, 11),))
    assert ha.zha_group_names == {group_id: "ds-rig-g"}
    await ha.zha_group_remove(group_id)
    assert ha.zha_group_names == {}


async def test_fake_bridge_runs_the_real_verbs_over_memory():
    bridge = FakeBridge(
        {
            "device": {"d1": {"id": "d1"}},
            "zigbee_device_discovery": {"disc": {"id": "disc", "status": "ready"}},
            "light": {"l1": {"id": "l1", "owner": {"rid": "d1"}}},
            "zigbee_connectivity": {
                "c1": {"id": "c1", "mac_address": "00:17:88:01:0a:bc:de:f0", "owner": {"rid": "d1"}}
            },
        },
        on_search=lambda b: b.resources["device"].update({"d2": {"id": "d2"}}),
    )
    assert await bridge.device_id_by_ieee(IEEE) == "d1"
    await bridge.delete("device", "d1")
    assert await bridge.device_id_by_ieee(IEEE) is None
    assert bridge.resources["light"] == {}
    assert await bridge.post("zone", {"metadata": {"name": "z"}}) == [{"rid": "zone-0", "rtype": "zone"}]
    await bridge.put("zigbee_device_discovery", "disc", {"action": {"action_type": "search"}})
    assert [d["id"] for d in await bridge.get("device")] == ["d2"]
    await bridge.put("device", "d2", {"metadata": {"name": "x"}})
    assert (await bridge.get("device", "d2"))[0]["metadata"] == {"name": "x"}


async def test_z2m_group_add_refuses_a_name_already_taken():
    ha = FakeHA({})
    await ha.z2m_group_add("ds-rig-g", (IEEE,))
    with pytest.raises(ValueError, match="already has a group"):
        await ha.z2m_group_add("ds-rig-g")


async def test_device_by_ieee_refuses_hue():
    with pytest.raises(ValueError, match="found on the bridge"):
        await FakeHA({}).device_by_ieee("hue", IEEE)
