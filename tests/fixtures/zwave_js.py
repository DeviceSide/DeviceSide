"""Fabricate Z-Wave JS light entities the way the core zwave_js integration registers them, with a mocked client.

zwave_js_server is not installed in the test environment. This module stands in for the parts the adapter reads at
runtime:

    hass.config_entries.async_loaded_entries("zwave_js")[0]
        .runtime_data.client.driver.controller.nodes[node_id] -> ZwaveNode
            .manufacturer_id, .product_type, .product_id
            .endpoints[index] -> ZwaveEndpoint
                .command_classes: (CommandClassInfo(id, version), ...)
                .async_invoke_cc_api(command_class, method_name, *args) -> the CC's result (a class method awaiting a
                    mock, which a test gives a `side_effect` and reads the calls of)

The identities are arbitrary: the Z-Wave JS node's manufacturer, product type and product ID, which classes.py reads.
"""

import sys
from collections.abc import Iterable
from enum import IntEnum
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

_ZWAVE_JS_DOMAIN = "zwave_js"
HOME_ID = 3245146787
NODE_ID = 5
# An arbitrary vendor, product type and product ID: the `other` class. Inovelli's LZW42 is below.
VENDOR, PRODUCT_TYPE, PRODUCT_ID = 0x0099, 0x0004, 0x0002
LZW42 = (0x031E, 0x0005, 0x0001)
MULTILEVEL_SWITCH = 38


class CommandClass(IntEnum):
    """zwave_js_server.const.CommandClass: the members the tests use, with the CC IDs the Z-Wave specification gives."""

    BASIC = 32
    SWITCH_BINARY = 37
    SWITCH_MULTILEVEL = MULTILEVEL_SWITCH
    SWITCH_COLOR = 51


class ZwaveEndpoint:
    """Stands in for zwave_js_server's Endpoint: `async_invoke_cc_api` is a class method (the wire boundary
    tests/integrations/zwave_js/wire.py wraps) that awaits the test's mock, so a test sets `side_effect` and reads the
    calls there."""

    def __init__(self, index: int, command_classes: Iterable[tuple[int, int]], invoke: AsyncMock) -> None:
        self.index = index
        self.command_classes = tuple(SimpleNamespace(id=cc, version=version) for cc, version in command_classes)
        self.invoke_mock = invoke

    async def async_invoke_cc_api(self, command_class: CommandClass, method_name: str, *args: object) -> object:
        return await self.invoke_mock(command_class, method_name, *args)


def multilevel_get(level: object, **more: object) -> AsyncMock:
    """An invoke mock answering Multilevel Switch Get as Z-Wave JS does, `{currentValue, ...}`; `more` adds a V4
    Report's targetValue and duration."""
    return AsyncMock(return_value={"currentValue": level, **more})


def zwave_device(
    hass: HomeAssistant,
    endpoints: dict[int, Iterable[tuple[int, int]]] | None = None,
    identity: tuple[int, int, int] = (VENDOR, PRODUCT_TYPE, PRODUCT_ID),
    level: object = 50,
) -> tuple[MockConfigEntry, AsyncMock, SimpleNamespace]:
    """A loaded Z-Wave JS config entry holding one node. `endpoints` maps an endpoint index to its (command class ID,
    version) pairs: the root endpoint, 0, with Multilevel Switch V4 unless given. Every endpoint's
    async_invoke_cc_api sends through one mock, which answers a Get with `level`.

    Returns (entry, the invoke mock, the node)."""
    invoke = multilevel_get(level)
    endpoints = {0: [(MULTILEVEL_SWITCH, 4)]} if endpoints is None else endpoints
    node = SimpleNamespace(
        node_id=NODE_ID,
        manufacturer_id=identity[0],
        product_type=identity[1],
        product_id=identity[2],
        endpoints={index: ZwaveEndpoint(index, ccs, invoke) for index, ccs in endpoints.items()},
    )
    controller = SimpleNamespace(home_id=HOME_ID, nodes={NODE_ID: node})
    client = SimpleNamespace(driver=SimpleNamespace(controller=controller))

    entry = MockConfigEntry(domain=_ZWAVE_JS_DOMAIN, unique_id=str(HOME_ID))
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    entry.runtime_data = SimpleNamespace(client=client)
    return entry, invoke, node


def add_zwave_light(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    entity_id: str,
    endpoint: int = 0,
    node_id: int = NODE_ID,
    state: str = "on",
    attributes: dict | None = None,
    unique_id: str | None = None,
) -> str:
    """Register a Z-Wave JS light with the unique_id core gives one on a Multilevel Switch, {home_id}.{node}-38-
    {endpoint}-currentValue (helpers.get_unique_id over the primary value's ID). Pass unique_id to register another."""
    domain, object_id = entity_id.split(".")
    unique_id = unique_id or f"{HOME_ID}.{node_id}-{MULTILEVEL_SWITCH}-{endpoint}-currentValue"
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(_ZWAVE_JS_DOMAIN, f"{HOME_ID}-{node_id}")}
    )
    er.async_get(hass).async_get_or_create(
        domain,
        _ZWAVE_JS_DOMAIN,
        unique_id,
        suggested_object_id=object_id,
        config_entry=entry,
        device_id=device.id,
    )
    hass.states.async_set(entity_id, state, attributes or {})
    return entity_id


@pytest.fixture(autouse=True)
def mock_zwave_js_server(monkeypatch):
    """Inject a minimal zwave_js_server.const into sys.modules, so the lazy `from zwave_js_server.const import
    CommandClass` in addressing.multilevel_switch_cc resolves to the fake enum."""
    const = SimpleNamespace(CommandClass=CommandClass)
    monkeypatch.setitem(sys.modules, "zwave_js_server", SimpleNamespace(const=const))
    monkeypatch.setitem(sys.modules, "zwave_js_server.const", const)
    return const
