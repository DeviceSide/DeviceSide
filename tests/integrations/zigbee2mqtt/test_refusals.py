"""Zigbee2MQTT's refusal entries (refusals.py), as the dispatcher applies them and the user reads them: turn_on_for's
failure harms, and what a refused light and plug say. The integration's, as the entries are: a family's own tests
cover its levels and calls."""

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside import actions
from custom_components.deviceside.core.errors import TargetNotSupported
from custom_components.deviceside.integrations.zigbee2mqtt import ADAPTERS
from custom_components.deviceside.integrations.zigbee2mqtt.refusals import REFUSALS

from .conftest import DEVICES, PLUG, TUYA, commands, interviewed, light
from ...conftest import allow_experimental
from ...conftest import call as call_service
from ...fixtures.zigbee2mqtt import IEEE, add_z2m_entity, z2m_entry

FAILURE_HARMS = {action.key: action.failure_harms for action in actions.discover()}


def test_turn_on_for_alone_harms():
    """turn_on_for's failure harms, so the dispatcher refuses a device it can't place too; no other Z2M adapter does."""
    assert [adapter.action for adapter in ADAPTERS if adapter.scope.harms(FAILURE_HARMS[adapter.action])] == [
        "turn_on_for"
    ]


async def test_turn_on_for_refuses_another_brand_s_light_as_not_built_with_experimental_on(
    hass, setup_production, broker
):
    """No pass, and research names only some makers' lights as running the timer (docs/evidence.md, On trial)."""
    allow_experimental(hass)
    entity_id = light(hass, broker, manufacturer="Innr", model_id="RB 285 C")

    with pytest.raises(TargetNotSupported) as raised:
        await call_service(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5})

    assert raised.value.reason == "not_built"
    assert raised.value.translation_placeholders["why"] == REFUSALS["turn_on_for"]["other"].reason
    assert commands(broker) == []


async def test_the_ts011f_s_refusal_says_what_the_user_sees(hass, setup_production, broker):
    allow_experimental(hass)
    add_z2m_entity(hass, z2m_entry(hass), "switch.plug", manufacturer=PLUG[0], model_id=PLUG[1])
    broker.retained[DEVICES] = [interviewed(IEEE, TUYA, "TS011F")]

    with pytest.raises(HomeAssistantError) as raised:
        await call_service(hass, "turn_on_for", {"entity_id": "switch.plug", "duration": 5})
    assert raised.value.translation_placeholders["why"] == REFUSALS["turn_on_for"]["tuya_ts011f"].reason
    assert "no timer, so it would stay on" in raised.value.translation_placeholders["why"]
