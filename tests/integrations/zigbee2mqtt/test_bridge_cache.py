"""Zigbee2MQTT bridge cache: bridge/devices, groups and info held, and options replies routed, for the entry's life."""

import asyncio
import json

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.deviceside.const import CONF_Z2M_COLOR_MODES, DOMAIN
from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.integrations.zigbee2mqtt import INTEGRATION, bridge, bridge_cache, classes, members

from ...fixtures.zigbee2mqtt import (
    GROUPS,
    IEEE,
    INFO,
    add_z2m_bridge,
    add_z2m_entity,
    add_z2m_group,
    bridge_ieee,
)

BASE = "zigbee2mqtt"

DEVICES = "zigbee2mqtt/bridge/devices"
STATE = "zigbee2mqtt/bridge/state"
DEVICE_RESPONSE = "zigbee2mqtt/bridge/response/device/options"
GROUP_RESPONSE = "zigbee2mqtt/bridge/response/group/options"
LOGGING = "zigbee2mqtt/bridge/logging"
HELD_TOPICS = [DEVICE_RESPONSE, GROUP_RESPONSE, LOGGING, DEVICES, GROUPS, INFO, STATE]
ROOM = [{"id": 7, "members": [{"ieee_address": "0x01"}]}]


class Connection:
    """HA's MQTT connection status, as the cache subscribes to it."""

    def __init__(self) -> None:
        self.callbacks: list = []

    def subscribe(self, hass, status_callback):
        self.callbacks.append(status_callback)
        return lambda: self.callbacks.remove(status_callback)

    def lost(self) -> None:
        for status_callback in list(self.callbacks):
            status_callback(False)

    def back(self) -> None:
        for status_callback in list(self.callbacks):
            status_callback(True)


@pytest.fixture
def connection(monkeypatch) -> Connection:
    fake = Connection()
    monkeypatch.setattr(bridge_cache.mqtt, "async_subscribe_connection_status", fake.subscribe)
    return fake


@pytest.fixture
def mqtt_up(monkeypatch):
    async def ready(hass):
        return True

    monkeypatch.setattr(bridge_cache.mqtt, "async_wait_for_mqtt_client", ready)


async def settle() -> None:
    for _ in range(3):
        await asyncio.sleep(0)


async def start(hass, entry) -> bridge_cache.BridgeCache:
    add_z2m_bridge(hass, entry)
    await bridge_cache.async_setup(hass, entry)
    await settle()  # the retained messages
    cache = bridge_cache.get(hass, BASE)
    assert cache is not None
    return cache


@pytest.fixture
def online(broker):
    broker.retained[STATE] = {"state": "online"}
    broker.retained[GROUPS] = ROOM
    broker.retained[DEVICES] = [{"ieee_address": "0x01"}]
    return broker


def wanted_on(current: dict) -> dict:
    return {} if current.get("x") else {"x": True}


# Holding devices, groups and info


async def test_subscribes_the_response_topics_before_the_barrier(hass, setup_production, online, connection, mqtt_up):
    await start(hass, setup_production)

    assert online.topics == HELD_TOPICS
    assert len(connection.callbacks) == 1


async def test_a_device_identifier_of_other_than_two_parts_does_not_stop_the_cache(
    hass, setup_production, online, connection, mqtt_up, monkeypatch
):
    monkeypatch.setattr(classes, "bridge_cache", bridge_cache)  # the real cache, not the fixture's stand-in
    other = MockConfigEntry(domain="homekit_controller")
    other.add_to_hass(hass)
    for identifiers in ({("homekit_controller", "a", "b")}, {("homekit_controller",)}):
        dr.async_get(hass).async_get_or_create(config_entry_id=other.entry_id, identifiers=identifiers)
    entity_id = add_z2m_entity(
        hass,
        setup_production,
        "light.one",
        ieee="0x01",
        name="one",
        manufacturer="IKEA of Sweden",
        model_id="LED1836G9",
    )
    online.retained[DEVICES] = [
        {"ieee_address": "0x01", "manufacturer": "IKEA of Sweden", "model_id": "LED1836G9", "interview_completed": True}
    ]

    await start(hass, setup_production)

    target = resolve(hass, get_runtime(hass).registry, entity_id)
    assert INTEGRATION.capability(hass, target) == "ikea"


async def test_groups_devices_and_info_come_from_the_cache(hass, setup_production, online, connection, mqtt_up):
    await start(hass, setup_production)
    online.topics.clear()

    assert await bridge.group_members(hass, BASE, "7") == ["0x01"]
    assert await bridge.has_feature(hass, BASE, ["0x01"], "color_hs") is False
    first = await bridge.retained(hass, BASE, "info")
    assert await bridge.retained(hass, BASE, "info") is first
    assert online.topics == []


async def test_each_payload_is_parsed_once_and_an_empty_one_clears_the_topic(
    hass, setup_production, online, connection, mqtt_up
):
    cache = await start(hass, setup_production)

    first = await bridge.retained(hass, BASE, "groups")
    assert await bridge.retained(hass, BASE, "groups") is first

    online.deliver(GROUPS, json.dumps([{"id": 8, "members": []}]))
    second = await bridge.retained(hass, BASE, "groups")
    assert second is not first
    assert second == [{"id": 8, "members": []}]
    assert await bridge.retained(hass, BASE, "groups") is second

    online.deliver(GROUPS, "")
    assert cache.parsed("groups") is None


async def test_an_empty_cache_reads_fresh(hass, setup_production, broker, connection, mqtt_up):
    cache = await start(hass, setup_production)  # Z2M has published no groups yet
    assert cache.parsed("groups") is None
    broker.topics.clear()

    with pytest.raises(TimeoutError, match="no bridge/groups from Zigbee2MQTT"):
        await bridge.retained(hass, BASE, "groups")
    assert broker.topics == [GROUPS]


async def test_settings_waits_for_bridge_devices_until_it_arrives_and_again_after_a_disconnect(
    hass, setup_production, broker, connection, mqtt_up
):
    cache = await start(hass, setup_production)  # Z2M has published no devices yet
    assert not cache.devices_ready.is_set()

    waiting = bridge_cache.capability_ready(hass)
    assert waiting is not None
    task = asyncio.ensure_future(waiting)
    await settle()
    assert not task.done()

    broker.deliver(DEVICES, json.dumps([{"ieee_address": "0x01"}]))
    await settle()
    assert task.done()
    assert bridge_cache.capability_ready(hass) is None

    connection.lost()  # the held payloads go until the resubscribe brings them back
    again = bridge_cache.capability_ready(hass)
    assert again is not None
    again.close()


async def test_a_bridge_devices_that_does_not_parse_does_not_make_the_cache_ready(
    hass, setup_production, broker, connection, mqtt_up
):
    cache = await start(hass, setup_production)

    broker.deliver(DEVICES, "not json")
    await settle()

    assert not cache.devices_ready.is_set()


async def test_without_a_cache_everything_reads_fresh(hass, broker):
    broker.retained[GROUPS] = ROOM

    assert bridge_cache.get(hass, BASE) is None
    assert await bridge.group_members(hass, BASE, "7") == ["0x01"]
    assert broker.topics == [GROUPS]


# Replies


async def test_live_replies_reach_the_call_without_its_own_subscription(
    hass, setup_production, online, connection, mqtt_up
):
    cache = await start(hass, setup_production)
    assert cache.replies_live
    online.topics.clear()
    confirmed: list[str] = []

    await bridge.ensure_options(hass, BASE, "device", ["0x01"], wanted_on, confirmed.append)
    await bridge.ensure_options(hass, BASE, "device", ["0x01"], wanted_on, confirmed.append)

    assert confirmed == ["0x01"]  # the second call sees the first's write, before Z2M republishes bridge/info
    assert online.topics == []  # neither bridge/info nor the reply topic
    assert len(online.requests()) == 1
    assert cache.pending == {}


async def test_a_refused_live_reply_still_raises_and_writes_nothing_through(
    hass, setup_production, online, connection, mqtt_up
):
    cache = await start(hass, setup_production)
    online.refused.add("0x01")

    with pytest.raises(RuntimeError, match="refused"):
        await bridge.ensure_options(hass, BASE, "device", ["0x01"], wanted_on, lambda _id: None)
    assert cache.pending == {}
    assert cache.confirmed == {}


async def test_without_the_barrier_each_call_subscribes_for_its_reply(
    hass, setup_production, broker, connection, mqtt_up
):
    del broker.retained[STATE]
    cache = await start(hass, setup_production)
    assert not cache.replies_live
    broker.topics.clear()
    confirmed: list[str] = []

    await bridge.ensure_options(hass, BASE, "group", ["7"], wanted_on, confirmed.append)

    assert confirmed == ["7"]
    assert broker.topics == [GROUP_RESPONSE, INFO]


async def test_a_disconnect_clears_it_until_the_resubscribe(hass, setup_production, online, connection, mqtt_up):
    cache = await start(hass, setup_production)

    connection.lost()

    assert not cache.replies_live
    assert cache.parsed("groups") is None and cache.parsed("devices") is None and cache.parsed("info") is None
    online.topics.clear()
    await bridge.ensure_options(hass, BASE, "device", ["0x01"], wanted_on, lambda _id: None)
    assert online.topics == [DEVICE_RESPONSE, INFO]

    connection.back()  # connected again, but nothing is resubscribed yet
    assert not cache.replies_live
    online.deliver(GROUPS, json.dumps(ROOM))  # HA's resubscribe, in topic order
    online.deliver(STATE, json.dumps({"state": "online"}))
    assert cache.replies_live
    assert await bridge.retained(hass, BASE, "groups") == ROOM


async def test_live_replies_without_info_read_it_fresh(hass, setup_production, online, connection, mqtt_up):
    cache = await start(hass, setup_production)
    online.deliver(INFO, "")  # bridge/info cleared
    assert cache.replies_live and cache.parsed("info") is None
    online.topics.clear()

    await bridge.ensure_options(hass, BASE, "device", ["0x01"], wanted_on, lambda _id: None)

    assert online.topics == [INFO]


# Confirmed options, written through


def info(devices: dict) -> str:
    return json.dumps({"config": {"devices": devices, "groups": {}}})


async def test_a_confirmed_write_shows_until_the_next_info(hass, setup_production, online, connection, mqtt_up):
    online.retained[INFO] = {"config": {"devices": {"0x01": {"y": 1}}, "groups": {}}}
    cache = await start(hass, setup_production)

    await bridge.ensure_options(hass, BASE, "device", ["0x01"], wanted_on, lambda _id: None)

    # No data.to in the reply: what was sent, over the options before.
    assert cache.settings("devices", "0x01") == {"y": 1, "x": True}
    assert (await bridge.retained(hass, BASE, "info"))["config"]["devices"]["0x01"] == {
        "y": 1
    }  # never changed in place

    online.deliver(INFO, info({"0x01": {"y": 2}}))  # Z2M's republish
    assert cache.confirmed == {}
    assert cache.settings("devices", "0x01") == {"y": 2}


async def test_a_confirmed_write_takes_z2m_s_own_options(hass, setup_production, online, connection, mqtt_up):
    cache = await start(hass, setup_production)
    online.reply = {"status": "ok", "data": {"from": {}, "to": {"x": True, "z": 3}}}

    await bridge.ensure_options(hass, BASE, "device", ["0x01"], wanted_on, lambda _id: None)

    assert cache.settings("devices", "0x01") == {"x": True, "z": 3}


async def test_settings_without_info(hass, setup_production, online, connection, mqtt_up):
    cache = await start(hass, setup_production)
    assert cache.settings("devices", "0x99") == {}  # held, but no options for it

    online.deliver(INFO, "")

    assert cache.settings("devices", "0x01") is None


async def test_a_disconnect_drops_confirmed_writes(hass, setup_production, online, connection, mqtt_up):
    cache = await start(hass, setup_production)
    await bridge.ensure_options(hass, BASE, "device", ["0x01"], wanted_on, lambda _id: None)
    assert cache.confirmed

    connection.lost()

    assert cache.confirmed == {}


# Lifecycle


async def test_unload_unsubscribes_everything(hass, setup_production, online, connection, mqtt_up):
    await start(hass, setup_production)

    assert await hass.config_entries.async_unload(setup_production.entry_id)

    assert bridge_cache.get(hass, BASE) is None
    assert not any(online.listening(topic) for topic in HELD_TOPICS)
    assert connection.callbacks == []


async def test_without_mqtt_nothing_is_held(hass, setup_production, broker, monkeypatch):
    async def no_client(hass):
        return False

    monkeypatch.setattr(bridge_cache.mqtt, "async_wait_for_mqtt_client", no_client)

    await bridge_cache.async_setup(hass, setup_production)

    assert bridge_cache.get(hass, BASE) is None
    assert broker.topics == []


async def test_without_a_known_bridge_nothing_is_held(hass, setup_production, broker, mqtt_up):
    await bridge_cache.async_setup(hass, setup_production)

    assert bridge_cache.get(hass, BASE) is None
    assert broker.topics == []


async def test_a_failed_subscribe_warns_and_holds_nothing(
    hass, setup_production, broker, connection, mqtt_up, monkeypatch, caplog
):
    subscribe = bridge.mqtt.async_subscribe

    async def refuse_state(hass, topic, *args, **kwargs):
        if topic == STATE:
            raise RuntimeError("MQTT is not connected")
        return await subscribe(hass, topic, *args, **kwargs)

    monkeypatch.setattr(bridge.mqtt, "async_subscribe", refuse_state)
    add_z2m_bridge(hass, setup_production)

    await bridge_cache.async_setup(hass, setup_production)
    await settle()

    assert bridge_cache.get(hass, BASE) is None
    assert not any(broker.listening(topic) for topic in HELD_TOPICS)
    assert (
        "Couldn't subscribe to Zigbee2MQTT's bridge, so each action reads it fresh, Zigbee2MQTT groups run only "
        "with Labs on, and turn on with timer refuses them and every device but Hue's" in caplog.text
    )


async def test_setup_entry_starts_it_once_mqtt_is_up(hass, broker, connection, mqtt_up):
    entry = MockConfigEntry(domain=DOMAIN, options={CONF_Z2M_COLOR_MODES: False})
    entry.add_to_hass(hass)
    add_z2m_bridge(hass, entry)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert bridge_cache.get(hass, BASE) is not None
    assert await hass.config_entries.async_unload(entry.entry_id)


# Z2M saying online, for the restore journal's replay


async def onlines(hass, entry) -> list[str]:
    seen: list[str] = []
    add_z2m_bridge(hass, entry)
    await bridge_cache.async_setup(hass, entry, lambda base: seen.append(base))
    await settle()
    return seen


async def test_the_retained_online_calls_on_online(hass, setup_production, online, connection, mqtt_up):
    assert await onlines(hass, setup_production) == ["zigbee2mqtt"]


@pytest.mark.parametrize(("payload", "calls"), [("online", 1), ("offline", 0), ('{"state": "offline"}', 0), ("{", 0)])
async def test_each_online_calls_on_online(hass, setup_production, broker, connection, mqtt_up, payload, calls):
    """Z2M publishes JSON; older versions, and its last will, a bare string. Anything else isn't online."""
    broker.retained[STATE] = {"state": "offline"}
    seen = await onlines(hass, setup_production)

    broker.deliver(STATE, payload)

    assert len(seen) == calls
    assert bridge_cache.get(hass, BASE).replies_live


async def test_a_malformed_payload_counts_as_none(hass, setup_production, online, connection, mqtt_up):
    """A retained bridge/info that doesn't parse is no bridge/info: read fresh, which times out on it too."""
    cache = await start(hass, setup_production)
    online.retained.pop(INFO)
    online.deliver(INFO, "{not json")

    assert cache.parsed("info") is None
    with pytest.raises(TimeoutError, match="no bridge/info"):
        await bridge.ensure_options(hass, BASE, "device", ["0x01"], wanted_on, lambda _id: None)


async def test_a_malformed_fresh_payload_raises_timeout(hass, broker, monkeypatch):
    async def malformed(hass, base, suffix):
        return "{not json"

    monkeypatch.setattr(bridge, "first_retained", malformed)

    with pytest.raises(TimeoutError, match="no parseable bridge/groups"):
        await bridge.retained(hass, BASE, "groups")


@pytest.mark.parametrize(
    ("message", "logged"),
    [
        pytest.param(
            f"Publish 'set' 'read' to 'lamp' failed: ZCL command {IEEE}/11 lightingColorCtrl.read() failed"
            " (UNSUPPORTED_ATTRIBUTE)",
            "lightingColorCtrl.read failed (UNSUPPORTED_ATTRIBUTE)",
            id="a_status",
        ),
        pytest.param(
            f"Publish 'set' 'brightness' to 'lamp' failed: 'Error: ZCL command {IEEE}/11 genLevelCtrl.moveToLevel("
            "{\"level\":51}) failed (Delivery failed for '12345')'",
            "genLevelCtrl.moveToLevel failed (Delivery failed)",
            id="a_quoted_nwk",
        ),
        pytest.param(
            "Publish 'set' 'brightness' to 'room' failed: 'Error: ZCL command 7 genLevelCtrl.moveToLevel({}) failed "
            "(~x~> [ZCL GROUP groupId=7] Failed to send with status=BUSY.)'",
            "genLevelCtrl.moveToLevel failed (Failed to send with status=BUSY.)",
            id="a_group_sender",
        ),
        pytest.param(
            f"Publish 'set' 'state' to 'lamp' failed: 'Error: ZCL command {IEEE}/11 genOnOff.on({{}}) failed "
            "(Timeout - 46516 - 11 - 7 - 6 - 11 after 10000ms)'",
            "genOnOff.on failed (Timeout after 10000ms)",
            id="a_timeouts_address_fields",
        ),
        pytest.param(
            f"Publish 'set' 'state' to 'lamp' failed: 'Error: ZCL command {IEEE}/11 genOnOff.on({{}}) failed "
            "(Data request failed with error: 'MAC no ack' (233))'",
            "genOnOff.on failed (Data request failed with error: 'MAC no ack' (233))",
            id="quoted_text_and_codes_kept",
        ),
        pytest.param(
            "Publish 'set' 'state' to 'lamp' failed: 'Error: No converter available for 'state' on 'lamp''",
            "No converter available for 'state' on '<device>'",
            id="another_set_failure_gives_its_error",
        ),
        pytest.param(
            "Publish 'set' 'state' to 'lamp' failed: 'Error: Command lamp/11 genOnOff.on failed'",
            "Command <device>/11 genOnOff.on failed",
            id="a_name_ahead_of_an_endpoint",
        ),
        pytest.param(
            "Publish 'set' 'state' to 'Kid's lamp' failed: 'Error: No converter available for 'state' on 'Kid's lamp''",
            "No converter available for 'state' on '<device>'",
            id="a_name_with_an_apostrophe",
        ),
        pytest.param("Failed to ping 'lamp'", "a failure DeviceSide doesn't parse", id="another_shape"),
    ],
)
def test_a_failure_line_is_logged_as_its_call_and_cause_without_addressing(message, logged):
    assert bridge_cache.cause(message) == logged


def test_an_options_error_is_scrubbed_of_the_id_it_was_asked_about():
    assert (
        bridge_cache.scrub(f"Device '{IEEE}' does not exist", IEEE, label="device")
        == "Device '<device>' does not exist"
    )


async def test_expand_group_of_another_instance_gets_no_members(
    hass, setup_production, online, connection, mqtt_up, monkeypatch
):
    monkeypatch.setattr(members, "bridge_cache", bridge_cache)  # the real cache, not the fixture's stand-in
    await start(hass, setup_production)
    entry = hass.config_entries.async_entries("mqtt") or [setup_production]
    add_z2m_group(hass, entry[0], "light.up_room", group_id=7, name="room", base_topic="z2m_up", bridge_base="z2m_up")
    registry = get_runtime(hass).registry

    assert members.expand_group(hass, resolve(hass, registry, "light.up_room")) is None


# Several instances: a cache per base topic, following HA's registry


UP = "z2m_up"  # a second instance's base topic


def up(suffix: str) -> str:
    return f"{UP}/bridge/{suffix}"


UP_HELD_TOPICS = [up(t.split("/bridge/")[1]) for t in HELD_TOPICS]


@pytest.fixture
def two(online):
    """A second instance on the broker, its group 7 holding another member and its own options."""
    online.retained[INFO] = {"config": {"devices": {}, "groups": {"7": {"name": "first"}}}}
    online.retained[up("state")] = {"state": "online"}
    online.retained[up("groups")] = [{"id": 7, "members": [{"ieee_address": "0x02"}]}]
    online.retained[up("devices")] = [{"ieee_address": "0x02"}]
    online.retained[up("info")] = {"config": {"devices": {}, "groups": {"7": {"name": "second"}}}}
    return online


def bridge_entity(hass, base: str) -> str:
    return er.async_get(hass).async_get_entity_id("sensor", "mqtt", f"bridge_{bridge_ieee(base)}_version_{base}")


async def start_two(hass, entry, seen: list[str] | None = None) -> None:
    add_z2m_bridge(hass, entry)
    add_z2m_bridge(hass, entry, UP)
    await bridge_cache.async_setup(hass, entry, (seen if seen is not None else []).append)
    await settle()


async def test_each_instance_has_its_own_cache(hass, setup_production, two, connection, mqtt_up):
    seen: list[str] = []
    await start_two(hass, setup_production, seen)

    first, second = bridge_cache.get(hass, BASE), bridge_cache.get(hass, UP)
    assert first is not None and second is not None and first is not second
    assert first.replies_live and second.replies_live
    assert two.topics == UP_HELD_TOPICS + HELD_TOPICS  # by base topic, each in its own order, the barrier last
    assert sorted(seen) == [UP, BASE]  # each instance's online, with its base
    assert len(connection.callbacks) == 2  # each cache clears on its own disconnect


async def test_each_instances_group_lists_its_own_members(
    hass, setup_production, two, connection, mqtt_up, monkeypatch
):
    monkeypatch.setattr(members, "bridge_cache", bridge_cache)  # the real cache, not the fixture's stand-in
    entry = (hass.config_entries.async_entries("mqtt") or [setup_production])[0]
    add_z2m_entity(hass, entry, "light.one", ieee="0x01", name="one")
    add_z2m_entity(hass, entry, "light.two", ieee="0x02", name="two", base_topic=UP, bridge_base=UP)
    add_z2m_group(hass, entry, "light.room", group_id=7, name="room")
    add_z2m_group(hass, entry, "light.up_room", group_id=7, name="up room", base_topic=UP, bridge_base=UP)
    await start_two(hass, entry)
    registry = get_runtime(hass).registry

    listed = {
        group: [m.entity_id for m in members.expand_group(hass, resolve(hass, registry, group))]
        for group in ("light.room", "light.up_room")
    }

    assert listed == {"light.room": ["light.one"], "light.up_room": ["light.two"]}
    assert await bridge.group_members(hass, UP, "7") == ["0x02"]
    assert await bridge.group_members(hass, BASE, "7") == ["0x01"]


async def test_each_instances_options_come_from_and_go_to_its_own(hass, setup_production, two, connection, mqtt_up):
    await start_two(hass, setup_production)
    first, second = bridge_cache.get(hass, BASE), bridge_cache.get(hass, UP)
    assert first.settings("groups", "7") == {"name": "first"}
    assert second.settings("groups", "7") == {"name": "second"}
    two.topics.clear()
    confirmed: list[str] = []

    await bridge.ensure_options(hass, UP, "group", ["7"], wanted_on, confirmed.append)

    assert confirmed == ["7"]
    assert [p["topic"] for p in two.published] == [up("request/group/options")]
    assert two.topics == []  # the reply reached the second cache's own response topic
    assert second.settings("groups", "7") == {"name": "second", "x": True}
    assert first.settings("groups", "7") == {"name": "first"}  # group 7 of the other instance is another group


async def test_a_bridge_added_after_setup_gets_a_cache_and_one_removed_stops(
    hass, setup_production, two, connection, mqtt_up
):
    await bridge_cache.async_setup(hass, setup_production)
    assert bridge_cache.get(hass, UP) is None
    assert two.topics == []

    add_z2m_bridge(hass, setup_production, UP)
    await settle()

    assert bridge_cache.get(hass, UP).replies_live
    assert two.topics == UP_HELD_TOPICS
    assert bridge_cache.get(hass, BASE) is None

    er.async_get(hass).async_remove(bridge_entity(hass, UP))

    assert bridge_cache.get(hass, UP) is None
    assert not any(two.listening(topic) for topic in UP_HELD_TOPICS)
    assert connection.callbacks == []


async def test_removing_the_bridge_device_stops_its_cache(hass, setup_production, two, connection, mqtt_up):
    await start_two(hass, setup_production)
    bridge_device = add_z2m_bridge(hass, setup_production, UP)  # the one registered, as it is idempotent

    dr.async_get(hass).async_remove_device(bridge_device.id)
    await settle()

    assert bridge_cache.get(hass, UP) is None
    assert not any(two.listening(topic) for topic in UP_HELD_TOPICS)
    assert bridge_cache.get(hass, BASE) is not None


async def test_a_renamed_bridge_entity_keeps_its_cache(hass, setup_production, two, connection, mqtt_up):
    await start_two(hass, setup_production)
    cache = bridge_cache.get(hass, UP)

    er.async_get(hass).async_update_entity(bridge_entity(hass, UP), new_entity_id="sensor.upstairs_bridge_version")

    assert bridge_cache.get(hass, UP) is cache
    er.async_get(hass).async_remove("sensor.upstairs_bridge_version")  # tracked under its new id
    assert bridge_cache.get(hass, UP) is None


async def test_a_changed_base_topic_moves_the_cache(hass, setup_production, two, connection, mqtt_up):
    """Renaming the base topic: Z2M announces the bridge's entities under the new one, and the old ones are removed."""
    await start_two(hass, setup_production)
    bridge_device = add_z2m_bridge(hass, setup_production, UP)  # the one registered, as it is idempotent
    old = bridge_entity(hass, UP)
    two.retained[up("state").replace(UP, "z2m_new")] = {"state": "online"}

    er.async_get(hass).async_get_or_create(
        "sensor",
        "mqtt",
        f"bridge_{bridge_ieee(UP)}_version_z2m_new",
        config_entry=setup_production,
        device_id=bridge_device.id,
    )
    # Its entities disagree until the old one goes: no base is known, so no cache.
    assert bridge_cache.get(hass, UP) is None and bridge_cache.get(hass, "z2m_new") is None
    assert not any(two.listening(topic) for topic in UP_HELD_TOPICS)

    er.async_get(hass).async_remove(old)
    await settle()

    assert bridge_cache.get(hass, "z2m_new").replies_live
    assert bridge_cache.get(hass, BASE) is not None


@pytest.fixture
def held_at_logging(monkeypatch):
    """Each subscribe to the second instance's bridge/logging waits until the returned event is set, as if HA's
    subscribe suspended there, after the response topics."""
    gate = asyncio.Event()
    subscribe = bridge.mqtt.async_subscribe

    async def gated(hass, topic, *args, **kwargs):
        if topic == up(LOG):
            await gate.wait()
        return await subscribe(hass, topic, *args, **kwargs)

    monkeypatch.setattr(bridge.mqtt, "async_subscribe", gated)
    return gate


LOG = "logging"


async def test_a_bridge_removed_mid_subscribe_leaves_nothing_subscribed(
    hass, setup_production, two, connection, mqtt_up, held_at_logging
):
    await start_two(hass, setup_production)
    assert two.listening(up("response/group/options")) and bridge_cache.get(hass, UP) is None

    er.async_get(hass).async_remove(bridge_entity(hass, UP))
    held_at_logging.set()
    await settle()

    assert bridge_cache.get(hass, UP) is None
    assert not any(two.listening(topic) for topic in UP_HELD_TOPICS)
    assert len(connection.callbacks) == 1  # the first instance's
    assert bridge_cache.get(hass, BASE).replies_live


async def test_unload_mid_subscribe_leaves_nothing_subscribed(
    hass, setup_production, two, connection, mqtt_up, held_at_logging
):
    await start_two(hass, setup_production)

    assert await hass.config_entries.async_unload(setup_production.entry_id)
    held_at_logging.set()
    await settle()

    assert bridge_cache.get(hass, UP) is None and bridge_cache.get(hass, BASE) is None
    assert not any(two.listening(topic) for topic in HELD_TOPICS + UP_HELD_TOPICS)
    assert connection.callbacks == []


async def test_a_bridge_back_mid_subscribe_gets_one_cache(
    hass, setup_production, two, connection, mqtt_up, held_at_logging
):
    await start_two(hass, setup_production)
    er.async_get(hass).async_remove(bridge_entity(hass, UP))
    add_z2m_bridge(hass, setup_production, UP)  # back before the first subscribe is done

    held_at_logging.set()
    await settle()

    assert bridge_cache.get(hass, UP).replies_live
    assert all(len(two.subscribers.get(topic, [])) == 1 for topic in UP_HELD_TOPICS)
    assert len(connection.callbacks) == 2


async def test_another_bridge_entity_mid_subscribe_starts_nothing_more(
    hass, setup_production, two, connection, mqtt_up, held_at_logging
):
    await start_two(hass, setup_production)
    bridge_device = add_z2m_bridge(hass, setup_production, UP)
    er.async_get(hass).async_get_or_create(
        "binary_sensor",
        "mqtt",
        f"bridge_{bridge_ieee(UP)}_connection_state_{UP}",
        config_entry=setup_production,
        device_id=bridge_device.id,
    )

    held_at_logging.set()
    await settle()

    assert bridge_cache.get(hass, UP).replies_live
    assert all(len(two.subscribers.get(topic, [])) == 1 for topic in UP_HELD_TOPICS)


async def test_a_failed_subscribe_is_retried_only_once_its_bridge_goes_and_comes_back(
    hass, setup_production, two, connection, mqtt_up, monkeypatch
):
    subscribe = bridge.mqtt.async_subscribe
    refusing = True

    async def refuse_once(hass, topic, *args, **kwargs):
        if refusing and topic == up("state"):
            raise RuntimeError("MQTT is not connected")
        return await subscribe(hass, topic, *args, **kwargs)

    monkeypatch.setattr(bridge.mqtt, "async_subscribe", refuse_once)
    await start_two(hass, setup_production)
    assert bridge_cache.get(hass, UP) is None
    refusing = False

    # Still the same bridge: nothing retries a failed subscribe until it goes and comes back.
    er.async_get(hass).async_remove(bridge_entity(hass, UP))
    add_z2m_bridge(hass, setup_production, UP)
    await settle()

    assert bridge_cache.get(hass, UP).replies_live
    assert all(len(two.subscribers.get(topic, [])) == 1 for topic in UP_HELD_TOPICS)
