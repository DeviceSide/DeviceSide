"""Zigbee2MQTT addresses a device target only when it is its device's unsuffixed state entity
(`<ieee>_<domain>_zigbee2mqtt`, addressing.state_unique_id), whatever else Z2M's discovery put in the domain: a plug's
child lock is a `switch` beside it. The gangs' own refusals are test_classes.py's."""

import pytest
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er

from custom_components.deviceside.core.errors import Reason
from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.integrations.zigbee2mqtt import INTEGRATION
from custom_components.deviceside.integrations.zigbee2mqtt.addressing import not_addressable

from .conftest import DEVICES, PLUG, commands, light
from .families.tuya.test_countdown import LAB, listed
from ...conftest import allow_labs, refusal
from ...conftest import call as call_service
from ...fixtures.zigbee2mqtt import GROUPS, IEEE, add_z2m_entity, add_z2m_group, z2m_entry


def entry(hass):
    """The one MQTT entry Z2M's devices share: a device's identifier is unique within an entry only."""
    return next(iter(hass.config_entries.async_entries("mqtt")), None) or z2m_entry(hass)


def plug(hass, broker, *, ieee: str = IEEE, name: str = "plug") -> None:
    """A plug Z2M exposes as one `switch`, named `name`, registered as Z2M does."""
    add_z2m_entity(hass, entry(hass), f"switch.{name}", ieee=ieee, manufacturer=PLUG[0], model_id=PLUG[1], name=name)
    broker.retained.setdefault(DEVICES, []).append(listed(ieee, LAB))


def sibling(
    hass, entity_id: str, object_id: str, *, ieee: str = IEEE, category=None, disabled: bool = False, name: str = "plug"
) -> str:
    """A second `switch` on the plug's device, as Z2M makes one for a writable binary expose."""
    add_z2m_entity(hass, entry(hass), entity_id, ieee=ieee, unique_object_id=object_id, name=name, manufacturer=PLUG[0])
    er.async_get(hass).async_update_entity(
        entity_id,
        entity_category=category,
        disabled_by=er.RegistryEntryDisabler.USER if disabled else None,
    )
    return entity_id


def verdict(hass, entity_id: str, **kwargs) -> str | None:
    return not_addressable(hass, resolve(hass, get_runtime(hass).registry, entity_id), **kwargs)


CHILD_LOCKS = [
    pytest.param(EntityCategory.CONFIG, False, id="config"),
    pytest.param(EntityCategory.CONFIG, True, id="config_disabled"),
    pytest.param(None, False, id="uncategorized"),
]


@pytest.mark.parametrize(("category", "disabled"), CHILD_LOCKS)
async def test_a_plug_beside_a_child_lock_switch_is_addressed(hass, setup_production, broker, category, disabled):
    """Run B (2026-11-16): the child lock made two `switch` entities, and the count refused every such plug."""
    sibling(hass, "switch.plug_child_lock", "switch_child_lock", category=category, disabled=disabled)
    plug(hass, broker)
    allow_labs(hass)

    assert verdict(hass, "switch.plug") is None
    assert verdict(hass, "switch.plug", reads_state=True) is None
    response = await call_service(hass, "turn_on_for", {"entity_id": "switch.plug", "duration": 5})
    assert response["switch.plug"]["status"] == "sent"


@pytest.mark.parametrize(("category", "disabled"), CHILD_LOCKS)
async def test_the_child_lock_switch_itself_is_refused_and_nothing_is_sent(
    hass, setup_production, broker, category, disabled
):
    """Its call would turn the plug on: the misroute the guard exists to prevent."""
    plug(hass, broker)
    sibling(hass, "switch.plug_child_lock", "switch_child_lock", category=category, disabled=disabled)
    allow_labs(hass)

    assert verdict(hass, "switch.plug_child_lock") == Reason.NOT_ADDRESSABLE
    if not disabled:
        data = {"entity_id": "switch.plug_child_lock", "duration": 5}
        assert await refusal(hass, "turn_on_for", data) == "not_addressable"
    assert commands(broker) == []


async def test_a_config_switch_on_a_sensor_is_refused(hass, setup_production, broker):
    """A presence sensor's indicator is its device's only `switch`: counted once, it used to pass."""
    add_z2m_entity(
        hass, z2m_entry(hass), "switch.sensor_indicator", unique_object_id="switch_indicator", manufacturer="Tuya"
    )
    allow_labs(hass)

    assert verdict(hass, "switch.sensor_indicator") == Reason.NOT_ADDRESSABLE
    assert verdict(hass, "switch.sensor_indicator", reads_state=True) == Reason.NOT_ADDRESSABLE


async def test_a_device_whose_unique_id_ends_in_another_base_topic_is_refused(hass, setup_production, broker):
    """Its unique_id ends in its base topic, and the topics here name the default: the publish would reach nothing."""
    add_z2m_entity(hass, z2m_entry(hass), "switch.plug", manufacturer=PLUG[0], base_topic="z2m", name="plug")
    allow_labs(hass)

    assert verdict(hass, "switch.plug") == Reason.NOT_ADDRESSABLE
    assert await refusal(hass, "turn_on_for", {"entity_id": "switch.plug", "duration": 5}) == "not_addressable"
    assert commands(broker) == []


async def test_a_switch_group_falls_back_to_a_plug_beside_its_child_lock(hass, setup_production, broker):
    """The member is the plug's state switch, though the child lock registered first, and it is addressable."""
    sibling(hass, "switch.plug_child_lock", "switch_child_lock", ieee="0x03", category=EntityCategory.CONFIG)
    plug(hass, broker, ieee="0x03")
    add_z2m_group(hass, entry(hass), "switch.lamps", group_id=9, name="lamps")
    broker.retained[GROUPS] = [{"id": 9, "members": [{"ieee_address": "0x03"}]}]

    listed = INTEGRATION.expand_group(hass, resolve(hass, get_runtime(hass).registry, "switch.lamps"))

    assert [(member.entity_id, member.addressable) for member in listed] == [("switch.plug", True)]


async def test_a_bulb_is_addressed(hass, setup_production, broker):
    """The unsuffixed light: Z2M's `<ieee>_light_zigbee2mqtt`."""
    entity_id = light(hass, broker, "light.one", "0x01")

    assert verdict(hass, entity_id) is None
