"""Fabricate ZHA entities and groups the way the zha library registers them, and the zha gateway and zigpy clusters
behind them, which zcl's helpers reach as on a real network (the zha library and zigpy aren't dev dependencies).

The fake is zigpy's surface as zcl uses it, so the helpers run unchanged: `Gateway` is zha's (`get_device`,
`get_group`), a device's `async_get_cluster` raises KeyError for a cluster it lacks, and a `Cluster` answers
`read_attributes` as zigpy's `(success, failure)` and `request` with a Default Response. A test sets what the device
answers, never a helper's return value: a cluster's `values` (or, for every device at once, the gateway's `answers`),
its `error` for a read or request that fails to deliver, and `before`, run as each one arrives, for a slow or changing
device. `Cluster.read_attributes` and `Cluster.request` are ZHA's wire boundaries (tests/integrations/zha/wire.py)."""

import dataclasses
import enum
import inspect
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.deviceside.integrations.zha.zcl import COLOR_CLUSTER, LEVEL_CLUSTER, ON_OFF_CLUSTER

IEEE = "00:17:88:01:02:03:04:05"
# A Hue bulb's Zigbee strings (research/2026-11-14-lab-probe.md, §1), which place a device in the `hue` class.
HUE = ("Signify Netherlands B.V.", "LTA009")
# Where the fake gateway lives in hass.data, holding the zigpy devices add_zha_entity fabricates.
_GATEWAY = "test_zha_gateway"


class Status(enum.IntEnum):
    """zigpy.zcl.foundation.Status, the codes the fake answers."""

    SUCCESS = 0x00
    UNSUPPORTED_ATTRIBUTE = 0x86


@dataclasses.dataclass(eq=False)
class DefaultResponse:
    """zigpy's reply to a cluster command: the ZCL Default Response, the command it answers and its status."""

    command_id: int
    status: Status


@dataclasses.dataclass(eq=False)
class Cluster:
    """A zigpy cluster (zigpy.zcl.Cluster) as zcl's helpers use it. Its fields are its address, which a transcript
    records it by; the rest is the device's state and what it was sent:

    - `values`: the attributes the device answers, or None to answer the gateway's `answers` for its cluster id;
    - `cache`: zigpy's attribute cache, which `get` reads and each answered read fills;
    - `status`: what a request's Default Response answers;
    - `error`: raised by each read or request instead of an answer, as a delivery failure or a timeout;
    - `before`: called with the cluster (and awaited, if it returns an awaitable) as each read or request arrives.
    """

    ieee: str
    endpoint_id: int
    cluster_id: int
    gateway: dataclasses.InitVar[Gateway]

    def __post_init__(self, gateway: Gateway) -> None:
        self._gateway = gateway
        self.values: dict[int, Any] | None = None
        self.cache: dict[int, Any] = {}
        self.status = Status.SUCCESS
        self.error: BaseException | None = None
        self.before: Callable[[Cluster], Any] | None = None

    def get(self, key: int, default: Any = None) -> Any:
        return self.cache.get(key, default)

    async def read_attributes(
        self,
        attributes: list[int],
        allow_cache: bool = False,
        only_cache: bool = False,
        manufacturer: int | None = None,
    ) -> tuple[dict[int, Any], dict[int, Status]]:
        """As zigpy's: cached values first where allowed, then one read of the rest, each attribute the device lacks
        in the failure dict."""
        self._gateway.reads.append((self.ieee, self.cluster_id, list(attributes)))
        success: dict[int, Any] = {}
        failure: dict[int, Status] = {}
        wanted = []
        for attribute in attributes:
            if (allow_cache or only_cache) and attribute in self.cache:
                success[attribute] = self.cache[attribute]
            else:
                wanted.append(attribute)
        if not wanted or only_cache:
            return success, failure
        await self._arrive()
        values = self._gateway.answers.get(self.cluster_id, {}) if self.values is None else self.values
        for attribute in wanted:
            if attribute in values:
                success[attribute] = self.cache[attribute] = values[attribute]
            else:
                failure[attribute] = Status.UNSUPPORTED_ATTRIBUTE
        return success, failure

    async def request(
        self,
        general: bool,
        command_id: int,
        schema: type,
        *args: Any,
        manufacturer: int | None = None,
        expect_reply: bool = True,
        tsn: int | None = None,
    ) -> DefaultResponse:
        self._gateway.requests.append((self.ieee, self.cluster_id, general, command_id, args, manufacturer))
        await self._arrive()
        return DefaultResponse(command_id, self.status)

    async def _arrive(self) -> None:
        if self.before is not None and inspect.isawaitable(pending := self.before(self)):
            await pending
        if self.error is not None:
            raise self.error


class StandardOnOff(Cluster):
    """An On/Off cluster as zigpy defines it: `command` from zigpy, as a quirk keeping the standard frame leaves it."""

    command = None


StandardOnOff.__module__ = "zigpy.zcl"


def quirk_on_off(module: str) -> type:
    """An On/Off cluster whose quirk, in `module`, defines its own `command`, as a Tuya datapoint quirk does."""
    return type("QuirkOnOff", (StandardOnOff,), {"command": None, "__module__": module})


class ZhaDevice:
    """The zha library's Device: the zigpy device behind it, and its clusters by endpoint."""

    def __init__(self, device: SimpleNamespace) -> None:
        self.device = device

    def async_get_cluster(self, endpoint_id: int, cluster_id: int, cluster_type: str = "in") -> Cluster:
        return getattr(self.device.endpoints[endpoint_id], f"{cluster_type}_clusters")[cluster_id]


class Gateway:
    """zha's gateway, as zcl reaches it through hass.data: the zigpy devices add_zha_entity fabricates (`devices`, by
    IEEE) and the zha groups (`groups`, by ID). `answers` holds what every device's clusters answer, by cluster id,
    where a cluster has no `values` of its own; `reads` and `requests` what the clusters were sent, in order, as
    (ieee, cluster id, attributes) and (ieee, cluster id, general, command id, args, manufacturer)."""

    def __init__(self) -> None:
        self.devices: dict[str, SimpleNamespace] = {}
        self.groups: dict[int, SimpleNamespace] = {}
        self.answers: dict[int, dict[int, Any]] = {}
        self.reads: list[tuple[str, int, list[int]]] = []
        self.requests: list[tuple] = []

    def get_device(self, ieee: str) -> ZhaDevice | None:
        return None if (device := self.devices.get(ieee)) is None else ZhaDevice(device)

    def get_group(self, group_id: int) -> SimpleNamespace | None:
        return self.groups.get(group_id)


class Struct:
    """zigpy.types.Struct: a request's schema, its fields by annotation."""


class SerializableBytes(bytes):
    """zigpy.types.SerializableBytes: bytes sent as they are."""


# zigpy.types as zcl imports it; EUI64.convert passes the IEEE through, as the fake gateway keys devices by it.
ZIGPY_TYPES = SimpleNamespace(EUI64=SimpleNamespace(convert=str), Struct=Struct, SerializableBytes=SerializableBytes)


def gateway_of(hass: HomeAssistant) -> Gateway:
    """The test's fake zha gateway, which add_zha_entity fills."""
    return hass.data.setdefault(_GATEWAY, Gateway())


def zigpy_devices(hass: HomeAssistant) -> dict:
    """The zigpy devices add_zha_entity fabricated, by IEEE."""
    return gateway_of(hass).devices


def zigpy_device(
    hass: HomeAssistant,
    ieee: str,
    strings: tuple[str | None, str | None],
    endpoint: int,
    on_off: type = StandardOnOff,
    *,
    light: bool = True,
) -> SimpleNamespace:
    """A zigpy device: its raw manufacturer and model, and on `endpoint` an On/Off cluster of type `on_off`, and a
    light's Level and Color clusters."""
    gateway = gateway_of(hass)
    clusters: dict[int, Cluster] = {ON_OFF_CLUSTER: on_off(ieee, endpoint, ON_OFF_CLUSTER, gateway)}
    if light:
        clusters |= {cid: Cluster(ieee, endpoint, cid, gateway) for cid in (LEVEL_CLUSTER, COLOR_CLUSTER)}
    manufacturer, model = strings
    return SimpleNamespace(
        manufacturer=manufacturer,
        model=model,
        endpoints={endpoint: SimpleNamespace(in_clusters=clusters, out_clusters={})},
    )


def cluster(hass: HomeAssistant, cluster_id: int, ieee: str = IEEE) -> Cluster:
    """The fabricated device's in cluster `cluster_id`, on its one endpoint."""
    (endpoint,) = zigpy_devices(hass)[ieee].endpoints.values()
    return endpoint.in_clusters[cluster_id]


def add_cluster(hass: HomeAssistant, cluster_id: int, ieee: str = IEEE) -> Cluster:
    """A new in cluster `cluster_id` on the fabricated device's one endpoint, as Hue's own on a Hue bulb."""
    ((endpoint_id, endpoint),) = zigpy_devices(hass)[ieee].endpoints.items()
    added = endpoint.in_clusters[cluster_id] = Cluster(ieee, endpoint_id, cluster_id, gateway_of(hass))
    return added


def zha_entry(hass: HomeAssistant) -> MockConfigEntry:
    """The one loaded ZHA config entry every ZHA device shares."""
    entry = MockConfigEntry(domain="zha")
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    return entry


def add_zha_entity(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    entity_id: str,
    ieee: str = IEEE,
    unique_id: str | None = None,
    state: str = "off",
    attributes: dict | None = None,
    strings: tuple[str | None, str | None] = HUE,
    on_off: type = StandardOnOff,
) -> str:
    """Register a ZHA entity; a light's unique_id is "{ieee}-{endpoint_id}" unless one is given. Its zigpy device has
    the Zigbee manufacturer and model `strings`, a Hue bulb's unless given, which the registry device shows too, and an
    On/Off cluster of type `on_off` on the entity's endpoint."""
    domain, object_id = entity_id.split(".")
    manufacturer, model = strings
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("zha", ieee)}, manufacturer=manufacturer, model=model
    )
    tail = (unique_id or f"{ieee}-11").removeprefix(f"{ieee}-")
    endpoint = int(tail) if tail.isdigit() else 11
    zigpy_devices(hass)[ieee] = zigpy_device(hass, ieee, strings, endpoint, on_off, light=domain == Platform.LIGHT)
    er.async_get(hass).async_get_or_create(
        domain,
        "zha",
        unique_id or f"{ieee}-11",
        suggested_object_id=object_id,
        config_entry=entry,
        device_id=device.id,
    )
    hass.states.async_set(entity_id, state, attributes)
    return entity_id


def zha_group(*members: tuple[str, int], coordinator: str | None = None, unknown: int = 0) -> SimpleNamespace:
    """A zha library Group: members as (ieee, endpoint_id), the way GroupMember exposes them, plus the `coordinator`
    (an IEEE) when it is one, and `unknown` members zigpy holds that ZHA doesn't, which Group.members leaves out."""
    listed = [(ieee, endpoint, False) for ieee, endpoint in members]
    if coordinator is not None:
        listed.append((coordinator, 1, True))
    zha_members = [
        SimpleNamespace(device=SimpleNamespace(ieee=ieee, is_coordinator=is_coordinator), endpoint_id=endpoint)
        for ieee, endpoint, is_coordinator in listed
    ]
    zigpy_members = {(ieee, endpoint): None for ieee, endpoint, _ in listed}
    zigpy_members |= {(f"ff:ff:ff:ff:ff:ff:ff:{n:02x}", 1): None for n in range(unknown)}
    return SimpleNamespace(members=zha_members, zigpy_group=SimpleNamespace(members=zigpy_members))
