"""Zigbee2MQTT's restore journal: hue_native_control values owed back to the user, kept on disk and replayed."""

import asyncio
import logging

import pytest

from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.integrations.zigbee2mqtt import bridge_cache
from custom_components.deviceside.integrations.zigbee2mqtt import restore_journal as rj

from ...fixtures.z2m import INFO

STORE = "deviceside.zigbee2mqtt_restore_journal"
STATE = "zigbee2mqtt/bridge/state"
OPTION = "hue_native_control"
LAMP = ("device", "0x01")


def owed_on_disk(hass_storage) -> dict:
    return hass_storage[STORE]["data"]


def left_owed(hass_storage, data: object) -> None:
    hass_storage[STORE] = {"version": 1, "key": STORE, "data": data}


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
    await bridge_cache.async_setup(hass, entry, lambda: rj.request_replay(hass))
    await replayed(hass)


async def replayed(hass) -> None:
    await settle()
    replays = get_runtime(hass).integration_state.get("zigbee2mqtt_restore_replays")
    if replays is not None and replays.task is not None:
        await replays.task


# The journal


async def test_two_first_callers_share_one_journal(hass, setup_production, hass_storage):
    first, second = await asyncio.gather(rj.journal(hass), rj.journal(hass))
    assert first is second

    await asyncio.gather(first.add(LAMP, False), second.add(("group", "7"), True))

    assert owed_on_disk(hass_storage) == {"device/0x01": False, "group/7": True}


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
    left_owed(hass_storage, {"0x01": False, "light/0x02": True, "device/": True, "device/0x03": "off", "group/7": True})

    with caplog.at_level(logging.WARNING):
        held = await rj.journal(hass)

    assert held.owed == {"group/7": True}
    assert caplog.text.count("Skipped a malformed hue_native_control restore journal entry") == 4


async def test_a_journal_that_isnt_a_mapping_is_ignored(hass, setup_production, hass_storage, caplog):
    left_owed(hass_storage, ["device/0x01"])

    assert (await rj.journal(hass)).owed == {}
    assert "isn't a mapping" in caplog.text


# Replay, on each online from bridge/state


async def test_the_retained_online_pays_what_is_owed(hass, setup_production, broker, mqtt_up, hass_storage):
    left_owed(hass_storage, {"device/0x01": False})
    option_is(broker, "0x01", True)

    await start(hass, setup_production)

    request = broker.requests()[0]["payload"]
    assert (request["id"], request["options"]) == ("0x01", {OPTION: False})
    assert (await rj.journal(hass)).owed == {}
    assert owed_on_disk(hass_storage) == {}


async def test_a_value_the_user_set_back_is_left_and_struck(hass, setup_production, broker, mqtt_up, hass_storage):
    left_owed(hass_storage, {"device/0x01": False})
    option_is(broker, "0x01", False)

    await start(hass, setup_production)

    assert broker.requests() == []
    assert (await rj.journal(hass)).owed == {}


async def test_a_refused_replay_stays_owed(hass, setup_production, broker, mqtt_up, hass_storage, caplog):
    left_owed(hass_storage, {"group/7": True})
    broker.reply = {"status": "error", "error": "refused"}

    await start(hass, setup_production)

    assert (await rj.journal(hass)).owed == {"group/7": True}
    assert "Couldn't put Zigbee2MQTT's hue_native_control back to True for group/7: refused" in caplog.text


async def test_a_z2m_offline_at_startup_is_paid_when_it_comes_back(
    hass, setup_production, broker, mqtt_up, hass_storage
):
    left_owed(hass_storage, {"device/0x01": False})
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
    left_owed(hass_storage, {"device/0x01": False, "device/0x02": False})
    option_is(broker, "0x01", True)
    option_is(broker, "0x02", True)
    lock = rj.locks(hass).setdefault(LAMP, asyncio.Lock())
    await lock.acquire()

    await bridge_cache.async_setup(hass, setup_production, lambda: rj.request_replay(hass))
    await settle()
    assert broker.requests() == []
    held = await rj.journal(hass)
    await held.strike(LAMP, False)  # the action's restore
    lock.release()
    await replayed(hass)

    assert [r["payload"]["id"] for r in broker.requests()] == ["0x02"]
    assert held.owed == {}


async def test_an_online_during_a_replay_runs_it_once_more(hass, setup_production, monkeypatch):
    runs: list[None] = []
    release = asyncio.Event()

    async def slow_replay(hass):
        runs.append(None)
        await release.wait()

    monkeypatch.setattr(rj, "replay", slow_replay)

    rj.request_replay(hass)
    await settle()
    rj.request_replay(hass)
    rj.request_replay(hass)
    assert len(runs) == 1
    release.set()
    await replayed(hass)
    assert len(runs) == 2

    rj.request_replay(hass)
    await replayed(hass)
    assert len(runs) == 3


async def test_an_unreadable_journal_warns(hass, setup_production, monkeypatch, caplog):
    async def unreadable(self):
        raise OSError("unreadable")

    monkeypatch.setattr(rj.Journal, "load", unreadable)

    await rj.replay(hass)

    assert "Couldn't read the hue_native_control restore journal: unreadable" in caplog.text


async def test_a_strike_that_fails_warns(hass, setup_production, broker, mqtt_up, hass_storage, monkeypatch, caplog):
    left_owed(hass_storage, {"device/0x01": False})
    held = await rj.journal(hass)

    async def broken(*args):
        raise OSError("disk full")

    monkeypatch.setattr(held, "strike", broken)

    await rj.replay(hass)

    assert "Couldn't strike the hue_native_control restore for device/0x01 off the journal: disk full" in caplog.text


async def test_entry_setup_wires_the_replay(hass, setup_production, broker, mqtt_up, hass_storage):
    """Reloading the entry runs bridge_cache.async_setup as __init__ wires it: the retained online pays."""
    left_owed(hass_storage, {"device/0x01": False})
    option_is(broker, "0x01", True)

    assert await hass.config_entries.async_reload(setup_production.entry_id)
    await hass.async_block_till_done()
    await replayed(hass)

    assert (await rj.journal(hass)).owed == {}
