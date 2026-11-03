"""What a rig run has changed and not yet put back, on disk so the next run can put it back after an abort.

Each section is written before the change it guards and cleared once that change is undone; an empty journal is
deleted. scripts/rig.py keeps them in the git common dir, out of the repo: they hold household entity IDs.

Each run has its own journal, `device_side-rig.journal.<id>.json`, and holds a lock on `<id>.lock` beside it for its
whole life. A journal whose lock nobody holds is an orphan: its run died, and another run may put back what it left.
The lock file is locked before it takes its name, so whoever finds one unlocked knows its run is gone.
"""

import fcntl
import json
import os
import secrets
from pathlib import Path
from typing import Any, TextIO

PREFIX = "device_side-rig.journal."
# The one journal every run shared before each had its own; only --recover, which holds everything, puts it back.
LEGACY_NAME = "device_side-rig.journal.json"


class Journal:
    def __init__(self, path: Path, lock: TextIO | None = None):
        self.path = path
        self.sections: dict[str, Any] = json.loads(path.read_text()) if path.exists() else {}
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
        """Write the file whole and move it into place, so a process killed mid-write leaves the previous one."""
        if not self.sections:
            self.path.unlink(missing_ok=True)
            return
        temp = self.path.with_name(f"{self.path.name}.tmp")
        temp.write_text(json.dumps(self.sections, indent=2))
        os.replace(temp, self.path)


def orphans(directory: Path) -> list[Journal]:
    """The journals in `directory` whose runs have died, each locked by this process until released; sweeps up the
    lock files dead runs left with no journal."""
    found = []
    for lock_path in sorted(directory.glob(f"{PREFIX}*.lock")):
        handle = lock_path.open("a+")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()  # a live run's
            continue
        journal = Journal(lock_path.with_suffix(".json"), handle)
        if journal:
            found.append(journal)
        else:
            journal.release()
    return found
