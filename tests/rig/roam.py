"""Roaming: the rig moves a profile's lab bulbs between Zigbee networks, all together, to each network whose suites
the run holds, in the order Hue, ZHA, Z2M (profile.CYCLE), then straight home to Hue. Every move is direct: a bulb
leaves the network it is on for the target, so recovery takes one move from anywhere.

Each move releases the bulbs from their network and joins them to the target, by the procedure the A60 move probe proved
(docs/plans/2026-10-31-a60-move-probe.md): Hue deletes the device (CLIP v2 only), ZHA and Z2M remove it, each sending
a Leave; then the next network opens a finite join window, closed once every bulb is in. After each join the bulb's
light entity is renamed to its fixed profile entity ID, and on Z2M its options are set again.

Hue is home. Before a bulb first leaves, its room and zone membership, the scene actions that target it and its
name are saved; when it returns they are rewritten against its new device and light IDs.

On each visit the run makes the profile's `ds-rig-*` groups on the bulbs' network: a Z2M group, a ZHA group or a Hue
zone (whose grouped_light is the group), plus a Hue scene in the zone where the profile names one, each renamed to
its fixed entity ID. They are removed before the bulbs move on, and by --recover after a crash.

The journal's `roam` section is written before every change: where each bulb is, the move in flight, the saved
home and each rig-made group, with each bulb's IEEE, entity ID and Z2M options, so --recover can bring the bulbs home
and remove the groups with no profile loaded. Where a bulb is, though, is always read from the networks themselves;
the journal's copy is for a person reading it.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from dataclasses import dataclass, field

from .bridge import BridgeError, HueBridge
from .client import HAClient, HAError, device_ieee
from .journal import Journal
from .profile import (
    CYCLE,
    RIG_PREFIX,
    ZHA_GROUP_MIN,
    RoamBulb,
    RoamGroup,
    colon_ieee,
    hex_ieee,
    normalize_ieee,
    rig_name,
)

HOME = CYCLE[0]
NAMES = {"hue": "Hue", "zha": "ZHA", "zigbee2mqtt": "Z2M"}
JOIN_S = 120  # how long a join window stays open, and how long a bulb has to join it
REINTERVIEWS = 3  # how many times a join asks Z2M to interview a bulb again after a failed interview
REINTERVIEW_GAP_S = 20  # between asks for one bulb: the retained device list may still say FAILED just after one
JOIN_LOG_LEVEL = "info"  # Z2M's log level during a join: its default, warning, logs no join or interview
VERBOSE_LOG_LEVELS = ("info", "debug")
RELEASE_S = 30  # for a released bulb to drop off its network
ENTITY_S = 90  # for HA to show a joined bulb's device and light entity (ZHA's interview took about 60 s)
HUE_SEARCH_S = 56  # how long a Hue search stays open; it can't be ended early
# Searches per return to Hue: a second only when a bulb is still missing once the first has ended, so a normal run
# opens one window, and a failing one two, for whatever device is resetting nearby to join.
HUE_SEARCHES = 2
POLL_S = 2.0
GONE_S = 15  # for HA to drop a rig-made group's entity once the group is removed; after that the rig removes it
# The rig-made Hue scene: every member on at 40 %, and 366 mirek (2732 K) where it takes a color temperature. Below
# full, so a recall mid-fade shows (raise_brightness-predicted_state's bridge_scene_recall_mid_fade_shows_at_once).
SCENE_BRIGHTNESS = 40.0
SCENE_MIREK = 366
# HA's platform for each network's entities, so the rig removes only a leftover entity of its own kind.
PLATFORMS = {"hue": "hue", "zha": "zha", "zigbee2mqtt": "mqtt"}
# Z2M registers a group's HA device as ("mqtt", "zigbee2mqtt_<base topic as character codes>_<group ID>")
# (getEncodedBaseTopic in Z2M's lib/extension/homeassistant.ts; device_side's zigbee2mqtt/addressing.py reads it).
Z2M_GROUP_IDENTIFIER = "zigbee2mqtt_" + "".join(str(ord(c)) for c in "zigbee2mqtt") + "_{}"
# The zha library gives a group's entity the unique_id "{platform}_zha_group_0x{group_id:04x}" (zha/addressing.py).
ZHA_GROUP_UNIQUE_ID = "light_zha_group_0x{:04x}"
# A bulb on no network is found with the Hue app, which can reset a bulb over Bluetooth and add it to the bridge.
BLUETOOTH_RESET = (
    "Reset it over Bluetooth in the Hue app and add it to the bridge, then run scripts/rig.py --recover, which puts "
    "back its Hue rooms and scenes; the journal keeps them until then."
)
# zha.remove drops a bulb from HA whether or not it acts on the Leave; one that misses it stays on ZHA's network until
# power-up, when it announces itself and ZHA adds it back.
MISSED_ZHA_LEAVE = (
    "It may have missed ZHA's Leave: switch its lamp off and on, and once ZHA shows it again run scripts/rig.py "
    "--recover. If ZHA doesn't show it, reset it over Bluetooth in the Hue app and add it to the bridge first."
)


Finder = Callable[[], Awaitable[dict | None]]  # finds a rig-made group's HA entity: its registry entry, or None


class RoamError(Exception):
    """A move that couldn't finish. The journal keeps what --recover needs."""


class GroupError(RoamError):
    """A rig-made group, zone or scene that couldn't be made. The bulbs are fine, so they can still move home."""


def plan_lines(
    bulbs: Iterable[RoamBulb], groups: Iterable[RoamGroup] = (), moving: bool = True, route: Iterable[str] = CYCLE
) -> list[str]:
    """What a lab run does between its phases, for the plan before the gate: the moves, and the groups it makes.
    `route` is the networks the run visits, in order; it ends home on Hue."""
    names = ", ".join(bulb.entity_id for bulb in bulbs)
    lines = []
    if moving:
        stops = [network for network in route if network != HOME]
        lines = [
            f"Roams {names} together: {' -> '.join(NAMES[network] for network in [HOME, *stops, HOME])}.",
            "  Leaving: Hue deletes the device on the bridge; ZHA and Z2M remove it.",
            f"  Joining ZHA or Z2M: open for up to {JOIN_S} s, closed once all are in.",
            f"  Joining Hue: a search, open about {HUE_SEARCH_S} s, and it can't be ended early;",
            "    one more only if a bulb is still missing. Any other device that joins meanwhile is named.",
            "  After each join the bulbs are renamed to their entity IDs; back on Hue their rooms and scenes are "
            "restored.",
        ]
    for group in groups:
        where = "on each visit" if moving else "on Hue"
        if moving and not group.made_on("zha"):
            where = f"on each visit but ZHA's (one member; ZHA needs {ZHA_GROUP_MIN})"
        scene = f", with scene {group.scene} (Hue)" if group.scene else ""
        lines.append(
            f"Makes {rig_name(group.entity_id)} {where} as {group.entity_id} ({', '.join(group.members)}){scene}; "
            "removed after it."
        )
    return lines


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
        groups: Iterable[RoamGroup] = (),
    ):
        self.ha, self.bridge, self.journal, self.out = ha, bridge, journal, out
        self.bulbs = list(bulbs)
        self.groups = list(groups)
        saved = (journal.get("roam") if journal is not None else None) or {}
        self.at: dict[str, str | None] = dict(saved.get("at", {}))
        self.home: dict[str, dict] = dict(saved.get("home", {}))
        self.moving: dict | None = saved.get("move")
        # Each rig-made group or scene, journaled before it is made: {network, kind, name, entity_id, renamed}.
        self.made: list[dict] = [dict(made) for made in saved.get("made", [])]
        # The bridge's devices before a search, until search_over has named any newcomer; journaled, so recovery can.
        before = saved.get("bridge_before")
        self.bridge_before: set[str] | None = set(before) if before is not None else None
        # The bulbs in the order they last joined a network; journaled, so recovery releases them in reverse.
        self.arrived: list[str] = list(saved.get("arrived", []))
        # Z2M's own log level while a join holds it at JOIN_LOG_LEVEL; journaled, so a crash mid-join still restores it.
        self.z2m_log_level: str | None = saved.get("z2m_log_level")

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
                    "made": self.made,
                    "bridge_before": sorted(self.bridge_before) if self.bridge_before is not None else None,
                    "arrived": self.arrived,
                    "z2m_log_level": self.z2m_log_level,
                }
            )

    def finish(self) -> None:
        """Clear the journal's roam section once every bulb is home with its home put back, and no rig-made group is
        left."""
        if (
            self.journal is not None
            and not self.home
            and self.moving is None
            and not self.made
            and not self.z2m_log_level
        ):
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
        """Remove the rig-made groups, then move every bulb not on `to` straight there, in one move, whichever
        networks they are on (after a crash, they may differ). On a bulb found on no network it raises RoamError."""
        await self.remove_groups()
        await self.restore_z2m_log_level()  # a crash mid-join left it raised
        await self.settle(to)
        if away := [bulb for bulb in self.bulbs if self.at[bulb.entity_id] != to]:
            await self.move(away, to)
        if to == HOME:
            await self.restore_home()
            if not await self.search_over():
                self.out("The Hue search is still open; anything resetting nearby may yet join the bridge.")
            self.finish()

    async def settle(self, to: str) -> None:
        """Find every bulb, and finish a move a crash cut short: rename whoever reached `to`. A bulb that move released
        and that is on no network stays None, for go to join to `to`; one on no network that no move released raises
        RoamError."""
        for bulb in self.bulbs:
            self.at[bulb.entity_id] = await self.locate(bulb)
        # A bulb a crash caught between its release and its join is on no network, but joins whichever one opens.
        released = set(self.moving["bulbs"]) if self.moving is not None else set()
        nowhere = [bulb for bulb in self.bulbs if self.at[bulb.entity_id] is None]
        if lost := [bulb.entity_id for bulb in nowhere if bulb.entity_id not in released]:
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

    async def move(self, bulbs: list[Bulb], target: str) -> None:
        """Release each bulb from the network it is on (none, for a bulb a crash left released) and join them all to
        `target`."""
        origins = {bulb.entity_id: self.at[bulb.entity_id] for bulb in bulbs}
        names = ", ".join(bulb.entity_id for bulb in bulbs)
        sources = [NAMES[network] for network in CYCLE if network in origins.values()]
        if None in origins.values():
            sources.append("no network (a move cut short)")
        self.out(f"Moving {names} from {' and '.join(sources)} to {NAMES[target]}.")
        if leaving_home := [bulb for bulb in bulbs if origins[bulb.entity_id] == HOME]:
            await self.save_home(leaving_home)
        self.moving = {"from": origins, "to": target, "bulbs": list(origins)}
        self.save()
        # A released bulb joins whatever network is open, so only the target may be.
        await self.close_all()
        for bulb in self.release_order(bulbs):
            if (source := origins[bulb.entity_id]) is not None:
                await self.release(source, bulb)
                self.at[bulb.entity_id] = None
                self.save()
        await self.join(target, bulbs, origins)
        for bulb in bulbs:
            self.at[bulb.entity_id] = target
            self.save()
            await self.adopt(target, bulb)
        self.moving = None
        self.save()
        self.out(f"{names} on {NAMES[target]}.")

    def release_order(self, bulbs: list[Bulb]) -> list[Bulb]:
        """Last joined first. A bulb often joins through one that joined before it, and a Leave sent after that
        parent has gone doesn't arrive: the lab saw ZHA's Leave miss the later bulb on most back-to-back removes, with
        route failures for it. A bulb whose join wasn't seen (it rejoined on power-up) goes first."""
        rank = {entity_id: index for index, entity_id in enumerate(self.arrived)}
        return sorted(bulbs, key=lambda bulb: -rank.get(bulb.entity_id, len(self.arrived)))

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
            try:
                await self.ha.z2m_remove_device(hex_ieee(bulb.ieee))
            except TimeoutError:
                # Z2M keeps a device it couldn't send the Leave to: one that rejoined but can't be reached.
                raise RoamError(
                    f"Z2M couldn't remove {bulb.entity_id}: it didn't take the Leave. Switch its lamp off and on, and "
                    "once Z2M has interviewed it again run scripts/rig.py --recover."
                ) from None

        async def gone() -> bool:
            return not await self.joined(network, bulb)

        if not await _until(gone, RELEASE_S):
            raise RoamError(f"{bulb.entity_id} is still on {NAMES[network]} {RELEASE_S} s after its removal")

    async def join(self, network: str, bulbs: list[Bulb], origins: dict[str, str | None] | None = None) -> None:
        """Open `network` for the bulbs and wait until all are in; ZHA and Z2M close once they are, or on a timeout."""

        self.arrived = []

        async def all_in() -> bool:
            for bulb in bulbs:
                if bulb.entity_id not in self.arrived and await self.joined(network, bulb):
                    self.arrived.append(bulb.entity_id)
                    self.save()
            return all(bulb.entity_id in self.arrived for bulb in bulbs)

        if network == "zha":
            async with self.ha.zha_joining(JOIN_S):
                arrived = await _until(all_in, JOIN_S)
        elif network == "zigbee2mqtt":
            interviews: dict[str, list[float]] = {}

            async def all_in_z2m() -> bool:
                await self.reinterview(bulbs, interviews)
                return await all_in()

            async with self.z2m_logging():
                await self.ha.z2m_permit_join(JOIN_S)
                try:
                    arrived = await _until(all_in_z2m, JOIN_S)
                finally:
                    await self.ha.z2m_permit_join(0)
        else:
            arrived = await self.hue_join(bulbs, all_in)
        if not arrived:
            await self.missed(network, [bulb for bulb in bulbs if not await self.joined(network, bulb)], origins or {})

    async def reinterview(self, bulbs: list[Bulb], interviews: dict[str, list[float]]) -> None:
        """Ask Z2M to interview again a bulb whose interview failed: it joined, but Z2M couldn't reach it (on 3 Nov,
        `Delivery failed`), and Z2M only tries again when the bulb next announces itself, which may be after the
        window. At most REINTERVIEWS per bulb per join, REINTERVIEW_GAP_S apart; `interviews` holds each bulb's asks'
        times."""
        now = asyncio.get_running_loop().time()
        for bulb in bulbs:
            asked = interviews.setdefault(bulb.entity_id, [])
            if bulb.entity_id in self.arrived or len(asked) >= REINTERVIEWS:
                continue
            if asked and now - asked[-1] < REINTERVIEW_GAP_S:
                continue
            device = await self.ha.z2m_device(hex_ieee(bulb.ieee))
            if device is None or device.get("interview_state") != "FAILED":
                continue
            asked.append(now)
            self.out(f"Z2M's interview of {bulb.entity_id} failed; asking for another ({len(asked)}).")
            await self.ha.z2m_interview(hex_ieee(bulb.ieee))

    @contextlib.asynccontextmanager
    async def z2m_logging(self) -> AsyncIterator[None]:
        """Z2M at JOIN_LOG_LEVEL for a join, so its log shows each bulb's join and interview, then back to its own
        level, which is journaled first. A level that can't be read or set leaves the log as it is: it never stops
        the move."""
        try:
            before = await self.ha.z2m_log_level()
            if before is not None and before not in VERBOSE_LOG_LEVELS:
                self.z2m_log_level = before
                self.save()
                await self.ha.z2m_set_log_level(JOIN_LOG_LEVEL)
        except (TimeoutError, HAError) as err:
            self.out(f"Z2M's log level stays as it is for the join: {err}")
        try:
            yield
        finally:
            await self.restore_z2m_log_level()

    async def restore_z2m_log_level(self) -> None:
        """Put back the log level a join raised, if one is journaled. A failure is printed and stays journaled."""
        if self.z2m_log_level is None:
            return
        try:
            await self.ha.z2m_set_log_level(self.z2m_log_level)
        except (TimeoutError, HAError) as err:
            self.out(f"Z2M's log level is still raised, not {self.z2m_log_level}: {err}. --recover tries again.")
            return
        self.z2m_log_level = None
        self.save()

    async def missed(self, network: str, bulbs: list[Bulb], origins: dict[str, str | None]) -> None:
        """Raise RoamError for bulbs that didn't join `network`. One back on a network (it missed the Leave, or
        rejoined the network it knew) is recorded there, so --recover moves it again."""
        window = {"hue": f"{HUE_SEARCHES} searches", "zigbee2mqtt": f"{JOIN_S} s, open on the coordinator only"}
        window = window.get(network, f"{JOIN_S} s")
        names = ", ".join(bulb.entity_id for bulb in bulbs)
        found = {bulb.entity_id: await self.locate(bulb) for bulb in bulbs}
        self.at.update({entity_id: where for entity_id, where in found.items() if where is not None})
        self.save()
        back = [f"{entity_id} on {NAMES[where]}" for entity_id, where in found.items() if where is not None]
        lost = [bulb.entity_id for bulb in bulbs if found[bulb.entity_id] is None]
        lines = [f"{names} did not join {NAMES[network]} within {window}."]
        if back:
            lines.append(
                f"Still or again on a network: {', '.join(back)} (it missed the Leave, or rejoined the network it "
                "knew); scripts/rig.py --recover moves it again."
            )
        if lost:
            hint = MISSED_ZHA_LEAVE if any(origins.get(entity_id) == "zha" for entity_id in lost) else BLUETOOTH_RESET
            lines.append(f"Not on any Zigbee network: {', '.join(lost)}. {hint}")
        raise RoamError(" ".join(lines))

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
        hue_ids = [ident for domain, ident, *_ in device.get("identifiers", []) if domain == "hue"]
        if hue_ids:
            # The bridge may still have the device under another name; it is stale once the bridge has dropped it,
            # or holds it as this bulb.
            on_bridge = {d["id"] for d in await self.bridge.get("device")}
            mine = await self.bridge.device_id_by_ieee(bulb.ieee)
            return all(ident not in on_bridge or ident == mine for ident in hue_ids)
        return False

    # --- rig-made groups, zones and scenes -------------------------------------------------------------------------

    async def make_groups(self, network: str) -> None:
        """Make each profile group on `network`, where every bulb now is, and rename it to its fixed entity ID; on Hue
        a zone, and the scene in it where the group names one."""
        for group in self.groups:
            if not group.made_on(network):
                continue
            if network == "hue":
                zone_id = await self.make(network, "zone", group.entity_id, lambda g=group: self.make_zone(g))
                if group.scene:
                    await self.make(network, "scene", group.scene, lambda g=group, z=zone_id: self.make_scene(g, z))
            elif network == "zha":
                await self.make(network, "group", group.entity_id, lambda g=group: self.make_zha_group(g))
            else:
                await self.make(network, "group", group.entity_id, lambda g=group: self.make_z2m_group(g))

    async def make(
        self, network: str, kind: str, entity_id: str, create: Callable[[], Awaitable[tuple[str, Finder]]]
    ) -> str:
        """Journal a group or scene, make it with `create` (which returns its native ID and a finder for its HA
        entity's registry entry), and rename that entity to `entity_id`. Returns the native ID."""
        name = rig_name(entity_id)
        if any(entry["entity_id"] == entity_id for entry in await self.ha.entity_registry()):
            raise GroupError(
                f"{entity_id} is already in HA's entity registry, so the rig's {NAMES[network]} {kind} can't take it; "
                "rename or remove that entity"
            )
        if await self.native_id(network, kind, name) is not None:
            where = NAMES[network]
            raise GroupError(f"{where} already has a {kind} named {name}, which no run journaled; remove it there")
        made = {"network": network, "kind": kind, "name": name, "entity_id": entity_id, "renamed": False}
        self.made.append(made)
        self.save()
        native, find = await create()
        found: dict | None = None

        async def shown() -> bool:
            nonlocal found
            found = await find()
            return found is not None

        if not await _until(shown, ENTITY_S):
            raise GroupError(f"HA showed no entity for the rig's {NAMES[network]} {kind} {name} in {ENTITY_S} s")
        assert found is not None
        if found["entity_id"] != entity_id or found.get("disabled_by"):
            await self.ha.rename_entity(found["entity_id"], entity_id, enable=bool(found.get("disabled_by")))
        made["renamed"] = True
        self.save()
        self.out(f"Made {NAMES[network]} {kind} {name} as {entity_id}.")
        return native

    async def make_zone(self, group: RoamGroup) -> tuple[str, Finder]:
        lights = [await self.hue_light(member) for member in group.members]
        body = {
            "metadata": {"name": rig_name(group.entity_id), "archetype": "other"},
            "children": [{"rid": light, "rtype": "light"} for light in lights],
        }
        zone_id = (await self.bridge.post("zone", body))[0]["rid"]
        zone = (await self.bridge.get("zone", zone_id))[0]
        grouped = next((s["rid"] for s in zone.get("services", []) if s.get("rtype") == "grouped_light"), None)
        if grouped is None:
            raise GroupError(f"the Hue bridge made zone {zone_id} with no grouped_light")
        return zone_id, self.entity("hue", "light", grouped)

    async def make_scene(self, group: RoamGroup, zone_id: str) -> tuple[str, Finder]:
        actions = []
        for member in group.members:
            light_id = await self.hue_light(member)
            light = (await self.bridge.get("light", light_id))[0]
            action: dict = {"on": {"on": True}, "dimming": {"brightness": SCENE_BRIGHTNESS}}
            if "color_temperature" in light:
                action["color_temperature"] = {"mirek": SCENE_MIREK}
            actions.append({"target": {"rid": light_id, "rtype": "light"}, "action": action})
        body = {
            "metadata": {"name": rig_name(group.scene)},
            "group": {"rid": zone_id, "rtype": "zone"},
            "actions": actions,
        }
        scene_id = (await self.bridge.post("scene", body))[0]["rid"]
        return scene_id, self.entity("hue", "scene", scene_id)

    async def make_zha_group(self, group: RoamGroup) -> tuple[str, Finder]:
        """A ZHA group of each member's light endpoint, read from its light's unique_id ("{ieee}-{endpoint}")."""
        registry = {entry["entity_id"]: entry for entry in await self.ha.entity_registry()}
        members = []
        for member in group.members:
            parts = (registry.get(member, {}).get("unique_id") or "").split("-")
            if len(parts) < 2 or not parts[1].isdigit():
                raise GroupError(f"{member} has no ZHA light endpoint in its unique_id, so it can't join a ZHA group")
            members.append((colon_ieee(parts[0]), int(parts[1])))
        group_id = await self.ha.zha_group_add(rig_name(group.entity_id), tuple(members))
        return str(group_id), self.entity("zha", "light", ZHA_GROUP_UNIQUE_ID.format(group_id))

    async def make_z2m_group(self, group: RoamGroup) -> tuple[str, Finder]:
        name = rig_name(group.entity_id)
        by_id = {bulb.entity_id: bulb for bulb in self.bulbs}
        try:
            await self.ha.z2m_group_add(name, tuple(hex_ieee(by_id[member].ieee) for member in group.members))
        except ValueError as err:
            raise GroupError(str(err)) from None
        made = await self.ha.z2m_group(name)
        if made is None:
            raise GroupError(f"Z2M lists no group {name} after making it")
        identifier = ["mqtt", Z2M_GROUP_IDENTIFIER.format(made["id"])]

        async def find() -> dict | None:
            """The light on the group's HA device, which appears with it."""
            devices = await self.ha.command({"type": "config/device_registry/list"})
            ids = {d["id"] for d in devices if identifier in map(list, d.get("identifiers", []))}
            lights = [e for e in await self.ha.entity_registry() if e["entity_id"].startswith("light.")]
            return next((e for e in lights if e.get("device_id") in ids), None)

        return str(made["id"]), find

    def entity(self, platform: str, domain: str, unique_id: str) -> Finder:
        """A finder for the registry entry with this platform, domain and unique_id."""

        async def find() -> dict | None:
            return next(
                (
                    entry
                    for entry in await self.ha.entity_registry()
                    if entry.get("platform") == platform
                    and entry["entity_id"].startswith(f"{domain}.")
                    and entry.get("unique_id") == unique_id
                ),
                None,
            )

        return find

    async def hue_light(self, entity_id: str) -> str:
        bulb = next(bulb for bulb in self.bulbs if bulb.entity_id == entity_id)
        if (device_id := await self.bridge.device_id_by_ieee(bulb.ieee)) is None:
            raise GroupError(f"{entity_id} is not on the Hue bridge, so it can't join a zone")
        return _light_of((await self.bridge.get("device", device_id))[0])

    async def native_id(self, network: str, kind: str, name: str) -> str | None:
        """The ID of the rig-made group, zone or scene called `name` on `network`, or None."""
        if network == "hue":
            found = await self.bridge.get(kind)
            return next((item["id"] for item in found if item.get("metadata", {}).get("name") == name), None)
        if network == "zha":
            return next((str(g["group_id"]) for g in await self.ha.zha_groups() if g.get("name") == name), None)
        group = await self.ha.z2m_group(name)
        return None if group is None else str(group["id"])

    async def remove_groups(self) -> None:
        """Remove every rig-made group and scene, newest first (a scene before its zone). One that can't be removed
        is printed and stays in the journal, for --recover to try again."""
        for made in reversed(list(self.made)):
            try:
                await self.unmake(made)
            except (BridgeError, HAError, RoamError, TimeoutError) as err:
                network = NAMES[made["network"]]
                self.out(f"Could not remove {network} {made['kind']} {made['name']}: {err}. --recover tries again.")
                continue
            self.made.remove(made)
            self.save()

    async def unmake(self, made: dict) -> None:
        network, kind, name = made["network"], made["kind"], made["name"]
        if (native := await self.native_id(network, kind, name)) is not None:
            if network == "hue":
                await self.bridge.delete(kind, native)
            elif network == "zha":
                await self.ha.zha_group_remove(int(native))
            else:
                await self.ha.z2m_group_remove(name)
            self.out(f"Removed {NAMES[network]} {kind} {name}.")
        if made["renamed"]:
            await self.drop_entity(made["entity_id"], PLATFORMS[network])

    async def drop_entity(self, entity_id: str, platform: str) -> None:
        """Wait for HA to drop a removed group's entity; if it keeps it, remove it, so the next visit can take its
        ID. An entity of another platform under that ID isn't the rig's, and is left alone."""

        async def gone() -> bool:
            entry = next((e for e in await self.ha.entity_registry() if e["entity_id"] == entity_id), None)
            return entry is None or entry.get("platform") != platform

        if not await _until(gone, GONE_S):
            await self.ha.remove_entity(entity_id)
            self.out(f"Removed {entity_id}, which HA kept after its group went.")

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
                "zones": [zone["id"] for zone in zones if _has_child(zone, light_id) and not _rig_made(zone)],
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


def _rig_made(resource: dict) -> bool:
    return resource.get("metadata", {}).get("name", "").startswith(RIG_PREFIX)


def _has_child(group: dict, rid: str) -> bool:
    return any(child.get("rid") == rid for child in group.get("children", []))
