"""Fakes shared by the rig's tests: a fake HAClient (and its admin twin, with device_side's options flow), a
registry whose adapters all take options, and the step files that tests/scripts/test_rig.py reuses."""

import asyncio
import contextlib
import copy
import json
from collections.abc import AsyncIterator, Callable
from types import SimpleNamespace

from tests.rig.bridge import BridgeError, HueBridge, normalize_ieee
from tests.rig.client import HAClient, HAError, device_ieee
from tests.rig.profile import Profile, RigEntity

PENDING: list[asyncio.TimerHandle | asyncio.Task] = []


class FakeHA(HAClient):
    """Entity states HA would hold, plain on/off services, and device_side actions answered by `respond`.

    It inherits HAClient's network helpers (ZHA, Z2M, registries) and fakes the three things they sit on: `command`,
    `call_service` and the MQTT subscription. A bulb joins with `join`; a leave, a permit window and a Z2M group act
    as the real networks would. Nothing here is the network's timing: a join is instant.
    """

    def __init__(self, states: dict[str, dict], respond: Callable | None = None):
        self.states = {
            entity_id: {"entity_id": entity_id, "state": "off", "attributes": {}} | state
            for entity_id, state in states.items()
        }
        self.respond = respond
        self.calls: list[tuple[str, str, dict]] = []
        self.devices: list[dict] = [{"id": "d1", "model": "Mini", "model_id": "S3", "sw_version": "2.0"}]
        self.entity_devices: dict[str, str] = {}  # the entity registry: entity ID -> device ID
        self.zha_open = False
        self.zha_groups: dict[int, str] = {}
        self.z2m_open = False
        self.z2m_devices: list[str] = []
        self.z2m_groups: dict[str, list[str]] = {}
        self.z2m_ignores: set[str] = set()  # request topics Z2M never acts on

    def join(self, integration: str, ieee: str, entity_id: str | None = None) -> str:
        """A bulb joins `integration` ("zha" or "zigbee2mqtt"), with a registry entity if `entity_id` is given."""
        device_id = f"dev-{len(self.devices)}-{normalize_ieee(ieee)}"
        ident = ["zha", ieee] if integration == "zha" else ["mqtt", f"zigbee2mqtt_{ieee}"]
        self.devices.append({"id": device_id, "identifiers": [ident]})
        if integration == "zigbee2mqtt":
            self.z2m_devices.append(ieee)
        if entity_id is not None:
            self.entity_devices[entity_id] = device_id
            self.states.setdefault(entity_id, {"entity_id": entity_id, "state": "off", "attributes": {}})
        return device_id

    def _leave(self, integration: str, ieee: str) -> None:
        """The device goes from the network and the device registry; its entities stay as orphans, as HA leaves them."""
        wanted = normalize_ieee(ieee)
        gone = [
            d["id"] for d in self.devices if (found := device_ieee(d, integration)) and normalize_ieee(found) == wanted
        ]
        self.devices = [d for d in self.devices if d["id"] not in gone]
        for entity_id, device_id in self.entity_devices.items():
            if device_id in gone:
                self.entity_devices[entity_id] = None

    def _z2m_handle(self, topic: str, payload: dict) -> None:
        if topic in self.z2m_ignores:
            return
        if topic == "permit_join":
            self.z2m_open = payload["time"] > 0
        elif topic == "device/remove":
            self.z2m_devices = [i for i in self.z2m_devices if normalize_ieee(i) != normalize_ieee(payload["id"])]
            self._leave("zigbee2mqtt", payload["id"])
            for members in self.z2m_groups.values():
                members[:] = [i for i in members if normalize_ieee(i) != normalize_ieee(payload["id"])]
        elif topic == "group/add":
            self.z2m_groups.setdefault(payload["friendly_name"], [])
        elif topic == "group/remove":
            self.z2m_groups.pop(payload["id"], None)
        elif topic == "group/members/add":
            self.z2m_groups[payload["group"]].append(payload["device"])

    @contextlib.asynccontextmanager
    async def _mqtt_messages(self, topic: str) -> AsyncIterator[asyncio.Queue[str]]:
        retained = {
            "info": {"permit_join": self.z2m_open, "config": {"devices": {}}},
            "devices": [{"ieee_address": ieee} for ieee in self.z2m_devices],
            "groups": [
                {"friendly_name": name, "members": [{"ieee_address": i} for i in members]}
                for name, members in self.z2m_groups.items()
            ],
        }[topic.removeprefix("zigbee2mqtt/bridge/")]
        queue: asyncio.Queue[str] = asyncio.Queue()
        queue.put_nowait(json.dumps(retained))
        yield queue

    def set(self, entity_id: str, state: str, **attributes) -> None:
        # HA keeps an entity's name whatever its state; every other attribute is the new state's own.
        if name := self.states.get(entity_id, {}).get("attributes", {}).get("friendly_name"):
            attributes = {"friendly_name": name} | attributes
        self.states[entity_id] = {"entity_id": entity_id, "state": state, "attributes": attributes}

    def later(self, delay: float, entity_id: str, state: str) -> None:
        PENDING.append(asyncio.get_running_loop().call_later(delay, self.set, entity_id, state))

    async def call_service(self, domain: str, service: str, data: dict | None = None, return_response=False):
        self.calls.append((domain, service, dict(data or {})))
        if domain == "device_side":
            return self.respond(self, service, data)
        if domain == "zha":
            if service == "permit":
                self.zha_open = data["duration"] > 0
            else:
                self._leave("zha", data["ieee"])
            return None
        if domain == "mqtt":
            self._z2m_handle(data["topic"].removeprefix("zigbee2mqtt/bridge/request/"), json.loads(data["payload"]))
            return None
        entity_id = data["entity_id"]
        attributes = {key: value for key, value in data.items() if key != "entity_id"}
        state = "on" if service == "turn_on" else "off"
        members = self.states[entity_id]["attributes"].get("entity_id")
        for member in members or []:
            self.set(member, state, **attributes)
        self.set(entity_id, state, **attributes)
        if members:
            self.states[entity_id]["attributes"]["entity_id"] = members
        return None

    async def get_state(self, entity_id: str) -> dict | None:
        return copy.deepcopy(self.states.get(entity_id))

    async def wait_for(self, entity_id: str, predicate, timeout: float):
        async with asyncio.timeout(timeout):
            while not predicate(state := await self.get_state(entity_id)):
                await asyncio.sleep(0.005)
        return state

    async def command(self, payload: dict):
        kind, entity_id = payload["type"], payload.get("entity_id")
        if kind == "config/entity_registry/get":
            return {"entity_id": entity_id, "device_id": self.entity_devices.get(entity_id)}
        if kind == "config/entity_registry/update":
            new = payload["new_entity_id"]
            if new in self.entity_devices or new in self.states:
                raise HAError({"code": "invalid_info", "message": f"Entity with this ID is already registered: {new}"})
            self.entity_devices[new] = self.entity_devices.pop(entity_id)
            if entity_id in self.states:
                self.states[new] = {**self.states.pop(entity_id), "entity_id": new}
            return {"entity_entry": {"entity_id": new}}
        if kind == "config/entity_registry/remove":
            self.entity_devices.pop(entity_id)
            self.states.pop(entity_id, None)
            return None
        if kind == "zha/group/add":
            group_id = 0x1000 + len(self.zha_groups)
            self.zha_groups[group_id] = payload["group_name"]
            return {"group_id": group_id}
        if kind == "zha/group/remove":
            for group_id in payload["group_ids"]:
                self.zha_groups.pop(group_id)
            return None
        return {
            "get_config": {"version": "2026.10.1"},
            "config/entity_registry/list_for_display": {"entities": [{"ei": "switch.plug", "di": "d1"}]},
            "config/device_registry/list": copy.deepcopy(self.devices),
        }[kind]


class FakeBridge(HueBridge):
    """HueBridge over an in-memory CLIP v2: the real get, post, put, delete and IEEE lookup, with a faked transport.

    `resources` holds each type's items by id. A POST to `zigbee_device_discovery` runs `on_search`, which a test
    uses to make a bulb join. A DELETE of a device removes it, its connectivity and its lights.
    """

    def __init__(self, resources: dict[str, dict[str, dict]] | None = None, on_search: Callable | None = None):
        super().__init__("bridge.invalid", "key")
        self.resources = resources or {}
        self.on_search = on_search
        self.requests: list[tuple[str, str, str | None, dict | None]] = []
        self.fail: dict[tuple[str, str], str] = {}  # (method, resource type) -> an error the bridge returns

    async def _request(self, method: str, resource_type: str, resource_id: str | None, body: dict | None = None):
        self.requests.append((method, resource_type, resource_id, body))
        if (error := self.fail.get((method, resource_type))) is not None:
            raise BridgeError(f"{method} {resource_type} got 400: {error}")
        items = self.resources.setdefault(resource_type, {})
        if method == "POST":
            return self._post(resource_type, items, body)
        if resource_id is None:
            return copy.deepcopy(list(items.values()))
        if resource_id not in items:
            raise BridgeError(f"{method} {resource_type}/{resource_id} got 404: not found")
        if method == "PUT":
            items[resource_id].update(body)
        elif method == "DELETE":
            self._delete(resource_type, items, resource_id)
        else:
            return [copy.deepcopy(items[resource_id])]
        return [{"rid": resource_id, "rtype": resource_type}]

    def _post(self, resource_type: str, items: dict, body: dict) -> list[dict]:
        if resource_type == "zigbee_device_discovery" and self.on_search is not None:
            self.on_search(self)
        new_id = f"{resource_type}-{len(items)}"
        items[new_id] = {"id": new_id, **body}
        return [{"rid": new_id, "rtype": resource_type}]

    def _delete(self, resource_type: str, items: dict, resource_id: str) -> None:
        del items[resource_id]
        if resource_type == "device":
            for owned in self.resources.values():
                for key, item in list(owned.items()):
                    if item.get("owner", {}).get("rid") == resource_id:
                        del owned[key]


def profile(integration: str = "shelly", pause: tuple[str, ...] = (), **roles: str) -> Profile:
    entities = [RigEntity(entity_id, frozenset({role})) for role, entity_id in roles.items()]
    return Profile({integration: entities}, pause, name="house")


OPTION_REGISTRY = SimpleNamespace(
    adapter=lambda action, integration: SimpleNamespace(
        scope=SimpleNamespace(
            confirmable=False, capabilities=None, fields=frozenset(), options=frozenset({"opt", "other"})
        )
    )
)


class FakeAdmin(FakeHA):
    """FakeHA plus device_side's entry and its options flow, which saves what it is sent."""

    def __init__(self, states: dict[str, dict], respond: Callable | None = None, options: dict | None = None):
        super().__init__(states, respond)
        self.options = {"opt": True, "other": False} | (options or {})
        self.saved: list[dict] = []
        self.aborted = 0

    async def command(self, payload: dict):
        if payload["type"] == "config_entries/get":
            return [{"entry_id": "e1", "state": "loaded"}]
        return await super().command(payload)

    async def rest(self, method: str, path: str, json: dict | None = None):
        if path.endswith("/options/flow"):
            schema = [{"name": name, "default": value, "type": "boolean"} for name, value in self.options.items()]
            return {"type": "form", "flow_id": "f1", "data_schema": schema}
        if method == "delete":
            self.aborted += 1
            return {"message": "Flow aborted"}
        self.options = dict(json)
        self.saved.append(dict(json))
        return {"type": "create_entry"}


RESTORED_MIDWAY = """
action: raise_brightness
rig_seconds: 5
tests:
  - name: t
    roles: [light_ct]
    steps:
      - set: {state: off}
      - restore: null
      - set: {state: off}
"""
WAITING_MIDWAY = RESTORED_MIDWAY.replace("      - restore: null\n", "      - wait: 30\n")
