"""The pause ledger: which automations and switches the rig's runs have turned off, and for whom, so runs side by side
share them. In the git common dir with the locks and the journals (it holds household entity IDs).

`device_side-rig.paused.json` maps each entity to `{"was_on": bool, "holders": [...]}`, a holder being a run's
journal name (journal.Journal.name). It is read and written only under `device_side-rig.paused.lock`, held for one
pause or resume.

- Pausing an entity already in the ledger adds the run to its holders. Otherwise its state is read, and the entry is
  written before an entity that is on is turned off.
- Resuming takes the run off every entity's holders. One left with none is turned back on if it was on, and dropped.
- A holder whose journal lock nobody holds is dead: its run is gone. Each pause or resume prunes the dead first. An
  entity left with no holder is taken over by a run pausing it, as it is, or else resumed. So a crashed run's pauses
  come back with the next run's pause or resume, or with --recover's.
"""

import asyncio
import contextlib
import fcntl
import json
from collections.abc import AsyncIterator, Callable, Iterable
from pathlib import Path

from .client import HAClient
from .journal import locked, write_whole

NAME = "device_side-rig.paused.json"
LOCK_NAME = "device_side-rig.paused.lock"
LOCK_POLL_S = 0.1  # how often a run retries the ledger's lock, held only for one pause or resume


class Ledger:
    def __init__(self, directory: Path, holder: str, out: Callable[[str], None] = print):
        self.path, self.lock_path = directory / NAME, directory / LOCK_NAME
        self.directory, self.holder, self.out = directory, holder, out
        self.entries: dict[str, dict] = {}

    async def pause(self, ha: HAClient, entity_ids: Iterable[str]) -> None:
        """Hold each of `entity_ids` paused: join its holders, or turn it off if it is on. One HA doesn't know stops
        the run, before any test; the dead runs' entities this run doesn't pause are resumed first."""
        wanted = list(dict.fromkeys(entity_ids))
        async with self.edit():
            orphaned = self.prune()
            for entity_id in orphaned & set(wanted):  # taken over as it is, rather than resumed and paused again
                self.entries[entity_id]["holders"].append(self.holder)
            await self.resume_unheld(ha, orphaned - set(wanted))
            for entity_id in wanted:
                if (entry := self.entries.get(entity_id)) is not None:
                    if self.holder not in entry["holders"]:
                        entry["holders"].append(self.holder)
                        self.save()
                    continue
                if (state := await ha.get_state(entity_id)) is None:
                    raise SystemExit(f"{entity_id} in the profile's pause list has no state in Home Assistant")
                on = state["state"] == "on"
                self.entries[entity_id] = {"was_on": on, "holders": [self.holder]}
                self.save()
                if on:
                    await ha.call_service(entity_id.partition(".")[0], "turn_off", {"entity_id": entity_id})
                    self.out(f"Paused {entity_id} for the run.")

    async def resume(self, ha: HAClient) -> None:
        """Let go of what this run holds paused; whatever no live run holds any more goes back on if it was on."""
        async with self.edit():
            unheld = self.prune()
            for entity_id, entry in self.entries.items():
                if self.holder in entry["holders"]:
                    entry["holders"].remove(self.holder)
                    if not entry["holders"]:
                        unheld.add(entity_id)
            await self.resume_unheld(ha, unheld)

    def prune(self) -> set[str]:
        """Drop the dead holders; the entities left with none."""
        alive: dict[str, bool] = {}
        for entry in self.entries.values():
            entry["holders"] = [h for h in entry["holders"] if alive.setdefault(h, self.alive(h))]
        return {entity_id for entity_id, entry in self.entries.items() if not entry["holders"]}

    def alive(self, holder: str) -> bool:
        """Whether `holder`'s run still holds its journal lock: this run's own reads as alive, as flock tells handles
        apart even within a process."""
        if holder == self.holder:
            return True
        path = self.directory / f"{holder}.lock"
        try:
            handle = path.open("r")
        except FileNotFoundError:
            return False
        with handle:
            if locked(handle):  # free: the run is gone; closing the handle lets it go again
                return False
        return True

    async def resume_unheld(self, ha: HAClient, entity_ids: Iterable[str]) -> None:
        """Turn each back on if it was on, then drop it; a failure is printed, so it can be turned on by hand."""
        for entity_id in sorted(entity_ids):
            if self.entries[entity_id]["was_on"]:
                await turn_on(ha, entity_id, self.out)
            del self.entries[entity_id]
            self.save()

    @contextlib.asynccontextmanager
    async def edit(self) -> AsyncIterator[None]:
        """Hold the ledger's lock and its entries, read now; what is saved is written as it goes."""
        with self.lock_path.open("a+") as lock:
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    await asyncio.sleep(LOCK_POLL_S)
            self.entries = json.loads(self.path.read_text()) if self.path.exists() else {}
            try:
                yield
            finally:
                self.save()
                self.entries = {}

    def save(self) -> None:
        write_whole(self.path, self.entries)


async def turn_on(ha: HAClient, entity_id: str, out: Callable[[str], None]) -> None:
    """Turn a paused entity back on; a failure is printed, so it can be turned on by hand."""
    try:
        await ha.call_service(entity_id.partition(".")[0], "turn_on", {"entity_id": entity_id})
        out(f"Resumed {entity_id}.")
    except Exception as err:  # noqa: BLE001 - try every one, and say which stayed off
        out(f"Could not turn {entity_id} back on: {err}. Turn it on by hand.")
