"""Zigbee2MQTT's standard lights: where the class lands on the catalog's table (zigbee/standard_lights.py, whose own
tests are tests/zigbee/test_standard_lights.py), and its levels with the Labs option off (docs/evidence.md,
Documented, a pass-through request)."""

from types import SimpleNamespace

import pytest

from custom_components.deviceside.core.scope import OTHER, Level
from custom_components.deviceside.integrations.zigbee2mqtt import ADAPTERS, INTEGRATION
from custom_components.deviceside.integrations.zigbee2mqtt.classes import device_class
from custom_components.deviceside.zigbee.reasons import OTHER_TIMER_REASON
from custom_components.deviceside.zigbee.standard_lights import STANDARD_LIGHT

from .conftest import DEVICES, SENT, SET, call, commands, light, target
from ...conftest import refusal, result

MEMBER = ("OSRAM", "4058075816718")  # a member whose light exposes color_hs
MEMBER_WITHOUT_HS = ("LEDVANCE", "4058075168572")
NINE = {
    "raise_brightness",
    "lower_brightness",
    "stop",
    "raise_hue",
    "lower_hue",
    "raise_saturation",
    "lower_saturation",
    "set_attributes",
    "get_attributes",
}


def _scopes() -> dict:
    return {adapter.action: adapter.scope for adapter in ADAPTERS}


def _defined(broker, model: str) -> None:
    """Give the last light() its definition's model in bridge/devices, as Zigbee2MQTT publishes it."""
    broker.retained[DEVICES][-1]["definition"]["model"] = model


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        (MEMBER[1], STANDARD_LIGHT),
        ("924.70", OTHER),  # excluded
        ("RB 285 C", OTHER),  # turnsOffAtBrightness1
        ("NEW-MODEL", OTHER),
    ],
)
def test_the_definition_model_places_the_class(model, expected):
    registry = SimpleNamespace(manufacturer="Acme", model=None, model_id=model)
    bridge = {"zigbee_manufacturer": "Acme", "zigbee_model": "bulb", "definition_model": model}

    assert device_class(registry, bridge) == expected


@pytest.mark.parametrize("action", sorted(NINE))
def test_a_member_is_documented_on_the_nine_actions_and_other_is_not(action):
    scope = _scopes()[action]

    assert scope.class_level(STANDARD_LIGHT, "light") is Level.DOCUMENTED
    assert scope.refusal([STANDARD_LIGHT], domain="light", failure_harms=False) is None
    # `other` keeps its levels: in Labs or not built, never Documented.
    assert scope.class_level(OTHER, "light") is Level.LABS


@pytest.mark.parametrize("action", ["get_attributes", "set_attributes"])
def test_reads_and_writes_serve_a_member_on_lights_alone(action):
    assert not _scopes()[action].admits(STANDARD_LIGHT, "switch")


def test_another_brand_s_switch_stays_refused_on_get_attributes():
    assert _scopes()["get_attributes"].refusal([OTHER], domain="switch", failure_harms=False) == ("not_built", None)


@pytest.mark.parametrize("action", ["turn_off_for", "set_auto_off", "clear_auto_off"])
def test_the_other_actions_are_not_built(action):
    assert STANDARD_LIGHT not in _scopes()[action].capabilities


def test_turn_on_for_refuses_a_member_with_other_s_entry():
    scope = _scopes()["turn_on_for"]

    assert scope.refusal([STANDARD_LIGHT], domain="light", failure_harms=True) == ("not_built", OTHER_TIMER_REASON)


async def test_a_member_fades_with_labs_off(hass, setup_production, broker):
    entity_id = light(hass, broker, manufacturer=MEMBER[0], model_id=MEMBER[1])
    _defined(broker, MEMBER[1])

    assert INTEGRATION.capability(hass, target(hass, entity_id)) == STANDARD_LIGHT
    response = await call(hass, "raise_brightness", {"entity_id": entity_id})

    assert response == {entity_id: SENT}
    assert commands(broker) == [(SET, {"state": "ON", "brightness": 254, "transition": 2.0})]


@pytest.mark.parametrize("model", ["924.70", "RB 285 C"])
async def test_an_excluded_or_flagged_light_stays_in_labs(hass, setup_production, broker, model):
    entity_id = light(hass, broker, manufacturer="Acme", model_id=model)
    _defined(broker, model)

    assert await refusal(hass, "raise_brightness", {"entity_id": entity_id}) == "labs_off"
    assert commands(broker) == []


@pytest.mark.parametrize("action", ["raise_hue", "raise_saturation"])
async def test_a_member_without_color_hs_drops_a_hue_or_saturation_move(hass, setup_production, broker, action):
    """One class for hue and saturation (Decision 15): a member that doesn't expose color_hs is never sent the move."""
    entity_id = light(hass, broker, manufacturer=MEMBER_WITHOUT_HS[0], model_id=MEMBER_WITHOUT_HS[1], color_hs=False)
    _defined(broker, MEMBER_WITHOUT_HS[1])

    response = await call(hass, action, {"entity_id": entity_id})

    assert response == {entity_id: result("zigbee2mqtt", "unchanged", detail="fields_dropped")}
    assert commands(broker) == []
