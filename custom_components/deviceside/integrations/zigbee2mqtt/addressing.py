"""Extract the Z2M device or group address, and its instance's base topic, from the HA registries.

A target's base topic is its bridge's: Z2M links every device and group to its bridge (`via_device`) and puts the base
topic in each bridge entity's unique_id (docs/integrations/zigbee2mqtt/research/2026-11-24-base-topics.md). No base
topic is assumed here, so a target whose device has no such bridge is not addressable. That is what lets any base topic,
and several instances on one broker, work: a guessed default would reach nothing silently. Why and what was probed:
docs/integrations/zigbee2mqtt/internals.md#addressing.
"""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Literal, NamedTuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from ...core.errors import Reason
from ...core.models import Target

_LOGGER = logging.getLogger(__name__)

IDENTIFIER_PREFIX = "zigbee2mqtt_"  # of the identifier Z2M registers each device and group under
# A group's address is <encoded base topic>_<group ID>; a device's is its IEEE, which starts with 0x.
_GROUP_ADDRESS = re.compile(r"^(\d+)_(\d+)$")
_IEEE_ADDRESS = re.compile(r"^0x[0-9a-fA-F]+$")
# The bridge's device identifier, `zigbee2mqtt_bridge_<coordinator IEEE>`.
_BRIDGE_IDENTIFIER = re.compile(r"zigbee2mqtt_bridge_(0x[0-9a-fA-F]+)")
# A bridge entity's unique_id, `bridge_<coordinator IEEE>_<object_id>_<base topic>`, the base topic verbatim (spaces and
# `/` included). The object_ids are Z2M's fixed eight; some are disabled by default, so any one counts.
_BRIDGE_ENTITY = re.compile(r"bridge_(0x[0-9a-fA-F]+)_(.+)")
_BRIDGE_OBJECT_IDS = (
    "connection_state",
    "restart_required",
    "restart",
    "log_level",
    "version",
    "coordinator_version",
    "network_map",
    "permit_join",
)


class Address(NamedTuple):
    """Where a target's Z2M options and commands live: its instance's base topic, the kind of entity, and its ID there
    (an IEEE for a device, the group ID for a group)."""

    base: str
    kind: Literal["device", "group"]
    z2m_id: str


def encode_base_topic(base: str) -> str:
    """Z2M's encoding of the base topic in a group's identifier: each character's code point, joined with no separator
    (getEncodedBaseTopic in lib/extension/homeassistant.ts)."""
    return "".join(str(ord(c)) for c in base)


def _bridge_base(hass: HomeAssistant, bridge: dr.DeviceEntry) -> str | None:
    """The base topic in a Z2M bridge device's entities' unique_ids, disabled ones included; None for a device that
    isn't a Z2M bridge or has no bridge entity of its own coordinator."""
    ieee = next(
        (m[1] for kind, ident in bridge.identifiers if kind == "mqtt" and (m := _BRIDGE_IDENTIFIER.fullmatch(ident))),
        None,
    )
    if ieee is None:
        return None
    # An object_id may end in what a base topic can start with (`restart` and `required_x`), so each entity allows every
    # base its unique_id splits into; the bridge's base is the one all of them allow, and none if that isn't one.
    allowed: set[str] | None = None
    for entry in er.async_entries_for_device(er.async_get(hass), bridge.id, include_disabled_entities=True):
        if entry.platform != "mqtt" or not (m := _BRIDGE_ENTITY.fullmatch(entry.unique_id)) or m[1] != ieee:
            continue
        bases = {m[2][len(o) + 1 :] for o in _BRIDGE_OBJECT_IDS if m[2].startswith(f"{o}_") and len(m[2]) > len(o) + 1}
        allowed = bases if allowed is None else allowed & bases
    if allowed is None:
        return None
    if len(allowed) != 1:
        # The first report of "every light of my second Zigbee2MQTT was refused" holds why: a stale bridge entity left
        # by a base topic rename makes them disagree.
        _LOGGER.debug(
            "A Zigbee2MQTT bridge's entities don't name one base topic (%s), so its devices and groups aren't "
            "addressable until the stale ones are removed",
            "they name different ones" if not allowed else "each could be one of several",
        )
        return None
    return next(iter(allowed))


def bridge_bases(hass: HomeAssistant) -> dict[str, str]:
    """Each Z2M bridge device's id and its instance's base topic, for the bridges with a known bridge entity."""
    return {
        device.id: base for device in dr.async_get(hass).devices if (base := _bridge_base(hass, device)) is not None
    }


def _is_bridge_entity(entry: er.RegistryEntry) -> bool:
    return entry.platform == "mqtt" and _BRIDGE_ENTITY.fullmatch(entry.unique_id) is not None


def follow_bases(
    hass: HomeAssistant, entry: ConfigEntry, start: Callable[[str], Awaitable[Callable[[], None]]], name: str
) -> Callable[[], None]:
    """Run `start(base)` for each base topic in bridge_bases, now and whenever a bridge entity is created, changed or
    removed, and call the stop it returns once that base goes; the returned callable stops everything.

    Each start runs as the entry's background task (eagerly, so a start that never suspends is done before this
    returns). A base that goes while its start runs cancels it, so `start` must undo what it did on CancelledError.
    HA's mqtt.async_subscribe never suspends today, so no start does either; the cancel path keeps a start correct if
    one ever does. A start that raises is started again only once its base goes and comes back, or the entry
    reloads; `start` should recover instead (the bridge cache warns and returns a no-op stop).
    """
    return _Follower(hass, entry, start, name).stop_all


class _Follower:
    """follow_bases' state: what runs and what is starting, by base topic."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        start: Callable[[str], Awaitable[Callable[[], None]]],
        name: str,
    ) -> None:
        self.hass, self.entry, self.start, self.name = hass, entry, start, name
        self.entities = er.async_get(hass)
        self.stops: dict[str, Callable[[], None]] = {}
        self.starting: dict[str, asyncio.Task[None]] = {}
        # The bridge entities at the last sync: a removed one is gone from the registry, so its id alone shows it was.
        self.tracked: set[str] = set()
        self.stop_listening = hass.bus.async_listen(
            er.EVENT_ENTITY_REGISTRY_UPDATED, self.updated, event_filter=self.bridge_changed
        )
        self.sync()

    async def run(self, base: str) -> None:
        me = asyncio.current_task()
        try:
            stop = await self.start(base)
        finally:
            # A base that went while this ran popped and cancelled it; one that came back since started another.
            if self.starting.get(base) is me:
                del self.starting[base]
        self.stops[base] = stop

    @callback
    def sync(self) -> None:
        self.tracked = {e.entity_id for e in self.entities.entities.values() if _is_bridge_entity(e)}
        wanted = set(bridge_bases(self.hass).values())
        for base in [b for b in self.starting if b not in wanted]:
            self.starting.pop(base).cancel()
        for base in [b for b in self.stops if b not in wanted]:
            self.stops.pop(base)()
        for base in sorted(wanted - self.stops.keys() - self.starting.keys()):
            task = self.entry.async_create_background_task(self.hass, self.run(base), f"z2m {self.name}")
            if not task.done():
                self.starting[base] = task

    @callback
    def bridge_changed(self, data: er.EventEntityRegistryUpdatedData) -> bool:
        if data["entity_id"] in self.tracked or data.get("old_entity_id") in self.tracked:
            return True
        return (registered := self.entities.async_get(data["entity_id"])) is not None and _is_bridge_entity(registered)

    @callback
    def updated(self, _event: Event[er.EventEntityRegistryUpdatedData]) -> None:
        self.sync()

    @callback
    def stop_all(self) -> None:
        self.stop_listening()
        for task in self.starting.values():
            task.cancel()
        self.starting.clear()
        for stop in self.stops.values():
            stop()
        self.stops.clear()


def device_base(hass: HomeAssistant, device: dr.DeviceEntry) -> str | None:
    """The base topic of the bridge the device links to (`via_device`)."""
    if device.via_device_id is None or (bridge := dr.async_get(hass).async_get(device.via_device_id)) is None:
        return None
    return _bridge_base(hass, bridge)


def base_topic(hass: HomeAssistant, target: Target) -> str | None:
    """The base topic of the target's Zigbee2MQTT instance, from its device's bridge; None when it has none known."""
    return None if target.device is None else device_base(hass, target.device)


def known_base(hass: HomeAssistant, target: Target) -> str:
    """base_topic of a target an action has accepted (supports() refuses one with none); LookupError otherwise."""
    if (base := base_topic(hass, target)) is None:
        raise LookupError(f"{target.entity_id} has no known Zigbee2MQTT base topic")
    return base


def device_identifier(address: str) -> tuple[str, str]:
    """The device-registry identifier Z2M registers the device or group at this address under."""
    return ("mqtt", f"{IDENTIFIER_PREFIX}{address}")


def z2m_device(hass: HomeAssistant, group: Target, address: str) -> dr.DeviceEntry | None:
    """The device Z2M registered at this address, under the MQTT entry that owns the group; None when HA has none.

    A device's identifier is unique within a config entry only (since HA 2026.10), and Z2M announces a group and its
    members through the same broker, so the group's entry is the one to look in.
    """
    if (entry_id := group.entry.config_entry_id) is None:
        return None
    return dr.async_get(hass).async_get_device_by_identifier(device_identifier(address), entry_id)


def entity_name(hass: HomeAssistant, address: Address) -> str:
    """The light entity HA has for a Z2M device (by IEEE) or group (by ID), for a log line, which never names the
    IEEE, group ID, friendly name or topic; "a Zigbee2MQTT <kind> with no light" when HA has none."""
    identified = address.z2m_id if address.kind == "device" else f"{encode_base_topic(address.base)}_{address.z2m_id}"
    entities = er.async_get(hass)
    for device in dr.async_get(hass).async_get_devices(identifiers={device_identifier(identified)}):
        for entry in er.async_entries_for_device(entities, device.id):
            if entry.domain == Platform.LIGHT:
                return entry.entity_id
    return f"a Zigbee2MQTT {address.kind} with no light"


def z2m_address(device: dr.DeviceEntry) -> str | None:
    """The address after "zigbee2mqtt_" in the device identifier, or None.

    Z2M registers devices with identifier ("mqtt", "zigbee2mqtt_<ieee>") and groups with
    ("mqtt", "zigbee2mqtt_<encoded base topic>_<group ID>"). Anything else with the prefix (the bridge's own
    device, say) is not addressable and gives None.
    """
    for itype, ident in device.identifiers:
        if itype == "mqtt" and ident.startswith(IDENTIFIER_PREFIX):
            addr = ident[len(IDENTIFIER_PREFIX) :]
            if _IEEE_ADDRESS.match(addr) or _GROUP_ADDRESS.match(addr):
                return addr
    return None


def is_z2m_group(hass: HomeAssistant, target: Target) -> bool:
    """True for a Z2M group entity, whatever its base topic."""
    if target.device is None or (addr := z2m_address(target.device)) is None:
        return False
    return _GROUP_ADDRESS.match(addr) is not None


def options_address(hass: HomeAssistant, target: Target) -> Address | None:
    """Where the target's Z2M options and commands live, or None when it cannot be addressed: its device has no known
    bridge, or it is a group whose encoded base topic isn't its bridge's (a group of the other instance). Asks Z2M
    nothing."""
    if target.device is None or (addr := z2m_address(target.device)) is None:
        return None
    if (base := base_topic(hass, target)) is None:
        return None
    if group := _GROUP_ADDRESS.match(addr):
        encoded_base, group_id = group.groups()
        return Address(base, "group", group_id) if encoded_base == encode_base_topic(base) else None
    return Address(base, "device", addr)


def group_address(hass: HomeAssistant, target: Target) -> Address | None:
    """options_address of a group entity; None for anything else."""
    return address if (address := options_address(hass, target)) is not None and address.kind == "group" else None


def topic(hass: HomeAssistant, target: Target, suffix: str) -> str | None:
    """MQTT topic <base>/<address>/<suffix> for this Z2M entity, or None when it cannot be addressed.

    The suffix is "set" for a command and "get" for a read. A device is addressed by IEEE and a group by ID, under the
    base topic of the target's bridge (`options_address`).
    """
    if (address := options_address(hass, target)) is None:
        return None
    return f"{address.base}/{address.z2m_id}/{suffix}"


def state_unique_id(address: str, domain: str, base: str) -> str:
    """The unique_id Z2M's discovery gives a device's unsuffixed state entity in the domain: `<ieee>_<domain>_<base
    topic>`, from a `switch`/`light` expose with no endpoint (`${ID}_${object_id}_${base_topic}`, object_id the
    domain; lib/extension/homeassistant.ts)."""
    return f"{address}_{domain}_{base}"


def not_addressable(hass: HomeAssistant, target: Target, *, reads_state: bool = False) -> str | None:
    """The unsupported reason when no set topic reaches the target, or when a device target isn't its device's
    unsuffixed state entity (`state_unique_id`), else None; every Z2M adapter's supports() checks it. With
    reads_state, a device also needs a state topic, which an action reading its state back relies on.

    DeviceSide's set and get topics name the device alone, with the unsuffixed `state` key (internals.md,
    Addressing), so a call reaches exactly the entity Z2M defines by that key. Any other entity in the domain is
    refused: a gang (`light_l2`: the call would switch the default endpoint), and a config switch beside a plug (a
    child lock or a presence sensor's indicator: the call would switch the device itself). A target whose device has
    no known bridge is refused too: its base topic, so its topic, is unknown."""
    if target.device is not None and z2m_address(target.device) is not None and base_topic(hass, target) is None:
        # The first report of "my Zigbee2MQTT light was refused" holds why.
        _LOGGER.debug(
            "%s: its device has no Zigbee2MQTT bridge with a known bridge entity, so its base topic is unknown",
            target.entity_id,
        )
        return Reason.NOT_ADDRESSABLE
    if (address := options_address(hass, target)) is None or (
        reads_state and not target.is_group and state_topic(hass, target) is None
    ):
        return Reason.NOT_ADDRESSABLE
    if not target.is_group and target.entry.unique_id != state_unique_id(address.z2m_id, target.domain, address.base):
        # The first report of "my plug (or two-gang's light) was refused" holds why.
        _LOGGER.debug(
            "%s: it isn't its device's unsuffixed %s entity, so a call on its device topic wouldn't reach it",
            target.entity_id,
            target.domain,
        )
        return Reason.NOT_ADDRESSABLE
    return None


def state_entity(hass: HomeAssistant, device: dr.DeviceEntry, domain: str) -> er.RegistryEntry | None:
    """The device's unsuffixed state entity in the domain (`state_unique_id`), whether or not it is disabled; None
    when it has none, or its bridge is unknown."""
    if (address := z2m_address(device)) is None or (base := device_base(hass, device)) is None:
        return None
    wanted = state_unique_id(address, domain, base)
    return next(
        (
            e
            for e in er.async_entries_for_device(er.async_get(hass), device.id, include_disabled_entities=True)
            if e.domain == domain and e.platform == "mqtt" and e.unique_id == wanted
        ),
        None,
    )


def state_topic(hass: HomeAssistant, target: Target) -> str | None:
    """MQTT topic <base>/<friendly name> on which Z2M publishes this entity's state, or None.

    Z2M names the HA device after its friendly name (a user's rename is name_by_user, which this ignores).
    Addressable like topic(), under the same base topic.
    """
    if (address := options_address(hass, target)) is None or not target.device.name:
        return None
    return f"{address.base}/{target.device.name}"


def bridge_topic(base: str, suffix: str) -> str:
    """Z2M's bridge topic <base>/bridge/<suffix> of the instance on this base topic."""
    return f"{base}/bridge/{suffix}"
