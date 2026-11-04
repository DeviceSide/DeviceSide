"""The home record: what a roaming bulb was before the rig first moved it, kept until it is back as it was, across
runs and crashes. In the git common dir with the locks and the journals (it holds household entity IDs).

`device_side-rig.home.json` maps a bulb's IEEE to:

- `entity_id`: its fixed entity ID, to say which bulb it is;
- `network`: its home network;
- `hue`: its Hue home, while it left Hue (Roamer.save_home): its device and light IDs, name, rooms, zones and the
  scene actions on its light; absent for a bulb that first left another network;
- `state`: its state in HA before the first move: on or off, and brightness with xy or a color temperature; None
  where HA had none.

An entry is written once, before the bulb's first move, and never overwritten while it exists: a second crash keeps
the first home. Only a part it lacks is filled in: the Hue home of a bulb found leaving Hue after it was written. It
is dropped only once the bulb is home, its Hue home is put back and its state is too. The file is written whole
under `device_side-rig.home.lock`; with no directory (a test's run, with no journal), the record lives in memory.
"""

import contextlib
import fcntl
import json
from collections.abc import Iterator
from pathlib import Path

from .journal import write_whole

NAME = "device_side-rig.home.json"
LOCK_NAME = "device_side-rig.home.lock"


class HomeRecord:
    def __init__(self, directory: Path | None):
        self.directory = directory
        self.entries: dict[str, dict] = {}  # in memory only with no directory

    def get(self, ieee: str) -> dict | None:
        return self.all().get(ieee)

    def all(self) -> dict[str, dict]:
        """The entries as they are now; read with no lock, as each write replaces the file whole."""
        if self.directory is None:
            return dict(self.entries)
        path = self.directory / NAME
        return json.loads(path.read_text()) if path.exists() else {}

    def add(self, ieee: str, entry: dict) -> bool:
        """Write `entry` for `ieee` unless one is there; whether it was written."""
        with self.edit() as entries:
            if ieee in entries:
                return False
            entries[ieee] = entry
            return True

    def fill(self, ieee: str, part: str, value: object) -> None:
        """Set one part of `ieee`'s entry where it has none; an entry with that part keeps it."""
        with self.edit() as entries:
            if (entry := entries.get(ieee)) is not None and entry.get(part) is None:
                entry[part] = value

    def drop(self, ieee: str) -> None:
        with self.edit() as entries:
            entries.pop(ieee, None)

    @contextlib.contextmanager
    def edit(self) -> Iterator[dict[str, dict]]:
        """The entries under the lock, read now and written back after: held only for one change."""
        if self.directory is None:
            yield self.entries
            return
        with (self.directory / LOCK_NAME).open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            path = self.directory / NAME
            entries = json.loads(path.read_text()) if path.exists() else {}
            before = json.dumps(entries, sort_keys=True)
            yield entries
            if json.dumps(entries, sort_keys=True) != before:
                write_whole(path, entries)


def light_state(state: dict | None) -> dict | None:
    """What of a light's HA state the record keeps: on or off, and when on its brightness and its xy or color
    temperature, whichever its color mode says. None for no state, or one neither on nor off."""
    if state is None or state["state"] not in ("on", "off"):
        return None
    kept: dict = {"state": state["state"]}
    if state["state"] == "off":
        return kept
    attributes = state.get("attributes", {})
    if attributes.get("brightness") is not None:
        kept["brightness"] = attributes["brightness"]
    if attributes.get("color_mode") == "color_temp" and attributes.get("color_temp_kelvin") is not None:
        kept["color_temp_kelvin"] = attributes["color_temp_kelvin"]
    elif attributes.get("xy_color") is not None:
        kept["xy_color"] = list(attributes["xy_color"])
    return kept
