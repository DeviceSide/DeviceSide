#!/usr/bin/env python3
"""Generate the README's device table and the evidence block of docs/device-compatibility.md, from the test records,
the adapters' scopes, docs/models.yaml and each integration's bundle, docs/integrations/<integration>/. The rules
the cards show (levels, the `experimental` flag, caveats) are in docs/evidence.md.

**Evidence** for an action is its passing test records (`<action>.md`, `<action>-<option>.md`) and the `_manual.md`
rows whose Passed names it. A record's Device row gives the models it tested: a group (firmware `unknown`, or named
Group or Zone) shows as "group", and an entry the format can't read is an error; a manual row's Devices are model ids.
A level comes from the scope alone (verify, then trust): a record never ages.

**Cards.** One collapsed section between the README's devices markers, the legend first and a link to the integrations
page last, with a card per integration: its name, linked to its page (the bundle's index.md), and maintainers
(`IntegrationInfo.maintainers`; "⚠️ Unmaintained · formerly maintained by" when every adapter is), then the features
of the adapters with each `caveat` (⚠️ Unmaintained, then ⚠️ Untested fix, linking its reason), then a bullet per tier:
- Works: the models the evidence of unflagged adapters tested (rig-tested ones end ✔), and native groups.
- Should work: the classes (devices.yaml `capabilities`) unflagged adapters hold as Documented.
- Experimental features: the classes held as `experimental(...)`, and the features of adapters flagged whole
  (`experimental=True`), all alike: whether one was tested is the judgment of whoever lifts its flag.
- Doesn't work: devices.yaml `doesnt_work`.
Classes with the same features share an entry, and those of one page section a link. A model or blocker drops the
integration's name where it leads, as the card's name already gives it.

**Evidence block.** Per integration, a row per action and level its domains, capabilities and fields hold (an adapter
flagged whole has one), the first with the evidence's models and records; each row carries the adapter's caveat. The
prose outside the evidence markers is kept as written.

**Data.** docs/models.yaml holds what integrations share: `models`, one entry per physical model (`name`, `ids` across
integrations, `type`, optional `section`), and `doesnt_work` entries that name their `integrations`. Each bundle's
devices.yaml holds its integration's: `column` and `column_order` (the README feature table's, read by
gen_features), `requires` (shown after the card's name), `capabilities` (a `phrase` and `section` per domain or
capability the scopes hold below Verified) and `doesnt_work` (`what`, `reason`, `source`, optional `section`: devices
that fail the call DeviceSide sends, not what isn't built). Every integration needs a bundle.

**Links.** A card links each model, class or blocker to the heading its `section` names (default: the model's
`name`, the blocker's `what`): on the card's integration page when that has the heading; a model's or native groups'
heading may be on any integration's page; else on docs/device-compatibility.md outside the evidence block. A heading
none of them has is an error.

Usage: scripts/gen_compat.py [--check]

--check exits 1 when the README or the page differs from what this generates.
"""

import argparse
import copy
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from custom_components.deviceside.core.registry import AdapterRegistry  # noqa: E402
from custom_components.deviceside.core.scope import CaveatKind, Level  # noqa: E402
from scripts.check_release import MANUAL, MANUAL_ROW, adapters, result, test_records_dir  # noqa: E402
from scripts.gen_features import FEATURES as TABLE_FEATURES  # noqa: E402
from scripts.gen_features import anchors, bundle, columns, page, slug  # noqa: E402

PAGE = REPO / "docs" / "device-compatibility.md"
README = REPO / "README.md"
MODELS = REPO / "docs" / "models.yaml"
# Absolute: HACS renders the README inside Home Assistant, where a relative link doesn't resolve.
BLOB_URL = "https://github.com/DeviceSide/DeviceSide/blob/main/"
PAGE_URL = f"{BLOB_URL}docs/device-compatibility.md"
CARDS = ("<!-- devices:start -->", "<!-- devices:end -->")
CARDS_TITLE = "Device compatibility by integration"
EVIDENCE = ("<!-- evidence:start -->", "<!-- evidence:end -->")

DEVICE = re.compile(r"^\| Device \| (.*) \|$", re.MULTILINE)
ENTRY = re.compile(r"^(?P<name>.*?)(?: \(`(?P<model>[^`]+)`\))?, firmware `(?P<firmware>[^`]+)`$")
BACKTICKS = re.compile(r"`([^`]+)`")
REPORT_URL = "https://github.com/DeviceSide/DeviceSide/issues/new?template=device_report.yml"
GROUP_NAMES = {"group", "zone"}
GROUP = "group"
# The scope's levels, strongest first, as the evidence block names them.
LEVELS = ((Level.VERIFIED, "Verified"), (Level.DOCUMENTED, "Documented"), (Level.EXPERIMENTAL, "Experimental"))
NOUNS = ("entities", "components", "fields")  # for a scope's domains, capabilities and fields

# Device types, in a card's order for its Works models.
TYPES = ("bulb", "relay", "plug", "dimmer", "LED controller")
# Tiers, in a card's order: (key, icon, legend).
OUTCOMES = (
    ("works", "🟢", "works"),
    ("should", "🟡", "should work: same call pattern as a tested device"),
    (
        "experimental",
        "🧪",
        f"experimental: off until you turn on Experimental features; please [report how it goes]({REPORT_URL})",
    ),
    ("no", "🔴", "doesn't work"),
)
VERIFIED = "✔"
UNMAINTAINED = "⚠️ Unmaintained"
UNTESTED_FIX = "⚠️ Untested fix"
# The scope's caveats, as (kind, label), in a card's order.
MARKS = ((CaveatKind.UNMAINTAINED, UNMAINTAINED), (CaveatKind.UNTESTED_FIX, UNTESTED_FIX))
CARDS_LEGEND = " · ".join(
    [
        f"{OUTCOMES[0][1]} {OUTCOMES[0][2]}",
        f"{VERIFIED} verified on automated rig",
        *(f"{icon} {legend}" for _, icon, legend in OUTCOMES[1:]),
        "⚠️ unmaintained: no one is fixing it; use at your own risk",
        "⚠️ untested fix: changed, not yet tested; please report whether it works",
    ]
)
GITHUB = "https://github.com/"
INTEGRATIONS_URL = "https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations.md"
# The keys each devices.yaml entry may hold, so a typo fails instead of being ignored.
SHARED_KEYS = {"models", "doesnt_work"}
BUNDLE_KEYS = {"column", "column_order", "requires", "capabilities", "doesnt_work"}
MODEL_KEYS = {"name", "ids", "type", "section"}
CLASS_KEYS = {"phrase", "section"}
BROKEN_KEYS = {"what", "integrations", "reason", "source", "section"}
GROUPS_ENTRY = ("native groups", "Native groups")  # (phrase, section) for the groups a record tested


def card_features() -> dict[str, str]:
    """Each action's feature, as a card names it, in the README feature table's order (gen_features.FEATURES). An
    action in more than one row (`stop`, riding every smooth move) is named by itself, last, so a card names it only
    when nothing else is."""
    rows = [action for *_, actions in TABLE_FEATURES for action in actions]
    shared = sorted({action for action in rows if rows.count(action) > 1})
    names = {action: card for *_, card, actions in TABLE_FEATURES for action in actions if action not in shared}
    return names | {action: action for action in shared}


FEATURES = card_features()


@dataclass
class Data:
    """docs/models.yaml and the bundles' devices.yaml, merged and validated."""

    requires: dict[str, str]
    models: dict[str, dict]  # by each of its ids
    capabilities: dict[str, dict[str, dict]]
    doesnt_work: list[dict]
    # Every heading an entry links to, with the integration whose card links it (None: any card, as for a model).
    sections: set[tuple[str | None, str]] = field(default_factory=set)
    # The heading anchors of each integration's page; a section on none of them is on PAGE.
    pages: dict[str, set[str]] = field(default_factory=dict)

    def model(self, model_id: str, where: str) -> dict:
        if model_id not in self.models:
            raise SystemExit(f"{where}: model {model_id!r} is not in docs/models.yaml; add it to `models`")
        return self.models[model_id]

    def url(self, key: str | None, section: str) -> str:
        """The section's heading: on the integration's page when that has it, else (a model's or native groups',
        which any card may link) on the integration page that has it, else on PAGE. Where `check_sections` looks, so
        its pass means a live link."""
        anchor = slug(section)
        owners = [key] if key is not None else []
        if (None, section) in self.sections:
            owners += sorted(self.pages)
        for owner in owners:
            if anchor in self.pages.get(owner, set()):
                return f"{BLOB_URL}{page(owner)}#{anchor}"
        return f"{PAGE_URL}#{anchor}"


def fail(message: str) -> None:
    raise SystemExit(f"device data: {message}")


def check_type(kind, where: str) -> None:
    if kind not in TYPES:
        fail(f"{where}: type {kind!r} is not one of {', '.join(TYPES)}")


def load(registry: AdapterRegistry, models: Path = MODELS) -> Data:
    """docs/models.yaml and every integration's bundle: its devices.yaml merged in, its page's headings read."""
    shared = yaml.safe_load(models.read_text()) or {}
    bundles = {key: bundle(key) for key in sorted(registry.integrations)}
    data = load_raw(merge(shared, bundles), registry)
    for key in bundles:
        if not (path := REPO / page(key)).is_file():
            raise SystemExit(f"no {page(key)}; add the {key} bundle's user page")
        data.pages[key] = anchors(path.read_text())
    return data


def merge(shared: dict, bundles: dict[str, dict]) -> dict:
    """The shared file and the bundles as one mapping, each bundle's entries named for its integration: a bundle's
    `doesnt_work` entries are its own, so they take no `integrations` key."""
    need(shared, "docs/models.yaml")
    if extra := set(shared) - SHARED_KEYS:
        fail(f"docs/models.yaml: unknown key {', '.join(sorted(extra))}")
    raw: dict = {"integrations": {}, "capabilities": {}, "models": shared.get("models")}
    raw["doesnt_work"] = list(shared.get("doesnt_work") or [])
    for key, data in bundles.items():
        where = f"docs/integrations/{key}/devices.yaml"
        if extra := set(data) - BUNDLE_KEYS:
            fail(f"{where}: unknown key {', '.join(sorted(extra))}")
        if "requires" in data:
            raw["integrations"][key] = {"requires": data["requires"]}
        if data.get("capabilities"):
            raw["capabilities"][key] = data["capabilities"]
        if not isinstance(broken := data.get("doesnt_work") or [], list):
            fail(f"{where}: doesnt_work must be a list")
        for entry in broken:
            if isinstance(entry, dict) and "integrations" in entry:
                fail(f"{where}: a doesnt_work entry is {key}'s own; drop its integrations")
            raw["doesnt_work"].append({**entry, "integrations": [key]} if isinstance(entry, dict) else entry)
    return raw


def need(
    entry, where: str, strings: tuple[str, ...] = (), lists: tuple[str, ...] = (), keys: set[str] | None = None
) -> None:
    """A clean error for a wrong shape, instead of a KeyError or a string iterated per character."""
    if not isinstance(entry, dict):
        fail(f"{where} must be a mapping")
    if keys is not None and (extra := set(entry) - keys):
        fail(f"{where}: unknown key {', '.join(sorted(map(str, extra)))}")
    for key in strings:
        if not isinstance(entry.get(key), str) or not entry[key]:
            fail(f"{where} needs {'an' if key[0] in 'aeiou' else 'a'} {key}")
    for key in lists:
        if not isinstance(entry.get(key), list):
            fail(f"{where}: {key} must be a list")


def check_shape(raw: dict, known: set[str]) -> None:
    """The file's top level: only known keys, a mapping or list where one belongs, and no unknown integration."""
    if extra := set(raw) - {"integrations", "models", "capabilities", "doesnt_work"}:
        fail(f"unknown key {', '.join(sorted(extra))}")
    for key in ("integrations", "capabilities"):
        need(raw.get(key) or {}, key)
        if unknown := set(raw.get(key) or {}) - known:
            fail(f"{key}: no integration {', '.join(repr(name) for name in sorted(unknown))}")
    for key in ("models", "doesnt_work"):
        if not isinstance(raw.get(key) or [], list):
            fail(f"{key} must be a list")


def load_raw(raw: dict, registry: AdapterRegistry) -> Data:
    need(raw, "the file")
    raw = copy.deepcopy(raw)  # defaults are filled in place
    known = set(registry.integrations)
    check_shape(raw, known)
    for key, entry in (raw.get("integrations") or {}).items():
        need(entry, f"integrations {key}", ("requires",), keys={"requires"})
    requires = {key: entry["requires"] for key, entry in (raw.get("integrations") or {}).items()}
    data = Data(requires, {}, raw.get("capabilities") or {}, [])
    for model in raw.get("models") or []:
        load_model(model, data)
    data.sections.add((None, GROUPS_ENTRY[1]))  # every card with groups links it, as it does a model
    for key, items in data.capabilities.items():
        need(items, f"capabilities {key}")
        for item, entry in items.items():
            need(entry, f"capabilities {key} {item}", ("phrase", "section"), keys=CLASS_KEYS)
            data.sections.add((key, entry["section"]))
    for entry in raw.get("doesnt_work") or []:
        load_broken(entry, known, data)
    return data


def load_model(model: dict, data: Data) -> None:
    need(model, f"model {model.get('name') if isinstance(model, dict) else model!r}", ("name",), ("ids",), MODEL_KEYS)
    if any(other["name"] == model["name"] for other in data.models.values()):
        fail(f"model name {model['name']!r} is listed twice")
    check_type(model.get("type"), f"model {model.get('name')!r}")
    model.setdefault("section", model["name"])
    for model_id in model["ids"]:
        if not isinstance(model_id, str):
            fail(f"model {model['name']!r}: id {model_id!r} must be a string; quote it")
        if model_id in data.models:
            fail(f"model id {model_id!r} is listed twice")
        data.models[model_id] = model
    data.sections.add((None, model["section"]))


def load_broken(entry: dict, known: set[str], data: Data) -> None:
    need(
        entry,
        f"doesnt_work {entry.get('what') if isinstance(entry, dict) else entry!r}",
        ("what",),
        ("integrations",),
        BROKEN_KEYS,
    )
    if not str(entry.get("source", "")).startswith("https://"):
        fail(f"doesnt_work {entry['what']!r}: source must be an https URL")
    if unknown := set(entry["integrations"]) - known:
        fail(f"doesnt_work {entry['what']!r}: no integration {', '.join(sorted(unknown))}")
    for key in ("reason", "source"):
        if not entry.get(key):
            fail(f"doesnt_work {entry['what']!r} needs a {key}")
    entry.setdefault("section", entry["what"])
    data.sections.update((key, entry["section"]) for key in entry["integrations"])
    data.doesnt_work.append(entry)


def entries(record: Path) -> list[tuple[str, str] | str]:
    """The devices a record tested, as (model id, firmware) or GROUP, in the order the record lists them. A Device row
    that is missing or unreadable is an error, not an empty list: a silent gap would pass for a tested model."""
    if not (row := DEVICE.search(record.read_text())):
        raise SystemExit(f"{record.relative_to(REPO)}: no Device row")
    if row[1] == "none":
        return []
    found: list[tuple[str, str] | str] = []
    for item in row[1].split("; "):
        if entry := ENTRY.match(item.strip()):
            if entry["firmware"] == "unknown" or entry["name"].lower() in GROUP_NAMES:
                found.append(GROUP)
            else:
                found.append((entry["model"] or entry["name"], entry["firmware"]))
        else:
            raise SystemExit(f"{record.relative_to(REPO)}: can't read Device entry {item!r}")
    return found


def passing(integration: str, action: str) -> list[Path]:
    """The adapter's passing test records: `<action>.md`, and `<action>-<option>.md` for a run with an option set."""
    pattern = re.compile(rf"{re.escape(action)}(-[^.]+)?\.md")
    found = (path for path in test_records_dir(integration).glob("*.md") if pattern.fullmatch(path.name))
    return sorted(path for path in found if result(path) == "pass")


def manual(integration: str, action: str) -> list[list[str]]:
    """The model ids of each `_manual.md` row whose Passed names the action. A line that is no row of the format is
    skipped: `check_release.py --signoffs` reports it."""
    path = test_records_dir(integration) / MANUAL
    rows = []
    for line in path.read_text().splitlines() if path.is_file() else []:
        if MANUAL_ROW.fullmatch(line := line.strip()):
            cells = line.strip("|").split("|")
            if action in BACKTICKS.findall(cells[4]):
                rows.append(BACKTICKS.findall(cells[3]))
    return rows


@dataclass
class Evidence:
    """An action's evidence on one integration: its passing records and the `_manual.md` rows naming it."""

    records: list[Path]
    manual: list[list[str]]

    @classmethod
    def of(cls, adapter) -> Evidence:
        return cls(passing(adapter.integration, adapter.action), manual(adapter.integration, adapter.action))

    def devices(self, data: Data) -> list[tuple[str, str | None] | str]:
        """The devices tested, each once, as (model id, firmware; None for a manual row) or GROUP: the records' first,
        then the manual rows', groups last. Every model must be in docs/models.yaml."""
        found: list[tuple[str, str | None] | str] = []
        sources = [(record.relative_to(REPO), entries(record)) for record in self.records]
        sources += [(MANUAL, [(model, None) for model in row]) for row in self.manual]
        for where, items in sources:
            for item in items:
                if item != GROUP:
                    data.model(item[0], str(where))
                if item not in found:
                    found.append(item)
        found.sort(key=lambda item: item == GROUP)
        return found


def items(scope) -> list[tuple[Level, str, str]]:
    """The scope's items, as (level, item, noun), domains first: all Experimental in an adapter flagged whole."""
    axes = (scope.domains, scope.capabilities or {}, scope.fields)
    return [
        (Level.EXPERIMENTAL if scope.experimental else level, item, noun)
        for axis, noun in zip(axes, NOUNS, strict=True)
        for item, level in axis.items()
    ]


# The evidence block.


def link(record: Path, action: str) -> str:
    option = record.stem.removeprefix(action).lstrip("-")
    label = option.replace("_", " ") if option else "record"
    return f"[{label}]({record.relative_to(REPO / 'docs').as_posix()})"


def caveat_reason(scope, kind: CaveatKind) -> str | None:
    """The reason of the scope's caveat when it is of that kind, else None."""
    return scope.caveat.reason if scope.caveat is not None and scope.caveat.kind is kind else None


def marked(label: str, reason: str) -> str:
    """A mark (⚠️ Unmaintained, ⚠️ Untested fix), linking its reason when that is a URL, else giving it in brackets."""
    return f"[{label}]({reason})" if reason.startswith("https://") else f"{label} ({reason})"


def cell(text: str) -> str:
    """Text for a table cell: a pipe would start another column."""
    return text.replace("|", "\\|")


def named(held: list[tuple[str, str]]) -> str:
    """Items as "light entities; RGB, CCT components", by noun in the scope's order."""
    by_noun: dict[str, list[str]] = {}
    for item, noun in held:
        by_noun.setdefault(noun, []).append(item)
    return "; ".join(f"{', '.join(names)} {noun}" for noun, names in by_noun.items())


def level_rows(scope) -> list[tuple[str, str]]:
    """(level, items) per row: a row per level the scope holds, strongest first."""
    found = []
    for level, label in LEVELS:
        if held := [(item, noun) for item_level, item, noun in items(scope) if item_level is level]:
            found.append((label, named(held)))
    return found


def table_row(cells: list[str]) -> str:
    return "|" + "|".join(f" {text} " if text else " " for text in cells) + "|"


def rows(adapter, data: Data) -> list[str]:
    """The action's rows: its evidence's models and records on the first."""
    evidence = Evidence.of(adapter)
    models = [
        item if item == GROUP else f"`{item[0]}`, firmware `{item[1]}`" if item[1] else f"`{item[0]}`, by hand"
        for item in evidence.devices(data)
    ]
    sources = [link(record, adapter.action) for record in evidence.records]
    if evidence.manual:
        path = test_records_dir(adapter.integration) / MANUAL
        sources.append(f"[by hand]({path.relative_to(REPO / 'docs').as_posix()})")
    marks = [marked(label, reason) for kind, label in MARKS if (reason := caveat_reason(adapter.scope, kind))]
    action = " ".join([f"`{adapter.action}`", *(cell(mark) for mark in marks)])
    first = ["<br>".join(models) or "none", ", ".join(sources)]
    return [
        table_row([action, level, held, *(first if index == 0 else ["", ""])])
        for index, (level, held) in enumerate(level_rows(adapter.scope))
    ]


def by_integration(registry: AdapterRegistry) -> dict[str, list]:
    """The adapters per integration, in the README feature table's column order, so the cards read across as it does."""
    grouped: dict[str, list] = {}
    for _, adapter in adapters(registry):
        grouped.setdefault(adapter.integration, []).append(adapter)
    return {key: sorted(grouped[key], key=lambda a: a.action) for key in columns(grouped)}


def evidence(registry: AdapterRegistry, data: Data) -> str:
    parts = [
        EVIDENCE[0],
        "<!-- Generated by scripts/gen_compat.py from the bundles' records and devices.yaml, docs/models.yaml and the"
        " adapters' scopes. Do not edit; run the script. -->",
        "",
    ]
    for key, integration_adapters in by_integration(registry).items():
        parts.append(f"### {registry.integrations[key].title}\n")
        parts.append("| Action | Level | Items | Tested models | Records |")
        parts.append("|---|---|---|---|---|")
        for adapter in integration_adapters:
            parts += rows(adapter, data)
        if broken := [entry for entry in data.doesnt_work if key in entry["integrations"]]:
            parts += ["", "| Doesn't work | Why | Source |", "|---|---|---|"]
            parts += [
                f"| {cell(entry['what'])} | {cell(entry['reason'])} | [source]({entry['source']}) |" for entry in broken
            ]
        parts.append("")
    parts.append(EVIDENCE[1])
    return "\n".join(parts)


# The README cards.


def features(actions: set[str], *, fold_stop: bool = True) -> tuple[str, ...]:
    """The actions' feature labels, `stop` folded into the others unless asked (a warning must name every action)."""
    labels = list(dict.fromkeys(FEATURES[action] for action in FEATURES if action in actions))
    labels += sorted(action for action in actions if action not in FEATURES)
    if fold_stop and len(labels) > 1 and "stop" in labels:
        labels.remove("stop")
    return tuple(labels)


def anchor(text: str, url: str) -> str:
    return f"[{text}]({url})"


@dataclass
class Card:
    title: str
    requires: str | None = None
    url: str | None = None  # the integration's page
    maintainers: tuple[str, ...] = ()
    # ⚠️ Unmaintained, then ⚠️ Untested fix entries: the features of the adapters so marked, by reason.
    marks: list[str] = field(default_factory=list)
    # Every adapter is unmaintained, so the heading says "formerly maintained".
    all_unmaintained: bool = False
    lines: dict[str, list[str]] = field(default_factory=dict)

    def short(self, name: str) -> str:
        """The name without the integration's, which the card's title already gives: "Hue Bridge v1" -> "Bridge v1"."""
        return name.removeprefix(f"{self.title} ")

    def render(self) -> str:
        requires = f" ({self.requires})" if self.requires else ""
        maintainers = ", ".join(f"[@{handle}]({GITHUB}{handle})" for handle in self.maintainers)
        title = f"[{self.title}]({self.url})" if self.url else self.title
        status = (
            f"⚠️ Unmaintained · formerly maintained by {maintainers}"
            if self.all_unmaintained
            else f"maintained by {maintainers}"
        )
        lines = [f"**{title}**{requires} · {status}", ""]
        lines += [f"- {entry}" for entry in self.marks]
        for key, icon, _ in OUTCOMES:
            if key in ("should", "experimental"):
                lines += [f"- {icon} {entry}" for entry in self.lines.get(key, [])]
            elif self.lines.get(key):
                lines.append(f"- {icon} {' · '.join(self.lines[key])}")
        return "\n".join(lines)


def classes(key: str, integration_adapters: list, level: Level, data: Data) -> dict[str, set[str]]:
    """Each domain or capability the unflagged adapters hold at the level, in first-seen order, with the actions that
    hold it there."""
    held: dict[str, set[str]] = {}
    for adapter in integration_adapters:
        if adapter.scope.experimental:
            continue
        for item_level, item, noun in items(adapter.scope):
            if item_level is level and noun != "fields":
                if item not in data.capabilities.get(key, {}):
                    fail(f"capabilities: no entry for {key} {item}, which a scope holds as {level.name.title()}")
                held.setdefault(item, set()).add(adapter.action)
    return held


def merged(phrases: list[str], url: str) -> str:
    """One link for the classes of a page section, their shared last words said once: "CCT LED controllers", "RGB LED
    controllers" -> "LED controllers (CCT, RGB)". With no shared ending, the phrases in a list."""
    if len(phrases) == 1:
        return anchor(phrases[0], url)
    words = [phrase.split() for phrase in phrases]
    shared = 0
    while all(len(w) > shared for w in words) and len({tuple(w[len(w) - shared - 1 :]) for w in words}) == 1:
        shared += 1
    if not shared or any(len(w) == shared for w in words):  # nothing shared, or a phrase with no prefix to list
        return anchor(", ".join(phrases), url)
    ending = " ".join(words[0][-shared:])
    return anchor(f"{ending} ({', '.join(' '.join(w[:-shared]) for w in words)})", url)


def class_entries(key: str, held: dict[str, set[str]], data: Data) -> list[str]:
    """Classes with the same features share one entry: "dimmers, LED controllers (CCT, RGB): turn on with timer"."""
    grouped: dict[tuple[str, ...], dict[str, list[str]]] = {}
    for item, actions in held.items():
        entry = data.capabilities[key][item]
        grouped.setdefault(features(actions), {}).setdefault(entry["section"], []).append(entry["phrase"])
    return [
        f"{', '.join(merged(phrases, data.url(key, section)) for section, phrases in sections.items())}: "
        f"{', '.join(names)}"
        for names, sections in grouped.items()
    ]


def works(card: Card, key: str, integration_adapters: list, data: Data) -> list[str]:
    """The models the unflagged adapters' evidence tested, by device type, then first seen, then native groups. A
    rig-tested model and the native groups end ✔."""
    rig: set[str] = set()
    names: list[str] = []
    groups = False
    for adapter in integration_adapters:
        if adapter.scope.experimental:
            continue
        for item in Evidence.of(adapter).devices(data):
            if item == GROUP:
                groups = True
                continue
            name = data.models[item[0]]["name"]
            if item[1] is not None:
                rig.add(name)
            if name not in names:
                names.append(name)
    by_name = {model["name"]: model for model in data.models.values()}
    lines = [
        anchor(card.short(name), data.url(key, by_name[name]["section"])) + (f" {VERIFIED}" if name in rig else "")
        for name in sorted(names, key=lambda name: TYPES.index(by_name[name]["type"]))
    ]
    if groups:
        lines.append(f"{anchor(GROUPS_ENTRY[0], data.url(key, GROUPS_ENTRY[1]))} {VERIFIED}")
    return lines


def mark_entries(integration_adapters: list) -> list[str]:
    """The adapters no one is fixing, then those shipping a fix no one could test, as their features, one entry per
    caveat and reason."""
    entries = []
    for kind, label in MARKS:
        by_reason: dict[str, set[str]] = {}
        for adapter in integration_adapters:
            if reason := caveat_reason(adapter.scope, kind):
                by_reason.setdefault(reason, set()).add(adapter.action)
        entries += [
            f"{marked(label, reason)}: {', '.join(features(actions, fold_stop=False))}"
            for reason, actions in by_reason.items()
        ]
    return entries


def card(key: str, registry: AdapterRegistry, integration_adapters: list, data: Data) -> Card:
    info = registry.integrations[key]
    result = Card(
        title=info.title,
        requires=data.requires.get(key),
        url=f"{BLOB_URL}{page(key)}" if key in data.pages else None,
        maintainers=info.maintainers,
        marks=mark_entries(integration_adapters),
        all_unmaintained=bool(integration_adapters)
        and all(caveat_reason(adapter.scope, CaveatKind.UNMAINTAINED) for adapter in integration_adapters),
    )
    result.lines["works"] = works(result, key, integration_adapters, data)
    result.lines["should"] = class_entries(key, classes(key, integration_adapters, Level.DOCUMENTED, data), data)
    result.lines["experimental"] = [
        *class_entries(key, classes(key, integration_adapters, Level.EXPERIMENTAL, data), data),
    ]
    if flagged := {adapter.action for adapter in integration_adapters if adapter.scope.experimental}:
        result.lines["experimental"].append(", ".join(features(flagged)))
    result.lines["no"] = []
    for entry in data.doesnt_work:
        if key in entry["integrations"]:
            result.lines["no"].append(anchor(result.short(entry["what"]), data.url(key, entry["section"])))
    return result


def cards(registry: AdapterRegistry, data: Data) -> str:
    parts = [
        CARDS[0],
        "<!-- Generated by scripts/gen_compat.py. Do not edit; run the script. -->",
        "",
        "<details>",
        f"<summary><b>{CARDS_TITLE}</b></summary>",
        "",
        CARDS_LEGEND,
        "",
    ]
    for key, integration_adapters in by_integration(registry).items():
        parts += [card(key, registry, integration_adapters, data).render(), ""]
    parts += [
        f"Details per integration are in [docs/integrations.md]({INTEGRATIONS_URL}).",
        "",
        "</details>",
        "",
        CARDS[1],
    ]
    return "\n".join(parts)


# Writing.


def splice(text: str, markers: tuple[str, str], block: str, name: str) -> str:
    start, end = markers
    if text.count(start) != 1 or text.count(end) != 1 or text.index(start) > text.index(end):
        raise SystemExit(f"{name} needs one {start} before one {end}")
    return text[: text.index(start)] + block + text[text.index(end) + len(end) :]


def check_sections(text: str, data: Data) -> None:
    """Every section a card links to is a heading on its integration's page or in the shared page's prose, so a
    renamed heading fails here rather than leaving a dead link. A model's or native groups' may be on any integration's
    page."""
    shared = anchors(splice(text, EVIDENCE, "", "the page"))
    anywhere = shared.union(*data.pages.values())
    dead = sorted(
        section
        for key, section in data.sections
        if slug(section) not in (anywhere if key is None else shared | data.pages.get(key, set()))
    )
    if dead:
        raise SystemExit(
            f"no heading for {', '.join(dead)} on docs/device-compatibility.md or the integration's page; add a section"
        )


def main(
    argv: list[str] | None = None,
    registry: AdapterRegistry | None = None,
    page: Path = PAGE,
    readme: Path = README,
    models: Path = MODELS,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail when the README or the page is out of date")
    args = parser.parse_args(argv)

    registry = registry or AdapterRegistry.discover()
    data = load(registry, models)
    # Both are computed before either is written, so a failure leaves neither half-updated.
    updates = {}
    for path, markers, block in ((page, EVIDENCE, evidence(registry, data)), (readme, CARDS, cards(registry, data))):
        text = path.read_text()
        updates[path] = (text, splice(text, markers, block, path.name))
    check_sections(updates[page][1], data)
    stale = [path for path, (text, new) in updates.items() if new != text]
    if not args.check:
        for path in stale:
            path.write_text(updates[path][1])
    if args.check and stale:
        names = " and ".join(path.name for path in stale)
        print(f"error: {names} out of date; run scripts/gen_compat.py", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
