"""Zigbee2MQTT's device classes: when a device is placed, the group members its classes come from, and what each
class's level does to a call. Which device is which class is test_classification.py's; a family's own rules and calls
are tested under families/."""

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr

from custom_components.deviceside.config_flow import _FORMS_BY_STEP, issue_url
from custom_components.deviceside.core.errors import TargetNotSupported
from custom_components.deviceside.core.models import Target
from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.core.scope import Level, OnDomains, Unplaced
from custom_components.deviceside.integrations.zigbee2mqtt import ADAPTERS, INTEGRATION, bridge_cache, classes, members
from custom_components.deviceside.integrations.zigbee2mqtt.families import tuya

from .conftest import DEVICES, PLUG, SENT, SET, TUYA, TUYA_MCU, call, commands, group, interviewed, light
from ...conftest import allow_labs, refusal
from ...conftest import call as call_service
from ...fixtures.zigbee2mqtt import GROUPS, IEEE, add_z2m_bridge, add_z2m_entity, add_z2m_group, z2m_entry

STRINGS = Path(__file__).parents[3] / "custom_components" / "deviceside" / "translations" / "en.json"
IKEA = ("IKEA of Sweden", "TRADFRI bulb E27 WW 806lm")
# Gledopto's GL-SPI-206P: Gledopto's definition, Tuya datapoint firmware (families/__init__.py, the rule order).
GLEDOPTO_TUYA = {"manufacturer": "Gledopto", "model_id": "GL-SPI-206P", "zigbee": (TUYA_MCU, "TS0601")}


def registry_only(hass, manufacturer: str | None, model_id: str | None = None) -> Target:
    """A target with a registry device alone, no config entry or state, and no bridge cache: the registry alone."""
    config = z2m_entry(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config.entry_id,
        identifiers={("mqtt", f"zigbee2mqtt_{IEEE}")},
        manufacturer=manufacturer,
        model_id=model_id,
    )
    entry = er.async_get(hass).async_get_or_create(
        "light", "mqtt", IEEE, device_id=device.id, suggested_object_id="lamp"
    )
    return Target(entry.entity_id, "light", "zigbee2mqtt", entry, device, None, None)


@pytest.mark.parametrize(
    ("manufacturer", "model_id", "expected"),
    [
        ("Philips", "9290018217", "hue"),
        ("IKEA of Sweden", "LED1836G9", "other"),
        ("Tuya", "TS0001_switch_module", "tuya_zcl"),
        ("Sengled", "E11-G13", "sengled"),
    ],
)
def test_on_the_registry_alone_only_a_hue_device_is_placed(hass, manufacturer, model_id, expected):
    """`hue`, which no Zigbee-string rule can override: every other class could still move, so it is Unplaced."""
    found = INTEGRATION.capability(hass, registry_only(hass, manufacturer, model_id))

    assert found == expected
    assert isinstance(found, Unplaced) is (expected != "hue")


async def test_until_bridge_devices_arrives_the_registry_places_the_device(hass, setup_production, broker):
    entity_id = light(hass, broker, manufacturer="Lidl", model_id="HG06337", zigbee=(TUYA, "TS011F"))
    target = resolve(hass, get_runtime(hass).registry, entity_id)
    del broker.retained[DEVICES]

    assert INTEGRATION.capability(hass, target) == "other"


async def test_a_device_bridge_devices_does_not_list_yet_is_placed_by_the_registry(hass, setup_production, broker):
    entity_id = light(hass, broker, manufacturer=PLUG[0], model_id=PLUG[1])
    broker.retained[DEVICES] = [{"ieee_address": "0x09", "manufacturer": TUYA_MCU, "model_id": "TS0601"}]

    assert INTEGRATION.capability(hass, resolve(hass, get_runtime(hass).registry, entity_id)) == "tuya_ts011f"


def test_the_bridge_cache_indexes_bridge_devices_once_per_payload():
    cache = bridge_cache.BridgeCache("zigbee2mqtt")
    cache._payloads["devices"] = (
        '[{"ieee_address": "0x01", "model_id": "TS011F"}, "junk", {"model_id": "x"}, {"ieee_address": 5}, '
        '{"ieee_address": null}]'
    )

    first = cache.device("0x01")
    assert first == {"ieee_address": "0x01", "model_id": "TS011F"}
    assert cache.device("0x01") is first
    assert cache.device("0x02") is None
    assert set(cache._devices[1]) == {"0x01"}  # only a string address is indexed
    # A new payload re-indexes: a device it adds is found, one it drops is gone.
    cache._payloads["devices"] = '[{"ieee_address": "0x02", "model_id": "TS0601"}]'
    assert cache.device("0x02") == {"ieee_address": "0x02", "model_id": "TS0601"}
    assert cache.device("0x01") is None
    cache._payloads["devices"] = '{"not": "a list"}'
    assert cache.device("0x02") is None


def test_a_target_with_no_device_has_no_class(hass):
    target = registry_only(hass, "Philips")
    assert (
        INTEGRATION.capability(hass, Target(target.entity_id, "light", "zigbee2mqtt", target.entry, None, None, None))
        is None
    )


def _scopes() -> dict:
    return {adapter.action: adapter.scope for adapter in ADAPTERS}


ALL = {
    "raise_brightness",
    "lower_brightness",
    "raise_hue",
    "lower_hue",
    "raise_saturation",
    "lower_saturation",
    "stop",
    "get_attributes",
    "set_attributes",
    "turn_on_for",
    "turn_off_for",
    "set_auto_off",
    "clear_auto_off",
}
AUTO_OFF = {"set_auto_off", "clear_auto_off"}
CERTIFIED = {"raise_brightness", "lower_brightness", "stop"}


@pytest.mark.parametrize(
    ("capability", "harmed", "not_built", "no_method"),
    [
        # Not built yet on turn_on_for, with an entry: today's call would leave them on (Decision 70). Not built on
        # every other action either, as no pass or research admits Tuya's firmware (docs/evidence.md, In Labs).
        # Another brand's lights and plugs: no pass, and a plug that never turns off would take on_time. Raw reads and
        # writes serve its lights alone (test_another_brands_reads_and_writes_are_in_labs_on_lights_alone).
        ("other", {"turn_on_for"}, ALL - CERTIFIED - {"get_attributes", "set_attributes"}, set()),
        # Other brands' standard lights: Documented on `other`'s light actions and the hue and saturation moves, and
        # refused on turn_on_for with `other`'s entry (test_standard_lights.py).
        ("standard_light", {"turn_on_for"}, {"turn_on_for", "turn_off_for"} | AUTO_OFF, set()),
        # Hue's plug, on the switch domain alone; its bulbs keep their own level.
        ("hue", {"turn_on_for"}, {"turn_off_for"} | AUTO_OFF, set()),
        ("tuya_zcl", {"turn_on_for"}, ALL, set()),
        # Tuya's inching: set_auto_off and clear_auto_off serve it in Labs, and it keeps `tuya_zcl`'s refusal on
        # turn_on_for and its place in no other scope.
        ("tuya_inching", {"turn_on_for"}, {"turn_on_for", "turn_off_for", "get_attributes"}, set()),
        # Nor a TS011F off the countdown, so get_attributes doesn't read it.
        ("tuya_ts011f", {"turn_on_for"}, {"turn_on_for", "turn_off_for", "get_attributes"} | AUTO_OFF, set()),
        # Reported failing Tuya's countdown with harm (Decision 41).
        ("tuya_countdown_harmed", {"turn_on_for"}, {"turn_on_for", "turn_off_for", "get_attributes"} | AUTO_OFF, set()),
        # The time left can't be read (probe P6); turn_on_for serves it in Labs, on its kin's pass.
        ("tuya_countdown", set(), {"turn_off_for", "get_attributes"} | AUTO_OFF, {"get_attributes"}),
        # Tuya's datapoint countdown: turn_on_for and turn_off_for serve them in Labs, on research, and no action holds
        # an entry for them.
        ("tuya_datapoint", set(), ALL - {"turn_on_for", "turn_off_for"}, set()),
        ("tuya_datapoint_24h", set(), ALL - {"turn_on_for", "turn_off_for"}, set()),
        ("tuya_datapoint_2h", set(), ALL - {"turn_on_for", "turn_off_for"}, set()),
        ("tuya_mcu", {"turn_on_for"}, ALL, set()),
        ("sengled", set(), ALL, set()),
        ("gledopto", set(), ALL, set()),
        # `other`'s actions for lights, in Labs: Level Control's moves, stop, and raw reads and writes. turn_on_for is
        # refused with its own entry: the bulb ignores on_time (research/aqara/2026-11-25-agl003-probe.md).
        ("aqara", {"turn_on_for"}, ALL - CERTIFIED - {"get_attributes", "set_attributes"}, set()),
        # In Labs on Level Control's moves and, on lights, turn_on_for; its outlets refused there with an entry.
        ("ikea", {"turn_on_for"}, ALL - CERTIFIED - {"turn_on_for"}, set()),
        # Reported to stay on with the timer (Zigbee2MQTT #29158).
        ("ikea_timer_harmed", {"turn_on_for"}, ALL - CERTIFIED, set()),
        # Sonoff's inching: set_auto_off and clear_auto_off serve it in Labs, on research, and it keeps `other`'s level
        # elsewhere, refused on turn_on_for with the same entry.
        ("sonoff_inching", {"turn_on_for"}, ALL - CERTIFIED - AUTO_OFF, set()),
        # The S60 plugs: refused on both auto-off actions, as DISABLE is reported to have no effect on them, and on
        # turn_on_for; a plug has no brightness fades or stop.
        ("sonoff_s60", {"turn_on_for"} | AUTO_OFF, {"turn_on_for", "turn_off_for", "get_attributes"} | AUTO_OFF, set()),
    ],
)
def test_where_each_class_is_refused(capability, harmed, not_built, no_method):
    """The integration's guard on what a family's change can let through: the actions that refuse the class with an
    entry, because the call would harm it or has no known method, and those that leave it out, among the actions a
    domain it can be reaches (the rest never hold it: test_actions_for_lights_alone_never_hold_a_switch_only_class).
    Its level where it is served is its family's (families/<family>/)."""
    scopes = {
        action: scope for action, scope in _scopes().items() if INTEGRATION.classes[capability] & scope.domains.keys()
    }
    assert {action for action, scope in scopes.items() if capability in scope.no_known_method} == no_method
    assert {action for action, scope in scopes.items() if capability in scope.not_built} == harmed
    assert {action for action, scope in scopes.items() if capability not in scope.capabilities} == not_built


SWITCH_ONLY = {
    "tuya_ts011f",
    "tuya_countdown",
    *tuya.VERIFIED_COUNTDOWNS,
    "tuya_countdown_harmed",
    "sonoff_s60",
    "tuya_inching",
}


def test_actions_for_lights_alone_never_hold_a_switch_only_class():
    """A TS011F is a plug, a switch, so an action for lights alone holds it in no axis, and refuses it as not built yet;
    the card leaves it off (scripts/gen_compat.py)."""
    assert {name for name, domains in INTEGRATION.classes.items() if domains == {"switch"}} == SWITCH_ONLY
    lights_alone = {action: scope for action, scope in _scopes().items() if scope.domains.keys() == {"light"}}
    assert lights_alone.keys() == {
        "raise_brightness",
        "lower_brightness",
        "raise_hue",
        "lower_hue",
        "raise_saturation",
        "lower_saturation",
        "stop",
        "set_attributes",
    }
    for scope in lights_alone.values():
        held = scope.capabilities.keys() | scope.no_known_method.keys() | scope.not_built.keys()
        assert not held & SWITCH_ONLY
        assert scope.refusal(["tuya_ts011f"], failure_harms=False) == ("not_built", None)


# Group members, from the bridge cache.


async def test_a_group_lists_its_members_from_the_held_bridge_groups(hass, setup_production, broker):
    entity_id = group(hass, broker, one={}, two={"manufacturer": "IKEA of Sweden"})
    target = resolve(hass, get_runtime(hass).registry, entity_id)

    members = INTEGRATION.expand_group(hass, target)

    assert [member.entity_id for member in members] == ["light.one", "light.two"]
    assert {member.via_group for member in members} == {entity_id}
    assert [INTEGRATION.capability(hass, member) for member in members] == ["hue", "ikea"]


async def test_membership_is_unknowable_without_bridge_groups(hass, setup_production, broker):
    entity_id = group(hass, broker, one={}, two={})
    del broker.retained[GROUPS]

    assert INTEGRATION.expand_group(hass, resolve(hass, get_runtime(hass).registry, entity_id)) is None


async def test_without_the_bridge_cache_membership_is_unknowable(hass, setup_production):
    add_z2m_group(hass, z2m_entry(hass), "light.room", group_id=7)

    assert INTEGRATION.expand_group(hass, resolve(hass, get_runtime(hass).registry, "light.room")) is None


@pytest.mark.parametrize(
    ("groups", "expected"),
    [
        pytest.param([{"id": 3, "members": [{"ieee_address": "0x01"}]}], None, id="unlisted"),
        pytest.param([{"id": 7, "members": [{"ieee_address": "0x09"}]}], None, id="no_member_in_ha"),
        pytest.param([{"id": 7, "members": []}], [], id="listed_empty"),
    ],
)
async def test_only_a_group_listed_with_no_members_is_empty(hass, setup_production, broker, groups, expected):
    entity_id = group(hass, broker, one={}, two={})
    broker.retained[GROUPS] = groups

    assert INTEGRATION.expand_group(hass, resolve(hass, get_runtime(hass).registry, entity_id)) == expected


def plug_in_group(hass, broker, registry: tuple[str, str] = PLUG, zigbee: tuple[str, str] = (TUYA, "TS011F")) -> str:
    """Group 7 of two Hue bulbs and a plug, 0x03 (a TS011F unless `registry` and `zigbee` say otherwise), which Z2M
    exposes as a switch, so HA has no light for it."""
    entity_id = group(hass, broker, one={}, two={})
    entry = hass.config_entries.async_entries("mqtt")[0]
    add_z2m_entity(hass, entry, "switch.plug", ieee="0x03", manufacturer=registry[0], model_id=registry[1])
    broker.retained[DEVICES].append(interviewed("0x03", *zigbee))
    broker.retained[GROUPS][0]["members"].append({"ieee_address": "0x03"})
    return entity_id


# Another brand's plug, `other`, a class an action for lights alone still holds (stop, the brightness fades), as the
# class holds lights too.
INNR_PLUG = {"registry": ("Innr", "SP 120"), "zigbee": ("innr", "SP 120")}


async def test_a_member_ha_has_no_light_for_is_classed_by_its_device(hass, setup_production, broker):
    """Left out, the plug would leave the group Verified on the Hue bulbs alone, and get its light command."""
    entity_id = plug_in_group(hass, broker)

    members = INTEGRATION.expand_group(hass, resolve(hass, get_runtime(hass).registry, entity_id))

    classed = {member.entity_id: INTEGRATION.capability(hass, member) for member in members}
    # The plug's stand-in is the group's own entity, with its device, no state and not addressable, so no action
    # reaches it: a group that falls back skips it (not_addressable).
    assert classed == {"light.one": "hue", "light.two": "hue", entity_id: "tuya_ts011f"}
    assert [(member.state, member.addressable) for member in members if member.entity_id == entity_id] == [
        (None, False)
    ]


async def test_a_stand_in_is_left_out_of_the_member_lights_and_logged(hass, setup_production, broker, caplog):
    """The plug's stand-in has no state, so no action reads or commands it; the debug log says why it is missing."""
    caplog.set_level("DEBUG", logger=members.__name__)
    entity_id = plug_in_group(hass, broker)
    group_target = resolve(hass, get_runtime(hass).registry, entity_id)

    lights = await members.member_lights(hass, group_target)

    assert [member.entity_id for member in lights] == ["light.one", "light.two"]
    assert f"{entity_id}: a member device (switch.plug) has no light entity" in caplog.text


async def test_a_group_with_a_member_harmed_by_the_call_falls_back_with_labs_on(hass, setup_production, broker):
    """The audit's H1: the plug once left the membership unknown, so with Labs on the group ran
    whole, and the plug took the group's timer and stayed on."""
    entity_id = plug_in_group(hass, broker)
    allow_labs(hass)

    response = await call_service(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5})

    # A group that fell back has no entry, so no member map: each member's entry names its own class.
    assert response == {"light.one": SENT | {"capability": "hue"}, "light.two": SENT | {"capability": "hue"}}
    assert {topic for topic, _ in commands(broker)} == {SET.replace(IEEE, "0x01"), SET.replace(IEEE, "0x02")}


@pytest.mark.parametrize(
    ("service", "data", "sent"),
    [
        ("stop", {}, {"brightness_move": "stop"}),
        ("raise_hue", {"sweep_time": 10}, None),
    ],
)
async def test_a_light_group_with_a_ts011f_plug_falls_back_on_a_light_action_with_labs_on(
    hass, setup_production, broker, caplog, service, data, sent
):
    """Per docs/evidence.md's "A class names its domains": no action for lights alone holds a TS011F, a switch, so its
    class refuses the group, which falls back to its members even with Labs on: each bulb gets its own
    call, where the group once took one groupcast that reached the plug, and the plug's stand-in is skipped as not built
    yet."""
    entity_id = plug_in_group(hass, broker)
    allow_labs(hass)

    response = await call_service(hass, service, {"entity_id": entity_id} | data)

    assert response == {"light.one": SENT | {"capability": "hue"}, "light.two": SENT | {"capability": "hue"}}
    topics = [topic for topic, _ in commands(broker)]
    assert set(topics) == {SET.replace(IEEE, "0x01"), SET.replace(IEEE, "0x02")}
    assert "zigbee2mqtt/7/set" not in topics
    if sent is not None:
        assert sorted(commands(broker)) == sorted((topic, sent) for topic in topics)
    assert "a member device of light.room (not_built)" in caplog.text


# What a native group's member_capabilities holds (docs/action-behavior.md, The class).

HUE_PAIR = {"light.one": "hue", "light.two": "hue"}


@pytest.mark.parametrize("service", ["stop", "raise_brightness"])
async def test_a_stand_in_is_left_out_of_the_member_map_and_its_class_kept(hass, setup_production, broker, service):
    """The audit's H1 on #431: the plug's stand-in is keyed on the group's own entity_id, so the map once credited
    its class to light.room, a class whose state the rig never sees."""
    entity_id = plug_in_group(hass, broker, **INNR_PLUG)
    allow_labs(hass)
    data = {"entity_id": entity_id} | ({"sweep_time": 10} if service == "raise_brightness" else {})

    response = await call_service(hass, service, data)

    assert response[entity_id]["capabilities"] == ["hue", "other"]
    assert response[entity_id]["member_capabilities"] == HUE_PAIR


async def test_two_stand_ins_in_one_group_are_both_left_out(hass, setup_production, broker):
    """Two plugs would both be keyed on the group's entity_id: one would hide the other's class."""
    entity_id = plug_in_group(hass, broker, **INNR_PLUG)
    add_z2m_entity(
        hass,
        hass.config_entries.async_entries("mqtt")[0],
        "switch.plug_two",
        ieee="0x04",
        manufacturer=IKEA[0],
        model_id="E1603",
    )
    broker.retained[DEVICES].append(interviewed("0x04", IKEA[0], "TRADFRI control outlet"))
    broker.retained[GROUPS][0]["members"].append({"ieee_address": "0x04"})
    allow_labs(hass)

    response = await call_service(hass, "stop", {"entity_id": entity_id})

    assert response[entity_id]["capabilities"] == ["hue", "ikea", "other"]
    assert response[entity_id]["member_capabilities"] == HUE_PAIR


async def test_an_unavailable_member_is_left_out_of_the_member_map(hass, setup_production, broker):
    """Its state can't show the call reached it; its class, kept from the registry, still counts in the list."""
    entity_id = group(hass, broker, one={}, two={"manufacturer": "IKEA of Sweden"})
    hass.states.async_set("light.two", "unavailable")
    allow_labs(hass)

    response = await call_service(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5})

    assert response == {
        entity_id: SENT | {"capabilities": ["hue", "ikea"], "member_capabilities": {"light.one": "hue"}}
    }


async def test_a_member_named_beside_its_group_is_in_the_map_and_has_its_own_entry(hass, setup_production, broker):
    entity_id = group(hass, broker, one={}, two={})

    response = await call_service(hass, "turn_on_for", {"entity_id": [entity_id, "light.one"], "duration": 5})

    assert response == {
        entity_id: SENT | {"capabilities": ["hue"], "member_capabilities": HUE_PAIR},
        "light.one": SENT | {"capability": "hue"},
    }


async def test_a_member_with_no_device_leaves_membership_unknowable(hass, setup_production, broker):
    entity_id = group(hass, broker, one={}, two={})
    broker.retained[GROUPS][0]["members"].append({"ieee_address": "0x09"})

    assert INTEGRATION.expand_group(hass, resolve(hass, get_runtime(hass).registry, entity_id)) is None


async def test_a_member_on_two_endpoints_counts_once(hass, setup_production, broker):
    entity_id = group(hass, broker, one={}, two={})
    broker.retained[GROUPS][0]["members"].append({"ieee_address": "0x01", "endpoint": 2})

    members = INTEGRATION.expand_group(hass, resolve(hass, get_runtime(hass).registry, entity_id))

    assert [member.entity_id for member in members] == ["light.one", "light.two"]


GANG = "0x05"


def two_gang(
    hass, broker, group_id: int | None = 7, *, disabled: bool = False, domain: str = "light", name: str = "gang"
) -> None:
    """A Hue two-gang, 0x05, with light.gang_1 on endpoint 1 (disabled, with `disabled`) and light.gang_2 on endpoint
    2, as Z2M announces each (`<ieee>_light_l1_zigbee2mqtt`), and endpoint 2 alone in Z2M group `group_id`, unless
    that is None. `domain` and `name` make it a relay's `switch.<name>_1` and `_2`."""
    entry = hass.config_entries.async_entries("mqtt")[0]
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        via_device_id=add_z2m_bridge(hass, entry).id,
        identifiers={("mqtt", f"zigbee2mqtt_{GANG}")},
        manufacturer="Philips",
        name="two_gang",
    )
    for gang in (1, 2):
        er.async_get(hass).async_get_or_create(
            domain,
            "mqtt",
            f"{GANG}_{domain}_l{gang}_zigbee2mqtt",
            suggested_object_id=f"{name}_{gang}",
            config_entry=entry,
            device_id=device.id,
            disabled_by=er.RegistryEntryDisabler.USER if disabled and gang == 1 else None,
        )
        if not (disabled and gang == 1):
            attributes = {"supported_color_modes": ["xy"]} if domain == "light" else {}
            hass.states.async_set(f"{domain}.{name}_{gang}", "on", attributes)
    broker.retained[DEVICES].append(interviewed(GANG, "Philips", "ZIGBEE_SWITCH"))
    if group_id is None:
        return
    next(g for g in broker.retained[GROUPS] if g["id"] == group_id)["members"].append(
        {"ieee_address": GANG, "endpoint": 2}
    )


@pytest.mark.parametrize("disabled", [False, True], ids=["both_enabled", "gang_1_disabled"])
async def test_a_device_with_several_lights_is_classed_but_never_addressed_alone(
    hass, setup_production, broker, disabled
):
    """bridge/groups holds its endpoint 2, but a set on its device topic reaches its default endpoint, gang 1."""
    entity_id = group(hass, broker, one={}, two={})
    two_gang(hass, broker, disabled=disabled)

    listed = INTEGRATION.expand_group(hass, resolve(hass, get_runtime(hass).registry, entity_id))

    gang = "light.gang_2" if disabled else "light.gang_1"
    assert {member.entity_id: member.addressable for member in listed} == {
        "light.one": True,
        "light.two": True,
        gang: False,
    }
    assert [INTEGRATION.capability(hass, member) for member in listed] == ["hue"] * 3


async def test_member_lights_leave_out_a_device_with_several_lights(hass, setup_production, broker, caplog):
    caplog.set_level("DEBUG", logger=members.__name__)
    entity_id = group(hass, broker, one={}, two={})
    two_gang(hass, broker)

    lights = await members.member_lights(hass, resolve(hass, get_runtime(hass).registry, entity_id))

    assert [member.entity_id for member in lights] == ["light.one", "light.two"]
    assert f"{entity_id}: a member device (light.gang_1, light.gang_2) has no unsuffixed light entity" in caplog.text
    assert f"{entity_id}: leaving out the devices of light.gang_1, each with several light entities" in caplog.text


async def test_a_switch_as_x_light_beside_a_z2m_light_leaves_its_device_addressable(hass, setup_production, broker):
    """Only Z2M's own entities are endpoints: a switch_as_x light on the same device is no second light."""
    entity_id = group(hass, broker, one={}, two={})
    device_id = er.async_get(hass).async_get("light.one").device_id
    er.async_get(hass).async_get_or_create(
        "light", "switch_as_x", "wrapper", suggested_object_id="one_wrapper", device_id=device_id
    )

    listed = INTEGRATION.expand_group(hass, resolve(hass, get_runtime(hass).registry, entity_id))

    assert {member.entity_id: member.addressable for member in listed} == {"light.one": True, "light.two": True}


async def test_a_fallback_skips_a_device_with_several_lights_as_not_addressable(hass, setup_production, broker, caplog):
    """Addressed alone, the two-gang would get the call on gang 1, which the group doesn't hold."""
    entity_id = group(hass, broker, one={}, two={"manufacturer": "IKEA of Sweden"})
    two_gang(hass, broker)

    response = await call(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5})

    assert response == {"light.one": SENT}
    assert commands(broker) == [(SET.replace(IEEE, "0x01"), {"state": "ON", "on_time": 5.0})]
    assert "the device of light.gang_1 (not_addressable)" in caplog.text


async def test_a_groupcast_still_reaches_a_device_with_several_lights(hass, setup_production, broker):
    entity_id = group(hass, broker, one={}, two={})
    two_gang(hass, broker)

    assert await call(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5}) == {entity_id: SENT}
    assert commands(broker) == [("zigbee2mqtt/7/set", {"state": "ON", "on_time": 5.0})]


def gang_alone(hass, broker) -> str:
    """Group 8, light.gangs, holding the two-gang's endpoint 2 and nothing else."""
    group(hass, broker, one={}, two={})
    add_z2m_group(hass, hass.config_entries.async_entries("mqtt")[0], "light.gangs", group_id=8, name="gangs")
    hass.states.async_set("light.gangs", "on", {"supported_color_modes": ["xy"]})
    broker.retained[GROUPS].append({"id": 8, "members": []})
    two_gang(hass, broker, 8)
    return "light.gangs"


@pytest.mark.parametrize(
    ("service", "data"),
    [
        ("get_attributes", {}),
        ("set_attributes", {"brightness": 50}),
        ("raise_brightness", {"sweep_time": 10}),
        ("stop", {}),
    ],
)
async def test_a_group_of_only_devices_with_several_lights_refuses_a_call_through_its_members(
    hass, setup_production, broker, service, data
):
    """Each of these reaches the group's lights one by one, and it has none it can address: refused before anything is
    sent, as core refuses a group none of whose members runs."""
    entity_id = gang_alone(hass, broker)

    assert await refusal(hass, service, {"entity_id": entity_id, **data}) == "not_addressable"
    assert commands(broker) == []


@pytest.mark.parametrize(
    ("service", "data"),
    [
        ("raise_brightness", {"sweep_time": 10}),
        ("lower_brightness", {"sweep_time": 10}),
        ("stop", {}),
        ("set_attributes", {"brightness": 50}),
    ],
)
async def test_a_group_holding_a_device_with_several_lights_refuses_a_call_that_plans_from_each(
    hass, setup_production, broker, service, data
):
    """The audit's M1: these plan from each member's state, the groupcast reaches the gang the plan can't see. A raise
    from an off bulb and a lit gang would send the bottom-out groupcast and dip the gang; a lower or stop would
    answer off while the gang is lit and moving; set_attributes would confirm a level it never read back."""
    entity_id = group(hass, broker, one={"state": "off"}, two={"state": "off"})
    two_gang(hass, broker)

    assert await refusal(hass, service, {"entity_id": entity_id, **data}) == "not_addressable"
    assert commands(broker) == []


async def test_get_attributes_reads_a_group_holding_a_device_with_several_lights_from_the_others(
    hass, setup_production, broker
):
    """Averaging the members it can read answers for the group, so only a group with no other light is refused."""
    entity_id = group(hass, broker, one={}, two={})
    two_gang(hass, broker)
    target = resolve(hass, get_runtime(hass).registry, entity_id)

    assert members.unaddressable(hass, target, every=False) is None
    assert members.unaddressable(hass, target, every=True) == "not_addressable"


@pytest.mark.parametrize(("service", "data"), [("get_attributes", {}), ("raise_brightness", {"sweep_time": 10})])
async def test_a_group_of_a_device_with_several_lights_and_an_unavailable_bulb_is_refused(
    hass, setup_production, broker, service, data
):
    """The audit's L8: judged on available members, so the bulb can't hide the gang and leave the call nothing to
    address, skipped silently as an empty group."""
    entity_id = gang_alone(hass, broker)
    light(hass, broker, "light.away", "0x06", state="unavailable")
    broker.retained[GROUPS][-1]["members"].append({"ieee_address": "0x06"})

    assert await refusal(hass, service, {"entity_id": entity_id, **data}) == "not_addressable"
    assert commands(broker) == []


async def test_a_group_whose_fallback_reaches_only_a_device_with_several_lights_is_refused(
    hass, setup_production, broker
):
    """The IKEA bulb is gated, the two-gang can't be addressed alone: none runs, so the group raises its own reason."""
    entity_id = gang_alone(hass, broker)
    light(hass, broker, "light.tradfri", "0x06", manufacturer="IKEA of Sweden")
    broker.retained[GROUPS][-1]["members"].append({"ieee_address": "0x06"})

    assert await refusal(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5}) == "labs_off"
    assert commands(broker) == []


# A multi-endpoint device's light or switch targeted by itself: its call would reach the default endpoint.

ACTIONS = [
    ("turn_on_for", {"duration": 5}),
    ("get_attributes", {}),
    ("set_attributes", {"brightness": 50}),
    ("raise_brightness", {"sweep_time": 10}),
    ("lower_hue", {"sweep_time": 10}),
    ("stop", {}),
]


@pytest.mark.parametrize(("service", "data"), ACTIONS)
@pytest.mark.parametrize(
    ("entity_id", "disabled"),
    [("light.gang_1", False), ("light.gang_2", False), ("light.gang_2", True)],
    ids=["gang_1", "gang_2", "gang_2_beside_a_disabled_gang_1"],
)
async def test_a_named_light_of_a_device_with_several_is_refused(
    hass, setup_production, broker, service, data, entity_id, disabled
):
    """light.gang_2's call on the device topic would switch gang 1, which the user didn't target; gang 1 is refused
    too, as which endpoint is the default is the definition's, and the device's state comes in suffixed keys. A
    disabled gang 1 still counts: it is still an endpoint the device topic may reach."""
    light(hass, broker, "light.one", "0x01")
    two_gang(hass, broker, None, disabled=disabled)

    assert await refusal(hass, service, {"entity_id": entity_id, **data}) == "not_addressable"
    assert commands(broker) == []


async def test_an_indirect_light_of_a_device_with_several_is_skipped(hass, setup_production, broker, caplog):
    """Reached through a label, the gang is skipped with the warning and the label's other light runs."""
    light(hass, broker, "light.one", "0x01")
    two_gang(hass, broker, None)
    label_id = lr.async_get(hass).async_create("Den").label_id
    for entity_id in ("light.one", "light.gang_2"):
        er.async_get(hass).async_update_entity(entity_id, labels={label_id})

    response = await call(hass, "turn_on_for", {"label_id": label_id, "duration": 5})

    assert response == {"light.one": SENT}
    assert commands(broker) == [(SET.replace(IEEE, "0x01"), {"state": "ON", "on_time": 5.0})]
    assert "light.gang_2 (not_addressable)" in caplog.text


@pytest.mark.parametrize(("service", "data"), [("turn_on_for", {"duration": 5}), ("get_attributes", {})])
@pytest.mark.parametrize("entity_id", ["switch.relay_1", "switch.relay_2"])
async def test_a_named_switch_of_a_two_gang_relay_is_refused(hass, setup_production, broker, service, data, entity_id):
    """The same topic problem on a relay's switches: switch.relay_2's timer would run on relay 1."""
    light(hass, broker, "light.one", "0x01")
    two_gang(hass, broker, None, domain="switch", name="relay")
    allow_labs(hass)  # switches are in Labs, so the refusal shown is the addressing one

    assert await refusal(hass, service, {"entity_id": entity_id, **data}) == "not_addressable"
    assert commands(broker) == []


async def test_a_device_with_one_light_is_addressed(hass, setup_production, broker):
    entity_id = light(hass, broker, "light.one", "0x01")
    two_gang(hass, broker, None)

    assert await call(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5}) == {entity_id: SENT}
    assert commands(broker) == [(SET.replace(IEEE, "0x01"), {"state": "ON", "on_time": 5.0})]


async def test_a_switch_as_x_light_beside_a_z2m_light_leaves_it_addressable_by_name(hass, setup_production, broker):
    """Only Z2M's own entities are endpoints: a switch_as_x light on the same device is no second light."""
    entity_id = light(hass, broker, "light.one", "0x01")
    device_id = er.async_get(hass).async_get(entity_id).device_id
    er.async_get(hass).async_get_or_create(
        "light", "switch_as_x", "wrapper", suggested_object_id="one_wrapper", device_id=device_id
    )

    assert await call(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5}) == {entity_id: SENT}
    assert commands(broker) == [(SET.replace(IEEE, "0x01"), {"state": "ON", "on_time": 5.0})]


def second_light(hass, disabled: bool = False) -> None:
    """A second light entity on light.one's device, `<ieee>_light_l2`, beside its unsuffixed state entity."""
    entities = er.async_get(hass)
    entities.async_get_or_create(
        "light",
        "mqtt",
        "0x01_light_l2_zigbee2mqtt",
        suggested_object_id="one_l2",
        config_entry=hass.config_entries.async_entries("mqtt")[0],
        device_id=entities.async_get("light.one").device_id,
        disabled_by=er.RegistryEntryDisabler.USER if disabled else None,
    )
    if not disabled:
        hass.states.async_set("light.one_l2", "on")


@pytest.mark.parametrize("disabled", [False, True])
async def test_a_member_is_its_devices_unsuffixed_entity_whatever_sits_beside_it(
    hass, setup_production, broker, disabled
):
    """Argued, not seen on a device (internals.md, Addressing): the unsuffixed `state` key is the one DeviceSide sends,
    so that entity is the member, addressable, even with a suffixed light beside it."""
    entity_id = group(hass, broker, one={}, two={})
    second_light(hass, disabled)

    listed = INTEGRATION.expand_group(hass, resolve(hass, get_runtime(hass).registry, entity_id))

    assert [(member.entity_id, member.addressable) for member in listed] == [("light.one", True), ("light.two", True)]


# What a class's level does to a call.


async def test_a_hue_bulb_is_class_hue(hass, setup_production, broker):
    entity_id = light(hass, broker, manufacturer="Philips")

    response = await call_service(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5})

    assert response == {entity_id: SENT | {"capability": "hue"}}


async def test_an_ikea_light_is_in_labs(hass, setup_production, broker):
    entity_id = light(hass, broker, manufacturer="IKEA of Sweden")
    data = {"entity_id": entity_id, "duration": 5}

    assert await refusal(hass, "turn_on_for", data) == "labs_off"
    allow_labs(hass)
    assert await call_service(hass, "turn_on_for", data) == {entity_id: SENT | {"capability": "ikea"}}


async def test_a_brightness_fade_and_stop_run_on_another_brand_in_labs(hass, setup_production, broker):
    """The call a Hue bulb gets, pinned: the same publish, to another brand's bulb's topic, with Labs
    on (Zigbee 3.0 certification, docs/internals.md)."""
    entity_id = light(hass, broker, manufacturer="Innr")
    data = {"entity_id": entity_id, "limit": 80, "sweep_time": 10}
    assert await refusal(hass, "raise_brightness", data) == "labs_off"
    allow_labs(hass)

    response = await call_service(hass, "raise_brightness", data)
    assert response == {entity_id: SENT | {"capability": "other"}}
    assert commands(broker) == [(SET, {"state": "ON", "brightness": 203, "transition": 2.0})]

    broker.published.clear()
    assert await call_service(hass, "stop", {"entity_id": entity_id}) == {entity_id: SENT | {"capability": "other"}}
    assert commands(broker) == [(SET, {"brightness_move": "stop"})]


@pytest.mark.parametrize("action", ["get_attributes", "set_attributes"])
def test_another_brands_reads_and_writes_are_in_labs_on_lights_alone(action):
    """No departure is reported among other brands' lights, and a failed write harms nothing; a plug's harm is in its
    load, so a switch is refused (research/2026-11-24-other-brands-execute-if-off-and-reads.md)."""
    scope = _scopes()[action]
    assert scope.capabilities["other"] == OnDomains(Level.LABS, frozenset({"light"}), only=True)
    assert scope.admits("other", "light")
    assert not scope.admits("other", "switch")


async def test_a_hue_fade_is_not_built_on_another_brand(hass, setup_production, broker):
    """No research predicts how other firmware takes a hue move (docs/evidence.md, In Labs)."""
    entity_id = light(hass, broker, manufacturer="Innr")
    allow_labs(hass)

    assert await refusal(hass, "raise_hue", {"entity_id": entity_id, "sweep_time": 10}) == "not_built"
    assert commands(broker) == []


async def test_a_hue_and_ikea_group_falls_back_while_labs_is_off(hass, setup_production, broker, caplog):
    entity_id = group(hass, broker, one={}, two={"manufacturer": "IKEA of Sweden"})
    data = {"entity_id": entity_id, "duration": 5}

    # Off: the Hue bulb runs on its own, the IKEA one is skipped.
    assert await call_service(hass, "turn_on_for", data) == {"light.one": SENT | {"capability": "hue"}}
    assert commands(broker) == [(SET.replace(IEEE, "0x01"), {"state": "ON", "on_time": 5.0})]
    assert "light.two (labs_off)" in caplog.text

    # On: the group runs whole, one command to its group topic, at its weakest member's class.
    broker.published.clear()
    allow_labs(hass)
    assert await call_service(hass, "turn_on_for", data) == {
        entity_id: SENT
        | {"capabilities": ["hue", "ikea"], "member_capabilities": {"light.one": "hue", "light.two": "ikea"}}
    }
    assert commands(broker) == [("zigbee2mqtt/7/set", {"state": "ON", "on_time": 5.0})]


async def test_a_hue_group_is_verified_on_its_members_class(hass, setup_production, broker):
    entity_id = group(hass, broker, one={}, two={})

    response = await call_service(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5})

    assert response == {
        entity_id: SENT | {"capabilities": ["hue"], "member_capabilities": {"light.one": "hue", "light.two": "hue"}}
    }


# Where a call is known to harm, a class not yet known is refused (docs/evidence.md, No known method, not built yet,
# untested; Decisions 23 and 26): turn_on_for refuses a target it can't class, even with Labs on.
# The dispatcher applies it (tests/core/test_dispatcher.py), on the adapters whose entries harm (test_refusals.py).


async def test_turn_on_for_refuses_a_group_of_unknown_membership_with_labs_on(hass, setup_production, broker):
    """The audit's M1: before bridge/groups arrives, a group with a Tuya plug in it would run whole."""
    entity_id = group(hass, broker, one={}, two={})
    allow_labs(hass)
    data = {"entity_id": entity_id, "duration": 5}

    retained = broker.retained.pop(GROUPS)
    assert await refusal(hass, "turn_on_for", data) == "class_unknown"
    retained[0]["members"].append({"ieee_address": "0x09"})  # a member with no device in HA
    broker.retained[GROUPS] = retained
    assert await refusal(hass, "turn_on_for", data) == "class_unknown"
    assert commands(broker) == []
    # Elsewhere unknown stays in Labs: stop runs the group whole.
    assert await call(hass, "stop", {"entity_id": entity_id}) == {entity_id: SENT}


async def test_turn_on_for_refuses_a_device_only_the_registry_placed_in_other(hass, setup_production, broker):
    """The audit's M2: a rebadged TS011F (Lidl's definition) before bridge/devices arrives looks like another brand.
    Once it arrives, the plug is its own class, refused as not built yet, and an IKEA bulb runs in Labs again."""
    plug = light(hass, broker, "light.plug", "0x03", manufacturer="Lidl", model_id="HG06337", zigbee=(TUYA, "TS011F"))
    ikea = light(hass, broker, "light.tradfri", "0x04", manufacturer="IKEA of Sweden")
    allow_labs(hass)

    devices = broker.retained.pop(DEVICES)
    for entity_id in (plug, ikea):
        assert await refusal(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5}) == "class_unknown"
    assert commands(broker) == []

    broker.retained[DEVICES] = devices
    assert await refusal(hass, "turn_on_for", {"entity_id": plug, "duration": 5}) == "not_built"
    assert await call(hass, "turn_on_for", {"entity_id": ikea, "duration": 5}) == {ikea: SENT}


async def test_a_group_with_a_member_only_the_registry_placed_falls_back_to_its_members(
    hass, setup_production, broker, caplog
):
    """Only the member not yet placed is refused (plan step 6): the group isn't sent whole, which would reach it."""
    entity_id = group(hass, broker, one={}, two={"manufacturer": "Lidl", "model_id": "HG06337"})
    del broker.retained[DEVICES]
    allow_labs(hass)

    response = await call(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5})

    assert response == {"light.one": SENT}
    assert commands(broker) == [(SET.replace(IEEE, "0x01"), {"state": "ON", "on_time": 5.0})]
    assert "light.two (class_unknown)" in caplog.text


async def test_a_group_with_a_placed_and_an_unplaced_member_both_other_falls_back(
    hass, setup_production, broker, caplog
):
    """An IKEA bulb Zigbee2MQTT has interviewed and a Lidl-badged Tuya plug it hasn't, both `other`: equal classes,
    one Unplaced, so the group falls back and only the plug is refused (core's Classes keeps both)."""
    entity_id = group(
        hass,
        broker,
        one={"manufacturer": IKEA[0]},
        two={"manufacturer": "Lidl", "model_id": "HG06337", "zigbee": None},
    )
    allow_labs(hass)

    response = await call(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5})

    assert response == {"light.one": SENT}
    assert commands(broker) == [(SET.replace(IEEE, "0x01"), {"state": "ON", "on_time": 5.0})]
    assert "light.two (class_unknown)" in caplog.text


async def test_a_group_with_no_member_placed_is_refused_as_class_unknown(hass, setup_production, broker):
    entity_id = group(hass, broker, one={"manufacturer": "IKEA of Sweden"}, two={"manufacturer": "Lidl"})
    del broker.retained[DEVICES]
    allow_labs(hass)

    with pytest.raises(TargetNotSupported) as raised:
        await call_service(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5})

    assert raised.value.translation_key == "class_unknown"
    assert raised.value.translation_placeholders["integration"] == "Zigbee2MQTT"
    assert commands(broker) == []


async def test_a_member_not_yet_placed_still_runs_where_the_call_harms_no_class(hass, setup_production, broker):
    """stop's failure doesn't harm, so the group runs whole, with each member at the level its class has."""
    entity_id = group(hass, broker, one={}, two={"manufacturer": "Lidl", "model_id": "HG06337"})
    del broker.retained[DEVICES]
    allow_labs(hass)  # `other`, in Labs

    assert await call(hass, "stop", {"entity_id": entity_id}) == {entity_id: SENT}


async def test_a_hue_device_and_group_run_before_bridge_devices_arrives(hass, setup_production, broker):
    """The registry alone places a Hue bulb, so nothing waits on the cache for one."""
    entity_id = group(hass, broker, one={}, two={})
    lamp = light(hass, broker, manufacturer="Philips")
    del broker.retained[DEVICES]

    response = await call(hass, "turn_on_for", {"entity_id": [entity_id, lamp], "duration": 5})

    assert response == {entity_id: SENT, lamp: SENT}


async def test_a_group_with_a_ts011f_member_falls_back_to_its_members(hass, setup_production, broker, caplog):
    entity_id = group(hass, broker, one={}, two={"manufacturer": "Lidl", "zigbee": (TUYA, "TS011F")})

    response = await call(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5})

    assert response == {"light.one": SENT}
    assert commands(broker) == [(SET.replace(IEEE, "0x01"), {"state": "ON", "on_time": 5.0})]
    assert "light.two (not_built)" in caplog.text


async def test_turn_on_for_refuses_a_gledopto_badged_tuya_device_until_its_strings_arrive(
    hass, setup_production, broker
):
    """The audit's H1 (round 2): the registry alone put the GL-SPI-206P in `gledopto`, which with Labs
    features on took today's call; its Zigbee strings make it `tuya_mcu`, which the call leaves on."""
    entity_id = light(hass, broker, "light.strip", "0x03", **GLEDOPTO_TUYA)
    allow_labs(hass)
    data = {"entity_id": entity_id, "duration": 5}

    devices = broker.retained.pop(DEVICES)
    assert await refusal(hass, "turn_on_for", data) == "class_unknown"
    assert commands(broker) == []
    broker.retained[DEVICES] = devices
    assert await refusal(hass, "turn_on_for", data) == "not_built"


async def test_a_hue_group_with_a_gledopto_badged_tuya_member_runs_only_its_hue_member_until_its_strings_arrive(
    hass, setup_production, broker, caplog
):
    """Before, the strip would take the group's call; once its strings arrive it is `tuya_mcu`, refused as not
    built yet, and the group still falls back."""
    entity_id = group(hass, broker, one={}, two=GLEDOPTO_TUYA)
    devices = broker.retained.pop(DEVICES)
    allow_labs(hass)
    data = {"entity_id": entity_id, "duration": 5}
    hue_only = [(SET.replace(IEEE, "0x01"), {"state": "ON", "on_time": 5.0})]

    assert await call(hass, "turn_on_for", data) == {"light.one": SENT}
    assert commands(broker) == hue_only
    assert "light.two (class_unknown)" in caplog.text

    broker.retained[DEVICES] = devices
    assert await call(hass, "turn_on_for", data) == {"light.one": SENT}
    assert commands(broker) == hue_only * 2
    assert "light.two (not_built)" in caplog.text


async def test_a_hue_device_runs_with_no_bridge_cache(hass, setup_production, broker, monkeypatch):
    lamp = light(hass, broker, manufacturer="Philips")
    monkeypatch.setattr(classes, "bridge_cache", SimpleNamespace(get=lambda hass, base: None))

    assert await call(hass, "turn_on_for", {"entity_id": lamp, "duration": 5}) == {lamp: SENT}


async def test_a_tuya_device_is_refused_with_no_bridge_cache(hass, setup_production, broker, monkeypatch, caplog):
    """Without the cache (its subscribe failed) no device but a Hue one is ever placed, so a Tuya plug stays refused,
    and the debug log says what it waits for."""
    plug = light(hass, broker, "light.plug", manufacturer=PLUG[0], model_id=PLUG[1])
    monkeypatch.setattr(classes, "bridge_cache", SimpleNamespace(get=lambda hass, base: None))
    allow_labs(hass)
    caplog.set_level(logging.DEBUG, logger=classes.__name__)

    assert await refusal(hass, "turn_on_for", {"entity_id": plug, "duration": 5}) == "class_unknown"
    assert commands(broker) == []
    assert "light.plug: class tuya_ts011f is provisional until Zigbee2MQTT reports the device (no bridge cache)" in (
        caplog.text
    )


@pytest.mark.parametrize(
    ("zigbee", "interviewed", "expected"),
    [
        # Mid-interview: Z2M lists the device with null strings until it reads them.
        pytest.param(None, False, "class_unknown", id="no_strings"),
        pytest.param((None, "TS011F"), True, "class_unknown", id="model_only"),
        pytest.param((TUYA, "TS011F"), False, "class_unknown", id="mid_interview"),
        pytest.param((TUYA, "TS011F"), True, "not_built", id="interviewed"),
    ],
)
async def test_a_device_listed_with_null_strings_is_not_placed(
    hass, setup_production, broker, zigbee, interviewed, expected
):
    """The audit's M (round 2): Lidl's HG06337 mid-interview, `manufacturer: null`, once counted as placed in
    `other`, so it took today's call with Labs on."""
    entity_id = light(hass, broker, manufacturer="Lidl", model_id="HG06337", zigbee=zigbee, interviewed=interviewed)
    allow_labs(hass)

    assert await refusal(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5}) == expected


@pytest.mark.parametrize(
    ("zigbee", "interviewed"),
    [
        pytest.param((IKEA[0], None), True, id="no_model"),
        pytest.param((None, IKEA[1]), True, id="no_manufacturer"),
        pytest.param((IKEA[0], ""), True, id="empty_model"),
        pytest.param(("", IKEA[1]), True, id="empty_manufacturer"),
        pytest.param(IKEA, False, id="mid_interview"),
    ],
)
async def test_another_brand_waits_until_interviewed_with_both_strings(
    hass, setup_production, broker, zigbee, interviewed
):
    """A Tuya device could still show its string in the one missing, or finish its interview as another."""
    ikea = light(hass, broker, manufacturer=IKEA[0], zigbee=zigbee, interviewed=interviewed)
    allow_labs(hass)

    assert await refusal(hass, "turn_on_for", {"entity_id": ikea, "duration": 5}) == "class_unknown"


async def test_class_unknown_says_it_clears_once_zigbee2mqtt_reports_the_device(hass, setup_production, broker):
    entity_id = light(hass, broker, **GLEDOPTO_TUYA)
    del broker.retained[DEVICES]
    allow_labs(hass)

    with pytest.raises(TargetNotSupported) as raised:
        await call_service(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5})

    assert raised.value.translation_key == "class_unknown"
    assert raised.value.translation_placeholders == {
        "entity_id": entity_id,
        "reason": "class_unknown",
        "integration": "Zigbee2MQTT",
    }
    # Without the bridge it never clears in seconds, so the message doesn't promise them.
    message = json.loads(STRINGS.read_text())["exceptions"]["class_unknown"]["message"]
    assert "usually takes seconds; if it doesn't, reload DeviceSide" in message


async def test_an_indirect_target_of_unknown_class_is_skipped_and_the_rest_run(hass, setup_production, broker, caplog):
    """Refused as core refuses a target: skipped and logged when it came indirectly, here through `all`."""
    lamp = light(hass, broker, "light.lamp", "0x01")
    strip = light(hass, broker, "light.strip", "0x03", **GLEDOPTO_TUYA)
    del broker.retained[DEVICES]
    allow_labs(hass)

    assert await call(hass, "turn_on_for", {"entity_id": "all", "duration": 5}) == {lamp: SENT}
    assert f"{strip} (class_unknown)" in caplog.text


async def test_the_report_form_carries_the_tuya_string_bridge_devices_holds(hass, setup_production, broker):
    """The registry shows the definition's vendor, `Tuya`; the form takes the string a Tuya class keys on."""
    entity_id = light(hass, broker, manufacturer=PLUG[0], model_id=PLUG[1], zigbee=(TUYA, "TS011F"))
    device = dr.async_get(hass).async_get(resolve(hass, get_runtime(hass).registry, entity_id).entry.device_id)

    assert INTEGRATION.zigbee_manufacturer(hass, device) == TUYA
    url = await issue_url(hass, _FORMS_BY_STEP["report_device"], [entity_id])
    assert parse_qs(urlparse(url).query)["devices"] == [f"zigbee2mqtt · {PLUG[1]} · {TUYA}"]
    for private in (entity_id, "lamp", IEEE):
        assert private not in url


async def test_before_bridge_devices_lists_it_the_form_leaves_the_string_out(hass, setup_production, broker):
    """The registry's vendor, `Tuya`, is not the string a report is matched by, so it doesn't stand in."""
    entity_id = light(hass, broker, manufacturer=PLUG[0], model_id=PLUG[1], zigbee=(TUYA, "TS011F"))
    del broker.retained[DEVICES]

    url = await issue_url(hass, _FORMS_BY_STEP["report_device"], [entity_id])
    assert parse_qs(urlparse(url).query)["devices"] == [f"zigbee2mqtt · {PLUG[1]}"]
