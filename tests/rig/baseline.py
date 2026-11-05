"""The baseline: what the rig's runs change on HA and Z2M beyond the devices' own state, and what it was before, so
runs side by side share each change and the last one out puts it back. In the git common dir with the locks and the
journals (it holds household entity IDs).

`deviceside-rig.baseline.json` maps `kind:key` to `{"original": ..., "holders": [...]}`. It is read and written only
under `deviceside-rig.baseline.lock`, held for one hold or release. The kinds:

- an entity's domain (`automation`, `switch`), keyed by its entity ID: paused for the run; original "on" or "off".
- `ha_log_level`, keyed by an HA domain: its log level's name.
- `z2m_log_level`, with no key: Z2M's log level. Read as debug or trace while no run holds it, it is recorded as info:
  a run left it raised, and debug is never a resting level.
- `z2m_option`, keyed `<ieee>:<name>`: a Z2M device option, None while unset.

A holder is a run's journal name (journal.Journal.name), a `#` and its role (`pause`, `debug`, `join`, `case:<lane>`),
so each part of a run lets go of its own holds.

- Holding a key already in the baseline adds the holder. Otherwise its original is read, and written before the
  change, which is the caller's `apply`, run on every hold.
- Releasing takes the holder off every entry. One left with none is put back and dropped; a put-back that fails is
  printed and stays, held by no one, for the next run's prune or --recover to try again.
- A holder whose run's journal lock nobody holds is dead. Each hold or release prunes the dead first, and puts back
  what they leave unheld, unless the hold takes it over as it is.

With no directory (a test's run, with no journal), the baseline lives in memory. On first use the pause ledger it
replaced, `deviceside-rig.paused.json`, is read in.
"""

import asyncio
import contextlib
import fcntl
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from pathlib import Path
from typing import Any

from .client import HAClient
from .journal import Journal, locked, write_whole

NAME = "deviceside-rig.baseline.json"
LOCK_NAME = "deviceside-rig.baseline.lock"
LEDGER_NAME = "deviceside-rig.paused.json"  # the pause ledger's, read in once
LOCK_POLL_S = 0.1  # how often a run retries the baseline's lock, held only for one hold or release
RAISED_Z2M_LEVELS = ("debug", "trace")
RESTING_Z2M_LEVEL = "info"

Apply = Callable[[Any], Awaitable[None]]  # makes the change, given the original


class BaselineError(Exception):
    """An original that can't be read: nothing is held or changed."""


class Baseline:
    def __init__(self, ha: HAClient, directory: Path | None, holder: str, out: Callable[[str], None] = print):
        self.ha, self.directory, self.holder, self.out = ha, directory, holder, out
        self.run = holder.partition("#")[0]
        self.entries: dict[str, dict] = {}

    @classmethod
    def of(cls, ha: HAClient, journal: Journal | None, role: str, out: Callable[[str], None] = print) -> Baseline:
        """The baseline as `role` of the run `journal` names; in memory with no journal."""
        if journal is None:
            return cls(ha, None, role, out)
        return cls(ha, journal.path.parent, f"{journal.name}#{role}", out)

    async def hold(self, *holds: tuple[str, str, Apply]) -> None:
        """Hold each (kind, key, apply): record its original if no one has, then apply. What dead runs left unheld
        and this doesn't take over is put back first. An original that can't be read raises BaselineError, keeping
        the holds before it."""
        async with self.edit() as unheld:
            await self.put_back(unheld - {entry_name(kind, key) for kind, key, _ in holds})
            for kind, key, apply in holds:
                name = entry_name(kind, key)
                if (entry := self.entries.get(name)) is None:
                    entry = {"original": await self.read(kind, key), "holders": []}
                    self.entries[name] = entry
                if self.holder not in entry["holders"]:
                    entry["holders"].append(self.holder)
                self.save()
                await apply(entry["original"])

    async def pause(self, entity_ids: Iterable[str]) -> None:
        """Hold each entity off: turned off if it is on. One HA doesn't know stops the run, before any test."""

        def turn_off(entity_id: str) -> Apply:
            async def apply(original: Any) -> None:
                if original == "on":
                    await self.ha.call_service(entity_id.partition(".")[0], "turn_off", {"entity_id": entity_id})
                    self.out(f"Paused {entity_id} for the run.")

            return apply

        wanted = dict.fromkeys(entity_ids)
        try:
            await self.hold(*[(entity_id.partition(".")[0], entity_id, turn_off(entity_id)) for entity_id in wanted])
        except BaselineError as err:
            raise SystemExit(str(err)) from None

    async def release(self) -> None:
        """Let go of what this holder holds, and put back whatever no live run holds any more. A holder with no role
        (recovery, as the dead run) lets go of every role's."""
        async with self.edit() as unheld:
            for name, entry in self.entries.items():
                entry["holders"] = [holder for holder in entry["holders"] if not self.mine(holder)]
                if not entry["holders"]:
                    unheld.add(name)
            await self.put_back(unheld)

    async def prune(self) -> None:
        """Put back what dead runs left, holding nothing."""
        async with self.edit() as unheld:
            await self.put_back(unheld)

    def mine(self, holder: str) -> bool:
        return holder == self.holder or ("#" not in self.holder and holder.partition("#")[0] == self.holder)

    def alive(self, holder: str) -> bool:
        """Whether `holder`'s run still holds its journal lock: this run's own reads as alive, as flock tells handles
        apart even within a process."""
        run = holder.partition("#")[0]
        if run == self.run or self.directory is None:
            return True
        try:
            handle = (self.directory / f"{run}.lock").open("r")
        except FileNotFoundError:
            return False
        with handle:
            if locked(handle):  # free: the run is gone; closing the handle lets it go again
                return False
        return True

    # --- originals --------------------------------------------------------------------------------------------------

    async def read(self, kind: str, key: str) -> Any:
        if kind == "ha_log_level":
            levels = await self.ha.log_levels()
            if key not in levels:
                raise BaselineError(f"HA doesn't report {key}")
            return logging.getLevelName(levels[key])
        if kind == "z2m_log_level":
            if (level := await self.ha.z2m_log_level()) is None:
                raise BaselineError("Z2M's bridge/info gives no log level")
            if level in RAISED_Z2M_LEVELS:
                self.out(f"Z2M's log level is {level} with no run holding it; it goes back to {RESTING_Z2M_LEVEL}.")
                return RESTING_Z2M_LEVEL
            return level
        if kind == "z2m_option":
            ieee, _, option = key.partition(":")
            return (await self.ha.z2m_device_options(ieee)).get(option)
        if (state := await self.ha.get_state(key)) is None:
            raise BaselineError(f"{key} in the profile's pause list has no state in Home Assistant")
        return "on" if state["state"] == "on" else "off"

    async def restore(self, kind: str, key: str, original: Any) -> None:
        if kind == "ha_log_level":
            if key in await self.ha.log_levels():  # one HA no longer reports (it restarted since) is back already
                await self.ha.set_log_level(key, original)
        elif kind == "z2m_log_level":
            await self.ha.z2m_set_log_level(original)
        elif kind == "z2m_option":
            ieee, _, option = key.partition(":")
            if await self.ha.z2m_device(ieee) is not None:  # one Z2M removed has dropped its options
                await self.ha.set_z2m_device_options(ieee, {option: original})
        elif original == "on":
            await self.ha.call_service(kind, "turn_on", {"entity_id": key})
            self.out(f"Resumed {key}.")

    async def put_back(self, names: Iterable[str]) -> None:
        """Put each entry back and drop it; one that fails is printed and stays, held by no one."""
        for name in sorted(names):
            kind, _, key = name.partition(":")
            original = self.entries[name]["original"]
            try:
                await self.restore(kind, key, original)
            except Exception as err:  # noqa: BLE001 - try every one, and say which is left
                self.out(f"Could not put {name} back to {original}: {err}. --recover tries again.")
                continue
            del self.entries[name]
            self.save()

    # --- the file ---------------------------------------------------------------------------------------------------

    @contextlib.asynccontextmanager
    async def edit(self) -> AsyncIterator[set[str]]:
        """Hold the baseline's lock, with its entries read now and the dead holders dropped; yields the entries left
        with no holder. What is saved is written as it goes."""
        if self.directory is None:
            yield self.drop_dead()
            return
        with (self.directory / LOCK_NAME).open("a+") as lock:
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    await asyncio.sleep(LOCK_POLL_S)
            self.entries = self.load()
            try:
                yield self.drop_dead()
            finally:
                self.save()
                self.entries = {}

    def drop_dead(self) -> set[str]:
        """Drop the dead holders; the entries left with none."""
        alive: dict[str, bool] = {}
        for entry in self.entries.values():
            entry["holders"] = [h for h in entry["holders"] if alive.setdefault(h, self.alive(h))]
        return {name for name, entry in self.entries.items() if not entry["holders"]}

    def load(self) -> dict[str, dict]:
        assert self.directory is not None
        if (path := self.directory / NAME).exists():
            return json.loads(path.read_text())
        if not (ledger := self.directory / LEDGER_NAME).exists():
            return {}
        entries = {
            f"{entity_id.partition('.')[0]}:{entity_id}": {
                "original": "on" if entry["was_on"] else "off",
                "holders": entry["holders"],
            }
            for entity_id, entry in json.loads(ledger.read_text()).items()
        }
        write_whole(path, entries)
        ledger.unlink()
        return entries

    def save(self) -> None:
        if self.directory is not None:
            write_whole(self.directory / NAME, self.entries)


def entry_name(kind: str, key: str) -> str:
    return f"{kind}:{key}" if key else kind
