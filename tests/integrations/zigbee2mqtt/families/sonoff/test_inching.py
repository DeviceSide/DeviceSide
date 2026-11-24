"""Zigbee2MQTT's Sonoff family: which definitions are its classes, and set_auto_off and clear_auto_off on them
(docs/plans/2026-11-24-zigbee2mqtt-inching.md, step 2): the one publish each sends with its fields, the limits, a set
Z2M logs as failed, the S60 plugs and the 2-gang refused, and the other Zigbee classes left out. The order between its
rule group and the other families' is the integration's (test_classification.py)."""

import pytest

from custom_components.deviceside.core.rules import match
from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.zigbee2mqtt import ADAPTERS, rules
from custom_components.deviceside.integrations.zigbee2mqtt.families import sonoff
from custom_components.deviceside.integrations.zigbee2mqtt.families.sonoff import inching

from ...conftest import DEVICES, SET, answer, call, commands, failure, group, light
from .....conftest import allow_labs, refusal

SENT = {"status": "sent", "integration": "zigbee2mqtt"}
COMPOSITE = {"type": "composite", "name": "inching_control_set", "property": "inching_control_set", "access": 2}
STATE = {"type": "switch", "features": [{"name": "state", "property": "state"}]}
ENABLE = {"inching_control": "ENABLE", "inching_time": 1.0, "inching_mode": "OFF"}
# Every allowlisted definition model (ZHC src/devices/sonoff.ts), by the entity the device shows as.
MODELS = ["ZBMINIR2", "MINI-ZBD", "ZBMicro", "MINI-ZB1GS", "MINI-ZB1GSP", "BASIC-ZB1GSP", "S61SZBTPB", "MINI-ZBDIM"]


def relay(
    hass, broker, definition: str = "ZBMINIR2", entity_id: str = "switch.relay", exposes=None, ieee="0x01"
) -> str:
    """A Sonoff device Z2M registers under its definition, listed in bridge/devices with its exposes."""
    light(
        hass,
        broker,
        entity_id,
        ieee,
        manufacturer="SONOFF",
        model_id=definition,
        zigbee=("SONOFF", definition),
    )
    entry = next(device for device in broker.retained[DEVICES] if device["ieee_address"] == ieee)
    entry["definition"] = {"model": definition, "exposes": [STATE, COMPOSITE] if exposes is None else exposes}
    return entity_id


def request(service: str, entity_id: str) -> dict:
    """The call's data: clear_auto_off takes no duration."""
    return {"entity_id": entity_id} | ({"duration": 5} if service == "set_auto_off" else {})


def topic(ieee: str = "0x01") -> str:
    return SET.replace(SET.split("/")[1], ieee)


@pytest.mark.parametrize("model", MODELS)
def test_each_allowlisted_model_with_the_composite_is_sonoff_inching(model):
    fields = {"definition_model": model, "exposes": frozenset({"state", "inching_control_set"})}
    assert match(sonoff.RULES, fields) == "sonoff_inching"


@pytest.mark.parametrize("model", ["S60ZBTPF", "S60ZBTPG"])
def test_the_s60_plugs_are_a_class_of_their_own(model):
    fields = {"definition_model": model, "exposes": frozenset({"state", "inching_control_set"})}
    assert match(sonoff.RULES, fields) == "sonoff_s60"


@pytest.mark.parametrize(
    "fields",
    [
        pytest.param({"definition_model": "ZBMINIR2", "exposes": frozenset({"state"})}, id="no_composite"),
        pytest.param({"definition_model": "MINI-ZB2GS", "exposes": frozenset({"state"})}, id="two_gang"),
        pytest.param({"definition_model": "ZBMINIR2x", "exposes": frozenset({"inching_control_set"})}, id="longer"),
        pytest.param({"definition_model": "MINI-ZBD2", "exposes": frozenset({"inching_control_set"})}, id="prefix"),
        pytest.param({"exposes": frozenset({"inching_control_set"})}, id="no_definition"),
    ],
)
def test_a_device_off_the_allowlist_or_without_the_composite_is_not_a_sonoff_class(fields):
    assert match(sonoff.RULES, fields) is None


def test_the_allowlist_is_the_plan_s():
    assert sorted(sonoff.INCHING_MODELS) == sorted(MODELS)
    assert sorted(sonoff.S60_MODELS) == ["S60ZBTPF", "S60ZBTPG"]


def test_the_two_adapters_serve_only_their_own_calls_in_labs_on_lights_and_switches():
    scopes = {adapter.action: adapter.scope for adapter in ADAPTERS}
    for action, own in (("set_auto_off", inching.SET_AUTO_OFF), ("clear_auto_off", inching.CLEAR_AUTO_OFF)):
        scope = scopes[action]
        assert scope.own_calls_only
        assert scope.own_calls["sonoff_inching"] is own
        assert not scope.confirmable
        assert not scope.native_groups
        assert scope.class_level("sonoff_inching", "light") is Level.LABS
        assert scope.class_level("sonoff_inching", "switch") is Level.LABS
        assert "sonoff_s60" in scope.not_built
    limits = inching.SET_AUTO_OFF.limits
    assert (limits.min_s, limits.max_s, limits.step_s) == (0.5, 3599.5, 0.5)
    assert inching.CLEAR_AUTO_OFF.limits is None


@pytest.mark.parametrize("definition", MODELS)
async def test_set_auto_off_publishes_the_composite_in_mode_off(hass, setup_production, broker, definition):
    entity_id = relay(hass, broker, definition, "light.lamp" if definition == "MINI-ZBDIM" else "switch.relay")
    allow_labs(hass)

    response = await call(hass, "set_auto_off", {"entity_id": entity_id, "duration": 1})

    assert response == {entity_id: SENT}
    # One publish, every field sent: ZHC turns the relay on at once for a write without mode OFF (ZHC#13383).
    assert commands(broker) == [(topic("0x01"), {"inching_control_set": ENABLE})]


async def test_clear_auto_off_publishes_disable_with_the_least_time_in_mode_off(hass, setup_production, broker):
    entity_id = relay(hass, broker)
    allow_labs(hass)

    response = await call(hass, "clear_auto_off", {"entity_id": entity_id})

    assert response == {entity_id: SENT}
    assert commands(broker) == [
        (
            topic("0x01"),
            {"inching_control_set": {"inching_control": "DISABLE", "inching_time": 0.5, "inching_mode": "OFF"}},
        )
    ]


@pytest.mark.parametrize(
    ("duration", "time", "clamped_to"),
    [
        pytest.param({"milliseconds": 500}, 0.5, None, id="least"),
        pytest.param({"milliseconds": 2500}, 2.5, None, id="half_second_step"),
        pytest.param({"seconds": 3599, "milliseconds": 500}, 3599.5, None, id="most"),
        pytest.param({"hours": 2}, 3599.5, 3599.5, id="past_the_most_clamped"),
        pytest.param({"milliseconds": 100}, 0.5, 0.5, id="below_the_least_clamped"),
    ],
)
async def test_the_time_is_half_seconds_from_0_5_to_3599_5(hass, setup_production, broker, duration, time, clamped_to):
    entity_id = relay(hass, broker)
    allow_labs(hass)

    response = await call(hass, "set_auto_off", {"entity_id": entity_id, "duration": duration})

    assert response == {entity_id: SENT if clamped_to is None else SENT | {"clamped_to": clamped_to}}
    assert commands(broker) == [(topic(), {"inching_control_set": ENABLE | {"inching_time": time}})]


@pytest.mark.parametrize("service", ["set_auto_off", "clear_auto_off"])
async def test_labs_off_refuses_and_sends_nothing(hass, setup_production, broker, service):
    entity_id = relay(hass, broker)
    allow_labs(hass, False)

    assert await refusal(hass, service, request(service, entity_id)) == "labs_off"
    assert commands(broker) == []


@pytest.mark.parametrize("service", ["set_auto_off", "clear_auto_off"])
async def test_the_s60_plugs_are_refused_as_not_built_on_both_actions(hass, setup_production, broker, service):
    """DISABLE is reported to have no effect on them (Z2M #31799), so clear_auto_off would leave the plug pulsing."""
    entity_id = relay(hass, broker, "S60ZBTPF")
    allow_labs(hass)

    assert await refusal(hass, service, request(service, entity_id)) == "not_built"
    assert commands(broker) == []


def test_a_two_gang_with_a_per_endpoint_composite_is_other():
    """ZHC's exposeEndpoints gives MINI-ZB2GS one composite per endpoint, so no endpoint-less property reaches the
    rule (rules.definition_fields)."""
    entry = {
        "definition": {
            "model": "MINI-ZB2GS",
            "exposes": [
                {**COMPOSITE, "endpoint": "l1", "property": "inching_control_set_l1"},
                {**COMPOSITE, "endpoint": "l2", "property": "inching_control_set_l2"},
            ],
        }
    }
    fields = rules.definition_fields(entry)

    assert fields["exposes"] == frozenset()
    assert match(sonoff.RULES, fields) is None


@pytest.mark.parametrize("service", ["set_auto_off", "clear_auto_off"])
async def test_the_two_gang_waits_on_per_endpoint_addressing(hass, setup_production, broker, service):
    """Its composite is per endpoint, so the device exposes none: it keeps `other`, which has no inching call."""
    entity_id = relay(hass, broker, "MINI-ZB2GS", exposes=[STATE])
    allow_labs(hass)

    assert await refusal(hass, service, request(service, entity_id)) == "not_built"
    assert commands(broker) == []


@pytest.mark.parametrize("service", ["set_auto_off", "clear_auto_off"])
async def test_until_bridge_devices_lists_it_a_sonoff_device_is_refused_as_class_unknown(
    hass, setup_production, broker, service
):
    """It could be an S60, which the call would leave pulsing, so the refusal covers a device not yet placed."""
    entity_id = relay(hass, broker)
    del broker.retained[DEVICES]
    allow_labs(hass)

    assert await refusal(hass, service, request(service, entity_id)) == "class_unknown"
    assert commands(broker) == []


@pytest.mark.parametrize("service", ["set_auto_off", "clear_auto_off"])
async def test_another_brand_is_refused_as_not_built(hass, setup_production, broker, service):
    entity_id = light(hass, broker, "switch.relay", manufacturer="Innr", model_id="SP 120", zigbee=("innr", "SP 120"))
    allow_labs(hass)

    assert await refusal(hass, service, request(service, entity_id)) == "not_built"
    assert commands(broker) == []


@pytest.mark.usefixtures("live")
async def test_a_set_z2m_logs_failed_is_rejected(hass, setup_production, broker):
    entity_id = relay(hass, broker)
    allow_labs(hass)
    line = (
        "Publish 'set' 'inching_control_set' to 'relay' failed: 'Error: ZCL command 0x01/1 ewelink.protocolData({}) "
        "failed (Delivery failed for '12345')'"
    )
    answer(broker, topic(), line=line)

    assert await failure(hass, "set_auto_off", request("set_auto_off", entity_id)) == f"{entity_id}: send_failed"


async def test_a_group_falls_back_so_each_member_gets_its_own_call(hass, setup_production, broker):
    """A Z2M group's call isn't the composite, so the group falls back to its members."""
    entity_id = group(
        hass, broker, one={"manufacturer": "SONOFF", "model_id": "ZBMINIR2", "zigbee": ("SONOFF", "ZBMINIR2")}, two={}
    )
    for entry in broker.retained[DEVICES]:
        if entry["ieee_address"] == "0x01":
            entry["definition"] = {"model": "ZBMINIR2", "exposes": [STATE, COMPOSITE]}
    allow_labs(hass)

    response = await call(hass, "set_auto_off", {"entity_id": entity_id, "duration": 1})

    # The Hue bulb has no call for it: only the Sonoff relay is sent one.
    assert [*commands(broker)] == [(topic("0x01"), {"inching_control_set": ENABLE})]
    assert response["light.one"]["status"] == "sent"
