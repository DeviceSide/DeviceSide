"""A Zigbee2MQTT group of switches is a switch entity (internals.md, Addressing), and falls back to its members."""

import pytest
from homeassistant.exceptions import HomeAssistantError

from .conftest import DEVICES, GROUPS, call, commands, light
from .families.sonoff.test_inching import relay
from .families.tuya.test_countdown import LAB, listed
from .families.tuya.test_inching import switch as whd02
from ...conftest import allow_labs
from ...fixtures.zigbee2mqtt import add_z2m_entity, add_z2m_group, z2m_entry

SONOFF_ARM = (
    "zigbee2mqtt/0x02/set",
    {"inching_control_set": {"inching_control": "ENABLE", "inching_time": 5.0, "inching_mode": "OFF"}},
)
WHD02_ARM = ("zigbee2mqtt/0x01/set", {"inching_control_set": {"inching_control_1": "ENABLE", "inching_time_1": 5}})
SONOFF_CLEAR = (
    "zigbee2mqtt/0x02/set",
    {"inching_control_set": {"inching_control": "DISABLE", "inching_time": 0.5, "inching_mode": "OFF"}},
)
WHD02_CLEAR = ("zigbee2mqtt/0x01/set", {"inching_control_set": {"inching_control_1": "DISABLE", "inching_time_1": 1}})


def switch_group(hass, broker, entity_id: str = "switch.room", members: tuple[str, ...] = ("0x01", "0x02")) -> str:
    """Z2M group 7 as Z2M discovers it for its switch members: the entity `entity_id` (switch.room, or light.room for a
    group's light entity), reaching every member by one groupcast."""
    add_z2m_group(hass, hass.config_entries.async_entries("mqtt")[0], entity_id, group_id=7, name="room")
    hass.states.async_set(entity_id, "off", {})
    broker.retained[GROUPS] = [{"id": 7, "members": [{"ieee_address": ieee} for ieee in members]}]
    return entity_id


def inching_switches(hass, broker) -> None:
    """A WHD02 (0x01) and a Sonoff ZBMINIR2 (0x02), each a switch."""
    whd02(hass, broker, entity_id="switch.whd", ieee="0x01")
    relay(hass, broker, entity_id="switch.sonoff", ieee="0x02")


def plugs(hass, broker) -> None:
    """Two lab TS011F plugs (0x01, 0x02), each a switch."""
    entry = z2m_entry(hass)
    for entity_id, ieee in (("switch.plug_a", "0x01"), ("switch.plug_b", "0x02")):
        add_z2m_entity(
            hass,
            entry,
            entity_id,
            ieee=ieee,
            state="off",
            manufacturer="Tuya",
            model_id="TS011F_plug_1",
            name=entity_id[7:],
        )
        broker.retained.setdefault(DEVICES, []).append(listed(ieee, LAB))


async def test_a_switch_group_falls_back_to_its_members_for_set_auto_off(hass, setup_production, broker):
    inching_switches(hass, broker)
    entity_id = switch_group(hass, broker)
    allow_labs(hass)
    await call(hass, "set_auto_off", {"entity_id": entity_id, "duration": 5})
    assert sorted(commands(broker), key=str) == sorted([SONOFF_ARM, WHD02_ARM], key=str)


async def test_a_switch_group_falls_back_to_its_members_for_clear_auto_off(hass, setup_production, broker):
    inching_switches(hass, broker)
    entity_id = switch_group(hass, broker)
    allow_labs(hass)
    await call(hass, "clear_auto_off", {"entity_id": entity_id})
    assert sorted(commands(broker), key=str) == sorted([SONOFF_CLEAR, WHD02_CLEAR], key=str)


@pytest.mark.parametrize("labs", [True, False])
async def test_a_switch_group_of_countdown_plugs_gets_a_countdown_per_plug(hass, setup_production, broker, labs):
    plugs(hass, broker)
    entity_id = switch_group(hass, broker)
    allow_labs(hass, labs)
    await call(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5})
    assert sorted(commands(broker)) == [
        ("zigbee2mqtt/0x01/set", {"state": "ON", "countdown": 5}),
        ("zigbee2mqtt/0x02/set", {"state": "ON", "countdown": 5}),
    ]


async def test_a_mixed_groups_light_entity_sends_no_auto_off_to_its_switches(hass, setup_production, broker, caplog):
    inching_switches(hass, broker)
    light(hass, broker, "light.bulb", "0x03")
    entity_id = switch_group(hass, broker, "light.room", ("0x01", "0x02", "0x03"))
    allow_labs(hass)
    with pytest.raises(HomeAssistantError):
        await call(hass, "set_auto_off", {"entity_id": entity_id, "duration": 5})
    assert commands(broker) == []
    assert "(not_addressable)" in caplog.text


async def test_a_mixed_groups_switch_entity_arms_its_switches_and_skips_the_bulb(
    hass, setup_production, broker, caplog
):
    inching_switches(hass, broker)
    light(hass, broker, "light.bulb", "0x03")
    entity_id = switch_group(hass, broker, "switch.room", ("0x01", "0x02", "0x03"))
    allow_labs(hass)
    await call(hass, "set_auto_off", {"entity_id": entity_id, "duration": 5})
    assert sorted(commands(broker), key=str) == sorted([SONOFF_ARM, WHD02_ARM], key=str)
    assert "a member device of switch.room (not_built)" in caplog.text
