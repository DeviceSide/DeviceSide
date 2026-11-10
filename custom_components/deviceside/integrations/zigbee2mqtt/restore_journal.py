"""A journal of the hue_native_control values still owed back to the user, so a restart can pay them.

native_control.py changes the option for one publish and restores it after. A restart or crash between the two would
leave the user's option flipped for good, so each change is journaled once Z2M has taken it and struck off once the
restore is confirmed. `replay` pays what a previous run left, from bridge_cache.async_setup.
"""

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from ...core.runtime import get_runtime

_LOGGER = logging.getLogger(__name__)

_KEY = "zigbee2mqtt_restore_journal"
_VERSION = 1


class Journal:
    """The owed values by "<kind>/<Z2M ID>"; each is the user's value, to write back."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, bool]] = Store(hass, _VERSION, "deviceside.zigbee2mqtt_restore_journal")
        self.owed: dict[str, bool] = {}

    async def load(self) -> None:
        self.owed = await self._store.async_load() or {}

    async def add(self, kind: str, z2m_id: str, value: bool) -> None:
        self.owed[f"{kind}/{z2m_id}"] = value
        await self._store.async_save(self.owed)

    async def strike(self, kind: str, z2m_id: str) -> None:
        if self.owed.pop(f"{kind}/{z2m_id}", None) is not None:
            await self._store.async_save(self.owed)


async def journal(hass: HomeAssistant) -> Journal:
    """The run's journal, loaded from disk on first use."""
    state = get_runtime(hass).integration_state
    if (held := state.get(_KEY)) is None:
        held = Journal(hass)
        await held.load()
        state[_KEY] = held
    return held


async def replay(hass: HomeAssistant) -> None:
    """Write back every value a previous run left owed, striking each off once Z2M confirms it. Never raises: what
    can't be paid now (Z2M offline) stays journaled for the next start."""
    from .bridge import OPTION, ensure_options  # noqa: PLC0415 - bridge imports bridge_cache, which calls this

    held = await journal(hass)
    for key, value in list(held.owed.items()):
        kind, z2m_id = key.split("/", 1)
        try:
            await ensure_options(hass, kind, [z2m_id], lambda _current, value=value: {OPTION: value}, lambda _id: None)
        except Exception as err:  # noqa: BLE001 - kept for the next start
            _LOGGER.warning("Couldn't put Zigbee2MQTT's %s back to %s for %s: %s", OPTION, value, key, err)
            continue
        await held.strike(kind, z2m_id)
        _LOGGER.info("Put Zigbee2MQTT's %s back to %s for %s, left over from before a restart", OPTION, value, key)
