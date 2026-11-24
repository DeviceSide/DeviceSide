"""Zigbee2MQTT addressing and detection: which device identifiers are addressable, and the edges no call reaches."""

import logging
from dataclasses import replace
from types import SimpleNamespace

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.deviceside.integrations.zigbee2mqtt.addressing import (
    Address,
    base_topic,
    bridge_bases,
    bridge_topic,
    entity_name,
    is_z2m_group,
    not_addressable,
    options_address,
    state_topic,
    topic,
    z2m_address,
)
from custom_components.deviceside.integrations.zigbee2mqtt.detect import detect

from .conftest import target as registry_target
from ...fixtures.zigbee2mqtt import IEEE, add_z2m_bridge, add_z2m_entity, add_z2m_group, z2m_entry


@pytest.mark.parametrize(
    ("identifier", "address"),
    [
        ("zigbee2mqtt_0x00124b0012345678", "0x00124b0012345678"),
        ("zigbee2mqtt_1234567_7", "1234567_7"),
        ("zigbee2mqtt_bridge_0x00124b0012345678", None),
        ("zigbee2mqtt_bridge", None),
    ],
)
def test_only_a_device_or_a_group_has_an_address(identifier, address):
    device = SimpleNamespace(identifiers={("mqtt", identifier)})

    assert z2m_address(device) == address  # type: ignore[arg-type]


def target(identifier: str | None) -> SimpleNamespace:
    """A target whose device carries this MQTT identifier, or one with no device."""
    return SimpleNamespace(device=None if identifier is None else SimpleNamespace(identifiers={("mqtt", identifier)}))


def group_target(hass, entity_id: str):
    """The registered group entity as the dispatcher resolves it."""
    return replace(registry_target(hass, entity_id), is_group=True)


GROUP = "zigbee2mqtt_1221051039810110150109113116116_7"  # the literal Z2M writes, so this checks Z2M's scheme


@pytest.mark.parametrize(
    ("check", "expected"),
    [
        pytest.param(lambda: is_z2m_group(None, target(GROUP)), True, id="group_on_the_default_base_topic"),
        pytest.param(lambda: is_z2m_group(None, target("zigbee2mqtt_12250109_7")), True, id="group_on_another"),
        pytest.param(lambda: is_z2m_group(None, target(f"zigbee2mqtt_{IEEE}")), False, id="a_device_is_no_group"),
        pytest.param(lambda: is_z2m_group(None, target(None)), False, id="no_device_is_no_group"),
        pytest.param(lambda: detect(None, None, None), False, id="detect_without_a_device"),
        pytest.param(lambda: bridge_topic("z2m", "info"), "z2m/bridge/info", id="bridge_topic"),
        pytest.param(lambda: bridge_topic("home/z2m", "info"), "home/z2m/bridge/info", id="bridge_topic_with_a_slash"),
    ],
)
def test_the_edges_no_call_reaches(check, expected):
    assert check() == expected


# The base topic comes from the target's bridge (docs/integrations/zigbee2mqtt/research/2026-11-24-base-topics.md).

SPACED = "    zigbee2mqtt"  # #575's base topic: four leading spaces, which HA's UI hides
ENCODED_SPACED = "323232321221051039810110150109113116116"


@pytest.mark.parametrize("base", ["zigbee2mqtt", SPACED, "home/z2m", "home/upstairs z2m"])
async def test_a_device_and_group_are_addressed_on_their_bridge_base_topic(hass, base):
    entry = z2m_entry(hass)
    add_z2m_entity(hass, entry, "light.lamp", name="lamp", base_topic=base, bridge_base=base)
    add_z2m_group(hass, entry, "light.room", group_id=7, name="room", base_topic=base, bridge_base=base)
    lamp, room = registry_target(hass, "light.lamp"), group_target(hass, "light.room")

    assert base_topic(hass, lamp) == base
    assert topic(hass, lamp, "set") == f"{base}/{IEEE}/set"
    assert topic(hass, room, "get") == f"{base}/7/get"
    assert state_topic(hass, lamp) == f"{base}/lamp"
    assert state_topic(hass, room) == f"{base}/room"
    assert options_address(hass, lamp) == Address(base, "device", IEEE)
    assert options_address(hass, room) == Address(base, "group", "7")
    assert not_addressable(hass, lamp) is None
    assert not_addressable(hass, room) is None
    assert not_addressable(hass, lamp, reads_state=True) is None


async def test_a_spaced_base_topic_is_kept_verbatim(hass):
    entry = z2m_entry(hass)
    add_z2m_group(hass, entry, "light.room", group_id=7, base_topic=SPACED, bridge_base=SPACED)

    group = group_target(hass, "light.room")
    assert z2m_address(group.device) == f"{ENCODED_SPACED}_7"
    assert topic(hass, group, "set") == "    zigbee2mqtt/7/set"


async def test_two_bridges_give_each_device_its_own_base_topic(hass):
    entry = z2m_entry(hass)
    add_z2m_entity(hass, entry, "light.down", ieee="0x01", name="down")
    add_z2m_entity(hass, entry, "light.up", ieee="0x02", name="up", base_topic="z2m_up", bridge_base="z2m_up")
    # Both instances have a group 7.
    add_z2m_group(hass, entry, "light.down_room", group_id=7, name="room")
    add_z2m_group(hass, entry, "light.up_room", group_id=7, name="room", base_topic="z2m_up", bridge_base="z2m_up")

    assert sorted(bridge_bases(hass).values()) == ["z2m_up", "zigbee2mqtt"]
    got = {
        entity_id: (topic(hass, t, "set"), state_topic(hass, t), options_address(hass, t))
        for entity_id in ("light.down", "light.up", "light.down_room", "light.up_room")
        for t in [group_target(hass, entity_id) if "room" in entity_id else registry_target(hass, entity_id)]
    }
    assert got == {
        "light.down": ("zigbee2mqtt/0x01/set", "zigbee2mqtt/down", Address("zigbee2mqtt", "device", "0x01")),
        "light.up": ("z2m_up/0x02/set", "z2m_up/up", Address("z2m_up", "device", "0x02")),
        "light.down_room": ("zigbee2mqtt/7/set", "zigbee2mqtt/room", Address("zigbee2mqtt", "group", "7")),
        "light.up_room": ("z2m_up/7/set", "z2m_up/room", Address("z2m_up", "group", "7")),
    }
    assert entity_name(hass, Address("zigbee2mqtt", "group", "7")) == "light.down_room"
    assert entity_name(hass, Address("z2m_up", "group", "7")) == "light.up_room"
    assert entity_name(hass, Address("z2m_up", "group", "8")) == "a Zigbee2MQTT group with no light"


async def test_a_disabled_bridge_entity_still_gives_the_base_topic(hass):
    entry = z2m_entry(hass)
    bridge = add_z2m_bridge(hass, entry, "home/z2m")
    entities = er.async_get(hass)
    for entity in er.async_entries_for_device(entities, bridge.id):
        entities.async_remove(entity.entity_id)
    ieee = next(i for _, i in bridge.identifiers).removeprefix("zigbee2mqtt_bridge_")
    entities.async_get_or_create(
        "binary_sensor",
        "mqtt",
        f"bridge_{ieee}_coordinator_version_home/z2m",
        config_entry=entry,
        device_id=bridge.id,
        disabled_by=er.RegistryEntryDisabler.INTEGRATION,
    )

    assert bridge_bases(hass)[bridge.id] == "home/z2m"


async def test_a_bridge_entity_of_another_coordinator_is_not_the_bridge_s(hass):
    entry = z2m_entry(hass)
    bridge = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("mqtt", "zigbee2mqtt_bridge_0x01")}
    )
    er.async_get(hass).async_get_or_create(
        "sensor", "mqtt", "bridge_0x02_version_z2m", config_entry=entry, device_id=bridge.id
    )

    assert bridge.id not in bridge_bases(hass)


async def test_a_device_with_no_bridge_is_refused_and_says_so(hass, caplog):
    caplog.set_level(logging.DEBUG, logger="custom_components.deviceside")
    entry = z2m_entry(hass)
    add_z2m_entity(hass, entry, "light.lamp", name="lamp", bridge_base=None)
    add_z2m_group(hass, entry, "light.room", group_id=7, name="room", bridge_base=None)
    lamp, room = registry_target(hass, "light.lamp"), registry_target(hass, "light.room")

    assert base_topic(hass, lamp) is None
    assert topic(hass, lamp, "set") is None and state_topic(hass, lamp) is None
    assert options_address(hass, lamp) is None
    assert not_addressable(hass, lamp) == "not_addressable"
    assert not_addressable(hass, room) == "not_addressable"
    assert (
        "light.lamp: its device has no Zigbee2MQTT bridge with a known bridge entity, so its base topic is unknown"
        in caplog.text
    )


async def test_a_device_linked_to_a_bridge_with_no_bridge_entity_is_refused(hass):
    entry = z2m_entry(hass)
    bridge = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("mqtt", "zigbee2mqtt_bridge_0x01")}
    )
    add_z2m_entity(hass, entry, "light.lamp", name="lamp", bridge_base=None)
    lamp = registry_target(hass, "light.lamp")
    dr.async_get(hass).async_update_device(lamp.device.id, via_device_id=bridge.id)

    assert not_addressable(hass, registry_target(hass, "light.lamp")) == "not_addressable"


async def test_a_group_whose_encoded_base_is_the_other_instances_is_refused(hass):
    entry = z2m_entry(hass)
    add_z2m_bridge(hass, entry, "z2m_up")
    # A group Z2M registered on base z2m_up, linked to the bridge of base zigbee2mqtt.
    add_z2m_group(hass, entry, "light.room", group_id=7, base_topic="z2m_up", bridge_base="zigbee2mqtt")
    room = group_target(hass, "light.room")

    assert base_topic(hass, room) == "zigbee2mqtt"
    assert topic(hass, room, "set") is None
    assert options_address(hass, room) is None
    assert not_addressable(hass, room) == "not_addressable"


def _bridge_with(hass, entity_ids: list[str]):
    """A bridge device holding bridge entities with these object_id and base topic tails."""
    entry = z2m_entry(hass)
    bridge = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("mqtt", "zigbee2mqtt_bridge_0x01")}
    )
    for tail in entity_ids:
        er.async_get(hass).async_get_or_create(
            "sensor", "mqtt", f"bridge_0x01_{tail}", config_entry=entry, device_id=bridge.id
        )
    return bridge


async def test_a_base_that_starts_like_an_object_id_is_settled_by_a_second_entity(hass):
    # `restart` on base "required_x" reads as `restart_required` on base "x" too; `connection_state` settles it.
    bridge = _bridge_with(hass, ["restart_required_x", "connection_state_required_x"])

    assert bridge_bases(hass)[bridge.id] == "required_x"


async def test_a_base_the_bridge_s_entities_leave_ambiguous_is_refused(hass, caplog):
    caplog.set_level(logging.DEBUG, logger="custom_components.deviceside")
    bridge = _bridge_with(hass, ["restart_required_x"])

    assert bridge.id not in bridge_bases(hass)
    assert (
        "A Zigbee2MQTT bridge's entities don't name one base topic (each could be one of several), so its devices and "
        "groups aren't addressable until the stale ones are removed" in caplog.text
    )


async def test_bridge_entities_left_on_two_bases_by_a_rename_are_refused_and_say_so(hass, caplog):
    caplog.set_level(logging.DEBUG, logger="custom_components.deviceside")
    bridge = _bridge_with(hass, ["version_zigbee2mqtt", "connection_state_z2m_up"])

    assert bridge.id not in bridge_bases(hass)
    assert "A Zigbee2MQTT bridge's entities don't name one base topic (they name different ones)" in caplog.text
    ours = [r.getMessage() for r in caplog.records if r.name.startswith("custom_components.deviceside")]
    assert not any("0x01" in line or "z2m_up" in line for line in ours)
