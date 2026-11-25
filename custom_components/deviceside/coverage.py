"""The Configure menu's Device coverage: per light and switch entity, which DeviceSide features run now (Verified,
Documented), which need Labs, and which are refused and why (docs/design.md, Coverage view).

It reads what a call would do, never a copy of it: each cell is dispatcher.judge on the entity (resolved as a call
resolves it) with Labs off, for each action of the feature, on the action's minimal request. So a level, a refusal or a
class is only ever the dispatcher's. What is left out of the rows, and why, is in `collect`.
"""

import asyncio
import contextlib
import html
import logging
import re
from collections.abc import Awaitable, Iterable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

import probatio
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.icon import async_get_icons

from .const import DOMAIN
from .core.action import Action
from .core.dispatcher import Outcome, judge
from .core.models import Request, Target
from .core.registry import CARD_ORDER, AdapterRegistry
from .core.resolver import resolve
from .core.runtime import DATA
from .core.scope import Level, Unplaced
from .features import FEATURE_ACTIONS

_LOGGER = logging.getLogger(__name__)

# How long the view waits for an integration to report its devices (IntegrationInfo.capability_ready) before showing
# what it has: Z2M lists them seconds after it connects, and a bridge that is down never does.
WAIT_S = 10

DOMAINS = (Platform.LIGHT, Platform.SWITCH)
# Integrations whose groups the view leaves out: ZHA registers a group's entity on the coordinator's device, so its row
# would name the coordinator, not the group.
_GROUPS_ON_COORDINATOR = frozenset({"zha"})


@dataclass(frozen=True, slots=True)
class Column:
    """A feature's column: `feature` is its FEATURE_ACTIONS key, `heading` the short heading, `name` the full one."""

    feature: str
    heading: str
    name: str


COLUMNS = (
    Column("smooth dimming", "Dim", "Smooth dimming"),
    Column("smooth saturation", "Saturation", "Smooth saturation"),
    Column("smooth hue", "Hue", "Smooth hue"),
    Column("set without turning on", "Preset", "Set without turning on"),
    Column("turn on with timer", "Timer on", "Turn on with timer"),
    Column("turn off with timer", "Timer off", "Turn off with timer"),
    Column("auto-off/on", "Auto-off", "Auto-off/on"),
)


class Mark(StrEnum):
    VERIFIED = "🟢"
    DOCUMENTED = "🟡"
    LABS = "⚪"
    REFUSED = "🔴"


# A feature riding several actions takes its weakest.
_WEAKEST = (Mark.REFUSED, Mark.LABS, Mark.DOCUMENTED, Mark.VERIFIED)
_RUNS_NOW = (Mark.VERIFIED, Mark.DOCUMENTED)
_BY_LEVEL = {Level.VERIFIED: Mark.VERIFIED, Level.DOCUMENTED: Mark.DOCUMENTED, Level.LABS: Mark.LABS}


@dataclass(frozen=True, slots=True)
class Cell:
    """A feature's outcome on an entity; `reason` is a refusal's text, as the dispatcher raises with it."""

    mark: Mark
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class Row:
    entity_id: str
    name: str
    icon: str | None
    group: bool
    integration: str
    device: str  # The device's ID, else the entity's: what counts as one device.
    cells: Mapping[str, Cell]  # By Column.feature; a feature with no cell isn't for the entity, or isn't built.


@dataclass(frozen=True, slots=True)
class Coverage:
    rows: tuple[Row, ...]

    def _cells(self, *marks: Mark) -> list[tuple[Row, Cell]]:
        return [(row, cell) for row in self.rows for cell in row.cells.values() if cell.mark in marks]

    @property
    def features_now(self) -> int:
        """The cells that run now: Verified and Documented. A refusal never counts."""
        return len(self._cells(*_RUNS_NOW))

    @property
    def devices_now(self) -> int:
        return len({row.device for row, _ in self._cells(*_RUNS_NOW)})

    @property
    def features_in_labs(self) -> int:
        return len(self._cells(Mark.LABS))

    @property
    def devices_in_labs(self) -> int:
        return len({row.device for row, _ in self._cells(Mark.LABS)})


# What each action's minimal request is made of beyond its defaults: its required fields, and for set_attributes
# (which needs one field) a brightness alone.
_REQUIRED = {"duration": timedelta(seconds=5)}
_ONLY = {"set_attributes": {"brightness": 50}}


def minimal_request(hass: HomeAssistant, action: type[Action]) -> Request:
    """The action's request with its required fields alone (a duration), its defaults, and for set_attributes a
    brightness alone: what a call must carry, so a cell shows what the bare action does, no field held in Labs."""
    data = {marker.schema: marker.default() for marker in action.fields if callable(marker.default)}
    data |= {
        marker.schema: _REQUIRED[marker.schema]
        for marker in action.fields
        if isinstance(marker, probatio.Required) and marker.schema in _REQUIRED
    }
    return action.parse(hass, ServiceCall(hass, DOMAIN, action.key, data | _ONLY.get(action.key, {})))


def cell(hass: HomeAssistant, registry: AdapterRegistry, target: Target, column: Column) -> Cell | None:
    """The target's cell for a feature, from dispatcher.judge with Labs off on each of the feature's actions: the
    weakest, a refusal first. None where the feature isn't for the target (an action of it has no adapter or domain
    there) or isn't built (not built yet, an empty group)."""
    judged = []
    for key in FEATURE_ACTIONS[column.feature]:
        action, adapter = registry.actions.get(key), registry.adapter(key, target.integration)
        if action is None or adapter is None or not {target.domain} <= action.domains & adapter.scope.domains.keys():
            return None
        judged.append(judge(hass, registry, adapter, target, minimal_request(hass, action), False))
    if refused := next((gate for gate in judged if gate is not None and gate.outcome is Outcome.REFUSED), None):
        return Cell(Mark.REFUSED, refused.why or refused.reason)
    if any(gate is None or gate.outcome is Outcome.NOT_BUILT for gate in judged):
        return None
    marks = [Mark.LABS if gate.outcome is Outcome.LABS else _BY_LEVEL[gate.level] for gate in judged if gate]
    return Cell(min(marks, key=_WEAKEST.index))


def _unplaced(hass: HomeAssistant, registry: AdapterRegistry, target: Target) -> bool:
    """Whether the integration named the target's class from partial information (Unplaced): it is still being
    placed, so its row would show refusals that clear within seconds."""
    if target.is_group or (capability := registry.integrations[target.integration].capability) is None:
        return False
    try:
        return isinstance(capability(hass, target), Unplaced)
    except Exception:  # noqa: BLE001 - a classifier's bug is logged where a call classes it; here it just isn't Unplaced
        return False


def waiting(hass: HomeAssistant) -> list[Awaitable[None]]:
    """What the loaded integrations are still waiting on before they can class their devices
    (IntegrationInfo.capability_ready)."""
    if (runtime := hass.data.get(DATA)) is None:
        return []
    ready = (info.capability_ready(hass) for info in runtime.registry.integrations.values() if info.capability_ready)
    return [wait for wait in ready if wait is not None]


async def settle(pending: list[Awaitable[None]]) -> None:
    """Wait for what `waiting` listed, at most WAIT_S, then give up: the view shows what it has."""
    with contextlib.suppress(TimeoutError):
        async with asyncio.timeout(WAIT_S):
            await asyncio.gather(*pending)


async def collect(hass: HomeAssistant) -> Coverage:
    """A row per light or switch entity DeviceSide's resolver accepts, in the order of the README's device cards and
    by name within an integration. Left out: an entity with an entity_category, a disabled or hidden one, one the
    integration is still placing (Unplaced: Z2M lists a device it no longer knows, or one not yet interviewed), a ZHA
    group (_GROUPS_ON_COORDINATOR), and one with no cell at all."""
    if (runtime := hass.data.get(DATA)) is None:
        return Coverage(())
    registry = runtime.registry
    found: list[tuple[er.RegistryEntry, Target]] = []
    for entry in er.async_get(hass).entities.values():
        if (
            entry.domain not in DOMAINS
            or entry.entity_category is not None
            or entry.disabled_by is not None
            or entry.hidden_by is not None
            or isinstance(target := resolve(hass, registry, entry.entity_id), str)
            or (target.is_group and target.integration in _GROUPS_ON_COORDINATOR)
            or _unplaced(hass, registry, target)
        ):
            continue
        found.append((entry, target))
    icons = await _Icons.load(hass, {entry.platform for entry, _ in found})
    rows = []
    for entry, target in found:
        cells = {column.feature: got for column in COLUMNS if (got := cell(hass, registry, target, column)) is not None}
        if cells:
            rows.append(
                Row(
                    entry.entity_id,
                    _name(hass, entry),
                    icons.of(entry),
                    target.is_group,
                    target.integration,
                    entry.device_id or entry.entity_id,
                    cells,
                )
            )
    order = {key: place for place, key in enumerate(CARD_ORDER)}
    rows.sort(key=lambda row: (order.get(row.integration, len(order)), row.integration, row.name.casefold()))
    return Coverage(tuple(rows))


def _name(hass: HomeAssistant, entry: er.RegistryEntry) -> str:
    """The name HA shows: the state's friendly name, else the registry's."""
    if (state := hass.states.get(entry.entity_id)) is not None and state.name:
        return state.name
    return entry.name or entry.original_name or entry.entity_id


class _Icons:
    """The default icon HA shows for an entity (not the state's): the entry's icon, else the integration's icon for its
    translation key, else its domain's for its device class, else the domain's default (`_`)."""

    def __init__(self, entities: Mapping[str, Mapping], components: Mapping[str, Mapping]) -> None:
        self._entities = entities
        self._components = components

    @classmethod
    async def load(cls, hass: HomeAssistant, platforms: set[str]) -> _Icons:
        entities = await cls._fetch(hass, "entity", platforms)
        components = await cls._fetch(hass, "entity_component", [str(domain) for domain in DOMAINS])
        return cls(entities, components)

    @staticmethod
    async def _fetch(hass: HomeAssistant, category: str, integrations: Iterable[str]) -> Mapping[str, Mapping]:
        try:
            return await async_get_icons(hass, category, integrations) if integrations else {}
        except Exception:  # noqa: BLE001 - an icon file that won't load costs the icons, not the view
            _LOGGER.debug("The %s icons for the coverage view didn't load", category, exc_info=True)
            return {}

    def of(self, entry: er.RegistryEntry) -> str | None:
        if icon := entry.icon or entry.original_icon:
            return icon
        by_key = self._entities.get(entry.platform, {}).get(entry.domain, {})
        if entry.translation_key and (icon := by_key.get(entry.translation_key, {}).get("default")):
            return icon
        by_class = self._components.get(entry.domain, {})
        for name in (entry.device_class or entry.original_device_class, "_"):
            if name and (icon := by_class.get(name, {}).get("default")):
                return icon
        return None


_SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
_MARKDOWN = re.compile(r"([\\`*_{}\[\]()#+\-!|])")


def _plain(text: str) -> str:
    """Text for a table cell: HTML and Markdown characters shown as they are."""
    return _MARKDOWN.sub(r"\\\1", html.escape(text, quote=False))


def table(hass: HomeAssistant, coverage: Coverage) -> str:
    """The matrix in Markdown (HA's flow Markdown keeps tables, `ha-icon` and `abbr`, and strips style and class): an
    entity per row under its integration's title, a feature per column, a refusal as 🔴 with its footnote's number,
    and the footnotes, one per distinct reason, under it. Empty with no rows."""
    if not coverage.rows:
        return ""
    registry = hass.data[DATA].registry
    headings = " | ".join(f'<abbr title="{column.name}">{column.heading}</abbr>' for column in COLUMNS)
    lines = [f"| | {headings} |", "|---|" + ":-:|" * len(COLUMNS)]
    notes: dict[str, int] = {}
    shown = None
    for row in coverage.rows:
        if row.integration != shown:
            shown = row.integration
            lines.append(f"| **{_plain(registry.integrations[shown].title)}** |" + " |" * len(COLUMNS))
        icon = f' <ha-icon icon="{html.escape(row.icon)}"></ha-icon>' if row.icon else ""
        label = " <small>Group</small>" if row.group else ""
        cells = []
        for column in COLUMNS:
            got = row.cells.get(column.feature)
            if got is None:
                cells.append("")
            elif got.mark is Mark.REFUSED:
                number = notes.setdefault(got.reason or "", len(notes) + 1)
                cells.append(f"{got.mark}{str(number).translate(_SUPERSCRIPT)}")
            else:
                cells.append(got.mark)
        lines.append(f"| {_plain(row.name)}{icon}{label} | " + " | ".join(cells) + " |")
    footnotes = [f"{str(number).translate(_SUPERSCRIPT)} {_plain(text)}" for text, number in notes.items()]
    return "\n".join(lines) + ("\n\n" + "\n\n".join(footnotes) if footnotes else "")


def legend() -> str:
    """The four marks, and each column's heading against its full name."""
    marks = " · ".join(
        (f"{Mark.VERIFIED} Verified", f"{Mark.DOCUMENTED} Documented", f"{Mark.LABS} Labs", f"{Mark.REFUSED} refused")
    )
    return marks + "\n\n" + " · ".join(f"{column.heading}: {column.name}" for column in COLUMNS)
