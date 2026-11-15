"""Zigbee2MQTT turn_on_for on Tuya's countdown (plan step 5 part 3): the classes that place a TS011F plug on
converter A, and the one publish it gets."""

import pytest

from custom_components.deviceside.actions.turn_on_for import TurnOnForRequest
from custom_components.deviceside.core.errors import TargetNotSupported
from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.core.scope import Level, Unplaced
from custom_components.deviceside.integrations.zigbee2mqtt import INTEGRATION, classes, turn_on_for
from custom_components.deviceside.integrations.zigbee2mqtt.turn_on_for import Z2MTurnOnFor

from .conftest import DEVICES, SET, call, commands, group
from .test_set_check import answer, failure, live  # noqa: F401 - live is a fixture
from ...conftest import allow_experimental, refusal
from ...conftest import call as call_service
from ...fixtures.zigbee2mqtt import IEEE, INFO, add_z2m_entity, z2m_entry

LAB = "_TZ3000_0zfrhq4i"  # the lab plug (research/2026-11-15-tuya-countdown-probe.md)
UNLISTED = "_TZ3000_abcdefgh"  # a converter A string with no record
COUNTDOWN = {"type": "numeric", "name": "countdown", "property": "countdown"}
SWITCH = {"type": "switch", "features": [{"name": "state"}]}
# Converter A's On, undelivered after herdsman's retries: Z2M throws before 0x42 (plug() names the device `plug`).
ON_UNDELIVERED = (
    f"Publish 'set' 'state' to 'plug' failed: 'Error: ZCL command {IEEE}/1 genOnOff.on({{}}) failed "
    "(Delivery failed for '12345')'"
)


def listed(ieee: str, manufacturer: str, model_id="TS011F", definition="TS011F_plug_1", exposes=(SWITCH, COUNTDOWN)):
    """A plug's bridge/devices entry once Zigbee2MQTT has interviewed it, with its definition."""
    return {
        "ieee_address": ieee,
        "manufacturer": manufacturer,
        "model_id": model_id,
        "interview_completed": True,
        "definition": {"model": definition, "exposes": list(exposes)},
    }


def plug(hass, broker, manufacturer: str = LAB, entity_id: str = "switch.plug", ieee: str = IEEE, **entry) -> str:
    """A TS011F plug Z2M exposes as a switch, registered as Z2M does (vendor Tuya, its definition's model)."""
    add_z2m_entity(
        hass,
        z2m_entry(hass),
        entity_id,
        ieee=ieee,
        state="off",
        manufacturer="Tuya",
        model_id="TS011F_plug_1",
        name=entity_id.split(".")[1],
    )
    broker.retained.setdefault(DEVICES, []).append(listed(ieee, manufacturer, **entry))
    return entity_id


def placed_class(hass, entity_id: str) -> str | None:
    return INTEGRATION.capability(hass, resolve(hass, get_runtime(hass).registry, entity_id))


@pytest.mark.parametrize(
    ("manufacturer", "entry", "expected"),
    [
        pytest.param(LAB, {}, "tuya_countdown_tz3000_0zfrhq4i", id="verified_string"),
        pytest.param("_TZ3000_okaz9tjs", {}, "tuya_countdown_tz3000_okaz9tjs", id="white_label"),
        pytest.param(UNLISTED, {}, "tuya_countdown", id="unlisted_string"),
        pytest.param("AOYAN", {}, "tuya_countdown", id="no_tuya_string"),  # a white label of TS011F_plug_1
        pytest.param(UNLISTED, {"definition": "TS011F_plug_3"}, "tuya_countdown", id="other_definition"),
        pytest.param("_TZ3000_gjnozsaz", {}, "tuya_countdown_harmed", id="reported_harmed"),
        # Z2M shows no countdown for it: converter A is installed but its call isn't Z2M's stated one.
        pytest.param(UNLISTED, {"exposes": (SWITCH,)}, "tuya_ts011f", id="no_countdown_expose"),
        pytest.param(LAB, {"exposes": (SWITCH,)}, "tuya_ts011f", id="verified_string_without_expose"),
        # One per endpoint: a multi-gang plug, not one countdown for the device.
        # ZHC's withEndpoint keeps the name and suffixes the property (TS011F_5).
        pytest.param(
            UNLISTED,
            {"exposes": (SWITCH, COUNTDOWN | {"property": "countdown_l1", "endpoint": "l1"})},
            "tuya_ts011f",
            id="gangs",
        ),
        # The datapoint countdown, converter B.
        pytest.param("_TZ3218_pfnjjx6a", {"definition": "ZOT60"}, "tuya_ts011f", id="zot60"),
        pytest.param(UNLISTED, {"model_id": "TS0001"}, "tuya_zcl", id="not_a_ts011f"),
        pytest.param(UNLISTED, {"definition": None, "exposes": ()}, "tuya_ts011f", id="no_definition"),
    ],
)
async def test_converter_a_s_plugs_are_placed_by_their_definition(
    hass, setup_production, broker, manufacturer, entry, expected
):
    entity_id = plug(hass, broker, manufacturer, **entry)
    if entry.get("definition", "") is None:
        broker.retained[DEVICES][-1]["definition"] = None

    found = placed_class(hass, entity_id)

    assert found == expected
    assert not isinstance(found, Unplaced)


async def test_until_bridge_devices_lists_it_a_countdown_plug_waits(hass, setup_production, broker):
    """The registry can't show the expose, so the plug keeps tuya_ts011f's refusal, provisionally, until it fills."""
    entity_id = plug(hass, broker)
    del broker.retained[DEVICES]
    allow_experimental(hass)

    assert placed_class(hass, entity_id) == Unplaced("tuya_ts011f")
    assert await refusal(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5}) == "class_unknown"


def test_each_verified_string_has_a_class_of_its_own_verified_on_switches_on_turn_on_for_alone():
    scope = Z2MTurnOnFor.scope
    for string in classes.VERIFIED_STRINGS:
        name = classes.string_class(string)
        assert name in INTEGRATION.classes
        # On switches alone, as Z2M shows a plug: one Z2M shows as a light has no record.
        assert scope.class_level(name, "switch") is Level.VERIFIED
        assert scope.class_level(name, "light") is Level.EXPERIMENTAL
    assert scope.capabilities["tuya_countdown"] is Level.EXPERIMENTAL
    assert set(scope.own_calls) == set(classes.COUNTDOWNS)
    assert "tuya_countdown_harmed" in scope.not_supported


async def test_a_countdown_plug_gets_one_publish_with_the_countdown(hass, setup_production, broker):
    entity_id = plug(hass, broker, UNLISTED)
    allow_experimental(hass)

    response = await call(hass, "turn_on_for", {"entity_id": entity_id, "duration": 30})

    assert response == {entity_id: {"status": "sent", "integration": "zigbee2mqtt"}}
    # No on_time, which Z2M has no converter for on it, and no state reads: the plug reports its state at expiry.
    assert commands(broker) == [(SET, {"state": "ON", "countdown": 30})]


@pytest.mark.parametrize(
    ("duration", "countdown", "clamped_to"),
    [
        pytest.param({"seconds": 10}, 10, None, id="whole_seconds"),
        pytest.param({"milliseconds": 10400}, 10, 10, id="rounded_down"),
        pytest.param({"milliseconds": 10500}, 11, 11, id="rounded_half_up"),
        pytest.param({"milliseconds": 300}, 1, 1, id="below_one_second"),
        pytest.param({"hours": 12}, 43200, None, id="twelve_hours"),
        pytest.param({"hours": 13}, 43200, 43200, id="past_twelve_hours"),
    ],
)
async def test_the_countdown_is_whole_seconds_from_1_to_43200(
    hass, setup_production, broker, duration, countdown, clamped_to
):
    """Z2M refuses anything else before sending (probe P7); a rounded or clamped one says what was sent."""
    entity_id = plug(hass, broker, UNLISTED)
    allow_experimental(hass)

    response = await call(hass, "turn_on_for", {"entity_id": entity_id, "duration": duration})

    expected = {"status": "sent", "integration": "zigbee2mqtt"}
    assert response == {entity_id: expected if clamped_to is None else expected | {"clamped_to": clamped_to}}
    assert commands(broker) == [(SET, {"state": "ON", "countdown": countdown})]


async def test_a_verified_string_runs_with_experimental_features_off(hass, setup_production, broker):
    entity_id = plug(hass, broker, LAB)

    assert await call(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5}) == {
        entity_id: {"status": "sent", "integration": "zigbee2mqtt"}
    }
    assert commands(broker) == [(SET, {"state": "ON", "countdown": 5})]


async def test_an_unrecorded_string_is_experimental(hass, setup_production, broker):
    entity_id = plug(hass, broker, UNLISTED)

    assert await refusal(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5}) == "experimental_off"
    assert commands(broker) == []


async def test_the_reported_string_is_not_supported_with_experimental_on(hass, setup_production, broker):
    entity_id = plug(hass, broker, "_TZ3000_gjnozsaz")
    allow_experimental(hass)

    with pytest.raises(TargetNotSupported) as raised:
        await call_service(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5})

    assert raised.value.reason == "not_supported"
    assert (
        raised.value.translation_placeholders["why"]
        == classes.TURN_ON_FOR_NOT_SUPPORTED["tuya_countdown_harmed"].reason
    )
    assert commands(broker) == []


async def test_a_group_with_a_countdown_plug_falls_back_so_each_gets_its_own_call(hass, setup_production, broker):
    """A Z2M group's call carries `on_time`, which Z2M would send the plug as a plain On or the spec's tenths, so the
    group falls back: the bulb gets on_time, the plug its countdown."""
    # The second member is the plug, which Z2M exposes as a light here, so it is a member HA can address.
    tuya = {"manufacturer": "Tuya", "model_id": "TS011F_plug_1", "zigbee": (UNLISTED, "TS011F")}
    entity_id = group(hass, broker, one={}, two=tuya)
    entry = next(device for device in broker.retained[DEVICES] if device["ieee_address"] == "0x02")
    entry["definition"] = {"model": "TS011F_plug_1", "exposes": [SWITCH, COUNTDOWN]}
    assert placed_class(hass, "light.two") == "tuya_countdown"
    allow_experimental(hass)

    response = await call(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5})

    assert set(response) == {"light.one", "light.two"}
    assert sorted(commands(broker), key=lambda command: command[0]) == [
        (SET.replace(IEEE, "0x01"), {"state": "ON", "on_time": 5.0}),
        (SET.replace(IEEE, "0x02"), {"state": "ON", "countdown": 5}),
    ]


@pytest.mark.usefixtures("live")
async def test_a_countdown_set_z2m_logs_failed_is_rejected(hass, setup_production, broker):
    """Z2M logs the set failed when the On isn't delivered, and sends no 0x42 after it (internals.md, Tuya's
    countdown): the plug took nothing, and the call says so."""
    entity_id = plug(hass, broker, UNLISTED)
    allow_experimental(hass)
    answer(broker, SET, line=ON_UNDELIVERED)

    assert await failure(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5}) == f"{entity_id}: send_failed"


async def test_get_attributes_reports_no_timer_for_a_countdown_plug(hass, setup_production, broker):
    """Its OnTime holds the countdown last set, in seconds, not the time left (probe P6): 600 would read as 60 s."""
    entity_id = plug(hass, broker, UNLISTED)
    hass.states.async_set(entity_id, "on", {})
    broker.devices[IEEE] = ("plug", {"genOnOff": {"onOff": 1, "onTime": 600}})
    broker.retained[INFO]["config"]["devices"].setdefault(IEEE, {})
    allow_experimental(hass)

    response = await call(hass, "get_attributes", {"entity_id": entity_id})

    assert response == {entity_id: {}}


async def test_execute_branches_on_the_limits_the_dispatcher_planned_not_a_fresh_class(hass, setup_production, broker):
    """#440's review, LM3: a bridge/devices republish between planning and execute must not send the plug `on_time`
    fitted to 43200 s, or a bulb `countdown`: the run's limits are the class the dispatcher planned on."""
    entity_id = plug(hass, broker, UNLISTED)
    registry = get_runtime(hass).registry
    adapter = registry.adapter("turn_on_for", "zigbee2mqtt")
    target = resolve(hass, registry, entity_id)
    planned = TurnOnForRequest(duration_s=30, limits=turn_on_for.COUNTDOWN_LIMITS)
    del broker.retained[DEVICES]  # the plug is no longer placed as a countdown class

    await adapter.execute(hass, planned, [target])

    assert commands(broker) == [(SET, {"state": "ON", "countdown": 30})]
