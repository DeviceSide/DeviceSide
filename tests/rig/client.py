"""A small Home Assistant client for rig tests: WebSocket for service calls and state events, REST for reads."""

import asyncio
import contextlib
import itertools
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import aiohttp

from .bridge import normalize_ieee

Z2M = "zigbee2mqtt"
IEEE_INTEGRATIONS = ("zha", Z2M)
Z2M_TOPIC = "zigbee2mqtt/bridge"
Z2M_COORDINATOR = "Coordinator"  # the coordinator's friendly name, which permit_join's `device` takes
RETAINED_TIMEOUT_S = 5
Z2M_REQUEST_TIMEOUT_S = 30
Z2M_POLL_S = 0.5


def device_ieee(device: dict, integration: str) -> str | None:
    """The IEEE address of a device-registry entry on `integration` ("zha" or "zigbee2mqtt"), or None.

    ZHA identifies a device by its IEEE with colons; Z2M by `zigbee2mqtt_0x...` under the mqtt domain. A Hue device
    carries none, so the bridge finds it (`HueBridge.device_id_by_ieee`). An identifier need not be a pair: HomeKit
    Bridge registers (domain, entry ID, serial).
    """
    for domain, ident, *_ in device.get("identifiers", []):
        if integration == "zha" and domain == "zha":
            return ident
        if integration == Z2M and domain == "mqtt" and ident.startswith("zigbee2mqtt_0x"):
            return ident.removeprefix("zigbee2mqtt_")
    return None


class HAError(Exception):
    """A failed WebSocket command, carrying HA's error code and translation key."""

    def __init__(self, error: dict):
        super().__init__(error.get("message", ""))
        self.code: str | None = error.get("code")
        self.translation_key: str | None = error.get("translation_key")
        self.translation_placeholders: dict = error.get("translation_placeholders") or {}


class HAClient:
    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._mqtt: dict[int, asyncio.Queue[str]] = {}  # MQTT subscriptions by WebSocket id
        self._states: dict[str, dict] = {}
        self._changed = asyncio.Condition()
        self._reader: asyncio.Task | None = None
        self._state_events: int | None = None  # the state_changed subscription's WebSocket id

    async def connect(self) -> None:
        # The system resolver, not aiohttp's default aiodns: only the system one resolves mDNS (.local) names.
        connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
        self._session = aiohttp.ClientSession(connector=connector, headers={"Authorization": f"Bearer {self.token}"})
        try:
            self._ws = await self._session.ws_connect(f"{self.url}/api/websocket")
        except aiohttp.ClientError:
            await self._session.close()
            raise
        if (await self._ws.receive_json())["type"] != "auth_required":
            raise RuntimeError("unexpected WebSocket greeting")
        await self._ws.send_json({"type": "auth", "access_token": self.token})
        if (reply := await self._ws.receive_json())["type"] != "auth_ok":
            raise RuntimeError(f"WebSocket auth failed: {reply.get('message')}")
        self._reader = asyncio.create_task(self._read())
        self._state_events = next(self._ids)
        await self.command({"type": "subscribe_events", "event_type": "state_changed"}, self._state_events)

    async def close(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
        if self._ws is not None:
            await self._ws.close()
        if self._session is not None:
            await self._session.close()

    async def _read(self) -> None:
        async for message in self._ws:
            data = message.json()
            if data["type"] == "result":
                if (future := self._pending.pop(data["id"], None)) is not None and not future.done():
                    future.set_result(data)
            elif data["type"] != "event":
                continue
            elif (queue := self._mqtt.get(data["id"])) is not None:
                queue.put_nowait(data["event"]["payload"])
            # Anything else is an MQTT message for a subscription already closed, which HA can still send.
            elif data["id"] == self._state_events:
                event = data["event"]["data"]
                async with self._changed:
                    self._states[event["entity_id"]] = event["new_state"]
                    self._changed.notify_all()

    async def command(self, payload: dict, msg_id: int | None = None) -> Any:
        msg_id = next(self._ids) if msg_id is None else msg_id
        future = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = future
        await self._ws.send_json({"id": msg_id, **payload})
        reply = await asyncio.wait_for(future, timeout=30)
        if not reply["success"]:
            raise HAError(reply["error"])
        return reply["result"]

    async def call_service(
        self, domain: str, service: str, data: dict | None = None, return_response: bool = False
    ) -> dict | None:
        """Call a service; entity_id goes in data. Returns the service response when asked for one."""
        data = dict(data or {})
        payload = {"type": "call_service", "domain": domain, "service": service, "service_data": data}
        if return_response:
            payload["return_response"] = True
        result = await self.command(payload)
        return result.get("response") if return_response else None

    async def rest(self, method: str, path: str, json: dict | None = None) -> Any:
        """A REST call, for what the WebSocket API lacks (an options flow)."""
        async with self._session.request(method, f"{self.url}{path}", json=json) as response:
            response.raise_for_status()
            return await response.json()

    async def error_log(self) -> str:
        """HA's current session log as text (`/api/error_log`, admin only)."""
        async with self._session.get(f"{self.url}/api/error_log") as response:
            response.raise_for_status()
            return await response.text()

    async def log_levels(self) -> dict[str, int]:
        """The effective log level (a `logging` number) of each integration HA reports, by domain."""
        return {entry["domain"]: entry["level"] for entry in await self.command({"type": "logger/log_info"})}

    async def set_log_level(self, domain: str, level: str) -> None:
        """An integration's log level (a name such as DEBUG) until HA restarts: nothing is saved."""
        await self.command(
            {"type": "logger/integration_log_level", "integration": domain, "level": level, "persistence": "none"}
        )

    async def get_state(self, entity_id: str) -> dict | None:
        async with self._session.get(f"{self.url}/api/states/{entity_id}") as response:
            if response.status == 404:
                return None
            response.raise_for_status()
            state = await response.json()
        async with self._changed:
            # An event that landed while the request was in flight is newer; keep it.
            cached = self._states.get(entity_id)
            if cached is not None and cached["last_updated"] > state["last_updated"]:
                return cached
            self._states[entity_id] = state
        return state

    async def wait_for(self, entity_id: str, predicate: Callable[[dict | None], bool], timeout: float) -> dict | None:
        """The entity's state once predicate holds; raises TimeoutError otherwise. Checks the current state first."""
        current = await self.get_state(entity_id)
        if predicate(current):
            return current
        async with asyncio.timeout(timeout), self._changed:
            await self._changed.wait_for(lambda: predicate(self._states.get(entity_id)))
            return self._states.get(entity_id)

    @contextlib.asynccontextmanager
    async def _mqtt_messages(self, topic: str) -> AsyncIterator[asyncio.Queue[str]]:
        """Payloads on an MQTT topic while the block runs, a retained one first. Needs an admin token."""
        msg_id = next(self._ids)
        self._mqtt[msg_id] = asyncio.Queue()
        try:
            await self.command({"type": "mqtt/subscribe", "topic": topic}, msg_id)
            yield self._mqtt[msg_id]
        finally:
            with contextlib.suppress(HAError):
                await self.command({"type": "unsubscribe_events", "subscription": msg_id})
            del self._mqtt[msg_id]

    async def z2m_device_options(self, ieee: str) -> dict:
        """A Zigbee2MQTT device's options, from Z2M's retained bridge/info."""
        info = await self._z2m_retained("info")
        return info["config"]["devices"].get(ieee, {})

    async def set_z2m_device_options(self, ieee: str, options: dict) -> None:
        """Set Zigbee2MQTT device options, then wait until Z2M's bridge/info shows them; raises TimeoutError if not.

        It reads bridge/info rather than waiting for Z2M's reply: HA answers mqtt/subscribe before the broker has the
        subscription, so a reply can arrive first and be missed, while a fresh subscription always gets the retained
        bridge/info.
        """
        payload = {"id": ieee, "options": options}
        await self.call_service(
            "mqtt", "publish", {"topic": "zigbee2mqtt/bridge/request/device/options", "payload": json.dumps(payload)}
        )
        deadline = asyncio.get_running_loop().time() + 10
        while True:
            current = await self.z2m_device_options(ieee)
            if all(current.get(name) == value for name, value in options.items()):
                return
            if asyncio.get_running_loop().time() > deadline:
                raise TimeoutError(f"Zigbee2MQTT still shows {current} for {ieee}, not {options}")
            await asyncio.sleep(0.5)

    async def _z2m_retained(self, topic: str) -> Any:
        """Zigbee2MQTT's retained `bridge/<topic>` message, decoded."""
        async with self._mqtt_messages(f"{Z2M_TOPIC}/{topic}") as messages:
            try:
                return json.loads(await asyncio.wait_for(messages.get(), timeout=RETAINED_TIMEOUT_S))
            except TimeoutError:
                raise TimeoutError(f"no retained {Z2M_TOPIC}/{topic} within {RETAINED_TIMEOUT_S} s") from None

    async def _z2m_request(self, topic: str, payload: dict, done: Callable[[], Awaitable[bool]], what: str) -> None:
        """Publish a `bridge/request/<topic>`, then poll until `done()` (a coroutine function) says it took effect.

        Like set_z2m_device_options, it reads retained topics rather than waiting for Z2M's reply, which can arrive
        before HA's subscription is live.
        """
        await self.call_service(
            "mqtt", "publish", {"topic": f"{Z2M_TOPIC}/request/{topic}", "payload": json.dumps(payload)}
        )
        deadline = asyncio.get_running_loop().time() + Z2M_REQUEST_TIMEOUT_S
        while not await done():
            if asyncio.get_running_loop().time() > deadline:
                raise TimeoutError(f"Zigbee2MQTT did not {what} within {Z2M_REQUEST_TIMEOUT_S} s")
            await asyncio.sleep(Z2M_POLL_S)

    # --- Zigbee2MQTT: joining, removing, groups -------------------------------------------------------------------

    async def z2m_permit_join_open(self) -> bool:
        """Whether Zigbee2MQTT is accepting new devices, from its retained bridge/info."""
        return bool((await self._z2m_retained("info")).get("permit_join"))

    async def z2m_permit_join(self, seconds: int) -> None:
        """Open joining for `seconds` (0 closes it), and wait until bridge/info shows the change.

        It opens on the coordinator only, so a bulb can't join through a router with a full child table. bridge/info's
        `permit_join` is true for any open window, whichever device opened it.
        """

        async def done() -> bool:
            return await self.z2m_permit_join_open() == (seconds > 0)

        payload = {"time": seconds, "device": Z2M_COORDINATOR} if seconds else {"time": 0}
        await self._z2m_request("permit_join", payload, done, f"{'open' if seconds else 'close'} joining")

    async def z2m_log_level(self) -> str | None:
        """Zigbee2MQTT's log level, from its retained bridge/info."""
        return (await self._z2m_retained("info")).get("log_level")

    async def z2m_info(self) -> dict:
        """Zigbee2MQTT's retained bridge/info: its version, log level and configuration."""
        return await self._z2m_retained("info")

    async def z2m_set_log_level(self, level: str) -> None:
        """Set Zigbee2MQTT's log level (it persists in its configuration), and wait until bridge/info shows it."""

        async def done() -> bool:
            return await self.z2m_log_level() == level

        payload = {"options": {"advanced": {"log_level": level}}}
        await self._z2m_request("options", payload, done, f"set its log level to {level}")

    async def z2m_interview(self, ieee: str) -> None:
        """Ask Zigbee2MQTT to interview `ieee` again. Not awaited: the device's interview_state shows the outcome."""
        payload = json.dumps({"id": ieee})
        await self.call_service(
            "mqtt", "publish", {"topic": f"{Z2M_TOPIC}/request/device/interview", "payload": payload}
        )

    async def z2m_device(self, ieee: str) -> dict | None:
        """Zigbee2MQTT's entry for `ieee` in its retained bridge/devices (`interview_completed` says it is in), or
        None."""
        wanted = normalize_ieee(ieee)
        devices = await self._z2m_retained("devices")
        return next((d for d in devices if normalize_ieee(d.get("ieee_address", "")) == wanted), None)

    async def z2m_has_device(self, ieee: str) -> bool:
        """Whether Zigbee2MQTT's retained bridge/devices lists `ieee`."""
        return await self.z2m_device(ieee) is not None

    async def z2m_remove_device(self, ieee: str) -> None:
        """Remove a device from Zigbee2MQTT (it sends the bulb a Leave), then wait until bridge/devices drops it."""

        async def done() -> bool:
            return not await self.z2m_has_device(ieee)

        await self._z2m_request("device/remove", {"id": ieee}, done, f"remove {ieee}")

    async def z2m_group(self, name: str) -> dict | None:
        """Zigbee2MQTT's entry for the group `name` in its retained bridge/groups (its `id` and `members`), or None."""
        return next((g for g in await self._z2m_retained("groups") if g.get("friendly_name") == name), None)

    async def z2m_group_members(self, name: str) -> list[str] | None:
        """The IEEE addresses in the Zigbee2MQTT group `name`, or None if there is no such group."""
        if (group := await self.z2m_group(name)) is None:
            return None
        return [member["ieee_address"] for member in group.get("members", [])]

    async def z2m_group_add(self, name: str, members: tuple[str, ...] = ()) -> None:
        """Make a Zigbee2MQTT group and add `members` (IEEE addresses) to it. Raises if the name is already taken,
        since a group left by a crash would otherwise be reused with its old members."""
        if await self.z2m_group_members(name) is not None:
            raise ValueError(f"Zigbee2MQTT already has a group named {name}")

        async def made() -> bool:
            return await self.z2m_group_members(name) is not None

        await self._z2m_request("group/add", {"friendly_name": name}, made, f"add group {name}")
        for ieee in members:

            async def joined(ieee=ieee) -> bool:
                return normalize_ieee(ieee) in map(normalize_ieee, await self.z2m_group_members(name) or [])

            payload = {"group": name, "device": ieee}
            await self._z2m_request("group/members/add", payload, joined, f"add {ieee} to {name}")

    async def z2m_group_remove(self, name: str) -> None:
        """Remove a Zigbee2MQTT group; its members stay on the network."""

        async def gone() -> bool:
            return await self.z2m_group_members(name) is None

        await self._z2m_request("group/remove", {"id": name}, gone, f"remove group {name}")

    # --- ZHA: joining, removing, groups ---------------------------------------------------------------------------

    async def zha_permit(self, duration: int) -> None:
        """Open ZHA joining for `duration` seconds. Its state can't be read anywhere, so close it with `zha_close`."""
        await self.call_service("zha", "permit", {"duration": duration})

    async def zha_close(self) -> None:
        """Close ZHA joining: an explicit `duration: 0`, since a window is otherwise left to run out unseen."""
        await self.call_service("zha", "permit", {"duration": 0})

    @contextlib.asynccontextmanager
    async def zha_joining(self, duration: int) -> AsyncIterator[None]:
        """ZHA joining open for the block, always closed after it, even on an error."""
        await self.zha_permit(duration)
        try:
            yield
        finally:
            await self.zha_close()

    async def zha_remove(self, ieee: str) -> None:
        """Remove a device from ZHA (it sends the bulb a Leave)."""
        await self.call_service("zha", "remove", {"ieee": ieee})

    async def zha_group_add(self, name: str, members: tuple[tuple[str, int], ...] = ()) -> int:
        """Make a ZHA group of (IEEE, endpoint) members; returns its group id."""
        payload = {
            "type": "zha/group/add",
            "group_name": name,
            "members": [{"ieee": ieee, "endpoint_id": endpoint} for ieee, endpoint in members],
        }
        return (await self.command(payload))["group_id"]

    async def zha_groups(self) -> list[dict]:
        """ZHA's groups, each with its `group_id`, `name` and `members`."""
        return await self.command({"type": "zha/groups"})

    async def zha_group_remove(self, group_id: int) -> None:
        await self.command({"type": "zha/group/remove", "group_ids": [group_id]})

    async def zha_read_attribute(self, ieee: str, endpoint: int, cluster: int, attribute: int) -> int | None:
        """One server-cluster attribute read live off a ZHA device (never zigpy's cache); None if it didn't answer."""
        payload = {
            "type": "zha/devices/clusters/attributes/value",
            "ieee": ieee,
            "endpoint_id": endpoint,
            "cluster_id": cluster,
            "cluster_type": "in",
            "attribute": attribute,
        }
        value = await self.command(payload)  # HA answers with str() of the value: "None" for no answer
        try:
            return int(value)
        except TypeError, ValueError:
            return None

    # --- Registries -----------------------------------------------------------------------------------------------

    async def device_by_ieee(self, integration: str, ieee: str) -> dict | None:
        """The device-registry entry on `integration` ("zha" or "zigbee2mqtt") with this IEEE, or None."""
        if integration not in IEEE_INTEGRATIONS:
            raise ValueError(f"no IEEE in the device registry for {integration}; a Hue device is found on the bridge")
        wanted = normalize_ieee(ieee)
        for device in await self.command({"type": "config/device_registry/list"}):
            found = device_ieee(device, integration)
            if found is not None and normalize_ieee(found) == wanted:
                return device
        return None

    async def entity_registry(self) -> list[dict]:
        """Every entity-registry entry, with its entity_id, device_id and platform."""
        return await self.command({"type": "config/entity_registry/list"})

    async def rename_entity(self, entity_id: str, new_entity_id: str, enable: bool = False) -> None:
        """Change an entity's ID in the entity registry, and enable it too if asked. HA refuses when `new_entity_id`
        is taken."""
        payload = {"type": "config/entity_registry/update", "entity_id": entity_id, "new_entity_id": new_entity_id}
        await self.command(payload | ({"disabled_by": None} if enable else {}))

    async def remove_entity(self, entity_id: str) -> None:
        await self.command({"type": "config/entity_registry/remove", "entity_id": entity_id})
