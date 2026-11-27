"""Z-Wave addressing: the node and endpoint in a unique_id, the client through the config entry, and the refusals."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.deviceside.core.models import Target
from custom_components.deviceside.integrations.zwave_js import addressing

from ...conftest import call, refusal
from ...fixtures.zwave_js import HOME_ID, MULTILEVEL_SWITCH, NODE_ID, add_zwave_light, zwave_device

pytestmark = pytest.mark.usefixtures("setup_production")


@pytest.mark.parametrize(
    ("unique_id", "expected"),
    [
        (f"{HOME_ID}.5-38-0-currentValue", (5, 0)),
        (f"{HOME_ID}.12-38-3-currentValue", (12, 3)),
        (f"{HOME_ID}.7-51-0-currentColor", (7, 0)),  # any primary value: a color light's, a binary switch's
        (f"{HOME_ID}.7-112-0-3-extra", (7, 0)),  # a property key trails
        ("5-38-0-currentValue", None),  # no home ID: not a Z-Wave JS unique_id
        (f"{HOME_ID}.five-38-0-currentValue", None),
        (f"{HOME_ID}.5-38", None),
        ("0000000000000001-0000000000000002-MatterNodeDevice-1-MatterLight-6-0", None),
        ("", None),
    ],
)
def test_node_and_endpoint(unique_id, expected):
    assert addressing.node_and_endpoint(unique_id) == expected


def _target(hass, entity_id: str) -> Target:
    entry = er.async_get(hass).async_get(entity_id)
    return Target(
        entity_id=entity_id,
        domain="light",
        integration="zwave_js",
        entry=entry,
        device=None,
        config_entry=hass.config_entries.async_get_entry(entry.config_entry_id),
        state=hass.states.get(entity_id),
    )


async def test_a_light_is_addressed_through_the_entry(hass):
    entry, _, node = zwave_device(hass)
    add_zwave_light(hass, entry, "light.dimmer")
    target = _target(hass, "light.dimmer")

    assert addressing.zwave_client(hass, entry.entry_id) is entry.runtime_data.client
    assert addressing.zwave_client(hass) is entry.runtime_data.client
    assert addressing.node_for(hass, target) is node
    assert addressing.endpoint_for(hass, target) is node.endpoints[0]
    assert addressing.unsupported_reason(hass, target) is None
    assert addressing.light_reason(hass, target) is None
    assert addressing.multilevel_switch_version(node.endpoints[0]) == 4


async def test_a_light_on_another_endpoint_is_that_endpoints(hass):
    entry, _, node = zwave_device(hass, endpoints={0: [], 2: [(MULTILEVEL_SWITCH, 3)]})
    add_zwave_light(hass, entry, "light.second", endpoint=2)
    target = _target(hass, "light.second")

    assert addressing.endpoint_for(hass, target) is node.endpoints[2]
    assert addressing.multilevel_switch_version(node.endpoints[2]) == 3
    assert addressing.light_reason(hass, target) is None


@pytest.mark.parametrize(
    "unique_id",
    [f"{HOME_ID}.99-38-0-currentValue", "not-a-zwave-id", f"{HOME_ID}.{NODE_ID}-38-4-currentValue"],
    ids=["unknown_node", "unparsable", "unknown_endpoint"],
)
async def test_a_light_the_client_does_not_hold_is_not_addressable(hass, unique_id):
    entry, _, _ = zwave_device(hass)
    add_zwave_light(hass, entry, "light.dimmer", unique_id=unique_id)
    target = _target(hass, "light.dimmer")

    assert addressing.unsupported_reason(hass, target) == "not_addressable"
    assert addressing.light_reason(hass, target) == "not_addressable"


async def test_a_client_with_no_driver_is_not_addressable(hass):
    """Before the client connects, its driver is None."""
    entry, _, _ = zwave_device(hass)
    entry.runtime_data.client.driver = None
    add_zwave_light(hass, entry, "light.dimmer")

    assert addressing.node_for(hass, _target(hass, "light.dimmer")) is None
    assert await refusal(hass, "get_attributes", {"entity_id": "light.dimmer"}) == "not_addressable"


async def test_an_entry_with_no_runtime_data_has_no_client(hass):
    entry, _, _ = zwave_device(hass)
    del entry.runtime_data

    assert addressing.zwave_client(hass, entry.entry_id) is None
    assert addressing.zwave_client(hass) is None
    assert addressing.zwave_client(hass, "no-such-entry") is None


async def test_an_endpoint_with_no_multilevel_switch_is_not_dimmable(hass):
    entry, invoke, _ = zwave_device(hass, endpoints={0: [(37, 2)]})  # Binary Switch only
    add_zwave_light(hass, entry, "light.relay", unique_id=f"{HOME_ID}.{NODE_ID}-37-0-currentValue")
    target = _target(hass, "light.relay")

    assert addressing.unsupported_reason(hass, target) is None
    assert addressing.light_reason(hass, target) == "not_dimmable"
    assert await refusal(hass, "get_attributes", {"entity_id": "light.relay"}) == "not_dimmable"
    invoke.assert_not_awaited()


async def test_the_call_goes_to_the_lights_endpoint(hass):
    """Each endpoint has its own mock; the call is made on the one the entity's unique_id names."""
    entry, _, node = zwave_device(hass, endpoints={0: [(MULTILEVEL_SWITCH, 4)], 1: [(MULTILEVEL_SWITCH, 4)]})
    add_zwave_light(hass, entry, "light.one", endpoint=1)
    node.endpoints[0].invoke_mock = AsyncMock(return_value={"currentValue": 10})
    node.endpoints[1].invoke_mock = AsyncMock(return_value={"currentValue": 20})

    response = await call(hass, "get_attributes", {"entity_id": "light.one"})

    assert response["light.one"]["brightness"] == 20.2
    node.endpoints[0].invoke_mock.assert_not_awaited()
    node.endpoints[1].invoke_mock.assert_awaited_once()
