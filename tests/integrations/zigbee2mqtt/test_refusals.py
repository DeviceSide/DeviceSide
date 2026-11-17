"""Zigbee2MQTT's refusal entries (refusals.py): the classes turn_on_for refuses because today's call would harm them,
the countdown plugs get_attributes can't read a timer of, and what the user reads. The integration's, as the entries
are: a family's own tests cover its levels and calls."""

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside import actions
from custom_components.deviceside.core.errors import TargetNotSupported
from custom_components.deviceside.core.scope import NoKnownMethod, NotBuilt
from custom_components.deviceside.integrations.zigbee2mqtt import ADAPTERS
from custom_components.deviceside.integrations.zigbee2mqtt.families import tuya
from custom_components.deviceside.integrations.zigbee2mqtt.refusals import REFUSALS

from .conftest import DEVICES, PLUG, TUYA, commands, interviewed, light
from ...conftest import allow_experimental, refusal
from ...conftest import call as call_service
from ...fixtures.zigbee2mqtt import IEEE, add_z2m_entity, z2m_entry

COUNTDOWN = {"type": "numeric", "name": "countdown", "property": "countdown"}
FAILURE_HARMS = {action.key: action.failure_harms for action in actions.discover()}


def test_turn_on_for_alone_refuses_classes_not_built_and_harms_there_alone():
    """Each class turn_on_for refuses has a call that would work, not built yet. turn_on_for's failure harms, so the
    dispatcher refuses a device it can't place too; no other Z2M adapter does."""
    assert REFUSALS.keys() == {"turn_on_for", "get_attributes"}
    assert set(REFUSALS["turn_on_for"]) == {
        "other",
        "hue",
        "tuya_ts011f",
        "tuya_zcl",
        "tuya_mcu",
        "tuya_countdown_harmed",
    }
    assert all(isinstance(entry, NotBuilt) for entry in REFUSALS["turn_on_for"].values())
    assert [adapter.action for adapter in ADAPTERS if adapter.scope.harms(FAILURE_HARMS[adapter.action])] == [
        "turn_on_for"
    ]


def test_get_attributes_has_no_known_method_on_every_countdown_plug():
    """The time left can't be read (internals.md, Tuya's countdown, P6), on the Verified strings and the rest alike
    (docs/evidence.md, "A read serves only"). A read leaves nothing on or off, so get_attributes' failure doesn't
    harm."""
    assert set(REFUSALS["get_attributes"]) == set(tuya.COUNTDOWNS)
    for entry in REFUSALS["get_attributes"].values():
        assert isinstance(entry, NoKnownMethod)
        assert entry.source.endswith("research/2026-11-15-tuya-countdown-probe.md")


def test_each_entry_is_in_its_adapter_s_scope():
    scopes = {adapter.action: adapter.scope for adapter in ADAPTERS}

    assert {action: dict(scope.not_built) for action, scope in scopes.items() if scope.not_built} == {
        "turn_on_for": REFUSALS["turn_on_for"]
    }
    assert {action: dict(scope.no_known_method) for action, scope in scopes.items() if scope.no_known_method} == {
        "get_attributes": REFUSALS["get_attributes"]
    }


async def test_turn_on_for_refuses_a_ts011f_as_not_built_with_experimental_on(hass, setup_production, broker):
    """Z2M has no on_time converter for it, so today's call would turn the plug on with no timer
    (research/2026-11-14-lab-probe.md, §2): refused, not flagged, so Experimental features can't send it."""
    allow_experimental(hass)
    add_z2m_entity(hass, z2m_entry(hass), "switch.plug", manufacturer=PLUG[0], model_id=PLUG[1])
    broker.retained[DEVICES] = [interviewed(IEEE, TUYA, "TS011F")]

    assert await refusal(hass, "turn_on_for", {"entity_id": "switch.plug", "duration": 5}) == "not_built"
    assert commands(broker) == []


@pytest.mark.parametrize("manufacturer", ["Philips", "Innr"], ids=["hue", "other"])
async def test_turn_on_for_refuses_a_plug_with_no_switch_pass_as_not_built_with_experimental_on(
    hass, setup_production, broker, manufacturer
):
    """Research predicts most plugs and switches fail OnWithTimedOff (research/2026-11-14-timed-on-call-patterns.md),
    and no Hue or other brand's plug has a pass (docs/evidence.md, On trial): refused, so Experimental features can't
    send it, with why."""
    allow_experimental(hass)
    add_z2m_entity(hass, z2m_entry(hass), "switch.plug", manufacturer=manufacturer, model_id="SP 120")
    broker.retained[DEVICES] = [interviewed(IEEE, manufacturer, "SP 120")]

    with pytest.raises(TargetNotSupported) as raised:
        await call_service(hass, "turn_on_for", {"entity_id": "switch.plug", "duration": 5})

    assert raised.value.reason == "not_built"
    assert "plugs and switches ignore the timer" in raised.value.translation_placeholders["why"]
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
