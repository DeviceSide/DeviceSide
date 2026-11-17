"""Zigbee2MQTT's refusal entries (refusals.py): the classes turn_on_for refuses because today's call would harm them,
and what the user reads. The integration's, as the entries are: a family's own tests cover its levels and calls."""

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside import actions
from custom_components.deviceside.core.errors import TargetNotSupported
from custom_components.deviceside.core.scope import NotBuilt
from custom_components.deviceside.integrations.zigbee2mqtt import ADAPTERS
from custom_components.deviceside.integrations.zigbee2mqtt.refusals import REFUSALS

from .conftest import DEVICES, PLUG, TUYA, commands, interviewed, light
from ...conftest import allow_experimental, refusal
from ...conftest import call as call_service
from ...fixtures.zigbee2mqtt import IEEE, add_z2m_entity, z2m_entry

COUNTDOWN = {"type": "numeric", "name": "countdown", "property": "countdown"}
FAILURE_HARMS = {action.key: action.failure_harms for action in actions.discover()}


def test_turn_on_for_alone_refuses_classes_and_harms_there_alone():
    """No Z2M class has no known method: each refused one has a call that would work, not built yet. turn_on_for's
    failure harms, so the dispatcher refuses a device it can't place too; no other Z2M adapter does."""
    assert REFUSALS.keys() == {"turn_on_for"}
    assert set(REFUSALS["turn_on_for"]) == {"tuya_ts011f", "tuya_zcl", "tuya_mcu", "tuya_countdown_harmed"}
    assert all(isinstance(entry, NotBuilt) for entry in REFUSALS["turn_on_for"].values())
    assert [adapter.action for adapter in ADAPTERS if adapter.scope.harms(FAILURE_HARMS[adapter.action])] == [
        "turn_on_for"
    ]


def test_each_entry_is_in_its_adapter_s_scope():
    scopes = {adapter.action: adapter.scope for adapter in ADAPTERS}

    assert {action: dict(scope.not_built) for action, scope in scopes.items() if scope.not_built} == REFUSALS
    assert not any(scope.no_known_method for scope in scopes.values())


async def test_turn_on_for_refuses_a_ts011f_as_not_built_with_experimental_on(hass, setup_production, broker):
    """Z2M has no on_time converter for it, so today's call would turn the plug on with no timer
    (research/2026-11-14-lab-probe.md, §2): refused, not flagged, so Experimental features can't send it."""
    allow_experimental(hass)
    add_z2m_entity(hass, z2m_entry(hass), "switch.plug", manufacturer=PLUG[0], model_id=PLUG[1])
    broker.retained[DEVICES] = [interviewed(IEEE, TUYA, "TS011F")]

    assert await refusal(hass, "turn_on_for", {"entity_id": "switch.plug", "duration": 5}) == "not_built"
    assert commands(broker) == []


async def test_the_ts011f_s_refusal_says_what_the_user_sees(hass, setup_production, broker):
    allow_experimental(hass)
    add_z2m_entity(hass, z2m_entry(hass), "switch.plug", manufacturer=PLUG[0], model_id=PLUG[1])
    broker.retained[DEVICES] = [interviewed(IEEE, TUYA, "TS011F")]

    with pytest.raises(HomeAssistantError) as raised:
        await call_service(hass, "turn_on_for", {"entity_id": "switch.plug", "duration": 5})
    assert raised.value.translation_placeholders["why"] == REFUSALS["turn_on_for"]["tuya_ts011f"].reason
    assert "no timer, so it would stay on" in raised.value.translation_placeholders["why"]


@pytest.mark.parametrize(
    "registry",
    [
        pytest.param(("Tuya", "TS0001_switch_module"), id="tuya_zcl"),
        pytest.param(("Tuya", "TS0601_switch"), id="tuya_mcu"),
    ],
)
async def test_turn_on_for_refuses_every_tuya_class_as_not_built_with_experimental_on(
    hass, setup_production, broker, registry
):
    """Z2M turns `on_time` into a plain On on Tuya firmware (Decision 20), so the device would stay on."""
    allow_experimental(hass)
    entity_id = light(hass, broker, manufacturer=registry[0], model_id=registry[1])

    assert await refusal(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5}) == "not_built"
    assert commands(broker) == []


async def test_the_string_reported_harmed_on_the_countdown_is_not_built_with_experimental_on(
    hass, setup_production, broker
):
    """A countdown plug by its definition, so it would get Tuya's countdown, which its maker string is reported to
    fail with harm (Zigbee2MQTT #30493)."""
    add_z2m_entity(hass, z2m_entry(hass), "switch.plug", manufacturer=PLUG[0], model_id=PLUG[1])
    definition = {"model": PLUG[1], "exposes": [{"type": "switch", "features": [{"name": "state"}]}, COUNTDOWN]}
    broker.retained[DEVICES] = [interviewed(IEEE, "_TZ3000_gjnozsaz", "TS011F") | {"definition": definition}]
    allow_experimental(hass)

    with pytest.raises(TargetNotSupported) as raised:
        await call_service(hass, "turn_on_for", {"entity_id": "switch.plug", "duration": 5})

    assert raised.value.reason == "not_built"
    assert raised.value.translation_placeholders["why"] == REFUSALS["turn_on_for"]["tuya_countdown_harmed"].reason
    assert commands(broker) == []
