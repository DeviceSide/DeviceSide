"""What the Director says about its lights that a call can't wait to read: which are light groups, their members, and
which can't halt or run a ramp. Read as each Control4 entry loads and held here, so expand_group and supports() need
no I/O. A change made in Composer shows after the Control4 entry next reloads. docs/integrations/control4/internals.md,
`inventory`.

- Groups: a light group made with the open-source Light Group driver (`light_group.c4z`) is a native group: one light
  item that takes one command and sends it to its lights itself. Its members are light item ids in the driver's
  `Lights` property.
- Stop: a light whose own capabilities say `supports_brightness_stop: false` ignores SET_BRIGHTNESS_STOP, and its
  Director shows a ramp's end at once (Tested behavior), so a stop could only be confirmed wrongly.
- Ramp: a light on a driver in NO_RAMP_DRIVERS jumps to RAMP_TO_LEVEL's level, ignoring its time (Tested behavior), so
  a raise or lower would jump. Its capabilities don't say so: they claim brightness rates.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, callback

from .director import CAPABILITIES, item_id
from ...core.errors import describe
from ...core.models import Target
from ...core.resolver import resolve_members
from ...core.runtime import get_runtime

_LOGGER = logging.getLogger(__name__)

GROUP_DRIVER = "light_group.c4z"
# Chowmain's "Link Client - Light".
NO_RAMP_DRIVERS = frozenset({"chowmain_link_light.c4z"})
# The group driver's property holding its lights' item ids, comma-separated.
MEMBERS_PROPERTY = "Lights"
# Every item's capabilities in one request.
_CAPABILITIES_URI = f"/api/v1/items/variables?varnames={quote(CAPABILITIES)}"
_KEY = "control4_inventory"


@dataclass(slots=True)
class Inventory:
    """One Control4 entry's: each group's light item id to its members' item ids, and the items that can't stop or
    ramp."""

    groups: dict[int, tuple[int, ...]] = field(default_factory=dict)
    no_stop: frozenset[int] = frozenset()
    no_ramp: frozenset[int] = frozenset()


def _held(hass: HomeAssistant) -> dict[str, Inventory]:
    return get_runtime(hass).integration_state.setdefault(_KEY, {})


def _inventory(hass: HomeAssistant, target: Target) -> Inventory:
    return _held(hass).get(target.config_entry.entry_id, Inventory())


def is_group(hass: HomeAssistant, target: Target) -> bool:
    return item_id(target) in _inventory(hass, target).groups


def expand_group(hass: HomeAssistant, target: Target) -> list[Target] | None:
    """The group's lights that have a Control4 light entity, sorted by entity_id."""
    if (members := _inventory(hass, target).groups.get(item_id(target))) is None:
        return None
    return resolve_members(hass, get_runtime(hass).registry, target, "control4", (str(member) for member in members))


def can_stop(hass: HomeAssistant, target: Target) -> bool:
    """False only for a light whose capabilities said it can't halt a ramp; one that said nothing can."""
    return item_id(target) not in _inventory(hass, target).no_stop


def can_ramp(hass: HomeAssistant, target: Target) -> bool:
    """False only for a light on a driver known to ignore a ramp's time."""
    return item_id(target) not in _inventory(hass, target).no_ramp


def driven_by(items: list[dict[str, Any]], drivers: frozenset[str]) -> list[tuple[int, int]]:
    """(driver item, light item) for each item in the Director's item list, as core holds it
    (runtime_data.director_all_items), whose parent is an item of one of the drivers, as core ties a light entity to
    its device."""
    parents = {item["id"] for item in items if item.get("filename") in drivers and "id" in item}
    return [(item["parentId"], item["id"]) for item in items if item.get("parentId") in parents and "id" in item]


def group_items(items: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """(driver item, light item) for each Light Group driver group."""
    return driven_by(items, frozenset({GROUP_DRIVER}))


def parse_members(properties: list[dict[str, Any]]) -> tuple[int, ...]:
    """The light item ids in the driver's `Lights` property; none for a group with no lights chosen."""
    value = next((row.get("value") for row in properties if row.get("name") == MEMBERS_PROPERTY), None)
    return tuple(int(part) for part in str(value or "").split(",") if part.strip().isdecimal())


def parse_no_stop(rows: list[dict[str, Any]]) -> frozenset[int]:
    """The items whose capabilities say `supports_brightness_stop: false`."""
    no_stop = set()
    for row in rows:
        dynamic = row.get("value", {}).get("DynamicCapabilities") if isinstance(row.get("value"), dict) else None
        if isinstance(dynamic, dict) and dynamic.get("supports_brightness_stop") is False and "id" in row:
            no_stop.add(row["id"])
    return frozenset(no_stop)


async def load(hass: HomeAssistant, control4: ConfigEntry) -> None:
    """Read the entry's groups and stop flags and hold them, replacing what was held for it. A group whose read fails
    runs as a plain light; a failed capabilities read leaves every light able to stop, as before it was read."""
    runtime = getattr(control4, "runtime_data", None)
    director = getattr(runtime, "director", None)
    items = getattr(runtime, "director_all_items", None) or []
    inventory = Inventory(no_ramp=frozenset(light for _, light in driven_by(items, NO_RAMP_DRIVERS)))
    for driver, light in group_items(items):
        try:
            properties = json.loads(await director.send_get_request(f"/api/v1/items/{driver}/properties"))
            inventory.groups[light] = parse_members(properties)
        except Exception as err:  # noqa: BLE001 - one group's failure leaves only that group a plain light
            _LOGGER.warning(
                "A Control4 light group's members couldn't be read (%s); it runs as a plain light", describe(err)
            )
    try:
        inventory.no_stop = parse_no_stop(json.loads(await director.send_get_request(_CAPABILITIES_URI)))
    except Exception as err:  # noqa: BLE001 - stop is then sent to every light, as before
        _LOGGER.warning(
            "Control4 lights' capabilities couldn't be read (%s); stop is sent to every light", describe(err)
        )
    _held(hass)[control4.entry_id] = inventory
    _LOGGER.debug(
        "control4: %d light groups with %s members; %d lights can't stop, %d can't ramp",
        len(inventory.groups),
        [len(members) for members in inventory.groups.values()],
        len(inventory.no_stop),
        len(inventory.no_ramp),
    )


async def setup(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Load each Control4 entry's inventory now if it is loaded, and again each time it loads."""
    for control4 in hass.config_entries.async_entries("control4"):

        @callback
        def changed(control4: ConfigEntry = control4) -> None:
            if control4.state is ConfigEntryState.LOADED:
                entry.async_create_background_task(hass, load(hass, control4), "control4 inventory")

        entry.async_on_unload(control4.async_on_state_change(changed))
        if control4.state is ConfigEntryState.LOADED:
            await load(hass, control4)
