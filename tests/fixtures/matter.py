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
from dataclasses import dataclass, field
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


@pytest.fixture
def mock_chip(monkeypatch):
    """Inject a minimal mock for chip.clusters into sys.modules.

    Allows the lazy `from chip.clusters import Objects as clusters` in addressing.make_on_with_timed_off
    to succeed.  The mock's OnWithTimedOff factory returns a SimpleNamespace so tests can inspect
    the exact onOffControl/onTime/offWaitTime values that the adapter passed.
    """

    mock_objects = SimpleNamespace(OnOff=SimpleNamespace(Commands=SimpleNamespace(OnWithTimedOff=OnWithTimedOff)))
    mock_chip_clusters = SimpleNamespace(Objects=mock_objects)
    mock_chip_pkg = SimpleNamespace(clusters=mock_chip_clusters)

    monkeypatch.setitem(sys.modules, "chip", mock_chip_pkg)
    monkeypatch.setitem(sys.modules, "chip.clusters", mock_chip_clusters)
    # The `from chip.clusters import Objects` form needs .Objects on sys.modules["chip.clusters"].
    return mock_objects
