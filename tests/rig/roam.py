"""Roaming: the rig moves a profile's lab bulbs between Zigbee networks, all together, round the fixed cycle
Hue → ZHA → Z2M → Hue (profile.CYCLE), so each network's suites run on the same bulbs within one run.

Each move releases the bulbs from one network and joins them to the next, by the procedure the A60 move probe proved
(docs/plans/2026-10-31-a60-move-probe.md): Hue deletes the device (CLIP v2 only), ZHA and Z2M remove it, each sending
a Leave; then the next network opens a finite join window, closed once every bulb is in. After each join the bulb's
light entity is renamed to its fixed profile entity ID, and on Z2M its options are set again.

Hue is home. Before a bulb first leaves, its room and zone membership, the scene actions that target it and its
name are saved; when it returns they are rewritten against its new device and light IDs.

The journal's `roam` section is written before every change: where each bulb is, the move in flight and the saved
home, with each bulb's IEEE, entity ID and Z2M options, so --recover can bring the bulbs home with no profile loaded.
Where a bulb is, though, is always read from the networks themselves; the journal's copy is for a person reading it.
"""

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field

from .bridge import BridgeError, HueBridge
from .client import HAClient, device_ieee
from .journal import Journal
from .profile import CYCLE, RoamBulb, colon_ieee, hex_ieee, normalize_ieee

HOME = CYCLE[0]
NAMES = {"hue": "Hue", "zha": "ZHA", "zigbee2mqtt": "Z2M"}
JOIN_S = 120  # how long a join window stays open, and how long a bulb has to join it
RELEASE_S = 30  # for a released bulb to drop off its network
ENTITY_S = 90  # for HA to show a joined bulb's device and light entity (ZHA's interview took about 60 s)
HUE_SEARCH_S = 56  # how long a Hue search stays open; it can't be ended early
# Searches per return to Hue: a second only when a bulb is still missing once the first has ended, so a normal run
# opens one window, and a failing one two, for whatever device is resetting nearby to join.
HUE_SEARCHES = 2
POLL_S = 2.0
# A bulb on no network is found with the Hue app, which can reset a bulb over Bluetooth and add it to the bridge.
BLUETOOTH_RESET = (
    "Reset it over Bluetooth in the Hue app and add it to the bridge, then run scripts/rig.py --recover, which puts "
    "back its Hue rooms and scenes; the journal keeps them until then."
)


class RoamError(Exception):
    """A move that couldn't finish. The journal keeps what --recover needs."""


def hops(network: str, to: str) -> int:
    """Moves forward round the cycle from `network` to `to`."""
    return (CYCLE.index(to) - CYCLE.index(network)) % len(CYCLE)


def following(network: str) -> str:
    return CYCLE[(CYCLE.index(network) + 1) % len(CYCLE)]


def route(start: str = HOME) -> list[str]:
    """The networks a run visits, starting and ending at `start`: Hue, ZHA, Z2M, Hue."""
    return [*CYCLE[CYCLE.index(start) :], *CYCLE[: CYCLE.index(start)], start]


def plan_lines(bulbs: Iterable[RoamBulb]) -> list[str]:
    """What a roaming run does between its phases, for the plan before the gate."""
    names = ", ".join(bulb.entity_id for bulb in bulbs)
    return [
        f"Roams {names} together: {' -> '.join(NAMES[network] for network in route())}.",
        f"  Hue -> ZHA: delete on the bridge, then ZHA joining for up to {JOIN_S} s, closed once all are in.",
        f"  ZHA -> Z2M: zha.remove, then Z2M joining for up to {JOIN_S} s, closed once all are in.",
        f"  Z2M -> Hue: Z2M remove, then a Hue search: open about {HUE_SEARCH_S} s, and it can't be ended early;",
        "    one more only if a bulb is still missing. Any other device that joins meanwhile is named.",
        "  After each join the bulbs are renamed to their entity IDs; back on Hue their rooms and scenes are restored.",
    ]


@dataclass(slots=True)
class Bulb:
    """What the journal keeps of a roaming bulb: enough to move it home with no profile loaded."""

    ieee: str
    entity_id: str
    z2m_options: dict = field(default_factory=dict)

    @classmethod
    def of(cls, bulb: RoamBulb) -> Bulb:
        return cls(bulb.ieee, bulb.entity_id, dict(bulb.z2m_options))

    def saved(self) -> dict:
        return {"ieee": self.ieee, "entity_id": self.entity_id, "z2m_options": self.z2m_options}


async def _until(check: Callable[[], Awaitable[bool]], timeout: float) -> bool:
    """Poll `check` every POLL_S until it holds; whether it did within `timeout`."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not await check():
        if asyncio.get_running_loop().time() > deadline:
            return False
        await asyncio.sleep(POLL_S)
    return True


class Roamer:
    """Moves the lab bulbs between networks. `ha` must be an admin connection: registry writes and MQTT need one."""

    def __init__(
        self,
        ha: HAClient,
        bridge: HueBridge,
        bulbs: Iterable[Bulb],
        journal: Journal | None = None,
        out: Callable[[str], None] = print,
    ):
        self.ha, self.bridge, self.journal, self.out = ha, bridge, journal, out
        self.bulbs = list(bulbs)
        saved = (journal.get("roam") if journal is not None else None) or {}
        self.at: dict[str, str | None] = dict(saved.get("at", {}))
        self.home: dict[str, dict] = dict(saved.get("home", {}))
        self.moving: dict | None = saved.get("move")
        # The bridge's devices before a search, until search_over has named any newcomer; journaled, so recovery can.
        before = saved.get("bridge_before")
        self.bridge_before: set[str] | None = set(before) if before is not None else None

    @classmethod
    def from_journal(cls, ha: HAClient, bridge: HueBridge, journal: Journal, out: Callable[[str], None] = print):
        bulbs = [Bulb(**bulb) for bulb in journal.get("roam", {}).get("bulbs", [])]
        return cls(ha, bridge, bulbs, journal, out)

    # --- the journal ----------------------------------------------------------------------------------------------

    def save(self) -> None:
        if self.journal is not None:
            self.journal.update(
                roam={
                    "bulbs": [bulb.saved() for bulb in self.bulbs],
                    "at": self.at,
                    "move": self.moving,
                    "home": self.home,
                    "bridge_before": sorted(self.bridge_before) if self.bridge_before is not None else None,
                }
            )

    def finish(self) -> None:
        """Clear the journal's roam section once every bulb is home with its home put back."""
        if self.journal is not None and not self.home and self.moving is None:
            if all(self.at.get(bulb.entity_id) == HOME for bulb in self.bulbs):
                self.journal.clear("roam")

    # --- where a bulb is ------------------------------------------------------------------------------------------

    async def joined(self, network: str, bulb: Bulb) -> bool:
        """Whether `bulb` is on `network`, by that network's own account (for Z2M: interviewed)."""
        if network == "hue":
            return await self.bridge.device_id_by_ieee(bulb.ieee) is not None
        if network == "zha":
            return await self.ha.device_by_ieee("zha", bulb.ieee) is not None
        device = await self.ha.z2m_device(hex_ieee(bulb.ieee))
        return device is not None and bool(device.get("interview_completed"))

    async def locate(self, bulb: Bulb) -> str | None:
        """The network `bulb` is on, or None. Hue's bridge and Z2M's device list are asked before HA's ZHA registry,
        which is the only view of ZHA and may keep a device a Leave already took."""
        if await self.bridge.device_id_by_ieee(bulb.ieee) is not None:
            return "hue"
        if await self.ha.z2m_device(hex_ieee(bulb.ieee)) is not None:
            return "zigbee2mqtt"
        if await self.ha.device_by_ieee("zha", bulb.ieee) is not None:
            return "zha"
        return None

    # --- moving ---------------------------------------------------------------------------------------------------

    async def go(self, to: str) -> None:
        """Move every bulb forward round the cycle until all are on `to`. Bulbs on different networks (after a crash)
        move in turn, furthest first, so they meet on the way. On a bulb found on no network it raises RoamError."""
        for bulb in self.bulbs:
            self.at[bulb.entity_id] = await self.locate(bulb)
        if lost := [bulb.entity_id for bulb in self.bulbs if self.at[bulb.entity_id] is None]:
            self.save()
            raise RoamError(f"Not on any Zigbee network: {', '.join(lost)}. {BLUETOOTH_RESET}")
        if self.moving is not None:
            # A move to `to` cut short: whoever already joined may still need its rename and options.
            if self.moving["to"] == to:
                for bulb in self.bulbs:
                    if bulb.entity_id in self.moving["bulbs"] and self.at[bulb.entity_id] == to:
                        await self.adopt(to, bulb)
            self.moving = None
            self.save()
        while away := [bulb for bulb in self.bulbs if self.at[bulb.entity_id] != to]:
            start = max({self.at[bulb.entity_id] for bulb in away}, key=lambda network: hops(network, to))
            await self.move([bulb for bulb in away if self.at[bulb.entity_id] == start], start, following(start))
        if to == HOME:
            await self.restore_home()
            if not await self.search_over():
                self.out("The Hue search is still open; anything resetting nearby may yet join the bridge.")
            self.finish()

    async def move(self, bulbs: list[Bulb], source: str, target: str) -> None:
        names = ", ".join(bulb.entity_id for bulb in bulbs)
        self.out(f"Moving {names} from {NAMES[source]} to {NAMES[target]}.")
        if source == HOME:
            await self.save_home(bulbs)
        self.moving = {"from": source, "to": target, "bulbs": [bulb.entity_id for bulb in bulbs]}
        self.save()
        # A released bulb joins whatever network is open, so only the target may be.
        await self.close_all()
        for bulb in bulbs:
            await self.release(source, bulb)
            self.at[bulb.entity_id] = None
            self.save()
        await self.join(target, bulbs)
        for bulb in bulbs:
            self.at[bulb.entity_id] = target
            self.save()
            await self.adopt(target, bulb)
        self.moving = None
        self.save()
        self.out(f"{names} on {NAMES[target]}.")

    async def close_all(self) -> None:
        """Close joining on every network. ZHA's state can't be read, so it is always closed explicitly; a Hue
        search can't be ended, so it is waited out."""
        await self.ha.zha_close()
        if await self.ha.z2m_permit_join_open():
            await self.ha.z2m_permit_join(0)
        if not await self.search_over():
            raise RoamError("the Hue bridge is still searching for lights; nothing was released")

    async def hue_idle(self) -> bool:
        return (await self.discovery()).get("status") != "active"

    async def search_over(self) -> bool:
        """Wait out a Hue search, then name any device that joined the bridge during it and isn't a roaming bulb:
        an open search admits whatever is resetting nearby. It is left on the bridge, as it may be wanted. Whether
        the search ended in time."""
        if not await _until(self.hue_idle, HUE_SEARCH_S + 15):
            return False
        if self.bridge_before is not None:
            ours = {await self.bridge.device_id_by_ieee(bulb.ieee) for bulb in self.bulbs}
            for device in await self.bridge.get("device"):
                if device["id"] not in self.bridge_before | ours:
                    name = device.get("metadata", {}).get("name", "unnamed")
                    model = device.get("product_data", {}).get("model_id", "unknown model")
                    self.out(
                        f"A device that isn't a roaming bulb joined the Hue bridge during the search: {name} "
                        f"({model}, device {device['id']}). Check it in the Hue app; the rig leaves it there."
                    )
            self.bridge_before = None
            self.save()
        return True

    async def discovery(self) -> dict:
        """The bridge's one zigbee_device_discovery resource."""
        found = await self.bridge.get("zigbee_device_discovery")
        if not found:
            raise RoamError("the Hue bridge has no zigbee_device_discovery resource")
        return found[0]

    async def release(self, network: str, bulb: Bulb) -> None:
        """Take `bulb` off `network` (each sends it a Leave), and wait until the network no longer lists it."""
        if network == "hue":
            if (device_id := await self.bridge.device_id_by_ieee(bulb.ieee)) is not None:
                await self.bridge.delete("device", device_id)
        elif network == "zha":
            await self.ha.zha_remove(colon_ieee(bulb.ieee))
        else:
            await self.ha.z2m_remove_device(hex_ieee(bulb.ieee))

        async def gone() -> bool:
            return not await self.joined(network, bulb)

        if not await _until(gone, RELEASE_S):
            raise RoamError(f"{bulb.entity_id} is still on {NAMES[network]} {RELEASE_S} s after its removal")

    async def join(self, network: str, bulbs: list[Bulb]) -> None:
        """Open `network` for the bulbs and wait until all are in; ZHA and Z2M close once they are, or on a timeout."""

        async def all_in() -> bool:
            return all([await self.joined(network, bulb) for bulb in bulbs])

        if network == "zha":
            async with self.ha.zha_joining(JOIN_S):
                arrived = await _until(all_in, JOIN_S)
        elif network == "zigbee2mqtt":
            await self.ha.z2m_permit_join(JOIN_S)
            try:
                arrived = await _until(all_in, JOIN_S)
            finally:
                await self.ha.z2m_permit_join(0)
        else:
            arrived = await self.hue_join(bulbs, all_in)
        if not arrived:
            missing = [bulb.entity_id for bulb in bulbs if not await self.joined(network, bulb)]
            window = f"{HUE_SEARCHES} searches" if network == "hue" else f"{JOIN_S} s"
            raise RoamError(
                f"Not on any Zigbee network: {', '.join(missing)} did not join {NAMES[network]} within {window}. "
                f"{BLUETOOTH_RESET}"
            )

    async def hue_join(self, bulbs: list[Bulb], all_in: Callable[[], Awaitable[bool]]) -> bool:
        """Search until every bulb is in: one search, and one more if a bulb is still missing when it ends. Returns
        once all are in, so a search may still be open; the next move's close_all, or go(HOME), waits it out."""
        self.bridge_before = {device["id"] for device in await self.bridge.get("device")}
        self.save()
        discovery = await self.discovery()
        for search in range(HUE_SEARCHES):
            if search:
                missing = [bulb.entity_id for bulb in bulbs if not await self.joined("hue", bulb)]
                self.out(f"{', '.join(missing)} not on Hue after the search; searching once more.")
            await self.bridge.put("zigbee_device_discovery", discovery["id"], {"action": {"action_type": "search"}})
            started = False

            async def in_or_ended() -> bool:
                nonlocal started
                if await all_in():
                    return True
                # The bridge reports a search active at once (the probe saw it), so it has ended only once it was
                # seen active and no longer is. A bridge that never showed it would cost the timeout, not a result.
                idle = await self.hue_idle()
                started = started or not idle
                return started and idle

            await _until(in_or_ended, HUE_SEARCH_S + 15)
            if await all_in():
                return True
        await self.search_over()  # already over: name whatever joined
        return False

    # --- HA's view of a joined bulb -------------------------------------------------------------------------------

    async def ha_device(self, network: str, bulb: Bulb) -> dict | None:
        """HA's device-registry entry for `bulb` on `network`. HA's hue integration keys a device by its bridge id."""
        if network != "hue":
            return await self.ha.device_by_ieee(network, bulb.ieee)
        if (device_id := await self.bridge.device_id_by_ieee(bulb.ieee)) is None:
            return None
        devices = await self.ha.command({"type": "config/device_registry/list"})
        return next((d for d in devices if ["hue", device_id] in map(list, d.get("identifiers", []))), None)

    async def adopt(self, network: str, bulb: Bulb) -> None:
        """Once HA shows the joined bulb's light, give it the bulb's fixed entity ID; on Z2M, set its options."""
        light: dict | None = None

        async def shown() -> bool:
            nonlocal light
            if (device := await self.ha_device(network, bulb)) is None:
                return False
            lights = [
                entry
                for entry in await self.ha.entity_registry()
                if entry.get("device_id") == device["id"] and entry["entity_id"].startswith("light.")
            ]
            if len(lights) > 1:
                raise RoamError(f"{bulb.entity_id}'s {NAMES[network]} device has {len(lights)} lights, not one")
            light = lights[0] if lights else None
            return light is not None

        if not await _until(shown, ENTITY_S):
            raise RoamError(f"{bulb.entity_id} joined {NAMES[network]}, but HA showed no light for it in {ENTITY_S} s")
        assert light is not None
        if light["entity_id"] != bulb.entity_id:
            await self.free(bulb, network)
            await self.ha.rename_entity(light["entity_id"], bulb.entity_id)
            self.out(f"Renamed {light['entity_id']} to {bulb.entity_id}.")
        if network == "zigbee2mqtt" and bulb.z2m_options:
            await self.ha.set_z2m_device_options(hex_ieee(bulb.ieee), bulb.z2m_options)

    async def free(self, bulb: Bulb, network: str) -> None:
        """Remove a registry entry that holds the bulb's fixed ID from an earlier visit. Only a stale one goes: its
        device is gone, or is this bulb on another network. One held by any other device stops the move."""
        entry = next((e for e in await self.ha.entity_registry() if e["entity_id"] == bulb.entity_id), None)
        if entry is None:
            return
        if not await self.stale(entry, bulb):
            raise RoamError(
                f"{bulb.entity_id} belongs to another device, so the bulb's {NAMES[network]} light can't take it; "
                "rename that entity or change the profile"
            )
        await self.ha.remove_entity(bulb.entity_id)
        self.out(f"Removed {bulb.entity_id}'s stale registry entry.")

    async def stale(self, entry: dict, bulb: Bulb) -> bool:
        devices = {d["id"]: d for d in await self.ha.command({"type": "config/device_registry/list"})}
        if (device := devices.get(entry.get("device_id"))) is None:
            return True
        for integration in ("zha", "zigbee2mqtt"):
            if (ieee := device_ieee(device, integration)) is not None:
                return normalize_ieee(ieee) == bulb.ieee
        hue_ids = [ident for domain, ident in device.get("identifiers", []) if domain == "hue"]
        if hue_ids:
            # The bridge may still have the device under another name; it is stale once the bridge has dropped it,
            # or holds it as this bulb.
            on_bridge = {d["id"] for d in await self.bridge.get("device")}
            mine = await self.bridge.device_id_by_ieee(bulb.ieee)
            return all(ident not in on_bridge or ident == mine for ident in hue_ids)
        return False

    # --- home -----------------------------------------------------------------------------------------------------

    async def save_home(self, bulbs: list[Bulb]) -> None:
        """Before a bulb leaves Hue: its rooms (by device), zones (by light), the scene actions on its light and its
        name. A home already saved, by a run that crashed before restoring it, is kept."""
        rooms, zones, scenes = [await self.bridge.get(kind) for kind in ("room", "zone", "scene")]
        for bulb in bulbs:
            if bulb.entity_id in self.home:
                continue
            device_id = await self.bridge.device_id_by_ieee(bulb.ieee)
            device = (await self.bridge.get("device", device_id))[0]
            light_id = _light_of(device)
            self.home[bulb.entity_id] = {
                "device": device_id,
                "light": light_id,
                "metadata": {key: device.get("metadata", {}).get(key) for key in ("name", "archetype")},
                "rooms": [room["id"] for room in rooms if _has_child(room, device_id)],
                "zones": [zone["id"] for zone in zones if _has_child(zone, light_id)],
                "scenes": {
                    scene["id"]: actions
                    for scene in scenes
                    if (actions := [a for a in scene.get("actions", []) if a["target"]["rid"] == light_id])
                },
            }
        self.save()

    async def restore_home(self) -> None:
        """Put back each saved home on the bulb's new device and light: name, rooms, zones, then scenes, whose actions
        need the light in their room or zone. A room or scene gone from the bridge is skipped with a line."""
        for bulb in self.bulbs:
            if (home := self.home.get(bulb.entity_id)) is None:
                continue
            device_id = await self.bridge.device_id_by_ieee(bulb.ieee)
            device = (await self.bridge.get("device", device_id))[0]
            light_id = _light_of(device)
            await self._put(f"{bulb.entity_id}'s name", "device", device_id, {"metadata": home["metadata"]})
            for kind, key, child in (("room", "rooms", (device_id, "device")), ("zone", "zones", (light_id, "light"))):
                old = home["device"] if kind == "room" else home["light"]
                for group_id in home[key]:
                    await self._regroup(bulb, kind, group_id, old, child)
            for scene_id, actions in home["scenes"].items():
                await self._rescene(bulb, scene_id, home["light"], light_id, actions)
            del self.home[bulb.entity_id]
            self.save()
            self.out(f"Put back {bulb.entity_id}'s Hue rooms and scenes.")

    async def _regroup(self, bulb: Bulb, kind: str, group_id: str, old: str, child: tuple[str, str]) -> None:
        try:
            group = (await self.bridge.get(kind, group_id))[0]
        except BridgeError as err:
            self.out(f"Could not put {bulb.entity_id} back in {kind} {group_id}: {err}")
            return
        children = [c for c in group.get("children", []) if c["rid"] not in (old, child[0])]
        children.append({"rid": child[0], "rtype": child[1]})
        await self._put(f"{bulb.entity_id}'s {kind}", kind, group_id, {"children": children})

    async def _rescene(self, bulb: Bulb, scene_id: str, old: str, new: str, saved: list[dict]) -> None:
        try:
            scene = (await self.bridge.get("scene", scene_id))[0]
        except BridgeError as err:
            self.out(f"Could not put back {bulb.entity_id}'s action in scene {scene_id}: {err}")
            return
        actions = [a for a in scene.get("actions", []) if a["target"]["rid"] not in (old, new)]
        actions += [{**action, "target": {"rid": new, "rtype": "light"}} for action in saved]
        await self._put(f"{bulb.entity_id}'s scene action", "scene", scene_id, {"actions": actions})

    async def _put(self, what: str, kind: str, resource_id: str, body: dict) -> None:
        try:
            await self.bridge.put(kind, resource_id, body)
        except BridgeError as err:
            self.out(f"Could not put back {what} ({kind} {resource_id}): {err}")


def _light_of(device: dict) -> str:
    lights = [service["rid"] for service in device.get("services", []) if service.get("rtype") == "light"]
    if len(lights) != 1:
        raise RoamError(f"Hue device {device.get('id')} has {len(lights)} lights, not one")
    return lights[0]


def _has_child(group: dict, rid: str) -> bool:
    return any(child.get("rid") == rid for child in group.get("children", []))
