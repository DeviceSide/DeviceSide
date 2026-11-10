#!/usr/bin/env python3
"""Generate the README's device table and the evidence block of docs/device-compatibility.md, from the test records,
the adapters' scopes and docs/devices.yaml.

**Cards.** One collapsed section between the README's devices markers, with a card per integration: its name, then
a bullet per outcome:
- Works: the models in the passing records of adapters that ship (Verified), plus native groups, and the models of
  accepted working reports (linked to the report). A rig-tested entry ends ✔.
- Should work: the classes (devices.yaml `capabilities`) the shipping adapters hold as Documented; one whose sibling
  is Reported, so community-supported, links the sibling's reports.
- Help us test: the classes they hold as Experimental, refused until the Experimental features option is on.
- Doesn't work: devices.yaml `doesnt_work`.
Each class entry, a bullet of its own, names the features it is at that level for; classes sharing a page section
share a link. A model or blocker drops the integration's name where it leads, as the card's name already gives it.
Adapters with the `experimental` flag are left out of the cards: they are in RCs only. The legend leads the section, so
✔ (verified on the automated rig) is read before the first card. The section ends with a link to the integrations page.

**Evidence.** Per integration, every action's level, who supports it (`AdapterScope.support`) and the models its
passing records tested, with a row per level and support below Verified that its domains, capabilities or fields
hold, and the reports on it. A group (a Device entry with firmware `unknown`, or named Group or Zone) shows as
"group", not as a model; any other entry the record format can't read is an error. The prose outside the evidence
markers is kept as written; every heading a card links to must be in it.

Usage: scripts/gen_compat.py [--check]

--check exits 1 when the README or the page differs from what this generates.
"""

import argparse
import copy
import re
import sys
from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from custom_components.deviceside.core.registry import AdapterRegistry  # noqa: E402
from custom_components.deviceside.core.scope import Level, Support  # noqa: E402
from scripts.check_release import adapters, proven, records, result  # noqa: E402
from scripts.gen_features import COLUMNS, anchors, slug  # noqa: E402
from scripts.gen_features import FEATURES as TABLE_FEATURES  # noqa: E402

PAGE = REPO / "docs" / "device-compatibility.md"
README = REPO / "README.md"
DATA = REPO / "docs" / "devices.yaml"
# Absolute: HACS renders the README inside Home Assistant, where a relative link doesn't resolve.
PAGE_URL = "https://github.com/jasonmx/DeviceSide/blob/main/docs/device-compatibility.md"
CARDS = ("<!-- devices:start -->", "<!-- devices:end -->")
CARDS_TITLE = "Device compatibility by integration"
EVIDENCE = ("<!-- evidence:start -->", "<!-- evidence:end -->")

DEVICE = re.compile(r"^\| Device \| (.*) \|$", re.MULTILINE)
ENTRY = re.compile(r"^(?P<name>.*?)(?: \(`(?P<model>[^`]+)`\))?, firmware `(?P<firmware>[^`]+)`$")
ISSUE_URL = "https://github.com/jasonmx/DeviceSide/issues/"
ISSUE = re.compile(rf"^{re.escape(ISSUE_URL)}(\d+)$")
GROUP_NAMES = {"group", "zone"}
GROUP = "group"
IN_RCS = "Experimental (in RCs only)"
# An unflagged adapter whose Verified call has no passing record, so nothing proves it.
NO_RECORD = "Unproven: no passing record"
# The item levels below Verified, as (level, label, why the row has no models), in the page's order.
ITEM_LEVELS = (
    (Level.REPORTED, "Reported", "reported by users"),
    (Level.DOCUMENTED, "Documented", "untested"),
    (Level.EXPERIMENTAL, "Experimental", "untested, behind Experimental features"),
)

# Device types, in a card's order for its Works models.
TYPES = ("bulb", "relay", "plug", "dimmer", "LED controller")
# Outcomes, in a card's order: (key, icon, legend).
OUTCOMES = (
    ("works", "🟢", "works"),
    ("should", "🟡", "should work: same call pattern as a tested device"),
    ("help", "🙋", "testers wanted"),
    ("no", "🔴", "doesn't work"),
)
VERIFIED = "✔"
CARDS_LEGEND = " · ".join(
    [
        f"{OUTCOMES[0][1]} {OUTCOMES[0][2]}",
        f"{VERIFIED} verified on automated rig",
        *(f"{icon} {legend}" for _, icon, legend in OUTCOMES[1:]),
    ]
)
INTEGRATIONS_URL = "https://github.com/jasonmx/DeviceSide/blob/main/docs/integrations.md"
# The keys each devices.yaml entry may hold, so a typo fails instead of being ignored.
MODEL_KEYS = {"name", "ids", "type", "section"}
CLASS_KEYS = {"phrase", "section"}
BROKEN_KEYS = {"what", "integrations", "reason", "source", "section"}
REPORT_KEYS = {"integration", "model", "item", "firmware", "deviceside", "worked", "failed", "issue"}
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
    """docs/devices.yaml, validated."""

    requires: dict[str, str]
    models: dict[str, dict]  # by each of its ids
    capabilities: dict[str, dict[str, dict]]
    doesnt_work: list[dict]
    reports: list[dict]
    sections: set[str] = field(default_factory=set)  # every heading an entry links to

    def model(self, model_id: str, where: str) -> dict:
        if model_id not in self.models:
            raise SystemExit(f"{where}: model {model_id!r} is not in docs/devices.yaml; add it to `models`")
        return self.models[model_id]


def fail(message: str) -> None:
    raise SystemExit(f"docs/devices.yaml: {message}")


def check_type(kind, where: str) -> None:
    if kind not in TYPES:
        fail(f"{where}: type {kind!r} is not one of {', '.join(TYPES)}")


def load(path: Path, registry: AdapterRegistry) -> Data:
    return load_raw(yaml.safe_load(path.read_text()) or {}, registry)


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
    if extra := set(raw) - {"integrations", "models", "capabilities", "doesnt_work", "reports"}:
        fail(f"unknown key {', '.join(sorted(extra))}")
    for key in ("integrations", "capabilities"):
        need(raw.get(key) or {}, key)
        if unknown := set(raw.get(key) or {}) - known:
            fail(f"{key}: no integration {', '.join(repr(name) for name in sorted(unknown))}")
    for key in ("models", "doesnt_work", "reports"):
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
    data = Data(requires, {}, raw.get("capabilities") or {}, [], [])
    for model in raw.get("models") or []:
        load_model(model, data)
    for key, items in data.capabilities.items():
        need(items, f"capabilities {key}")
        for item, entry in items.items():
            need(entry, f"capabilities {key} {item}", ("phrase", "section"), keys=CLASS_KEYS)
            data.sections.add(entry["section"])
    for entry in raw.get("doesnt_work") or []:
        load_broken(entry, known, data)
    shipped = {(adapter.integration, adapter.action): adapter for _, adapter in adapters(registry)}
    for report in raw.get("reports") or []:
        load_report(report, known, shipped, data)
    check_reported(shipped, data)
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
    data.sections.add(model["section"])


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
    data.sections.add(entry["section"])
    data.doesnt_work.append(entry)


def load_report(report: dict, known: set[str], shipped: dict[tuple[str, str], object], data: Data) -> None:
    """A report names the domain or capability (Shelly: RPC component) its call reached as `item`. A working one must
    have promoted that item to Reported, unless a record already made it Verified."""
    where = f"report {report.get('issue') if isinstance(report, dict) else report}"
    need(report, where, ("integration", "item"), keys=REPORT_KEYS)
    if report["integration"] not in known:
        fail(f"{where}: no integration {report['integration']!r}")
    for key in ("worked", "failed"):
        if not isinstance(report.get(key) or [], list):
            fail(f"{where}: {key} must be a list")
    if "model" not in report:
        fail(f"{where} needs a model")
    if not ISSUE.match(str(report.get("issue"))):
        fail(f"{where}: issue must be a DeviceSide issue URL")
    report["model"] = str(report["model"])
    data.model(report["model"], f"docs/devices.yaml: {where}")
    for action in [*(report.get("worked") or []), *(report.get("failed") or [])]:
        if (adapter := shipped.get((report["integration"], action))) is None:
            fail(f"{where}: {report['integration']} has no {action} adapter")
        check_item(report, action, adapter, where)
    for key in ("firmware", "deviceside"):
        if not isinstance(report.get(key), str) or not report[key]:  # YAML reads firmware 1.10 as 1.1
            fail(f"{where} needs {key}, as a quoted string")
    data.reports.append(report)


def check_item(report: dict, action: str, adapter, where: str) -> None:
    # A scope that lists capabilities names its item by capability; the domain is only the entity's kind.
    scope = adapter.scope
    held = scope.capabilities if scope.capabilities is not None else scope.domains
    if (level := held.get(report["item"])) is None:
        fail(f"{where}: {report['integration']} {action} has no item {report['item']!r} in scope")
    if action in (report.get("worked") or []) and level < Level.REPORTED:
        fail(
            f"{where}: {report['integration']} {action} works on {report['item']}, which its scope holds as "
            f"{level.name.title()}; promote it to Level.REPORTED"
        )


def check_reported(shipped: dict[tuple[str, str], object], data: Data) -> None:
    """A Reported item stands on an accepted working report: a scope that holds one with no report has nothing behind
    it. Flagged adapters are in RCs only, and checked when the flag clears."""
    for (integration, action), adapter in shipped.items():
        if adapter.scope.experimental:
            continue
        if Level.REPORTED in adapter.scope.fields.values():
            fail(f"{integration} {action} holds a field as Reported; a report can't name a field yet")
        for items in (adapter.scope.domains, adapter.scope.capabilities or {}):
            for item, level in items.items():
                if level is Level.REPORTED and not worked_reports(integration, action, item, data):
                    fail(f"reports: none says {integration} {action} works on {item}, which a scope holds as Reported")


def worked_reports(integration: str, action: str, item: str, data: Data) -> list[str]:
    """The issues of the accepted reports that the action worked on the item."""
    return [
        report["issue"]
        for report in data.reports
        if report["integration"] == integration and report["item"] == item and action in (report.get("worked") or [])
    ]


def badges(issues) -> str:
    """The reports behind a user-reported entry, each linked once."""
    return "".join(f" ([report]({issue}))" for issue in dict.fromkeys(issues))


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
    return [path for path in records(integration, action) if result(path) == "pass"]


def tested(adapter, data: Data, found_records: list[Path] | None = None) -> list[tuple[str, str] | str]:
    """The devices the adapter's passing records tested, each once, single devices first. Every model must be in
    devices.yaml."""
    found: list[tuple[str, str] | str] = []
    if found_records is None:
        found_records = passing(adapter.integration, adapter.action)
    for record in found_records:
        for item in entries(record):
            if item != GROUP:
                data.model(item[0], str(record.relative_to(REPO)))
            if item not in found:
                found.append(item)
    found.sort(key=lambda item: item == GROUP)
    return found


# The evidence block.


def link(record: Path, action: str) -> str:
    option = record.stem.removeprefix(action).lstrip("-")
    label = option.replace("_", " ") if option else "record"
    return f"[{label}]({record.relative_to(REPO / 'docs').as_posix()})"


def reports_cell(integration: str, action: str, data: Data, items: Collection[str] | None = None) -> str:
    """The reports on the action, as links; only those that name one of `items` when given."""
    cells = []
    for report in data.reports:
        if report["integration"] != integration or (items is not None and report["item"] not in items):
            continue
        number = ISSUE.match(report["issue"])[1]
        for key, mark in (("worked", "✅"), ("failed", "❌")):
            if action in (report.get(key) or []):
                cells.append(f"{mark} [#{number}]({report['issue']}) `{report['model']}`")
    return "<br>".join(cells)


def padded(text: str) -> str:
    """A table cell's text between its pipes: one space when empty."""
    return f" {text} " if text else " "


def row(action: str, adapter, data: Data) -> str:
    found = passing(adapter.integration, action)
    level = IN_RCS if adapter.scope.experimental else "Verified" if found else NO_RECORD
    support = Support.MAINTAINER if found else ""
    models = [GROUP if item == GROUP else f"`{item[0]}`, firmware `{item[1]}`" for item in tested(adapter, data, found)]
    records_cell = ", ".join(link(record, action) for record in found)
    reports = reports_cell(adapter.integration, action, data)
    return f"| `{action}` | {level} | {support} | {'<br>'.join(models) or 'none'} | {records_cell} |{padded(reports)}|"


def cell(text: str) -> str:
    """Text for a table cell: a pipe would start another column."""
    return text.replace("|", "\\|")


def level_rows(action: str, adapter, data: Data) -> list[str]:
    """A row per level below Verified that the adapter's domains, capabilities or fields hold, and per support within
    it (a Documented item takes its sibling's), weakest last. They have no record, so no models; a community-supported
    row shows the reports on its items, and an experimental adapter's rows are in RCs only, as the rest of it is."""
    scope = adapter.scope
    rows = []
    for level, label, why in ITEM_LEVELS:
        held: dict[Support, list[str]] = {}
        named: dict[Support, list[str]] = {}
        for items, noun in (
            (scope.domains, "entities"),
            (scope.capabilities or {}, "components"),
            (scope.fields, "fields"),
        ):
            supports: dict[Support, list[str]] = {}
            for item, item_level in items.items():
                if item_level is level:
                    supports.setdefault(
                        Support.of(scope.proof(item) if item_level is Level.DOCUMENTED else level), []
                    ).append(item)
            for support, names in supports.items():
                held.setdefault(support, []).append(f"{', '.join(names)} {noun}")
                # A Documented item's reports are its sibling's.
                named.setdefault(support, []).extend(scope.siblings.get(name, name) for name in names)
        for support in sorted(held, key=list(Support).index):
            reports = (
                reports_cell(adapter.integration, action, data, named[support]) if support is Support.COMMUNITY else ""
            )
            rows.append(
                f"| `{action}` | {IN_RCS if scope.experimental else label} | {support} "
                f"| none ({why}: {'; '.join(held[support])}) | |{padded(reports)}|"
            )
    return rows


def by_integration(registry: AdapterRegistry) -> dict[str, list]:
    """The adapters per integration, in the README feature table's column order, so the cards read across as it does."""
    grouped: dict[str, list] = {}
    for _, adapter in adapters(registry):
        grouped.setdefault(adapter.integration, []).append(adapter)
    order = list(COLUMNS)  # the README feature table's columns, then any other by title

    def place(key: str) -> tuple[int, str]:
        return (order.index(key) if key in order else len(order), registry.integrations[key].title)

    return {key: sorted(grouped[key], key=lambda a: a.action) for key in sorted(grouped, key=place)}


def evidence(registry: AdapterRegistry, data: Data) -> str:
    parts = [
        EVIDENCE[0],
        "<!-- Generated by scripts/gen_compat.py from docs/test-records/, the adapters' scopes and docs/devices.yaml."
        " Do not edit; run the script. -->",
        "",
    ]
    for key, integration_adapters in by_integration(registry).items():
        parts.append(f"### {registry.integrations[key].title}\n")
        parts.append("| Action | Level | Support | Tested models | Records | Reports |")
        parts.append("|---|---|---|---|---|---|")
        for adapter in integration_adapters:
            # An unflagged adapter with no Verified call ships its items behind the option: level_rows lists them.
            if adapter.scope.experimental or proven(adapter.scope):
                parts.append(row(adapter.action, adapter, data))
            parts += level_rows(adapter.action, adapter, data)
        if broken := [entry for entry in data.doesnt_work if key in entry["integrations"]]:
            parts += ["", "| Doesn't work | Why | Source |", "|---|---|---|"]
            parts += [
                f"| {cell(entry['what'])} | {cell(entry['reason'])} | [source]({entry['source']}) |" for entry in broken
            ]
        parts.append("")
    parts.append(EVIDENCE[1])
    return "\n".join(parts)


# The README cards.


def features(actions: set[str]) -> tuple[str, ...]:
    labels = list(dict.fromkeys(FEATURES[action] for action in FEATURES if action in actions))
    labels += sorted(action for action in actions if action not in FEATURES)
    if len(labels) > 1 and "stop" in labels:
        labels.remove("stop")
    return tuple(labels)


def anchor(text: str, section: str) -> str:
    return f"[{text}]({PAGE_URL}#{slug(section)})"


@dataclass
class Card:
    title: str
    requires: str | None = None
    lines: dict[str, list[str]] = field(default_factory=dict)

    def short(self, name: str) -> str:
        """The name without the integration's, which the card's title already gives: "Hue Bridge v1" -> "Bridge v1"."""
        return name.removeprefix(f"{self.title} ")

    def render(self) -> str:
        requires = f" ({self.requires})" if self.requires else ""
        lines = [f"**{self.title}**{requires}", ""]
        for key, icon, _ in OUTCOMES:
            if key in ("should", "help"):
                lines += [f"- {icon} {entry}" for entry in self.lines.get(key, [])]
            elif self.lines.get(key):
                lines.append(f"- {icon} {' · '.join(self.lines[key])}")
        return "\n".join(lines)


def classes(key: str, integration_adapters: list, level: Level, data: Data) -> dict[str, dict[str, list[str]]]:
    """Each domain or capability the shipping adapters hold at the level, in first-seen order, with the actions that
    hold it there, each with the reports behind it when it rides a Reported sibling (community-supported)."""
    held: dict[str, dict[str, list[str]]] = {}
    for adapter in integration_adapters:
        if adapter.scope.experimental:
            continue
        for items in (adapter.scope.domains, adapter.scope.capabilities or {}):
            for item, item_level in items.items():
                if item_level is level:
                    if item not in data.capabilities.get(key, {}):
                        fail(f"capabilities: no entry for {key} {item}, which a scope holds as {level.name.title()}")
                    issues = []
                    if level is Level.DOCUMENTED and adapter.scope.proof(item) is Level.REPORTED:
                        issues = worked_reports(key, adapter.action, adapter.scope.siblings[item], data)
                    held.setdefault(item, {})[adapter.action] = issues
    return held


def merged(phrases: list[str], section: str) -> str:
    """One link for the classes of a page section, their shared last words said once: "CCT LED controllers", "RGB LED
    controllers" -> "LED controllers (CCT, RGB)". With no shared ending, the phrases in a list."""
    if len(phrases) == 1:
        return anchor(phrases[0], section)
    words = [phrase.split() for phrase in phrases]
    shared = 0
    while all(len(w) > shared for w in words) and len({tuple(w[len(w) - shared - 1 :]) for w in words}) == 1:
        shared += 1
    if not shared or any(len(w) == shared for w in words):  # nothing shared, or a phrase with no prefix to list
        return anchor(", ".join(phrases), section)
    ending = " ".join(words[0][-shared:])
    return anchor(f"{ending} ({', '.join(' '.join(w[:-shared]) for w in words)})", section)


def class_entries(key: str, held: dict[str, dict[str, list[str]]], data: Data) -> list[str]:
    """Classes with the same features and the same reports behind them share one entry: "dimmers, LED controllers
    (CCT, RGB): turn on with timer", then a link per report when community-supported. A class held by actions of
    different support is an entry per support, so a bare entry never takes another action's report links."""
    grouped: dict[tuple[tuple[str, ...], tuple[str, ...]], dict[str, list[str]]] = {}
    for item, actions in held.items():
        entry = data.capabilities[key][item]
        by_issues: dict[tuple[str, ...], set[str]] = {}
        for action, found in actions.items():
            by_issues.setdefault(tuple(dict.fromkeys(found)), set()).add(action)
        for issues, group in by_issues.items():
            grouped.setdefault((features(group), issues), {}).setdefault(entry["section"], []).append(entry["phrase"])
    return [
        f"{', '.join(merged(phrases, section) for section, phrases in sections.items())}: {', '.join(names)}"
        + badges(issues)
        for (names, issues), sections in grouped.items()
    ]


def works(card: Card, key: str, integration_adapters: list, data: Data) -> list[str]:
    """The models the shipping adapters' records tested, then those only users report, by device type, then first
    seen, then native groups. A rig-tested model and the native groups end ✔; a reported one links each report."""
    tested_names: list[str] = []
    groups = False
    shipping = {adapter.action for adapter in integration_adapters if not adapter.scope.experimental}
    for adapter in integration_adapters:
        if adapter.scope.experimental or not proven(adapter.scope):
            continue
        for item in tested(adapter, data):
            if item == GROUP:
                groups = True
            elif (name := data.models[item[0]]["name"]) not in tested_names:
                tested_names.append(name)
    reported: dict[str, list[str]] = {}
    for report in data.reports:
        if report["integration"] == key and shipping.intersection(report.get("worked") or []):
            reported.setdefault(data.models[report["model"]]["name"], []).append(report["issue"])
    by_name = {model["name"]: model for model in data.models.values()}
    names = [*tested_names, *(name for name in reported if name not in tested_names)]
    lines = []
    for name in sorted(names, key=lambda name: TYPES.index(by_name[name]["type"])):
        marks = f" {VERIFIED}" if name in tested_names else badges(reported[name])
        lines.append(anchor(card.short(name), by_name[name]["section"]) + marks)
    if groups:
        lines.append(f"{anchor(*GROUPS_ENTRY)} {VERIFIED}")
    return lines


def card(key: str, registry: AdapterRegistry, integration_adapters: list, data: Data) -> Card:
    result = Card(registry.integrations[key].title, data.requires.get(key))
    result.lines["works"] = works(result, key, integration_adapters, data)
    for outcome, level in (("should", Level.DOCUMENTED), ("help", Level.EXPERIMENTAL)):
        held = classes(key, integration_adapters, level, data)
        result.lines[outcome] = class_entries(key, held, data)
    result.lines["no"] = []
    for entry in data.doesnt_work:
        if key in entry["integrations"]:
            result.lines["no"].append(anchor(result.short(entry["what"]), entry["section"]))
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


def check_sections(page: str, data: Data) -> None:
    """Every section a card links to is a heading in the page's prose, so a renamed heading fails here rather than
    leaving a dead link."""
    prose = splice(page, EVIDENCE, "", "the page")
    headings = anchors(prose)
    if dead := sorted(section for section in {*data.sections, GROUPS_ENTRY[1]} if slug(section) not in headings):
        raise SystemExit(f"docs/device-compatibility.md has no heading for {', '.join(dead)}; add a section")


def main(
    argv: list[str] | None = None,
    registry: AdapterRegistry | None = None,
    page: Path = PAGE,
    readme: Path = README,
    data_path: Path = DATA,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail when the README or the page is out of date")
    args = parser.parse_args(argv)

    registry = registry or AdapterRegistry.discover()
    data = load(data_path, registry)
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
