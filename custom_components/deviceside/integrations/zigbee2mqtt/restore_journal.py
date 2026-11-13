"""A journal of the hue_native_control values still owed back to the user, so a later run or retry can pay them.

native_control.py changes the option for one publish and restores it after. A restart or crash between the two would
leave the user's option flipped for good, so each change is journaled as its request goes out and struck off once the
restore is confirmed. `replay` pays what is left owed, each time Z2M's bridge/state says online (entry setup hooks it
to the bridge cache): at startup, and again after a Z2M that was offline comes back.
"""

import asyncio
import logging
from typing import Literal

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .addressing import entity_name
from .bridge import OPTION, ensure_options
from ...core.errors import describe
from ...core.runtime import get_runtime

_LOGGER = logging.getLogger(__name__)

_KEY = "zigbee2mqtt_restore_journal"
_LOCKS_KEY = "zigbee2mqtt_native_control_locks"
_REPLAYS_KEY = "zigbee2mqtt_restore_replays"
_VERSION = 1
_KINDS = ("device", "group")

type Address = tuple[Literal["device", "group"], str]  # Z2M's options section and the ID in it


def locks(hass: HomeAssistant) -> dict[Address, asyncio.Lock]:
    """One lock per address, held by whatever sets or restores its option: an action from the set to the restore,
    a replay for each entry it pays."""
    return get_runtime(hass).integration_state.setdefault(_LOCKS_KEY, {})


class Journal:
    """The owed values by "<kind>/<Z2M ID>"; each is the user's value, to write back."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, bool]] = Store(hass, _VERSION, "deviceside.zigbee2mqtt_restore_journal")
        self.owed: dict[str, bool] = {}

    async def load(self) -> None:
        """Read what a previous run left; an entry that isn't "<device|group>/<ID>": bool is dropped with a warning."""
        loaded = await self._store.async_load() or {}
        if not isinstance(loaded, dict):
            _LOGGER.warning("Ignored the %s restore journal, which isn't a mapping: %s", OPTION, type(loaded).__name__)
            return
        for key, value in loaded.items():
            kind, _, z2m_id = str(key).partition("/")
            if kind not in _KINDS or not z2m_id or not isinstance(value, bool):
                _LOGGER.warning("Skipped a malformed %s restore journal entry", OPTION)
                continue
            self.owed[key] = value

    def owes(self, address: Address) -> bool | None:
        """The value owed back at this address, or None."""
        return self.owed.get(_key(address))

    async def add(self, address: Address, value: bool) -> bool:
        """Owe value, unless an earlier restore is still owed: that one holds the user's own value, where this one
        may be an action's flipped value. Whether this call added it; a save that fails (or is cancelled) takes it
        back out of memory, and raises."""
        if (key := _key(address)) in self.owed:
            return False
        self.owed[key] = value
        try:
            await self._store.async_save(self.owed)
        except BaseException:
            self.owed.pop(key, None)
            raise
        return True

    async def strike(self, address: Address, value: bool) -> None:
        """Strike the entry once value, the one written back, is what it owes; another value leaves it owed."""
        if self.owed.get(key := _key(address)) == value:
            del self.owed[key]
            await self._store.async_save(self.owed)


def _key(address: Address) -> str:
    return f"{address[0]}/{address[1]}"


async def journal(hass: HomeAssistant) -> Journal:
    """The run's journal, loaded from disk on first use. Single-flight: every caller awaits the one load, so two
    first callers share one Journal. A load that failed or was cancelled is retried by the next caller."""
    state = get_runtime(hass).integration_state
    loading: asyncio.Task[Journal] | None = state.get(_KEY)
    if loading is not None and loading.done() and not loading.cancelled() and loading.exception() is None:
        return loading.result()  # loaded: no await on the publish path
    if loading is None or (loading.done() and (loading.cancelled() or loading.exception() is not None)):
        loading = state[_KEY] = hass.async_create_task(_load(hass), "zigbee2mqtt restore journal load")
    # Shielded, so one caller's cancel doesn't cancel the load the others await.
    return await asyncio.shield(loading)


async def _load(hass: HomeAssistant) -> Journal:
    held = Journal(hass)
    await held.load()
    return held


class _Replays:
    """The replay in flight, and whether bridge/state said online again while it ran."""

    def __init__(self) -> None:
        self.task: asyncio.Task[None] | None = None
        self.again = False


@callback
def request_replay(hass: HomeAssistant) -> None:
    """Pay what is owed, in a task of its own: on each online from bridge/state. One replay at a time: an online
    arriving while one runs makes it run once more after, so an entry it failed on while Z2M was going down is
    retried."""
    replays: _Replays = get_runtime(hass).integration_state.setdefault(_REPLAYS_KEY, _Replays())
    if replays.task is not None and not replays.task.done():
        replays.again = True
        return
    replays.task = hass.async_create_background_task(_replay_until_settled(hass, replays), "zigbee2mqtt replay")


async def _replay_until_settled(hass: HomeAssistant, replays: _Replays) -> None:
    while True:
        replays.again = False
        await replay(hass)
        if not replays.again:
            return


async def replay(hass: HomeAssistant) -> None:
    """Write back every value left owed, striking each off once Z2M has it, under the address's lock.

    Only an option still holding the flipped value is written: one the user has set to their value since (in Z2M's
    UI) is left as it is, and struck. An entry an action paid while the replay waited for its lock is skipped. One
    that fails (Z2M offline) stays journaled for the next online, the next start, or the next action on the address.
    """
    try:
        held = await journal(hass)
    except Exception as err:  # noqa: BLE001 - nothing to pay from; the next online retries the load
        _LOGGER.warning("Couldn't read the %s restore journal: %s", OPTION, describe(err))
        return
    for key in list(held.owed):
        kind, z2m_id = key.split("/", 1)
        address: Address = (kind, z2m_id)  # type: ignore[assignment] - load keeps only device and group keys
        name = entity_name(hass, kind, z2m_id)  # type: ignore[arg-type] - as address above
        async with locks(hass).setdefault(address, asyncio.Lock()):
            if (value := held.owes(address)) is None:
                continue
            try:
                await ensure_options(
                    hass,
                    kind,
                    [z2m_id],
                    lambda current, value=value: {OPTION: value} if bool(current.get(OPTION)) != value else {},
                    lambda _id: None,
                )
            except Exception as err:  # noqa: BLE001 - kept for the next try
                _LOGGER.warning(
                    "Couldn't put Zigbee2MQTT's %s back to %s for %s: %s", OPTION, value, name, describe(err)
                )
                continue
            try:
                await held.strike(address, value)
            except Exception as err:  # noqa: BLE001 - struck in memory; the next start finds it already paid
                _LOGGER.warning(
                    "Couldn't strike the %s restore for %s off the journal: %s", OPTION, name, describe(err)
                )
        _LOGGER.info("Put Zigbee2MQTT's %s back to %s for %s, left owed by an earlier restore", OPTION, value, name)
