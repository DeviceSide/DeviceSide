"""A journal of the hue_native_control values still owed back to the user, so a later run or retry can pay them.

native_control.py changes the option for one publish and restores it after. A restart or crash between the
two would leave the user's option flipped for good, so each change is journaled as its request goes out and struck off
once the restore is confirmed. `replay` pays what is left owed on an instance, each time that instance's bridge/state
says online (entry setup hooks it to each base topic's bridge cache): at startup, and again after a Z2M that was
offline comes back.

Each entry is keyed by its full Address, base topic included, as two instances can both have group 7. Store version 1
keyed by kind and ID alone, when only the default base topic was addressable, so its entries move under that base.
Known limit: an entry owed on a base topic that is renamed for good stays owed and unpaid, as only its own base's
online pays it; rare (a restore owed across a rename), so nothing prunes it.
"""

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .addressing import Address, entity_name
from .bridge import OPTION, ensure_options
from .bridge_cache import KINDS
from ...core.errors import describe
from ...core.runtime import get_runtime

_LOGGER = logging.getLogger(__name__)

_KEY = "zigbee2mqtt_restore_journal"
_LOCKS_KEY = "zigbee2mqtt_native_control_locks"
_REPLAYS_KEY = "zigbee2mqtt_restore_replays"
_VERSION = 2  # 2: owed values by base topic, then "<kind>/<Z2M ID>"; 1 had no base topic
_V1_BASE = "zigbee2mqtt"  # Z2M's default base topic, the only one version 1 could address

type _Stored = dict[str, dict[str, bool]]


class _Store(Store[_Stored]):
    async def _async_migrate_func(self, old_major_version: int, old_minor_version: int, old_data: Any) -> Any:
        """Version 1's entries, moved under the base topic they were owed on, verbatim: `load` checks them as it
        checks version 2's. A newer version than this code knows never gets here (HA's Store raises
        UnsupportedStorageVersionError, and `journal` retries), so it is left on disk unread rather than overwritten."""
        if old_major_version == 1:
            return {_V1_BASE: old_data} if isinstance(old_data, dict) and old_data else old_data
        raise NotImplementedError  # a newer minor version of this one: HA keeps the data as it is


def locks(hass: HomeAssistant) -> dict[Address, asyncio.Lock]:
    """One lock per address, held by whatever sets or restores its option: an action from the set to the restore,
    a replay for each entry it pays."""
    return get_runtime(hass).integration_state.setdefault(_LOCKS_KEY, {})


class Journal:
    """The owed values by address; each is the user's value, to write back."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store = _Store(hass, _VERSION, "deviceside.zigbee2mqtt_restore_journal")
        self.owed: dict[Address, bool] = {}

    async def load(self) -> None:
        """Read what a previous run left; an entry that isn't <base>: {"<device|group>/<ID>": bool} is dropped with a
        warning. Raises when the store can't be read, a newer version's included, so nothing overwrites it."""
        loaded = await self._store.async_load() or {}
        if not isinstance(loaded, dict):
            _LOGGER.warning(
                "Ignored the %s restore journal, which isn't a mapping (%s), so any restore it owed is lost",
                OPTION,
                type(loaded).__name__,
            )
            return
        for base, entries in loaded.items():
            if not base or not isinstance(entries, dict):
                _LOGGER.warning("Skipped a malformed %s restore journal entry, so that restore is lost", OPTION)
                continue
            for key, value in entries.items():
                kind, _, z2m_id = str(key).partition("/")
                if kind not in KINDS or not z2m_id or not isinstance(value, bool):
                    _LOGGER.warning("Skipped a malformed %s restore journal entry, so that restore is lost", OPTION)
                    continue
                self.owed[Address(base, kind, z2m_id)] = value  # type: ignore[arg-type] - kind is one of KINDS

    def owes(self, address: Address) -> bool | None:
        """The value owed back at this address, or None."""
        return self.owed.get(address)

    async def add(self, address: Address, value: bool) -> bool:
        """Owe value, unless an earlier restore is still owed: that one holds the user's own value, where this one
        may be an action's flipped value. Whether this call added it; a save that fails (or is cancelled) takes it
        back out of memory, and raises."""
        if address in self.owed:
            return False
        self.owed[address] = value
        try:
            await self._store.async_save(self._stored())
        except BaseException:
            self.owed.pop(address, None)
            raise
        return True

    async def strike(self, address: Address, value: bool) -> None:
        """Strike the entry once value, the one written back, is what it owes; another value leaves it owed."""
        if self.owed.get(address) == value:
            del self.owed[address]
            await self._store.async_save(self._stored())

    def _stored(self) -> _Stored:
        stored: _Stored = {}
        for address, value in self.owed.items():
            stored.setdefault(address.base, {})[f"{address.kind}/{address.z2m_id}"] = value
        return stored


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
    """An instance's replay in flight, and whether its bridge/state said online again while it ran."""

    def __init__(self) -> None:
        self.task: asyncio.Task[None] | None = None
        self.again = False


def replays(hass: HomeAssistant) -> dict[str, _Replays]:
    """Each base topic's replay."""
    return get_runtime(hass).integration_state.setdefault(_REPLAYS_KEY, {})


@callback
def request_replay(hass: HomeAssistant, base: str) -> None:
    """Pay what is owed on the instance with this base topic, in a task of its own: on each online from its
    bridge/state. One replay at a time per instance, and instances' replays run side by side: an online arriving while
    its instance's replay runs makes it run once more after, so an entry it failed on while Z2M was going down is
    retried."""
    held = replays(hass).setdefault(base, _Replays())
    if held.task is not None and not held.task.done():
        held.again = True
        return
    held.task = hass.async_create_background_task(_replay_until_settled(hass, base, held), "zigbee2mqtt replay")


async def _replay_until_settled(hass: HomeAssistant, base: str, held: _Replays) -> None:
    while True:
        held.again = False
        await replay(hass, base)
        if not held.again:
            return


async def replay(hass: HomeAssistant, base: str) -> None:
    """Write back every value left owed on the instance with this base topic, striking each off once Z2M has it, under
    the address's lock. Another instance's entries wait for its own online, so one whose bridge is gone stays owed.

    Only an option still holding the flipped value is written: one the user has set to their value since (in Z2M's
    UI) is left as it is, and struck. An entry an action paid while the replay waited for its lock is skipped. One
    that fails (Z2M offline) stays journaled for the next online, the next start, or the next action on the address.
    """
    try:
        held = await journal(hass)
    except Exception as err:  # noqa: BLE001 - nothing to pay from; the next online retries the load
        _LOGGER.warning(
            "Couldn't read the %s restore journal: %s, so owed restores wait for the next online", OPTION, describe(err)
        )
        return
    for address in [owed for owed in held.owed if owed.base == base]:
        name = entity_name(hass, address)
        async with locks(hass).setdefault(address, asyncio.Lock()):
            if (value := held.owes(address)) is None:
                continue
            try:
                await ensure_options(
                    hass,
                    base,
                    address.kind,
                    [address.z2m_id],
                    lambda current, value=value: {OPTION: value} if bool(current.get(OPTION)) != value else {},
                    # INFO only for a write Z2M confirmed: one the user had made already writes nothing.
                    lambda _id, value=value, name=name: _LOGGER.info(
                        "Put Zigbee2MQTT's %s back to %s for %s, left owed by an earlier restore", OPTION, value, name
                    ),
                )
            except Exception as err:  # noqa: BLE001 - kept for the next try
                _LOGGER.warning(
                    "Couldn't put Zigbee2MQTT's %s back to %s for %s: %s, so it stays owed",
                    OPTION,
                    value,
                    name,
                    describe(err),
                )
                continue
            try:
                await held.strike(address, value)
            except Exception as err:  # noqa: BLE001 - struck in memory; the next start finds it already paid
                _LOGGER.warning(
                    "Couldn't strike the %s restore for %s off the journal: %s, so the next start strikes it",
                    OPTION,
                    name,
                    describe(err),
                )
