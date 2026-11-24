"""Fabricate Matter entities the way the core matter integration registers them, with a mocked client.

matter_server and chip are not installed in the test environment.  This module replaces them with
minimal mocks so the adapter runs and its boundary calls can be inspected.  The mock structure
follows what the adapter reads at runtime:

    hass.config_entries.async_loaded_entries("matter")[0]
        .runtime_data.adapter.matter_client
            .get_node(node_id) -> mock_node
                .node_data.attributes: the endpoint's OnOff FeatureMap ("{endpoint_id}/6/65532") and Basic
                    Information's VendorID and ProductID ("0/40/2", "0/40/4"), a WiZ Smart Plug's unless given
            .send_device_command(node_id, endpoint_id, command) -> None  (a MatterClient method awaiting an AsyncMock)
            .read_attribute(node_id, attribute_path) -> {attribute_path: value}  (likewise; OnOff on, OnTime the
                last command's onTime, else 1)
"""

import sys
from dataclasses import dataclass, field, make_dataclass
from dataclasses import field as dc_field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

_MATTER_DOMAIN = "matter"
# fabric_hex and node_hex are both fixed 16-char hex strings with no hyphens.
FABRIC_HEX = "0000000000000001"
NODE_HEX = "0000000000000002"
NODE_ID = int(NODE_HEX, 16)
# The lab's WiZ Smart Plug (zigbee2mqtt/research/2026-11-14-lab-probe.md): the `wiz_plug` class.
WIZ_VENDOR_ID, WIZ_PRODUCT_ID = 4107, 8979
# The clock every Matter test runs at (tests/integrations/matter/conftest.py): get_attributes puts `ends_at` from it in
# its rows, so the transcripts are the same on every run.
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


class MatterClient:
    """Stands in for python-matter-server's MatterClient, which stays out of the test environment: `send_device_command`
    and `read_attribute` are class methods (the wire boundaries tests/integrations/matter/wire.py wraps) that await
    the test's mocks, so a test sets `side_effect` and reads the calls there. `get_node` is the cache read, a plain
    mock."""

    def __init__(self, send_device_command: AsyncMock, read_attribute: AsyncMock, node: MagicMock) -> None:
        self.send_mock = send_device_command
        self.read_mock = read_attribute
        self.get_node = MagicMock(return_value=node)

    async def send_device_command(self, node_id: int, endpoint_id: int, command: object) -> object:
        return await self.send_mock(node_id=node_id, endpoint_id=endpoint_id, command=command)

    async def read_attribute(self, node_id: int, attribute_path: str) -> dict:
        return await self.read_mock(node_id=node_id, attribute_path=attribute_path)


def make_node_mock(
    endpoint_id: int,
    feature_map: int = 0x0001,
    vendor_id: int | None = WIZ_VENDOR_ID,
    product_id: int | None = WIZ_PRODUCT_ID,
    attributes: dict | None = None,
) -> MagicMock:
    """Return a mock MatterNode whose attribute cache holds one endpoint's OnOff FeatureMap and the node's VendorID
    and ProductID (left out when None), plus `attributes`."""
    node = MagicMock()
    node.node_id = NODE_ID
    ids = {"0/40/2": vendor_id, "0/40/4": product_id}
    node.node_data.attributes = (
        {f"{endpoint_id}/6/65532": feature_map}
        | {path: value for path, value in ids.items() if value is not None}
        | (attributes or {})
    )
    return node


def on_time_reads(on_time: int, on: bool = True) -> AsyncMock:
    """A read_attribute mock that answers like python-matter-server, {attribute_path: value}: OnOff.OnOff (x/6/0)
    reads `on`, any other path `on_time`."""
    return AsyncMock(
        side_effect=lambda node_id, attribute_path: {attribute_path: on_off_or(attribute_path, on, on_time)}
    )


def on_off_or(attribute_path: str, on: bool, value: object) -> object:
    return on if attribute_path.endswith("/6/0") else value


def matter_device(
    hass: HomeAssistant,
    endpoint_id: int = 1,
    feature_map: int = 0x0001,
    **node: object,
) -> tuple[MockConfigEntry, AsyncMock, AsyncMock]:
    """A loaded Matter config entry whose matter_client is a MatterClient sending through the returned mocks; `node`
    goes to make_node_mock.

    Returns (entry, send_device_command mock, read_attribute mock).
    """
    send_cmd = AsyncMock(return_value=None)

    def read(node_id: int, attribute_path: str) -> dict:
        """The timer just sent, running, as OnTime reads straight after the command; 1 before any."""
        on_time = send_cmd.call_args.kwargs["command"].onTime if send_cmd.call_args else 1
        return {attribute_path: on_off_or(attribute_path, True, on_time)}

    read_attr = AsyncMock(side_effect=read)

    node_mock = make_node_mock(endpoint_id, feature_map, **node)

    adapter = SimpleNamespace(matter_client=MatterClient(send_cmd, read_attr, node_mock))
    entry_data = SimpleNamespace(adapter=adapter)

    entry = MockConfigEntry(domain=_MATTER_DOMAIN, unique_id="mock-matter")
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    entry.runtime_data = entry_data
    return entry, send_cmd, read_attr


def add_matter_entity(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    entity_id: str,
    endpoint_id: int = 1,
    state: str = "off",
    attributes: dict | None = None,
    unique_id: str | None = None,
) -> str:
    """Register a Matter light or plug entity with a unique_id that the adapter can parse.

    Unique_id format: {fab_hex16}-{node_hex16}-MatterNodeDevice-{ep}-{key}-6-0, key MatterLight or
    MatterPlug (matches what homeassistant/components/matter/entity.py builds for each). Pass unique_id to
    register one the adapter can't parse.
    """
    domain, object_id = entity_id.split(".")
    key = "MatterPlug" if domain == "switch" else "MatterLight"
    unique_id = unique_id or f"{FABRIC_HEX}-{NODE_HEX}-MatterNodeDevice-{endpoint_id}-{key}-6-0"
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(_MATTER_DOMAIN, f"deviceid_{FABRIC_HEX}-{NODE_HEX}-MatterNodeDevice")},
    )
    er.async_get(hass).async_get_or_create(
        domain,
        _MATTER_DOMAIN,
        unique_id,
        suggested_object_id=object_id,
        config_entry=entry,
        device_id=device.id,
    )
    hass.states.async_set(entity_id, state, attributes or {})
    return entity_id


class LightNode:
    """The attribute table of a Matter light, which commands change as the node would: a MoveTo command sets its
    attributes (what a light does with the ExecuteIfOff override, on or off) and reads answer from the table, so a test
    changes a value, or the answer to one path, to make the light keep something else."""

    def __init__(self, attributes: dict[str, object]) -> None:
        self.attributes = dict(attributes)
        self.refused: set[str] = set()  # paths whose read raises

    def apply(self, endpoint_id: int, command: object) -> None:
        ep = f"{endpoint_id}/"
        match command.command.split(".")[-1]:
            case "MoveToLevel" | "MoveToLevelWithOnOff":
                self.attributes[ep + "8/0"] = command.level
            case "MoveToColorTemperature":
                self.attributes[ep + "768/7"] = command.colorTemperatureMireds
            case "MoveToColor":
                self.attributes[ep + "768/3"] = command.colorX
                self.attributes[ep + "768/4"] = command.colorY
            case "MoveToHueAndSaturation":
                self.attributes[ep + "768/0"] = command.hue
                self.attributes[ep + "768/1"] = command.saturation

    def read(self, node_id: int, attribute_path: str) -> dict:
        if attribute_path in self.refused:
            raise ConnectionError("lost connection")
        return {attribute_path: self.attributes.get(attribute_path)}


def light_device(
    hass: HomeAssistant, attributes: dict[str, object] | None = None, endpoint_id: int = 1, **node: object
) -> tuple[MockConfigEntry, AsyncMock, AsyncMock, LightNode]:
    """A Matter light, class `other` unless `node` says otherwise: Level Control on its endpoint (CurrentLevel 100,
    OnLevel null) and `attributes` over that, answering as a LightNode. Returns matter_device's three, then the node."""
    node.setdefault("vendor_id", 4874)
    node.setdefault("product_id", 80)
    light = LightNode({f"{endpoint_id}/8/0": 100, f"{endpoint_id}/8/17": None} | (attributes or {}))
    entry, send_cmd, read_attr = matter_device(hass, endpoint_id, attributes=light.attributes, **node)
    send_cmd.side_effect = lambda node_id, endpoint_id, command: light.apply(endpoint_id, command)
    read_attr.side_effect = light.read
    return entry, send_cmd, read_attr, light


@dataclass
class OnWithTimedOff:
    """chip's OnOff.Commands.OnWithTimedOff: the command's name, which chip's class carries as its type, and its
    fields, so a transcript shows which command went to the node."""

    onOffControl: int = 0
    onTime: int = 0
    offWaitTime: int = 0
    command: str = field(init=False)
    cluster: ClassVar[str] = "OnOff"

    def __post_init__(self) -> None:
        self.command = f"{self.cluster}.{type(self).__name__}"


def chip_command(cluster: str, name: str, *fields: str) -> type:
    """chip's `<cluster>.Commands.<name>`, as a dataclass of exactly those field names (an unknown one raises, as chip's
    does), recording its qualified name as `command`. Field names are the ones chip's Objects.py gives."""

    def post_init(self) -> None:
        self.command = f"{cluster}.{name}"

    return make_dataclass(
        name,
        [*((field_name, int, 0) for field_name in fields), ("command", str, dc_field(init=False))],
        namespace={"__post_init__": post_init, "cluster": cluster},
    )


# The Level and Color Control commands set_attributes sends. transitionTime, optionsMask and optionsOverride are on
# each, as in chip's Objects.py.
_OPTIONS = ("transitionTime", "optionsMask", "optionsOverride")
LEVEL_COMMANDS = {
    "MoveToLevel": ("level", *_OPTIONS),
    "MoveToLevelWithOnOff": ("level", *_OPTIONS),
}
COLOR_COMMANDS = {
    "MoveToHueAndSaturation": ("hue", "saturation", *_OPTIONS),
    "MoveToColor": ("colorX", "colorY", *_OPTIONS),
    "MoveToColorTemperature": ("colorTemperatureMireds", *_OPTIONS),
}


@pytest.fixture
def mock_chip(monkeypatch):
    """Inject a minimal mock for chip.clusters into sys.modules.

    Allows the lazy `from chip.clusters import Objects as clusters` in addressing.make_on_with_timed_off
    to succeed.  The mock's OnWithTimedOff factory returns a SimpleNamespace so tests can inspect
    the exact onOffControl/onTime/offWaitTime values that the adapter passed.
    """

    def commands(cluster: str, table: dict) -> SimpleNamespace:
        return SimpleNamespace(
            Commands=SimpleNamespace(**{name: chip_command(cluster, name, *fields) for name, fields in table.items()})
        )

    mock_objects = SimpleNamespace(
        OnOff=SimpleNamespace(Commands=SimpleNamespace(OnWithTimedOff=OnWithTimedOff)),
        LevelControl=commands("LevelControl", LEVEL_COMMANDS),
        ColorControl=commands("ColorControl", COLOR_COMMANDS),
    )
    mock_chip_clusters = SimpleNamespace(Objects=mock_objects)
    mock_chip_pkg = SimpleNamespace(clusters=mock_chip_clusters)

    monkeypatch.setitem(sys.modules, "chip", mock_chip_pkg)
    monkeypatch.setitem(sys.modules, "chip.clusters", mock_chip_clusters)
    # The `from chip.clusters import Objects` form needs .Objects on sys.modules["chip.clusters"].
    return mock_objects
