"""ZHA expand_group: a group entity's members, from the zha gateway's group and the entity registry."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.integrations.zha.addressing import group_id
from custom_components.deviceside.integrations.zha.groups import covers, expand_group, light_members

from ...fixtures.zha import add_zha_entity, zha_entry, zha_group

A, B, C = "00:00:00:00:00:00:00:0a", "00:00:00:00:00:00:00:0b", "00:00:00:00:00:00:00:0c"


def _group_target(hass, entity_id="light.zha_group"):
    return resolve(hass, get_runtime(hass).registry, entity_id)


async def test_members_in_the_group_entitys_domain(hass, setup_production, zha_groups):
    entry = zha_entry(hass)
    add_zha_entity(hass, entry, "light.zha_group", unique_id="light_zha_group_0x0002")
    add_zha_entity(hass, entry, "light.b", ieee=B)
    add_zha_entity(hass, entry, "light.a", ieee=A)
    add_zha_entity(hass, entry, "switch.plug", ieee=C, unique_id=f"{C}-1")
    zha_groups[2] = zha_group((B, 11), (A, 11), (C, 1), ("00:00:00:00:00:00:00:0d", 11))

    members = expand_group(hass, _group_target(hass))

    # The plug is in the switch group, and the last member has no entity: both are left out.
    assert [member.entity_id for member in members] == ["light.a", "light.b"]
    assert {member.via_group for member in members} == {"light.zha_group"}


async def test_a_multi_endpoint_member_is_its_endpoints_own_light(hass, setup_production, zha_groups):
    """ZHA names each light by its endpoint ("{ieee}-{endpoint}") and a Zigbee group holds endpoints, so a two-gang
    device's member is the gang the group holds, addressable on its own (unlike Zigbee2MQTT's, Target.addressable)."""
    entry = zha_entry(hass)
    add_zha_entity(hass, entry, "light.zha_group", unique_id="light_zha_group_0x0002")
    add_zha_entity(hass, entry, "light.gang_1", ieee=A, unique_id=f"{A}-1")
    add_zha_entity(hass, entry, "light.gang_2", ieee=A, unique_id=f"{A}-2")
    zha_groups[2] = zha_group((A, 2))

    members = expand_group(hass, _group_target(hass))

    assert [(m.entity_id, m.addressable) for m in members] == [("light.gang_2", True)]


async def test_a_member_that_cannot_resolve_is_dropped(hass, setup_production, zha_groups):
    entry = zha_entry(hass)
    add_zha_entity(hass, entry, "light.zha_group", unique_id="light_zha_group_0x0002")
    add_zha_entity(hass, entry, "light.b", ieee=B)
    unloaded = MockConfigEntry(domain="zha")
    unloaded.add_to_hass(hass)
    add_zha_entity(hass, unloaded, "light.a", ieee=A)  # resolve refuses it: integration_not_loaded
    zha_groups[2] = zha_group((A, 11), (B, 11))

    assert [member.entity_id for member in expand_group(hass, _group_target(hass))] == ["light.b"]


async def test_a_group_zha_no_longer_knows_is_empty(hass, setup_production, zha_groups):
    add_zha_entity(hass, zha_entry(hass), "light.zha_group", unique_id="light_zha_group_0x0002")

    assert expand_group(hass, _group_target(hass)) == []


async def test_light_members_are_every_light_the_group_holds(hass, setup_production, zha_groups):
    """Whether a call targets them or not: a groupcast reaches them all."""
    entry = zha_entry(hass)
    add_zha_entity(hass, entry, "light.a", ieee=A)
    add_zha_entity(hass, entry, "switch.plug", ieee=C, unique_id=f"{C}-1")
    zha_groups[2] = zha_group((A, 11), (C, 1), (B, 11))

    assert light_members(hass, 2) == {"light.a"}
    assert light_members(hass, 3) == frozenset()


@pytest.mark.parametrize(
    ("unique_id", "expected"),
    [
        ("light_zha_group_0x0002", 2),
        ("switch_zha_group_0xfff0", 0xFFF0),
        ("light_zha_group_0xzz", None),
        ("00:17:88:01:02:03:04:05-11", None),
    ],
)
def test_group_id(unique_id, expected):
    assert group_id(unique_id) == expected


async def test_covers_a_group_zha_no_longer_knows_is_false(hass, setup_production, zha_groups):
    add_zha_entity(hass, zha_entry(hass), "light.a", ieee=A)

    assert not covers(hass, 2, [resolve(hass, get_runtime(hass).registry, "light.a")])


async def test_covers_with_no_gateway_is_false(hass, setup_production, monkeypatch):
    """The gateway went away after planning: the members get their own commands, which fail one by one."""
    add_zha_entity(hass, zha_entry(hass), "light.a", ieee=A)

    monkeypatch.delitem(hass.data, "zha")

    assert not covers(hass, 2, [resolve(hass, get_runtime(hass).registry, "light.a")])
