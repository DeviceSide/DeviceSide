"""Zigbee2MQTT hue_native_control: set as an action needs it for its own publish, then the user's value put back."""

import asyncio
import logging

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.deviceside.core.models import Target
from custom_components.deviceside.integrations.zigbee2mqtt import native_control as nc

from .conftest import SET, light
from ...conftest import call
from ...fixtures.z2m import GROUPS, IEEE, INFO, add_z2m_entity, add_z2m_group, z2m_entry

SENT = {"status": "sent", "integration": "zigbee2mqtt"}
DEVICE_REQUEST = "zigbee2mqtt/bridge/request/device/options"
DEVICE_RESPONSE = "zigbee2mqtt/bridge/response/device/options"
GROUP_REQUEST = "zigbee2mqtt/bridge/request/group/options"
GROUP_RESPONSE = "zigbee2mqtt/bridge/response/group/options"
MEMBER = "0x00124b00aaaaaaaa"
LOGGER = "custom_components.deviceside.integrations.zigbee2mqtt"
RED = {"entity_id": "light.lamp", "duration": 6, "rgb_color": [255, 0, 0]}


@pytest.fixture
def turn_ons(hass):
    return async_mock_service(hass, "light", "turn_on")


def hue_bulb(hass, entity_id: str = "light.lamp", manufacturer: str = "Philips") -> str:
    return add_z2m_entity(hass, z2m_entry(hass), entity_id, manufacturer=manufacturer)


def options(broker) -> list[bool]:
    """The hue_native_control value of each options request, in order."""
    return [request["payload"]["options"][nc.OPTION] for request in broker.requests()]


def target(hass, entity_id: str) -> Target:
    entry = er.async_get(hass).async_get(entity_id)
    device = dr.async_get(hass).async_get(entry.device_id)
    return Target(entity_id, "light", "zigbee2mqtt", entry, device, None, hass.states.get(entity_id))


# turn_on_for: on for a color, then put back


async def test_hue_bulb_gets_it_on_for_the_turn_on_then_back_before_the_timer(
    hass, setup_production, broker, turn_ons, caplog
):
    hue_bulb(hass)

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        response = await call(hass, "turn_on_for", RED)

    assert response == {"light.lamp": SENT}
    on, back = broker.requests()
    assert (on["topic"], on["payload"]["id"], on["payload"]["options"]) == (DEVICE_REQUEST, IEEE, {nc.OPTION: True})
    assert back["payload"]["options"] == {nc.OPTION: False}
    assert broker.published.index(back) < broker.published.index(broker.timers()[0])
    assert len(turn_ons) == 1
    assert "Set Zigbee2MQTT's hue_native_control to True for light.lamp" in caplog.text
    assert "Set Zigbee2MQTT's hue_native_control to False for light.lamp" in caplog.text
    assert not any(r.levelno >= logging.INFO for r in caplog.records if r.name.startswith(LOGGER))
    assert not broker.listening(DEVICE_RESPONSE) and not broker.listening(INFO)


@pytest.mark.parametrize("field", [{"color_temp_kelvin": 3000}, {"hs_color": [120, 100]}, {"xy_color": [0.2, 0.3]}])
async def test_every_color_field_triggers_it(hass, setup_production, broker, turn_ons, field):
    hue_bulb(hass)

    await call(hass, "turn_on_for", {"entity_id": "light.lamp", "duration": 6, **field})

    assert options(broker) == [True, False]


async def test_option_already_on_sends_no_request(hass, setup_production, broker, turn_ons):
    hue_bulb(hass)
    broker.retained[INFO]["config"]["devices"][IEEE]["hue_native_control"] = True

    await call(hass, "turn_on_for", RED)

    assert broker.requests() == []
    assert len(broker.timers()) == 1


async def test_device_missing_from_settings_gets_it(hass, setup_production, broker, turn_ons):
    hue_bulb(hass)
    broker.retained[INFO] = {"config": {}}

    await call(hass, "turn_on_for", RED)

    assert options(broker) == [True, False]


async def test_other_brands_are_left_alone(hass, setup_production, broker, turn_ons):
    hue_bulb(hass, manufacturer="IKEA of Sweden")

    await call(hass, "turn_on_for", RED)

    assert broker.requests() == []
    assert broker.topics == []
    assert len(broker.timers()) == 1


@pytest.mark.parametrize("fields", [{}, {"brightness": 50}, {"transition": 1}])
async def test_without_a_color_nothing_is_read(hass, setup_production, broker, turn_ons, fields):
    hue_bulb(hass)

    await call(hass, "turn_on_for", {"entity_id": "light.lamp", "duration": 6, **fields})

    assert broker.requests() == []
    assert broker.topics == []


# A failed set: a warning, and the command goes out as the option stands, with nothing to put back


@pytest.mark.parametrize(
    ("break_it", "reason", "sent"),
    [
        pytest.param(lambda broker: broker.retained.pop(INFO), "no bridge/info from Zigbee2MQTT", [], id="no_info"),
        # Z2M may have applied a write it never answered, so it is put back.
        pytest.param(
            lambda broker: setattr(broker, "reply", None), "no reply from Zigbee2MQTT", [True, False], id="no_reply"
        ),
        pytest.param(
            lambda broker: setattr(broker, "reply", {"status": "error", "error": "Device 'x' does not exist"}),
            "Device 'x' does not exist",
            [True],
            id="error_reply",
        ),
        pytest.param(lambda broker: setattr(broker, "reply", {}), "status None", [True], id="no_status"),
        pytest.param(
            lambda broker: setattr(broker, "reply", "not json"),
            "no reply from Zigbee2MQTT",
            [True, False],
            id="unreadable",
        ),
    ],
)
async def test_failed_set_warns_and_still_sends(
    hass, setup_production, broker, turn_ons, caplog, break_it, reason, sent
):
    hue_bulb(hass)
    break_it(broker)

    response = await call(hass, "turn_on_for", RED)

    assert response == {"light.lamp": SENT}
    assert len(turn_ons) == 1 and len(broker.timers()) == 1
    assert options(broker) == sent
    assert (
        "Couldn't set Zigbee2MQTT's hue_native_control to True for light.lamp, so the command goes out as the option "
        f"stands: {reason}"
    ) in caplog.text
    assert not broker.listening(DEVICE_RESPONSE)


async def test_failed_restore_warns(hass, setup_production, broker, turn_ons, caplog):
    hue_bulb(hass)
    publish = broker.publish

    def refuse_after_the_first(service):
        if broker.requests():
            broker.reply = {"status": "error", "error": "refused"}
        publish(service)

    hass.services.async_register("mqtt", "publish", refuse_after_the_first)

    response = await call(hass, "turn_on_for", RED)

    assert response == {"light.lamp": SENT}
    assert options(broker) == [True, False]
    assert len(broker.timers()) == 1
    assert "Couldn't put Zigbee2MQTT's hue_native_control back to False for light.lamp, so it stays True" in caplog.text


# Groups: the group's own option, and only with a Hue member

BRIDGE_GROUPS = [{"id": 3, "members": []}, {"id": 7, "members": [{"ieee_address": MEMBER, "endpoint": 11}]}]
DOWNSTAIRS = {"entity_id": "light.downstairs", "duration": 6, "rgb_color": [255, 0, 0]}


def group_with_member(hass, manufacturer: str) -> None:
    entry = z2m_entry(hass)
    add_z2m_entity(hass, entry, "light.member", ieee=MEMBER, manufacturer=manufacturer)
    add_z2m_group(hass, entry, "light.downstairs", group_id=7)


async def test_group_with_a_hue_member_gets_the_group_option(hass, setup_production, broker, turn_ons):
    group_with_member(hass, "Philips")
    broker.retained[GROUPS] = BRIDGE_GROUPS
    broker.retained[INFO]["config"]["devices"][MEMBER] = {"hue_native_control": True}  # a member's own doesn't count

    response = await call(hass, "turn_on_for", DOWNSTAIRS)

    assert response == {"light.downstairs": SENT}
    assert [(r["topic"], r["payload"]["id"]) for r in broker.requests()] == [(GROUP_REQUEST, "7")] * 2
    assert options(broker) == [True, False]
    assert not broker.listening(GROUP_RESPONSE)


async def test_group_with_option_on_sends_no_request(hass, setup_production, broker, turn_ons):
    group_with_member(hass, "Philips")
    broker.retained[GROUPS] = BRIDGE_GROUPS
    broker.retained[INFO]["config"]["groups"]["7"] = {"hue_native_control": True}

    await call(hass, "turn_on_for", DOWNSTAIRS)

    assert broker.requests() == []


@pytest.mark.parametrize(
    ("manufacturer", "groups"),
    [
        pytest.param("IKEA of Sweden", BRIDGE_GROUPS, id="no_hue_member"),
        pytest.param("Philips", [{"id": 3, "members": []}], id="not_in_bridge_groups"),
    ],
)
async def test_group_is_left_alone(hass, setup_production, broker, turn_ons, manufacturer, groups):
    group_with_member(hass, manufacturer)
    broker.retained[GROUPS] = groups

    await call(hass, "turn_on_for", DOWNSTAIRS)

    assert broker.requests() == []
    assert len(broker.timers()) == 1


async def test_no_bridge_groups_warns_and_still_sends(hass, setup_production, broker, turn_ons, caplog):
    group_with_member(hass, "Philips")

    response = await call(hass, "turn_on_for", DOWNSTAIRS)

    assert response == {"light.downstairs": SENT}
    assert len(broker.timers()) == 1
    assert "so the command goes out as the option stands: no bridge/groups from Zigbee2MQTT" in caplog.text


# Ramps: off for brightness, on for saturation


async def test_brightness_ramp_turns_it_off_for_its_publish(hass, setup_production, clock, broker):
    entity_id = light(hass, broker, manufacturer="Philips")
    broker.retained[INFO]["config"]["devices"][IEEE]["hue_native_control"] = True

    response = await call(hass, "raise_brightness", {"entity_id": entity_id})

    assert response == {entity_id: SENT}
    off, back = broker.requests()
    fade = next(p for p in broker.published if p["topic"] == SET)
    assert broker.published.index(off) < broker.published.index(fade) < broker.published.index(back)
    assert options(broker) == [False, True]


async def test_saturation_ramp_turns_it_on_for_its_publish(hass, setup_production, clock, broker):
    entity_id = light(hass, broker, manufacturer="Philips")

    await call(hass, "raise_saturation", {"entity_id": entity_id})

    assert options(broker) == [True, False]


async def test_hue_move_leaves_it_alone(hass, setup_production, clock, broker):
    entity_id = light(hass, broker, manufacturer="Philips")

    await call(hass, "raise_hue", {"entity_id": entity_id})

    assert broker.requests() == []


# The context manager itself


async def test_restore_runs_when_the_body_raises(hass, setup_production, broker):
    hue_bulb(hass)

    with pytest.raises(RuntimeError):
        async with nc.native_control(hass, target(hass, "light.lamp"), True):
            assert options(broker) == [True]
            raise RuntimeError("publish failed")

    assert options(broker) == [True, False]


async def test_lock_keeps_opposite_needs_apart(hass, setup_production, broker):
    hue_bulb(hass)
    lamp = target(hass, "light.lamp")
    order: list[str] = []
    entered = asyncio.Event()

    async def hold(need: bool, name: str) -> None:
        async with nc.native_control(hass, lamp, need):
            order.append(f"{name} in")
            entered.set()
            await asyncio.sleep(0)
            order.append(f"{name} out")

    first = asyncio.create_task(hold(True, "on"))
    await entered.wait()
    # The option stays absent in bridge/info, so a need of False writes nothing: the lock is all that orders them.
    await asyncio.gather(first, hold(False, "off"))

    assert order == ["on in", "on out", "off in", "off out"]


async def test_lock_is_per_device(hass, setup_production, broker):
    entry = z2m_entry(hass)
    add_z2m_entity(hass, entry, "light.one", ieee=IEEE, manufacturer="Philips")
    add_z2m_entity(hass, entry, "light.two", ieee=MEMBER, manufacturer="Philips")
    order: list[str] = []
    release = asyncio.Event()

    async def hold(entity_id: str) -> None:
        async with nc.native_control(hass, target(hass, entity_id), True):
            order.append(entity_id)
            await release.wait()

    tasks = [asyncio.create_task(hold("light.one")), asyncio.create_task(hold("light.two"))]
    while len(order) < 2:
        await asyncio.sleep(0.01)
    release.set()
    await asyncio.gather(*tasks)

    assert sorted(order) == ["light.one", "light.two"]


async def test_state_reply_ends_the_wait(hass, setup_production, clock, broker, monkeypatch):
    monkeypatch.setattr(nc, "_REPLY_CAP_S", 5.0)
    entity_id = light(hass, broker, manufacturer="Philips")
    loop = asyncio.get_running_loop()

    start = loop.time()
    async with nc.native_control(hass, target(hass, entity_id), True):
        broker.deliver("zigbee2mqtt/lamp", '{"state": "ON"}')

    assert loop.time() - start < 1
    assert options(broker) == [True, False]
    assert not broker.subscribers["zigbee2mqtt/lamp"]


async def test_retained_state_doesnt_end_the_wait(hass, setup_production, clock, broker, monkeypatch):
    monkeypatch.setattr(nc, "_REPLY_CAP_S", 0.2)
    entity_id = light(hass, broker, manufacturer="Philips")
    broker.retained["zigbee2mqtt/lamp"] = {"state": "ON"}  # resent on subscribe: old state, not Z2M's answer
    loop = asyncio.get_running_loop()

    start = loop.time()
    async with nc.native_control(hass, target(hass, entity_id), True):
        pass

    assert loop.time() - start >= 0.2
    assert options(broker) == [True, False]


async def test_failed_state_subscribe_still_restores_after_the_cap(
    hass, setup_production, clock, broker, monkeypatch, caplog
):
    entity_id = light(hass, broker, manufacturer="Philips")
    subscribe = nc.mqtt.async_subscribe

    async def refuse_state(hass, topic, *args, **kwargs):
        if topic == "zigbee2mqtt/lamp":
            raise RuntimeError("MQTT is not connected")
        return await subscribe(hass, topic, *args, **kwargs)

    monkeypatch.setattr(nc.mqtt, "async_subscribe", refuse_state)
    loop = asyncio.get_running_loop()

    start = loop.time()
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        async with nc.native_control(hass, target(hass, entity_id), True):
            pass

    assert loop.time() - start >= nc._REPLY_CAP_S
    assert options(broker) == [True, False]
    assert "Couldn't subscribe to zigbee2mqtt/lamp, so the restore waits" in caplog.text


async def test_reply_cap_is_one_second():
    assert nc._REPLY_CAP_S == 1.0


async def test_no_need_writes_nothing(hass, setup_production, broker):
    hue_bulb(hass)

    async with nc.native_control(hass, target(hass, "light.lamp"), None):
        pass

    assert broker.topics == []
