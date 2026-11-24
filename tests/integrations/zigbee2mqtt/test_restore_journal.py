"""Zigbee2MQTT's restore journal: hue_native_control values owed back to the user, kept on disk and replayed."""

import asyncio
import logging

import pytest
from homeassistant.exceptions import UnsupportedStorageVersionError

from custom_components.deviceside.integrations.zigbee2mqtt import bridge_cache
from custom_components.deviceside.integrations.zigbee2mqtt import restore_journal as rj
from custom_components.deviceside.integrations.zigbee2mqtt.addressing import Address

from ...fixtures.zigbee2mqtt import INFO, add_z2m_bridge

STORE = "deviceside.zigbee2mqtt_restore_journal"
BASE = "zigbee2mqtt"
UP = "z2m_up"  # a second instance's base topic
STATE = "zigbee2mqtt/bridge/state"
OPTION = "hue_native_control"
LAMP = Address(BASE, "device", "0x01")


def owed_on_disk(hass_storage) -> dict:
    return hass_storage[STORE]["data"]


def left_owed(hass_storage, data: object, version: int = 2) -> None:
    hass_storage[STORE] = {"version": version, "key": STORE, "data": data}


def option_is(broker, ieee: str, value: bool) -> None:
    broker.retained[INFO]["config"]["devices"].setdefault(ieee, {})[OPTION] = value


@pytest.fixture
def mqtt_up(monkeypatch):
    async def ready(hass):
        return True

    monkeypatch.setattr(bridge_cache.mqtt, "async_wait_for_mqtt_client", ready)
    monkeypatch.setattr(bridge_cache.mqtt, "async_subscribe_connection_status", lambda hass, status: lambda: None)


async def settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def start(hass, entry) -> None:
    """The bridge cache, wired to the replay as entry setup wires it."""
    add_z2m_bridge(hass, entry)
    await bridge_cache.async_setup(hass, entry, lambda base: rj.request_replay(hass, base))
    await replayed(hass)


async def replayed(hass) -> None:
    await settle()
    for held in list(rj.replays(hass).values()):
        if held.task is not None:
            await held.task


# The journal


async def test_two_first_callers_share_one_journal(hass, setup_production, hass_storage):
    first, second = await asyncio.gather(rj.journal(hass), rj.journal(hass))
    assert first is second

    await asyncio.gather(first.add(LAMP, False), second.add(Address(BASE, "group", "7"), True))

    assert owed_on_disk(hass_storage) == {BASE: {"device/0x01": False, "group/7": True}}


@pytest.mark.parametrize("error", [OSError("disk full"), asyncio.CancelledError()])
async def test_a_save_that_fails_leaves_nothing_owed(hass, setup_production, monkeypatch, error):
    held = await rj.journal(hass)

    async def failing(data):
        raise error

    monkeypatch.setattr(held._store, "async_save", failing)

    with pytest.raises(type(error)):
        await held.add(LAMP, False)

    assert held.owed == {}


async def test_a_failed_load_is_retried(hass, setup_production, monkeypatch):
    load = rj.Journal.load
    calls: list[None] = []

    async def fails_once(self):
        calls.append(None)
        if len(calls) == 1:
            raise OSError("unreadable")
        await load(self)

    monkeypatch.setattr(rj.Journal, "load", fails_once)

    with pytest.raises(OSError, match="unreadable"):
        await rj.journal(hass)
    assert (await rj.journal(hass)).owed == {}


async def test_malformed_entries_are_dropped_and_the_rest_kept(hass, setup_production, hass_storage, caplog):
    left_owed(
        hass_storage,
        {
            BASE: {"0x01": False, "light/0x02": True, "device/": True, "device/0x03": "off", "group/7": True},
            UP: ["device/0x04"],
            "": {"device/0x05": False},
        },
    )

    with caplog.at_level(logging.WARNING):
        held = await rj.journal(hass)

    assert held.owed == {Address(BASE, "group", "7"): True}
    assert caplog.text.count("Skipped a malformed hue_native_control restore journal entry") == 6


@pytest.mark.parametrize("version", [1, 2])
async def test_a_journal_that_isnt_a_mapping_is_ignored(hass, setup_production, hass_storage, caplog, version):
    left_owed(hass_storage, ["device/0x01"], version)

    assert (await rj.journal(hass)).owed == {}
    assert "isn't a mapping" in caplog.text


async def test_it_round_trips_every_base_topic(hass, setup_production, hass_storage):
    """A base topic is kept verbatim, spaces and `/` included, and the same group ID on two instances is two entries."""
    held = await rj.journal(hass)
    owed = {
        Address(BASE, "group", "7"): True,
        Address(UP, "group", "7"): False,
        Address("  home/z2m", "device", "0x01"): False,
    }
    for address, value in owed.items():
        await held.add(address, value)

    assert hass_storage[STORE]["version"] == 2
    assert owed_on_disk(hass_storage) == {
        BASE: {"group/7": True},
        UP: {"group/7": False},
        "  home/z2m": {"device/0x01": False},
    }
    reloaded = rj.Journal(hass)
    await reloaded.load()
    assert reloaded.owed == owed


# Version 1, from before a key carried its base topic


async def test_a_version_1_journal_is_owed_on_the_default_base_topic(hass, setup_production, hass_storage):
    left_owed(hass_storage, {"device/0x01": False, "group/7": True}, version=1)

    assert (await rj.journal(hass)).owed == {LAMP: False, Address(BASE, "group", "7"): True}
    assert hass_storage[STORE]["version"] == 2
    assert owed_on_disk(hass_storage) == {BASE: {"device/0x01": False, "group/7": True}}


async def test_a_version_1_journal_keeps_dropping_only_its_malformed_entries(
    hass, setup_production, hass_storage, caplog
):
    left_owed(hass_storage, {"0x01": False, "device/0x03": "off", "group/7": True}, version=1)

    assert (await rj.journal(hass)).owed == {Address(BASE, "group", "7"): True}
    assert caplog.text.count("Skipped a malformed hue_native_control restore journal entry") == 2


async def test_a_version_1_restore_is_paid_on_the_default_instances_online(
    hass, setup_production, broker, mqtt_up, hass_storage
):
    left_owed(hass_storage, {"device/0x01": False}, version=1)
    option_is(broker, "0x01", True)

    await start(hass, setup_production)

    request = broker.requests()[0]
    assert (request["payload"]["id"], request["payload"]["options"]) == ("0x01", {OPTION: False})
    assert owed_on_disk(hass_storage) == {}


async def test_a_newer_journal_is_left_on_disk_unread(hass, setup_production, hass_storage, caplog):
    """From a later DeviceSide, before a downgrade: nothing here can read it, so nothing overwrites it either."""
    newer = {"format": "unknown"}
    left_owed(hass_storage, newer, version=3)

    with pytest.raises(UnsupportedStorageVersionError):
        await rj.journal(hass)
    await rj.replay(hass, BASE)

    assert "Couldn't read the hue_native_control restore journal" in caplog.text
    assert hass_storage[STORE] == {"version": 3, "key": STORE, "data": newer}


# Replay, on each online from bridge/state


async def test_the_retained_online_pays_what_is_owed(hass, setup_production, broker, mqtt_up, hass_storage):
    left_owed(hass_storage, {BASE: {"device/0x01": False}})
    option_is(broker, "0x01", True)

    await start(hass, setup_production)

    request = broker.requests()[0]["payload"]
    assert (request["id"], request["options"]) == ("0x01", {OPTION: False})
    assert (await rj.journal(hass)).owed == {}
    assert owed_on_disk(hass_storage) == {}


async def test_a_value_the_user_set_back_is_left_and_struck(hass, setup_production, broker, mqtt_up, hass_storage):
    left_owed(hass_storage, {BASE: {"device/0x01": False}})
    option_is(broker, "0x01", False)

    await start(hass, setup_production)

    assert broker.requests() == []
    assert (await rj.journal(hass)).owed == {}


async def test_a_refused_replay_stays_owed(hass, setup_production, broker, mqtt_up, hass_storage, caplog):
    left_owed(hass_storage, {BASE: {"group/7": True}})
    broker.reply = {"status": "error", "error": "refused"}

    await start(hass, setup_production)

    assert (await rj.journal(hass)).owed == {Address(BASE, "group", "7"): True}
    assert (
        "Couldn't put Zigbee2MQTT's hue_native_control back to True for a Zigbee2MQTT group with no light: "
        "RuntimeError('refused')" in (caplog.text)
    )


async def test_a_z2m_offline_at_startup_is_paid_when_it_comes_back(
    hass, setup_production, broker, mqtt_up, hass_storage
):
    left_owed(hass_storage, {BASE: {"device/0x01": False}})
    option_is(broker, "0x01", True)
    broker.retained[STATE] = {"state": "offline"}

    await start(hass, setup_production)
    assert broker.requests() == []

    broker.deliver(STATE, '{"state": "online"}')
    await replayed(hass)

    assert [r["payload"]["options"] for r in broker.requests()] == [{OPTION: False}]
    assert (await rj.journal(hass)).owed == {}


async def test_a_replay_waits_for_the_address_lock(hass, setup_production, broker, mqtt_up, hass_storage):
    """An action holding the address (its set to its restore) goes first; what it paid is skipped."""
    left_owed(hass_storage, {BASE: {"device/0x01": False, "device/0x02": False}})
    option_is(broker, "0x01", True)
    option_is(broker, "0x02", True)
    lock = rj.locks(hass).setdefault(LAMP, asyncio.Lock())
    await lock.acquire()

    add_z2m_bridge(hass, setup_production)
    await bridge_cache.async_setup(hass, setup_production, lambda base: rj.request_replay(hass, base))
    await settle()
    assert broker.requests() == []
    held = await rj.journal(hass)
    await held.strike(LAMP, False)  # the action's restore
    lock.release()
    await replayed(hass)

    assert [r["payload"]["id"] for r in broker.requests()] == ["0x02"]
    assert held.owed == {}


async def test_an_online_during_a_replay_runs_it_once_more(hass, setup_production, monkeypatch):
    runs: list[str] = []
    release = asyncio.Event()

    async def slow_replay(hass, base):
        runs.append(base)
        await release.wait()

    monkeypatch.setattr(rj, "replay", slow_replay)

    rj.request_replay(hass, BASE)
    await settle()
    rj.request_replay(hass, BASE)
    rj.request_replay(hass, BASE)
    assert runs == [BASE]
    release.set()
    await replayed(hass)
    assert runs == [BASE, BASE]

    rj.request_replay(hass, BASE)
    await replayed(hass)
    assert runs == [BASE] * 3


async def test_another_instances_online_during_a_replay_replays_it_too(hass, setup_production, monkeypatch):
    """Two onlines close together on two base topics: each instance's replay runs, side by side, once."""
    runs: list[str] = []
    release = asyncio.Event()

    async def slow_replay(hass, base):
        runs.append(base)
        await release.wait()

    monkeypatch.setattr(rj, "replay", slow_replay)

    rj.request_replay(hass, BASE)
    await settle()
    rj.request_replay(hass, UP)
    await settle()
    assert runs == [BASE, UP]
    release.set()
    await replayed(hass)
    assert runs == [BASE, UP]


async def test_an_unreadable_journal_warns(hass, setup_production, monkeypatch, caplog):
    async def unreadable(self):
        raise OSError("unreadable")

    monkeypatch.setattr(rj.Journal, "load", unreadable)

    await rj.replay(hass, BASE)

    assert (
        "Couldn't read the hue_native_control restore journal: OSError('unreadable'), so owed restores wait"
        in caplog.text
    )


async def test_a_strike_that_fails_warns(hass, setup_production, broker, mqtt_up, hass_storage, monkeypatch, caplog):
    left_owed(hass_storage, {BASE: {"device/0x01": False}})
    held = await rj.journal(hass)

    async def broken(*args):
        raise OSError("disk full")

    monkeypatch.setattr(held, "strike", broken)

    await rj.replay(hass, BASE)

    assert (
        "Couldn't strike the hue_native_control restore for a Zigbee2MQTT device with no light off the journal: "
        "OSError('disk full')" in caplog.text
    )
    assert not [r for r in caplog.records if r.name.startswith("custom_components") and "0x01" in r.getMessage()]


async def test_entry_setup_wires_the_replay(hass, setup_production, broker, mqtt_up, hass_storage):
    """Reloading the entry runs bridge_cache.async_setup as lifecycle.setup wires it: the retained online pays."""
    left_owed(hass_storage, {BASE: {"device/0x01": False}})
    option_is(broker, "0x01", True)
    add_z2m_bridge(hass, setup_production)

    assert await hass.config_entries.async_reload(setup_production.entry_id)
    await hass.async_block_till_done()
    await replayed(hass)

    assert (await rj.journal(hass)).owed == {}


# Several instances: each online pays its own instance's restores


def up_topic(suffix: str) -> str:
    return f"{UP}/bridge/{suffix}"


def option_requests(broker) -> list[tuple[str, str, bool]]:
    """Each options request, as (topic, ID, the value it writes)."""
    return [
        (p["topic"], p["payload"]["id"], p["payload"]["options"][OPTION])
        for p in broker.published
        if "/bridge/request/" in p["topic"]
    ]


@pytest.fixture
def two(broker):
    """A second instance on the broker; group 7 on each holds the value the other owes."""
    broker.retained[INFO]["config"]["groups"] = {"7": {OPTION: False}}
    broker.retained[up_topic("state")] = {"state": "online"}
    broker.retained[up_topic("info")] = {"config": {"devices": {}, "groups": {"7": {OPTION: True}}}}
    return broker


async def start_two(hass, entry) -> None:
    add_z2m_bridge(hass, entry, UP)
    await start(hass, entry)


async def test_two_instances_owing_the_same_group_are_paid_separately(
    hass, setup_production, two, mqtt_up, hass_storage
):
    left_owed(hass_storage, {BASE: {"group/7": True}, UP: {"group/7": False}})

    await start_two(hass, setup_production)

    assert sorted(option_requests(two)) == [
        (up_topic("request/group/options"), "7", False),
        ("zigbee2mqtt/bridge/request/group/options", "7", True),
    ]
    assert (await rj.journal(hass)).owed == {}
    assert owed_on_disk(hass_storage) == {}


async def test_an_online_pays_only_its_own_instances_restores(hass, setup_production, two, mqtt_up, hass_storage):
    """The default instance is offline: the other's online pays its own group 7, never the default's."""
    left_owed(hass_storage, {BASE: {"group/7": True}, UP: {"group/7": False}})
    two.retained[STATE] = {"state": "offline"}

    await start_two(hass, setup_production)

    assert option_requests(two) == [(up_topic("request/group/options"), "7", False)]
    assert (await rj.journal(hass)).owed == {Address(BASE, "group", "7"): True}

    two.deliver(STATE, '{"state": "online"}')
    await replayed(hass)

    assert option_requests(two)[1:] == [("zigbee2mqtt/bridge/request/group/options", "7", True)]
    assert (await rj.journal(hass)).owed == {}


async def test_a_restore_owed_on_a_base_with_no_bridge_stays_owed(
    hass, setup_production, broker, mqtt_up, hass_storage
):
    """Its instance is gone or renamed: nothing pays it, and nothing drops it, so its bridge coming back still can."""
    left_owed(hass_storage, {BASE: {"device/0x01": False}, "gone": {"device/0x05": False}})
    option_is(broker, "0x01", True)

    await start(hass, setup_production)

    assert [r["payload"]["id"] for r in broker.requests()] == ["0x01"]
    assert (await rj.journal(hass)).owed == {Address("gone", "device", "0x05"): False}
    assert owed_on_disk(hass_storage) == {"gone": {"device/0x05": False}}
