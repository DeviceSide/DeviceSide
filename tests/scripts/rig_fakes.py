"""Fakes shared by the rig's tests: a fake HAClient (and its admin twin, with device_side's options flow), a
registry whose adapters all take options, and the step files that tests/scripts/test_rig.py reuses."""

import asyncio
import contextlib
import copy
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from types import SimpleNamespace

from tests.rig.bridge import BridgeError, HueBridge, normalize_ieee
from tests.rig.client import HAClient, HAError, device_ieee
from tests.rig.profile import Profile, RigEntity, colon_ieee, hex_ieee
from tests.rig.roam import Z2M_GROUP_IDENTIFIER, ZHA_GROUP_UNIQUE_ID, Bulb

PENDING: list[asyncio.TimerHandle | asyncio.Task] = []


class FakeHA(HAClient):
    """Entity states HA would hold, plain on/off services, and device_side actions answered by `respond`.

    It inherits HAClient's network helpers (ZHA, Z2M, registries) and fakes the three things they sit on: `command`,
    `call_service` and the MQTT subscription. A bulb joins with `join`; a leave, a permit window and a ZHA or Z2M group
    act as the real networks would, a group with its HA light (dropped with it, unless `keeps_group_entities`).
    Nothing here is the network's timing: a join is instant.
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
        self.entity_meta: dict[str, dict] = {}  # the registry's platform, unique_id and disabled_by, by entity ID
        self.keeps_group_entities = False  # HA keeps a removed group's entity in its registry
        self.zha_open = False
        self.zha_group_names: dict[int, str] = {}
        self.zha_group_members: dict[int, list[dict]] = {}
        self.z2m_open = False
        self.z2m_devices: list[str] = []
        self.z2m_groups: dict[str, list[str]] = {}
        self.z2m_group_ids: dict[str, int] = {}
        self.z2m_ignores: set[str] = set()  # request topics Z2M never acts on
        self.z2m_options: dict[str, dict] = {}  # device options by IEEE, as bridge/info's config.devices
        self.z2m_level = "warning"  # Z2M's log level
        self.z2m_failing: dict[str, int] = {}  # IEEE -> interviews still to fail, its first (on joining) included
        self.z2m_interviews: list[str] = []  # each device/interview request's id
        self.on_open: Callable[[str], None] | None = None  # ZHA or Z2M joining opened (Lab joins its bulbs)
        self.on_leave: Callable[[str, str], None] | None = None  # (integration, IEEE) after a remove

    def join(self, integration: str, ieee: str, entity_id: str | None = None) -> str:
        """A bulb joins `integration` ("zha" or "zigbee2mqtt"), with a registry entity if `entity_id` is given."""
        device_id = f"dev-{len(self.devices)}-{normalize_ieee(ieee)}"
        ident = ["zha", ieee] if integration == "zha" else ["mqtt", f"zigbee2mqtt_{ieee}"]
        self.devices.append({"id": device_id, "identifiers": [ident]})
        if integration == "zigbee2mqtt":
            self.z2m_devices.append(ieee)
            self._z2m_interviewed(ieee)
        if entity_id is not None:
            unique_id = f"{ieee}-11" if integration == "zha" else f"{ieee}_light_zigbee2mqtt"
            self.register(entity_id, device_id, "zha" if integration == "zha" else "mqtt", unique_id)
        return device_id

    def register(
        self, entity_id: str, device_id: str | None, platform: str, unique_id: str, disabled_by: str | None = None
    ) -> None:
        """An entity in the registry, with a state."""
        self.entity_devices[entity_id] = device_id
        self.entity_meta[entity_id] = {"platform": platform, "unique_id": unique_id, "disabled_by": disabled_by}
        self.states.setdefault(entity_id, {"entity_id": entity_id, "state": "off", "attributes": {}})

    def unregister(self, unique_id: str) -> None:
        """HA drops the entity with this unique_id, unless it keeps removed groups' entities."""
        if self.keeps_group_entities:
            return
        for entity_id in [e for e, meta in self.entity_meta.items() if meta["unique_id"] == unique_id]:
            self.entity_devices.pop(entity_id, None)
            self.entity_meta.pop(entity_id)
            self.states.pop(entity_id, None)

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
            if self.z2m_open and self.on_open is not None:
                self.on_open("zigbee2mqtt")
        elif topic == "options":
            self.z2m_level = payload["options"]["advanced"]["log_level"]
        elif topic == "device/interview":
            self.z2m_interviews.append(payload["id"])
            self._z2m_interviewed(payload["id"])
        elif topic == "device/options":
            self.z2m_options.setdefault(payload["id"], {}).update(payload["options"])
        elif topic == "device/remove":
            self._z2m_remove(payload["id"])
        else:
            self._z2m_group_handle(topic, payload)

    def _z2m_group_handle(self, topic: str, payload: dict) -> None:
        if topic == "group/add":
            name = payload["friendly_name"]
            self.z2m_groups.setdefault(name, [])
            group_id = self.z2m_group_ids.setdefault(name, len(self.z2m_group_ids) + 1)
            device_id = f"z2m-group-{group_id}"
            self.devices.append({"id": device_id, "identifiers": [["mqtt", Z2M_GROUP_IDENTIFIER.format(group_id)]]})
            self.register(f"light.{name.replace('-', '_')}", device_id, "mqtt", f"{group_id}_light_zigbee2mqtt")
        elif topic == "group/remove":
            self.z2m_groups.pop(payload["id"], None)
            if (group_id := self.z2m_group_ids.pop(payload["id"], None)) is not None:
                self.devices = [d for d in self.devices if d["id"] != f"z2m-group-{group_id}"]
                self.unregister(f"{group_id}_light_zigbee2mqtt")
        elif topic == "group/members/add":
            self.z2m_groups[payload["group"]].append(payload["device"])

    def _z2m_interviewed(self, ieee: str) -> None:
        """One interview of `ieee`: it fails while z2m_failing still counts one for it."""
        key = normalize_ieee(ieee)
        if key in self.z2m_failing:
            self.z2m_failing[key] -= 1
            if self.z2m_failing[key] < 0:
                del self.z2m_failing[key]

    def _z2m_entry(self, ieee: str) -> dict:
        failed = normalize_ieee(ieee) in self.z2m_failing
        return {
            "ieee_address": ieee,
            "interview_completed": not failed,
            "interview_state": "FAILED" if failed else "SUCCESSFUL",
        }

    def _z2m_remove(self, ieee: str) -> None:
        self.z2m_devices = [i for i in self.z2m_devices if normalize_ieee(i) != normalize_ieee(ieee)]
        self.z2m_options.pop(ieee, None)  # as Z2M: a removed device's options go with it
        self._leave("zigbee2mqtt", ieee)
        for members in self.z2m_groups.values():
            members[:] = [i for i in members if normalize_ieee(i) != normalize_ieee(ieee)]
        if self.on_leave is not None:
            self.on_leave("zigbee2mqtt", ieee)

    @contextlib.asynccontextmanager
    async def _mqtt_messages(self, topic: str) -> AsyncIterator[asyncio.Queue[str]]:
        retained = {
            "info": {
                "permit_join": self.z2m_open,
                "log_level": self.z2m_level,
                "config": {"devices": self.z2m_options},
            },
            "devices": [self._z2m_entry(ieee) for ieee in self.z2m_devices],
            "groups": [
                {
                    "id": self.z2m_group_ids.get(name),
                    "friendly_name": name,
                    "members": [{"ieee_address": i} for i in members],
                }
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
                if self.zha_open and self.on_open is not None:
                    self.on_open("zha")
            else:
                self._leave("zha", data["ieee"])
                if self.on_leave is not None:
                    self.on_leave("zha", data["ieee"])
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
        if kind == "config/entity_registry/list":
            return [
                {"entity_id": e, "device_id": d, "platform": "fake", "unique_id": None} | self.entity_meta.get(e, {})
                for e, d in self.entity_devices.items()
            ]
        if kind == "config/entity_registry/update":
            return self._update_entity(entity_id, payload)
        if kind == "config/entity_registry/remove":
            self.entity_devices.pop(entity_id)
            self.entity_meta.pop(entity_id, None)
            self.states.pop(entity_id, None)
            return None
        if kind.startswith("zha/group"):
            return self._zha_group(kind, payload)
        return {
            "get_config": {"version": "2026.10.1"},
            "config/entity_registry/list_for_display": {"entities": [{"ei": "switch.plug", "di": "d1"}]},
            "config/device_registry/list": copy.deepcopy(self.devices),
        }[kind]

    def _update_entity(self, entity_id: str, payload: dict) -> dict:
        new = payload["new_entity_id"]
        if new != entity_id and (new in self.entity_devices or new in self.states):
            raise HAError({"code": "invalid_info", "message": f"Entity with this ID is already registered: {new}"})
        self.entity_devices[new] = self.entity_devices.pop(entity_id)
        if entity_id in self.entity_meta:
            self.entity_meta[new] = self.entity_meta.pop(entity_id)
            if "disabled_by" in payload:
                self.entity_meta[new]["disabled_by"] = payload["disabled_by"]
        if entity_id in self.states:
            self.states[new] = {**self.states.pop(entity_id), "entity_id": new}
        return {"entity_entry": {"entity_id": new}}

    def _zha_group(self, kind: str, payload: dict) -> dict | list | None:
        if kind == "zha/groups":
            return [
                {"group_id": group_id, "name": name, "members": self.zha_group_members[group_id]}
                for group_id, name in self.zha_group_names.items()
            ]
        if kind == "zha/group/add":
            group_id = 0x1000 + len(self.zha_group_names)
            self.zha_group_names[group_id] = payload["group_name"]
            self.zha_group_members[group_id] = payload["members"]
            entity_id = f"light.{payload['group_name'].replace('-', '_')}_zha_group_0x{group_id:04x}"
            self.register(entity_id, None, "zha", ZHA_GROUP_UNIQUE_ID.format(group_id))
            return {"group_id": group_id}
        for group_id in payload["group_ids"]:  # zha/group/remove
            self.zha_group_names.pop(group_id)
            self.zha_group_members.pop(group_id)
            self.unregister(ZHA_GROUP_UNIQUE_ID.format(group_id))
        return None


class FakeBridge(HueBridge):
    """HueBridge over an in-memory CLIP v2: the real get, post, put, delete and IEEE lookup, with a faked transport.

    `resources` holds each type's items by id. A search (a PUT of `action_type: search` to `zigbee_device_discovery`)
    runs `on_search`, which a test uses to make a bulb join. A DELETE runs `on_delete` (type, id) first; a device's
    removes its connectivity and lights too. A POST runs `on_post` (type, the new item) after; a new zone gets a
    grouped_light.
    """

    def __init__(self, resources: dict[str, dict[str, dict]] | None = None, on_search: Callable | None = None):
        super().__init__("bridge.invalid", "key")
        self.resources = resources or {}
        self.on_search = on_search
        self.on_delete: Callable[[str, str], None] | None = None
        self.on_post: Callable[[str, dict], None] | None = None
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
            searching = body.get("action", {}).get("action_type") == "search"
            if resource_type == "zigbee_device_discovery" and searching and self.on_search is not None:
                self.on_search(self)
        elif method == "DELETE":
            self._delete(resource_type, items, resource_id)
        else:
            return [copy.deepcopy(items[resource_id])]
        return [{"rid": resource_id, "rtype": resource_type}]

    def _post(self, resource_type: str, items: dict, body: dict) -> list[dict]:
        new_id = f"{resource_type}-{len(items)}"
        items[new_id] = {"id": new_id, **body}
        if resource_type == "zone":
            items[new_id]["services"] = [{"rid": f"grouped-{new_id}", "rtype": "grouped_light"}]
        if self.on_post is not None:
            self.on_post(resource_type, items[new_id])
        return [{"rid": new_id, "rtype": resource_type}]

    def _delete(self, resource_type: str, items: dict, resource_id: str) -> None:
        if self.on_delete is not None:
            self.on_delete(resource_type, resource_id)
        del items[resource_id]
        if resource_type == "device":
            for owned in self.resources.values():
                for key, item in list(owned.items()):
                    if item.get("owner", {}).get("rid") == resource_id:
                        del owned[key]


# The lab's two roaming bulbs, as a Roamer and as a profile file.
LAB_A, LAB_B = "0x001788010abcdef0", "0x001788010abcdef1"
LAB_OPTIONS = {"hue_native_control": True}
LAB_BULBS = [Bulb(LAB_A[2:], "light.lab_a", LAB_OPTIONS), Bulb(LAB_B[2:], "light.lab_b")]


def lab_profile(directory: Path, extra: str = "", networks: str = "hue, zha, zigbee2mqtt") -> Path:
    path = directory / "lab.yaml"
    path.write_text(
        "shelly:\n  - entity_id: switch.plug\n    roles: [switch_plug]\n"
        f"roam:\n  networks: [{networks}]\n  bulbs:\n"
        f'    - ieee: "{LAB_A}"\n      entity_id: light.lab_a\n      home: hue\n      roles: [light_ct, light_color]\n'
        "      z2m_options: {hue_native_control: true}\n"
        f'    - ieee: "00:17:88:01:0A:BC:DE:F1"\n      entity_id: light.lab_b\n      home: hue\n'
        "      roles: [light_dimmable]\n" + extra
    )
    return path


class Lab:
    """Bulbs that roam between a FakeHA's ZHA and Z2M and a FakeBridge, as the real networks do: a released bulb
    searches, and joins the next network that opens (unless it is `stuck`), under a new device and a generated entity
    ID. Leaving Hue drops the bulb from its rooms, zones and scene actions; each leave orphans its HA entity. A Hue
    search reads active for `search_s`; a `late` bulb sits out the first search it could join, and each of
    `strangers` is a device that isn't ours joining the next search. Each count in `deaf` is a Hue Leave the bulb
    misses: the bridge drops it, but it stays on Hue's network, joins nothing else, and the next search adopts it. A
    zone or scene made on the bridge gets its HA entity, which goes with it. The bulbs start on Hue under their fixed
    entity IDs, in room `r1`, zone `z1` and scene `s1`."""

    def __init__(self, ha: FakeHA, bridge: FakeBridge, bulbs: dict[str, str]):
        self.ha, self.bridge = ha, bridge
        self.searching: set[str] = set()
        self.stuck: set[str] = set()
        self.late: set[str] = set()
        self.deaf: dict[str, int] = {}  # Hue Leaves each bulb will miss, by IEEE
        self.kept_by_hue: set[str] = set()  # bulbs that missed one and are still on Hue's network
        self.strangers = 0
        self.search_s = 0.01
        self.zones_disabled_by: str | None = None  # HA adds a zone's light disabled
        self.joins = 0
        self.searches = 0
        ha.on_open = self.opened
        ha.on_leave = lambda _integration, ieee: self.searching.add(normalize_ieee(ieee))
        bridge.on_search = self.searched
        bridge.on_delete = self.deleted
        bridge.on_post = self.posted
        bridge.resources |= {
            "zigbee_device_discovery": {"disc": {"id": "disc", "status": "ready"}},
            "room": {"r1": {"id": "r1", "children": [{"rid": "other-device", "rtype": "device"}]}},
            "zone": {"z1": {"id": "z1", "children": [{"rid": "other-light", "rtype": "light"}]}},
            "scene": {"s1": {"id": "s1", "actions": [self.action("other-light", 10)]}},
        }
        for ieee, entity_id in bulbs.items():
            device_id, light_id = self.add("hue", normalize_ieee(ieee), entity_id)
            bridge.resources["device"][device_id]["metadata"]["name"] = f"Lamp {entity_id}"
            bridge.resources["room"]["r1"]["children"].append({"rid": device_id, "rtype": "device"})
            bridge.resources["zone"]["z1"]["children"].append({"rid": light_id, "rtype": "light"})
            bridge.resources["scene"]["s1"]["actions"].append(self.action(light_id, 50))

    @staticmethod
    def action(light_id: str, brightness: int) -> dict:
        return {"target": {"rid": light_id, "rtype": "light"}, "action": {"dimming": {"brightness": brightness}}}

    def searched(self, bridge: FakeBridge) -> None:
        self.searches += 1
        discovery = bridge.resources["zigbee_device_discovery"]["disc"]
        discovery["status"] = "active"
        asyncio.get_running_loop().call_later(self.search_s, discovery.update, {"status": "ready"})
        sitting_out = self.searching & self.late
        self.late -= sitting_out
        self.searching -= sitting_out
        for ieee in sorted(self.kept_by_hue):
            self.add("hue", ieee)
        self.kept_by_hue.clear()
        self.opened("hue")
        self.searching |= sitting_out
        for _ in range(self.strangers):
            stranger = f"stranger-{len(bridge.resources['device'])}"
            bridge.resources["device"][stranger] = {
                "id": stranger,
                "metadata": {"name": "Hue motion sensor"},
                "product_data": {"model_id": "SML001"},
                "services": [],
            }
        self.strangers = 0

    def opened(self, network: str) -> None:
        for ieee in sorted(self.searching - self.stuck):
            self.add(network, ieee)

    def add(self, network: str, ieee: str, entity_id: str | None = None) -> tuple[str, str]:
        self.searching.discard(ieee)
        self.joins += 1
        n = self.joins
        entity_id = entity_id or f"light.{network}_bulb_{n}"
        if network != "hue":
            spelled = colon_ieee(ieee) if network == "zha" else hex_ieee(ieee)
            return self.ha.join(network, spelled, entity_id), ""
        device_id, light_id, link = f"hue-device-{n}", f"hue-light-{n}", f"hue-link-{n}"
        resources = self.bridge.resources
        resources.setdefault("device", {})[device_id] = {
            "id": device_id,
            "metadata": {"name": "Hue color lamp", "archetype": "sultan_bulb"},
            "services": [{"rid": light_id, "rtype": "light"}, {"rid": link, "rtype": "zigbee_connectivity"}],
        }
        light = {"id": light_id, "owner": {"rid": device_id}, "color_temperature": {"mirek": 366}}
        resources.setdefault("light", {})[light_id] = light
        mac = colon_ieee(ieee)
        resources.setdefault("zigbee_connectivity", {})[link] = {
            "id": link,
            "mac_address": mac,
            "owner": {"rid": device_id},
        }
        self.ha.devices.append({"id": f"ha-{device_id}", "identifiers": [["hue", device_id]]})
        self.ha.register(entity_id, f"ha-{device_id}", "hue", light_id)
        return device_id, light_id

    def posted(self, resource_type: str, item: dict) -> None:
        """HA's hue integration adds a zone's grouped light, or a scene, under a name of its own."""
        name = item["metadata"]["name"].replace("-", "_")
        if resource_type == "zone":
            grouped = item["services"][0]["rid"]
            self.ha.register(f"light.{name}", None, "hue", grouped, disabled_by=self.zones_disabled_by)
        elif resource_type == "scene":
            self.ha.register(f"scene.{name}", None, "hue", item["id"])

    def deleted(self, resource_type: str, resource_id: str) -> None:
        """The bridge drops a device everywhere, and HA's hue integration drops its device; a zone or scene takes its
        HA entity with it."""
        if resource_type == "zone":
            self.ha.unregister(f"grouped-{resource_id}")
        elif resource_type == "scene":
            self.ha.unregister(resource_id)
        if resource_type == "device":
            self.drop_device(resource_id)

    def drop_device(self, device_id: str) -> None:
        resources = self.bridge.resources
        link = next(c for c in resources["zigbee_connectivity"].values() if c["owner"]["rid"] == device_id)
        ieee = normalize_ieee(link["mac_address"])
        if self.deaf.get(ieee):
            self.deaf[ieee] -= 1
            self.kept_by_hue.add(ieee)
        else:
            self.searching.add(ieee)
        lights = {s["rid"] for s in resources["device"][device_id]["services"] if s["rtype"] == "light"}
        for group in [*resources["room"].values(), *resources["zone"].values()]:
            group["children"] = [c for c in group["children"] if c["rid"] not in lights | {device_id}]
        for scene in resources["scene"].values():
            scene["actions"] = [a for a in scene["actions"] if a["target"]["rid"] not in lights]
        self.ha.devices = [d for d in self.ha.devices if d["id"] != f"ha-{device_id}"]
        for entity_id, owner in self.ha.entity_devices.items():
            if owner == f"ha-{device_id}":
                self.ha.entity_devices[entity_id] = None

    def device_of(self, entity_id: str) -> dict | None:
        """HA's device behind an entity, or None for an orphan."""
        owner = self.ha.entity_devices.get(entity_id)
        return next((d for d in self.ha.devices if d["id"] == owner), None)


def profile(integration: str = "shelly", pause: tuple[str, ...] = (), **roles: str) -> Profile:
    entities = [RigEntity(entity_id, frozenset({role})) for role, entity_id in roles.items()]
    return Profile({integration: entities}, {"all": pause} if pause else {}, name="house")


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
