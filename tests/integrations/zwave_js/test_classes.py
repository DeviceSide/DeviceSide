"""Z-Wave's device classes: the rules on the node and endpoint, the levels, and what each class is served."""

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.deviceside.core.models import Target
from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.zwave_js import INTEGRATION
from custom_components.deviceside.integrations.zwave_js.classes import (
    GET_ATTRIBUTES,
    LZW42,
    OTHER,
    V1,
    capability,
    node_class,
)
from custom_components.deviceside.integrations.zwave_js.get_attributes import ZwaveGetAttributes

from ...conftest import call, refusal
from ...fixtures.zwave_js import HOME_ID, MULTILEVEL_SWITCH, NODE_ID, add_zwave_light, zwave_device
from ...fixtures.zwave_js import LZW42 as LZW42_IDENTITY

pytestmark = pytest.mark.usefixtures("setup_production")


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


@pytest.mark.parametrize(
    ("identity", "version", "expected"),
    [
        ((0x0099, 0x0004, 0x0002), 4, OTHER),  # any vendor
        ((0x0099, 0x0004, 0x0002), 2, OTHER),
        ((0x0099, 0x0004, 0x0002), 1, V1),
        ((0x031E, 0x0004, 0x0001), 4, OTHER),  # Inovelli, another product
        ((0x031E, 0x0005, 0x0002), 4, OTHER),
        ((0x0099, 0x0005, 0x0001), 4, OTHER),  # LZW42's type and ID under another vendor
        (LZW42_IDENTITY, 4, LZW42),
        (LZW42_IDENTITY, 2, LZW42),  # the identity decides before the version
        (LZW42_IDENTITY, 1, LZW42),
        ((None, None, None), 4, OTHER),  # a node that hasn't reported its identity
    ],
)
async def test_node_class(hass, identity, version, expected):
    entry, _, node = zwave_device(hass, endpoints={0: [(MULTILEVEL_SWITCH, version)]}, identity=identity)

    assert node_class(node, node.endpoints[0]) == expected


async def test_capability_is_the_endpoints_class_or_none(hass):
    entry, _, _ = zwave_device(hass, identity=LZW42_IDENTITY)
    add_zwave_light(hass, entry, "light.bulb")
    add_zwave_light(hass, entry, "light.gone", unique_id=f"{HOME_ID}.99-38-0-currentValue")

    assert capability(hass, _target(hass, "light.bulb")) == LZW42
    assert capability(hass, _target(hass, "light.gone")) is None


async def test_every_class_is_a_light_and_other_is_the_default():
    assert INTEGRATION.default_class == OTHER
    assert {name: set(domains) for name, domains in INTEGRATION.classes.items()} == {
        LZW42: {"light"},
        V1: {"light"},
        OTHER: {"light"},
    }


def test_get_attributes_is_documented_on_other_and_lzw42():
    """The read is HA's own refresh_value call to every brand (docs/evidence.md, Levels); V1 is left out until a move
    serves it (core/registry.check_queries)."""
    assert dict(GET_ATTRIBUTES) == {OTHER: Level.DOCUMENTED, LZW42: Level.DOCUMENTED}
    scope = ZwaveGetAttributes.scope
    assert scope.level("light", classes=[OTHER]) == Level.DOCUMENTED
    assert scope.level("light", classes=[LZW42]) == Level.DOCUMENTED
    assert scope.admits(V1, "light") is False


@pytest.mark.parametrize(
    ("identity", "version", "expected"),
    [((0x0099, 0x0004, 0x0002), 4, OTHER), (LZW42_IDENTITY, 4, LZW42)],
)
async def test_documented_classes_read_without_labs(hass, identity, version, expected):
    entry, invoke, _ = zwave_device(hass, endpoints={0: [(MULTILEVEL_SWITCH, version)]}, identity=identity, level=99)
    add_zwave_light(hass, entry, "light.dimmer")

    response = await call(hass, "get_attributes", {"entity_id": "light.dimmer"})

    assert response == {"light.dimmer": {"capability": expected, "brightness": 100.0}}
    invoke.assert_awaited_once()


async def test_a_v1_dimmer_is_not_built(hass):
    entry, invoke, _ = zwave_device(hass, endpoints={0: [(MULTILEVEL_SWITCH, 1)]})
    add_zwave_light(hass, entry, "light.old", unique_id=f"{HOME_ID}.{NODE_ID}-38-0-currentValue")

    assert await refusal(hass, "get_attributes", {"entity_id": "light.old"}) == "not_built"
    invoke.assert_not_awaited()
