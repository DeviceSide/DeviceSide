"""Zigbee2MQTT's device classes: the rules that name a device's class, the group members its classes come from, and
what each class's level does to a call."""

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.deviceside.core.models import Target
from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.integrations.zigbee2mqtt import INTEGRATION, classes, native_control
from custom_components.deviceside.integrations.zigbee2mqtt.classes import CLASSES, RULES, Rule

from .conftest import SENT, SET, call, commands, group, light
from ...conftest import allow_experimental, refusal
from ...conftest import call as call_service
from ...fixtures.zigbee2mqtt import GROUPS, IEEE, add_z2m_entity, add_z2m_group, z2m_entry

TUYA = "_TZ3000_abcdefgh"  # a Tuya ZCL manufacturer string's shape, as Tuya's firmware reports it


def stand_in(hass, manufacturer: str | None, model: str | None = None) -> Target:
    """A target with a registry device alone, as the rig classes one: no config entry or state."""
    config = z2m_entry(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config.entry_id,
        identifiers={("mqtt", f"zigbee2mqtt_{IEEE}")},
        manufacturer=manufacturer,
        model=model,
    )
    entry = er.async_get(hass).async_get_or_create("light", "mqtt", IEEE, device_id=device.id)
    return Target(entry.entity_id, "light", "zigbee2mqtt", entry, device, None, None)


@pytest.mark.parametrize(
    ("manufacturer", "model", "expected"),
    [
        ("Philips", "Hue White A60 B22 (9290018217)", "hue"),
        ("Philips Lighting", None, "other"),  # the whole string, not a prefix
        ("IKEA of Sweden", "TRADFRI bulb E27 (LED1836G9)", "other"),
        (TUYA, "TS011F", "other"),  # no Tuya class until the lab probe gives its rule (plan, step 5 part 2)
        ("Sengled", "E11-G13", "other"),  # nor a Sengled one
        (None, None, "other"),
    ],
)
def test_a_device_s_class_is_its_first_matching_rule_or_the_default(hass, manufacturer, model, expected):
    assert INTEGRATION.capability(None, stand_in(hass, manufacturer, model)) == expected


def test_a_target_with_no_device_has_no_class(hass):
    target = stand_in(hass, "Philips")
    assert (
        INTEGRATION.capability(None, Target(target.entity_id, "light", "zigbee2mqtt", target.entry, None, None, None))
        is None
    )


def test_the_hue_rule_and_native_control_read_one_string():
    assert native_control.HUE_MANUFACTURER is classes.HUE_MANUFACTURER
    assert RULES[0] == Rule("hue", {"manufacturer": "Philips"})


@pytest.mark.parametrize(
    ("rule", "error"),
    [
        (lambda: Rule("other", {"manufacturer": "x"}), "no class but the default's"),
        (lambda: Rule("ikea", {"manufacturer": "x"}), "no class but the default's"),
        (lambda: Rule("hue", {"vendor": "x"}), r"tests \['vendor'\]"),
        (lambda: Rule("hue", {}), "tests nothing"),
    ],
)
def test_a_rule_names_a_declared_class_and_registry_fields(rule, error):
    with pytest.raises(ValueError, match=error):
        rule()


def test_the_default_class_is_other_and_held_below_verified():
    assert INTEGRATION.default_class == "other"
    assert INTEGRATION.classes == {"hue", "other"}


# Group members, from the bridge cache.


async def test_a_group_lists_its_members_from_the_held_bridge_groups(hass, setup_production, broker):
    entity_id = group(hass, broker, one={}, two={"manufacturer": "IKEA of Sweden"})
    target = resolve(hass, get_runtime(hass).registry, entity_id)

    members = INTEGRATION.expand_group(hass, target)

    assert [member.entity_id for member in members] == ["light.one", "light.two"]
    assert {member.via_group for member in members} == {entity_id}
    assert [INTEGRATION.capability(hass, member) for member in members] == ["hue", "other"]


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


# What a class's level does to a call.


async def test_a_hue_bulb_is_class_hue(hass, setup_production, broker):
    entity_id = light(hass, broker, manufacturer="Philips")

    response = await call_service(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5})

    assert response == {entity_id: SENT | {"capability": "hue"}}


async def test_a_non_hue_light_is_experimental(hass, setup_production, broker):
    entity_id = light(hass, broker, manufacturer="IKEA of Sweden")
    data = {"entity_id": entity_id, "duration": 5}

    assert await refusal(hass, "turn_on_for", data) == "experimental_off"
    allow_experimental(hass)
    assert await call_service(hass, "turn_on_for", data) == {entity_id: SENT | {"capability": "other"}}


async def test_a_ramp_runs_on_another_brand_with_experimental_on(hass, setup_production, broker):
    entity_id = light(hass, broker, manufacturer="IKEA of Sweden")
    data = {"entity_id": entity_id, "limit": 80, "sweep_time": 10}

    assert await refusal(hass, "raise_brightness", data) == "experimental_off"
    allow_experimental(hass)
    assert await call_service(hass, "raise_brightness", data) == {entity_id: SENT | {"capability": "other"}}
    assert commands(broker)


async def test_a_hue_and_ikea_group_falls_back_while_experimental_is_off(hass, setup_production, broker, caplog):
    entity_id = group(hass, broker, one={}, two={"manufacturer": "IKEA of Sweden"})
    data = {"entity_id": entity_id, "duration": 5}

    # Off: the Hue bulb runs on its own, the IKEA one is skipped.
    assert await call_service(hass, "turn_on_for", data) == {"light.one": SENT | {"capability": "hue"}}
    assert commands(broker) == [(SET.replace(IEEE, "0x01"), {"state": "ON", "on_time": 5.0})]
    assert "light.two (experimental_off)" in caplog.text

    # On: the group runs whole, one command to its group topic, at its weakest member's class.
    broker.published.clear()
    allow_experimental(hass)
    assert await call_service(hass, "turn_on_for", data) == {entity_id: SENT | {"capabilities": ["hue", "other"]}}
    assert commands(broker) == [("zigbee2mqtt/7/set", {"state": "ON", "on_time": 5.0})]


async def test_a_hue_group_is_verified_on_its_members_class(hass, setup_production, broker):
    entity_id = group(hass, broker, one={}, two={})

    response = await call_service(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5})

    assert response == {entity_id: SENT | {"capabilities": ["hue"]}}


@pytest.fixture
def tuya_rule(monkeypatch):
    """A stand-in Tuya class and rule, so a class an adapter doesn't serve shows its refusal; part 2 adds the real
    ones. Its field is a guess: Tuya's firmware reports `_TZ3000_…` as its Zigbee manufacturer, but Z2M's discovery
    likely registers its definition's vendor there, and the probe decides which field holds it."""
    monkeypatch.setattr(classes, "CLASSES", CLASSES | {"tuya_zcl"})
    monkeypatch.setattr(classes, "RULES", (*RULES, Rule("tuya_zcl", {"manufacturer": "_TZ3000_.*"})))


@pytest.mark.usefixtures("tuya_rule")
async def test_turn_on_for_refuses_a_tuya_device_as_not_supported(hass, setup_production, broker):
    """Rather than send `on_time`, which Z2M turns into a plain On that never ends on Tuya firmware."""
    allow_experimental(hass)
    add_z2m_entity(hass, z2m_entry(hass), "switch.plug", manufacturer=TUYA)

    assert await refusal(hass, "turn_on_for", {"entity_id": "switch.plug", "duration": 5}) == "not_supported"
    assert commands(broker) == []


@pytest.mark.usefixtures("tuya_rule")
async def test_a_group_with_a_tuya_member_falls_back_to_its_members(hass, setup_production, broker, caplog):
    entity_id = group(hass, broker, one={}, two={"manufacturer": TUYA})

    response = await call(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5})

    assert response == {"light.one": SENT}
    assert commands(broker) == [(SET.replace(IEEE, "0x01"), {"state": "ON", "on_time": 5.0})]
    assert "light.two (not_supported)" in caplog.text
