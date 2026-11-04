"""What a rig run has changed and not yet put back, on disk so the next run can put it back after an abort.

Each section is written before the change it guards and cleared once that change is undone; an empty journal is
deleted. scripts/rig.py keeps them in the git common dir, out of the repo: they hold household entity IDs.

Each run has its own journal, `device_side-rig.journal.<id>.json`, and holds a lock on `<id>.lock` beside it for its
whole life. A journal whose lock nobody holds is an orphan: its run died, and another run may put back what it left.
The lock file is locked before it takes its name, so whoever finds one unlocked knows its run is gone.

Each journal records when it was first saved, `started`, beside its sections, so orphans are put back oldest first: a
later run's changes were made on top of an earlier one's.
"""

import fcntl
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, TextIO

PREFIX = "device_side-rig.journal."
# A dry run or --check probing a journal's lock holds it for a moment; a run that finds it locked looks again this many
# times, this far apart, before taking it for a live run's.
PROBES = 3
PROBE_GAP_S = 0.05
# The one journal every run shared before each had its own; only --recover, which holds everything, puts it back.
LEGACY_NAME = "device_side-rig.journal.json"
STARTED = "started"


class Journal:
    def __init__(self, path: Path, lock: TextIO | None = None):
        self.path = path
        self.sections: dict[str, Any] = json.loads(path.read_text()) if path.exists() else {}
        # When it was first saved; one from before `started` goes by its file's age.
        self.started: float | None = self.sections.pop(STARTED, None)
        if self.started is None and path.exists():
            self.started = path.stat().st_mtime
        self.lock = lock  # held while this process owns the journal: its own, or an orphan it is putting back

    @classmethod
    def start(cls, directory: Path) -> Journal:
        """A new run's journal, locked for the process's life; nothing is on disk but the lock until it is written."""
        name = f"{PREFIX}{os.getpid()}-{secrets.token_hex(3)}"
        temp = directory / f"{name}.lock.tmp"
        lock = temp.open("a+")
        fcntl.flock(lock, fcntl.LOCK_EX)
        os.rename(temp, directory / f"{name}.lock")  # the inode, and so the lock, moves with it
        return cls(directory / f"{name}.json", lock)

    @property
    def name(self) -> str:
        """The run's name, which its lock file and the baseline know it by."""
        return self.path.stem

    @property
    def lock_path(self) -> Path:
        return self.path.with_suffix(".lock")

    def release(self) -> None:
        """Let go of the journal: its lock file goes with it once the journal is empty; otherwise it is an orphan."""
        if self.lock is None:
            return
        if not self.path.exists():
            self.lock_path.unlink(missing_ok=True)  # still held, so no one else is using it
        self.lock.close()
        self.lock = None

    def __bool__(self) -> bool:
        return bool(self.sections)

    def get(self, section: str, default: Any = None) -> Any:
        return self.sections.get(section, default)

    def update(self, **sections: Any) -> None:
        self.sections |= sections
        self.save()

    def put(self, section: str, key: str, value: Any) -> None:
        """Set one entry of a section that holds several, such as one per lane, leaving the others."""
        self.sections.setdefault(section, {})[key] = value
        self.save()

    def drop(self, section: str, key: str) -> None:
        """Remove one entry of a section, and the section once it is empty."""
        if (entries := self.sections.get(section)) is not None:
            entries.pop(key, None)
            if not entries:
                del self.sections[section]
        self.save()

    def clear(self, *sections: str) -> None:
        for section in sections:
            self.sections.pop(section, None)
        self.save()

    def save(self) -> None:
        if not self.sections:
            self.started = None
        elif self.started is None:
            self.started = time.time()
        write_whole(self.path, {**self.sections, STARTED: self.started} if self.sections else {})


def write_whole(path: Path, data: dict) -> None:
    """Write `data` to `path` whole and move it into place, so a process killed mid-write leaves the previous file;
    empty, the file is deleted."""
    if not data:
        path.unlink(missing_ok=True)
        return
    temp = path.with_name(f"{path.name}.tmp")
    temp.write_text(json.dumps(data, indent=2))
    os.replace(temp, path)


def orphans(directory: Path) -> list[Journal]:
    """The journals in `directory` whose runs have died, each locked by this process until released; sweeps up the
    lock files dead runs left with no journal. Oldest first."""
    found = []
    for lock_path in sorted(directory.glob(f"{PREFIX}*.lock")):
        handle = lock_path.open("a+")
        if not locked(handle):
            handle.close()  # a live run's
            continue
        journal = Journal(lock_path.with_suffix(".json"), handle)
        if journal:
            found.append(journal)
        else:
            journal.release()
    return sorted(found, key=lambda journal: journal.started or 0.0)


def locked(handle) -> bool:
    """Take `handle`'s lock if it comes free within PROBES tries; whether it did."""
    for probe in range(PROBES):
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            if probe < PROBES - 1:
                time.sleep(PROBE_GAP_S)
    return False
