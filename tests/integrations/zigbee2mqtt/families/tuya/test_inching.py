"""Zigbee2MQTT set_auto_off and clear_auto_off on Tuya's inching (docs/plans/2026-11-24-zigbee2mqtt-inching.md, step 3):
the two maker strings that class, the one publish each action sends with its fields, the limits, and the devices that
must stay `tuya_zcl`: the TS000F variant of the WHD02's string, and the enabled string reported to have no effect."""

import pytest

from custom_components.deviceside.core.rules import match
from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.zigbee2mqtt import ADAPTERS
from custom_components.deviceside.integrations.zigbee2mqtt.families import tuya
from custom_components.deviceside.integrations.zigbee2mqtt.families.tuya import inching
from custom_components.deviceside.zigbee import tuya as catalog

from ...conftest import DEVICES, SET, answer, call, commands, failure, group, light
from .....conftest import allow_labs, refusal

SENT = {"status": "sent", "integration": "zigbee2mqtt"}
COMPOSITE = {"type": "composite", "name": "inching_control_set", "property": "inching_control_set", "access": 2}
STATE = {"type": "switch", "features": [{"name": "state", "property": "state"}]}
ENABLE = {"inching_control_1": "ENABLE", "inching_time_1": 5}
DISABLE = {"inching_control_1": "DISABLE", "inching_time_1": 1}
# The two strings, each as Zigbee2MQTT lists it: the WHD02 (research/tuya/2026-11-24-inching.md, ZHC#13879) and the Mowe
# MW781Z (ZHC#13118), by the maker string, the Zigbee model and the definition's model.
WHD02 = ("_TZ3000_skueekg3", "TS0001", "WHD02")
MW781Z = ("_TZ300A_rncj86af", "TS0726", "TS0726_1_gang_scene_switch")
# The WHD02's TS000F variant (ZHC enables inching on its TS0001 alone), and the Moes ZM4LT3, enabled and reported having
# no effect (Z2M #30056).
WHD02_TS000F = ("_TZ3000_skueekg3", "TS000F", "TS000F_switch_module_1")
NO_EFFECT = ("_TZ3000_mzcp0of6", "TS0003", "TS0003_switch_module_2")


def switch(hass, broker, strings=WHD02, exposes=None, entity_id: str = "switch.relay", ieee: str = "0x01") -> str:
    """A Tuya switch Z2M registers under its definition (vendor Tuya), listed in bridge/devices with its exposes."""
    manufacturer, model, definition = strings
    light(hass, broker, entity_id, ieee, manufacturer="Tuya", model_id=definition, zigbee=(manufacturer, model))
    entry = next(device for device in broker.retained[DEVICES] if device["ieee_address"] == ieee)
    entry["definition"] = {"model": definition, "exposes": [STATE, COMPOSITE] if exposes is None else exposes}
    return entity_id


def request(service: str, entity_id: str) -> dict:
    """The call's data: clear_auto_off takes no duration."""
    return {"entity_id": entity_id} | ({"duration": 5} if service == "set_auto_off" else {})


def topic(ieee: str = "0x01") -> str:
    return SET.replace(SET.split("/")[1], ieee)


def fields(strings, *exposes: str) -> dict:
    return {
        "zigbee_manufacturer": strings[0],
        "zigbee_model": strings[1],
        "definition_model": strings[2],
        "exposes": frozenset(exposes),
    }


@pytest.mark.parametrize("strings", [WHD02, MW781Z], ids=["whd02", "mw781z"])
def test_each_measured_string_with_the_composite_is_tuya_inching(strings):
    assert match(tuya.ZIGBEE_RULES, fields(strings, "state", "inching_control_set")) == "tuya_inching"


@pytest.mark.parametrize(
    "device",
    [
        pytest.param(fields(WHD02, "state"), id="whd02_without_the_composite"),
        pytest.param(fields(WHD02_TS000F, "state"), id="whd02_ts000f_variant"),
        pytest.param(fields(NO_EFFECT, "state", "inching_control_set"), id="enabled_string_reported_no_effect"),
        pytest.param(fields(("_TZ3000_p26flek3", "TS0001", "TS0001"), "state"), id="removed_string"),
        pytest.param(fields(("_TZ3000_abcdefgh", "TS0001", "TS0001"), "state", "inching_control_set"), id="no_record"),
        pytest.param(fields(("_TZ3000_skueekg3x", "TS0001", "WHD02"), "state", "inching_control_set"), id="longer"),
    ],
)
def test_the_other_strings_stay_tuya_zcl(device):
    assert match(tuya.ZIGBEE_RULES, device) == "tuya_zcl"


def test_the_catalog_holds_the_two_strings_and_no_other_class_carries_them():
    assert (catalog.INCHING_WHD02_MANUFACTURER, catalog.INCHING_MW781Z_MANUFACTURER) == (WHD02[0], MW781Z[0])
    assert not {WHD02[0], MW781Z[0], NO_EFFECT[0]} & {*tuya.VERIFIED_STRINGS, catalog.COUNTDOWN_HARMED_MANUFACTURER}


def test_the_two_adapters_serve_only_their_own_calls_in_labs_on_switches():
    scopes = {adapter.action: adapter.scope for adapter in ADAPTERS}
    for action, own in (("set_auto_off", inching.SET_AUTO_OFF), ("clear_auto_off", inching.CLEAR_AUTO_OFF)):
        scope = scopes[action]
        assert scope.own_calls_only
        assert scope.own_calls["tuya_inching"] is own
        assert scope.class_level("tuya_inching", "switch") is Level.LABS
        assert "tuya_zcl" not in scope.capabilities
    limits = inching.SET_AUTO_OFF.limits
    assert (limits.min_s, limits.max_s, limits.step_s) == (1, 65535, 1)
    assert inching.CLEAR_AUTO_OFF.limits is None


def test_neither_string_is_in_a_class_turn_on_for_serves():
    """Inching and Tuya's countdown would share a channel, which research leaves unknown (plan, Tuya)."""
    scope = next(adapter.scope for adapter in ADAPTERS if adapter.action == "turn_on_for")
    assert "tuya_inching" not in scope.capabilities
    assert "tuya_inching" in scope.not_built
    for strings in (WHD02, MW781Z):
        assert match(tuya.ZIGBEE_RULES, fields(strings, "state", "inching_control_set", "countdown")) == "tuya_inching"
        assert match(tuya.ZIGBEE_RULES, fields(strings, "state", "countdown")) == "tuya_zcl"


@pytest.mark.parametrize("strings", [WHD02, MW781Z], ids=["whd02", "mw781z"])
async def test_set_auto_off_publishes_whole_seconds_for_gang_1(hass, setup_production, broker, strings):
    entity_id = switch(hass, broker, strings)
    allow_labs(hass)

    response = await call(hass, "set_auto_off", {"entity_id": entity_id, "duration": 5})

    assert response == {entity_id: SENT}
    # One publish with both fields: ZHC skips a gang missing either and sends an empty payload.
    assert commands(broker) == [(topic(), {"inching_control_set": ENABLE})]


@pytest.mark.parametrize("strings", [WHD02, MW781Z], ids=["whd02", "mw781z"])
async def test_clear_auto_off_publishes_disable_with_the_least_time(hass, setup_production, broker, strings):
    entity_id = switch(hass, broker, strings)
    allow_labs(hass)

    response = await call(hass, "clear_auto_off", {"entity_id": entity_id})

    assert response == {entity_id: SENT}
    assert commands(broker) == [(topic(), {"inching_control_set": DISABLE})]


@pytest.mark.parametrize(
    ("duration", "time", "clamped_to"),
    [
        pytest.param({"seconds": 1}, 1, None, id="least"),
        pytest.param({"seconds": 63}, 63, None, id="measured"),
        pytest.param({"seconds": 65535}, 65535, None, id="most"),
        pytest.param({"hours": 20}, 65535, 65535, id="past_the_most_clamped"),
        pytest.param({"milliseconds": 100}, 1, 1, id="below_the_least_clamped"),
    ],
)
async def test_the_time_is_whole_seconds_from_1_to_65535(hass, setup_production, broker, duration, time, clamped_to):
    entity_id = switch(hass, broker)
    allow_labs(hass)

    response = await call(hass, "set_auto_off", {"entity_id": entity_id, "duration": duration})

    assert response == {entity_id: SENT if clamped_to is None else SENT | {"clamped_to": clamped_to}}
    assert commands(broker) == [(topic(), {"inching_control_set": ENABLE | {"inching_time_1": time}})]


@pytest.mark.parametrize("service", ["set_auto_off", "clear_auto_off"])
async def test_labs_off_refuses_and_sends_nothing(hass, setup_production, broker, service):
    entity_id = switch(hass, broker)
    allow_labs(hass, False)

    assert await refusal(hass, service, request(service, entity_id)) == "labs_off"
    assert commands(broker) == []


@pytest.mark.parametrize("service", ["set_auto_off", "clear_auto_off"])
@pytest.mark.parametrize(
    ("strings", "exposes"),
    [
        # ZHC enables the WHD02's inching on its TS0001 model alone, so the TS000F variant exposes no composite.
        pytest.param(WHD02_TS000F, [STATE], id="whd02_ts000f_variant"),
        # Enabled in ZHC, reported having no effect: it exposes the composite, but isn't one of the two strings.
        pytest.param(NO_EFFECT, None, id="enabled_string_reported_no_effect"),
    ],
)
async def test_a_device_off_the_two_strings_is_refused_as_not_built(
    hass, setup_production, broker, service, strings, exposes
):
    entity_id = switch(hass, broker, strings, exposes)
    allow_labs(hass)

    assert await refusal(hass, service, request(service, entity_id)) == "not_built"
    assert commands(broker) == []


@pytest.mark.parametrize("service", ["set_auto_off", "clear_auto_off"])
async def test_the_whd02_without_the_composite_is_refused_as_not_built(hass, setup_production, broker, service):
    entity_id = switch(hass, broker, exposes=[STATE])
    allow_labs(hass)

    assert await refusal(hass, service, request(service, entity_id)) == "not_built"
    assert commands(broker) == []


@pytest.mark.usefixtures("live")
async def test_a_set_z2m_logs_failed_is_rejected(hass, setup_production, broker):
    entity_id = switch(hass, broker)
    allow_labs(hass)
    line = (
        "Publish 'set' 'inching_control_set' to 'relay' failed: 'Error: ZCL command 0x01/1 "
        "manuSpecificTuya4.write({\"attributes\":[]}) failed (Delivery failed for '12345')'"
    )
    answer(broker, topic(), line=line)

    assert await failure(hass, "set_auto_off", request("set_auto_off", entity_id)) == f"{entity_id}: send_failed"


async def test_a_group_falls_back_so_each_member_gets_its_own_call(hass, setup_production, broker):
    """A Z2M group's call isn't the composite, so the group falls back to its members."""
    entity_id = group(
        hass, broker, one={"manufacturer": "Tuya", "model_id": "WHD02", "zigbee": (WHD02[0], WHD02[1])}, two={}
    )
    for entry in broker.retained[DEVICES]:
        if entry["ieee_address"] == "0x01":
            entry["definition"] = {"model": WHD02[2], "exposes": [STATE, COMPOSITE]}
    allow_labs(hass)

    response = await call(hass, "set_auto_off", {"entity_id": entity_id, "duration": 5})

    assert [*commands(broker)] == [(topic("0x01"), {"inching_control_set": ENABLE})]
    assert response["light.one"]["status"] == "sent"
