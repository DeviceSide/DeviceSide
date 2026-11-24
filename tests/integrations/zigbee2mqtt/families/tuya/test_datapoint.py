"""Zigbee2MQTT turn_on_for on Tuya's datapoint countdown (docs/plans/2026-11-24-tuya-datapoint-single-endpoint.md, step
3): the one publish each class gets, its limit, a dimmer's light fields first, and a set Z2M logs as failed. Which
definitions take each class is test_classes.py's."""

import asyncio

import pytest
from homeassistant.core import ServiceCall

from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.zigbee2mqtt import light_turn_on
from custom_components.deviceside.integrations.zigbee2mqtt.families.tuya import datapoint
from custom_components.deviceside.integrations.zigbee2mqtt.turn_on_for import Z2MTurnOnFor

from ...conftest import DEVICES, SET, TUYA_MCU, answer, call, commands, failure, group, light
from .....conftest import allow_labs, refusal
from .....fixtures.zigbee2mqtt import IEEE

SENT = {"status": "sent", "integration": "zigbee2mqtt"}
STATE = {"type": "light", "features": [{"name": "state", "property": "state"}, {"name": "brightness"}]}
COUNTDOWN = {"type": "numeric", "name": "countdown", "property": "countdown", "unit": "s"}
# A definition of each class (datapoint.DATAPOINT_DEFINITIONS).
DIMMER = "TS0601_dimmer_1_gang_1"  # tuya_datapoint, 43,200 s
DAY = "TO-DM-W/B"  # tuya_datapoint_24h, 86,400 s
RELAY = "ZBS16"  # tuya_datapoint_2h, 7,210 s
# Converter B's state datapoint, undelivered: Z2M throws before the countdown's (light() names the device `lamp`).
STATE_UNDELIVERED = (
    f"Publish 'set' 'state' to 'lamp' failed: 'Error: ZCL command {IEEE}/1 manuSpecificTuya.dataRequest({{}}) failed "
    "(Delivery failed for '12345')'"
)


def datapoint_light(hass, broker, definition: str = DIMMER, entity_id: str = "light.lamp", ieee: str = IEEE) -> str:
    """A single-endpoint Tuya datapoint device Z2M registers under its definition, listed in bridge/devices with the
    device's countdown."""
    light(hass, broker, entity_id, ieee, manufacturer="Tuya", model_id=definition, zigbee=(TUYA_MCU, "TS0601"))
    entry = next(device for device in broker.retained[DEVICES] if device["ieee_address"] == ieee)
    entry["definition"] = {"model": definition, "exposes": [STATE, COUNTDOWN]}
    return entity_id


def test_each_datapoint_class_has_its_own_call_with_its_limit_in_labs_on_lights_and_switches():
    scope = Z2MTurnOnFor.scope
    for name, max_s in datapoint.CLASS_MAX_S.items():
        call_ = scope.own_calls[name]
        assert call_ is datapoint.DATAPOINT_CALLS[name]
        assert (call_.limits.min_s, call_.limits.max_s, call_.limits.step_s) == (1, max_s, 1)
        assert scope.class_level(name, "light") is Level.LABS
        assert scope.class_level(name, "switch") is Level.LABS
    # One send, one call object per class, so each class runs apart at its own limit.
    assert len({call_.send for call_ in datapoint.DATAPOINT_CALLS.values()}) == 1
    assert len(set(datapoint.DATAPOINT_CALLS.values())) == 3


@pytest.mark.parametrize("definition", [DIMMER, DAY, RELAY])
async def test_a_datapoint_device_gets_one_publish_with_state_then_countdown(
    hass, setup_production, broker, definition
):
    entity_id = datapoint_light(hass, broker, definition)
    allow_labs(hass)

    response = await call(hass, "turn_on_for", {"entity_id": entity_id, "duration": 30})

    assert response == {entity_id: SENT}
    # No on_time, which Z2M has no converter for on it, and no reads: the time left isn't served.
    assert commands(broker) == [(SET, {"state": "ON", "countdown": 30})]
    assert list(commands(broker)[0][1]) == ["state", "countdown"]


async def test_a_datapoint_device_is_refused_with_labs_off(hass, setup_production, broker):
    entity_id = datapoint_light(hass, broker)
    allow_labs(hass, False)

    assert await refusal(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5}) == "labs_off"
    assert commands(broker) == []


async def test_until_bridge_devices_lists_it_a_datapoint_device_is_refused_as_class_unknown(
    hass, setup_production, broker
):
    """Unplaced tuya_mcu, which today's call would harm, so refused rather than sent either call."""
    entity_id = datapoint_light(hass, broker)
    del broker.retained[DEVICES]
    allow_labs(hass)

    assert await refusal(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5}) == "class_unknown"
    assert commands(broker) == []


@pytest.mark.parametrize(
    ("definition", "duration", "countdown", "clamped_to"),
    [
        pytest.param(DIMMER, {"hours": 12}, 43200, None, id="twelve_hours"),
        pytest.param(DIMMER, {"hours": 24}, 43200, 43200, id="a_day_clamped_to_twelve_hours"),
        pytest.param(DAY, {"hours": 24}, 86400, None, id="a_day_on_the_day_class"),
        pytest.param(DAY, {"hours": 25}, 86400, 86400, id="past_a_day"),
        pytest.param(RELAY, {"hours": 24}, 7210, 7210, id="a_day_on_zbs16"),
        pytest.param(DIMMER, {"milliseconds": 10500}, 11, 11, id="rounded_half_up"),
        pytest.param(DIMMER, {"milliseconds": 300}, 1, 1, id="below_one_second"),
    ],
)
async def test_the_countdown_is_whole_seconds_from_1_to_the_class_s_limit(
    hass, setup_production, broker, definition, duration, countdown, clamped_to
):
    entity_id = datapoint_light(hass, broker, definition)
    allow_labs(hass)

    response = await call(hass, "turn_on_for", {"entity_id": entity_id, "duration": duration})

    assert response == {entity_id: SENT if clamped_to is None else SENT | {"clamped_to": clamped_to}}
    assert commands(broker) == [(SET, {"state": "ON", "countdown": countdown})]


async def test_a_dimmer_s_light_fields_go_first_by_light_turn_on(hass, setup_production, broker, monkeypatch):
    """light.turn_on applies the brightness and Z2M publishes the light's state, then the countdown goes out, its
    `state` first still."""
    monkeypatch.setattr(light_turn_on, "_STATE_TIMEOUT_S", 0.5)
    entity_id = datapoint_light(hass, broker)
    allow_labs(hass)
    events: list = []

    async def turn_on(service: ServiceCall) -> None:
        events.append(("light.turn_on", dict(service.data)))
        asyncio.get_running_loop().call_soon(broker.deliver, "zigbee2mqtt/lamp", '{"state":"ON"}')

    hass.services.async_register("light", "turn_on", turn_on)
    broker.on_set = lambda topic, payload: events.append((topic, payload))

    response = await call(hass, "turn_on_for", {"entity_id": entity_id, "duration": 30, "brightness": 50})

    assert response == {entity_id: SENT}
    assert events == [
        ("light.turn_on", {"entity_id": entity_id, "brightness": 128}),
        (SET, {"state": "ON", "countdown": 30}),
    ]


@pytest.mark.usefixtures("live")
async def test_a_countdown_set_z2m_logs_failed_is_rejected(hass, setup_production, broker):
    """Converter B awaits the state datapoint's send, so a lost one throws before the countdown's, and Z2M logs the set
    failed (research/2026-11-24-tuya-datapoint-call.md, §1): the device took nothing, and the call says so."""
    entity_id = datapoint_light(hass, broker)
    allow_labs(hass)
    answer(broker, SET, line=STATE_UNDELIVERED)

    assert await failure(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5}) == f"{entity_id}: send_failed"


async def test_a_group_with_a_datapoint_device_falls_back_so_each_gets_its_own_call(hass, setup_production, broker):
    """A Z2M group's call carries `on_time`, which Z2M has no converter for on a datapoint device, so the group falls
    back: the bulb gets on_time, the dimmer its countdown."""
    entity_id = group(hass, broker, one={}, two={"manufacturer": "Tuya", "zigbee": (TUYA_MCU, "TS0601")})
    entry = next(device for device in broker.retained[DEVICES] if device["ieee_address"] == "0x02")
    entry["definition"] = {"model": DIMMER, "exposes": [STATE, COUNTDOWN]}
    allow_labs(hass)

    response = await call(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5})

    assert set(response) == {"light.one", "light.two"}
    assert sorted(commands(broker), key=lambda command: command[0]) == [
        (SET.replace(IEEE, "0x01"), {"state": "ON", "on_time": 5.0}),
        (SET.replace(IEEE, "0x02"), {"state": "ON", "countdown": 5}),
    ]
