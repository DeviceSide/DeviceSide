#!/usr/bin/env python3
"""Generate the README's device cards and the evidence block of docs/device-compatibility.md, from the test records,
the adapters' scopes and docs/devices.yaml.

**Cards.** One collapsible card per integration, between the README's devices markers. Its lines:
- Works: the models in the passing records of adapters that ship (Verified), plus native groups, and the models of
  accepted working reports (👥, linked to the report).
- Should work: the classes (devices.yaml `capabilities`) the shipping adapters hold as Documented.
- Help us test: the classes they hold as Experimental, refused until the Experimental features option is on.
- Doesn't work: devices.yaml `doesnt_work`.
Each class entry names the features it is at that level for. The summary shows the best outcome per device type.
Adapters with the `experimental` flag are left out of the cards: they are in RCs only.

**Evidence.** Per integration, every action's level and the models its passing records tested, with a row per level
below Verified that its domains, capabilities or fields hold, and the reports on it. A group (a Device entry with no
firmware, firmware `unknown`, or named Group or Zone) shows as "group", not as a model. The prose outside the
evidence markers is kept as written; every heading a card links to must be in it.

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
from custom_components.deviceside.core.scope import Level  # noqa: E402
from scripts.check_release import adapters, proven, records  # noqa: E402
from scripts.gen_features import anchors, slug  # noqa: E402

PAGE = REPO / "docs" / "device-compatibility.md"
README = REPO / "README.md"
DATA = REPO / "docs" / "devices.yaml"
# Absolute: HACS renders the README inside Home Assistant, where a relative link doesn't resolve.
PAGE_URL = "https://github.com/jasonmx/DeviceSide/blob/main/docs/device-compatibility.md"
CARDS = ("<!-- devices:start -->", "<!-- devices:end -->")
EVIDENCE = ("<!-- evidence:start -->", "<!-- evidence:end -->")

RESULT = re.compile(r"^\| Result \| (\S+) \|", re.MULTILINE)
DEVICE = re.compile(r"^\| Device \| (.*) \|$", re.MULTILINE)
ENTRY = re.compile(r"^(?P<name>.*?)(?: \(`(?P<model>[^`]+)`\))?, firmware `(?P<firmware>[^`]+)`$")
ISSUE_URL = "https://github.com/jasonmx/DeviceSide/issues/"
ISSUE = re.compile(rf"^{re.escape(ISSUE_URL)}(\d+)$")
GROUP_NAMES = {"group", "zone"}
GROUP = "group"
IN_RCS = "Experimental (in RCs only)"
# An unflagged adapter whose Verified call has no passing record: check_release --records blocks a release on it.
NO_RECORD = "Unproven: no passing record"
# The item levels below Verified, as (level, label, why the row has no models), in the page's order.
ITEM_LEVELS = (
    (Level.REPORTED, "Reported", "reported by users"),
    (Level.DOCUMENTED, "Documented", "untested"),
    (Level.EXPERIMENTAL, "Experimental", "untested, behind Experimental features"),
)

# Device types, in a card summary's order within an outcome, with their plural.
TYPES = {
    "bulb": "bulbs",
    "relay": "relays",
    "plug": "plugs",
    "dimmer": "dimmers",
    "LED controller": "LED controllers",
    "group or scene": "groups",
}
# Outcomes, best first: (key, icon, label).
OUTCOMES = (
    ("works", "✅", "Works"),
    ("should", "🟡", "Should work"),
    ("help", "🙋", "Help us test"),
    ("no", "⛔", "Doesn't work"),
)
GROUPS_ENTRY = ("native groups", "Native groups")  # (phrase, section) for the groups a record tested
# Each action's feature, as a card names it, in the README feature table's order. `stop` rides a smooth move, so it
# is named only when nothing else is.
FEATURES = {
    "turn_on_for": "turn on with timer",
    "turn_off_for": "turn off with timer",
    "set_auto_off": "auto-off/on",
    "set_auto_on": "auto-off/on",
    "clear_auto_off": "auto-off/on",
    "clear_auto_on": "auto-off/on",
    "raise_brightness": "smooth dimming",
    "lower_brightness": "smooth dimming",
    "raise_saturation": "smooth saturation",
    "lower_saturation": "smooth saturation",
    "raise_hue": "smooth hue",
    "lower_hue": "smooth hue",
    "set_attributes": "set without turning on",
    "set_scene": "scenes",
    "get_attributes": "get attributes",
    "stop": "stop",
}


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


def check_type(kind, where: str, optional: bool = False) -> None:
    if (kind is None and not optional) or (kind is not None and kind not in TYPES):
        fail(f"{where}: type {kind!r} is not one of {', '.join(TYPES)}")


def load(path: Path, registry: AdapterRegistry) -> Data:
    return load_raw(yaml.safe_load(path.read_text()) or {}, registry)


def need(entry, where: str, strings: tuple[str, ...] = (), lists: tuple[str, ...] = ()) -> None:
    """A clean error for a wrong shape, instead of a KeyError or a string iterated per character."""
    if not isinstance(entry, dict):
        fail(f"{where} must be a mapping")
    for key in strings:
        if not isinstance(entry.get(key), str) or not entry[key]:
            fail(f"{where} needs a {key}")
    for key in lists:
        if not isinstance(entry.get(key), list):
            fail(f"{where}: {key} must be a list")


def load_raw(raw: dict, registry: AdapterRegistry) -> Data:
    need(raw, "the file")
    raw = copy.deepcopy(raw)  # defaults are filled in place
    if extra := set(raw) - {"integrations", "models", "capabilities", "doesnt_work", "reports"}:
        fail(f"unknown key {', '.join(sorted(extra))}")
    known = set(registry.integrations)
    for section in ("integrations", "capabilities"):
        if unknown := set(raw.get(section) or {}) - known:
            fail(f"{section}: no integration {', '.join(repr(key) for key in sorted(unknown))}")
    for key, entry in (raw.get("integrations") or {}).items():
        need(entry, f"integrations {key}", ("requires",))
    requires = {key: entry["requires"] for key, entry in (raw.get("integrations") or {}).items()}
    data = Data(requires, {}, raw.get("capabilities") or {}, [], [])
    for model in raw.get("models") or []:
        load_model(model, data)
    for key, items in data.capabilities.items():
        for item, entry in items.items():
            need(entry, f"capabilities {key} {item}", ("phrase", "section"))
            check_type(entry.get("type"), f"capabilities {key} {item}")
            data.sections.add(entry["section"])
    for entry in raw.get("doesnt_work") or []:
        load_broken(entry, known, data)
    actions = {(integration, action) for action, integration, adapter in registry.matrix() if adapter is not None}
    for report in raw.get("reports") or []:
        load_report(report, known, actions, data)
    return data


def load_model(model: dict, data: Data) -> None:
    need(model, f"model {model.get('name') if isinstance(model, dict) else model!r}", ("name",), ("ids",))
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
    need(entry, "a doesnt_work entry", ("what",), ("integrations",))
    if not str(entry.get("source", "")).startswith("https://"):
        fail(f"doesnt_work {entry['what']!r}: source must be an https URL")
    check_type(entry.get("type"), f"doesnt_work {entry['what']!r}", optional=True)
    if unknown := set(entry["integrations"]) - known:
        fail(f"doesnt_work {entry['what']!r}: no integration {', '.join(sorted(unknown))}")
    for key in ("reason", "source"):
        if not entry.get(key):
            fail(f"doesnt_work {entry['what']!r} needs a {key}")
    entry.setdefault("section", entry["what"])
    data.sections.add(entry["section"])
    data.doesnt_work.append(entry)


def load_report(report: dict, known: set[str], actions: set[tuple[str, str]], data: Data) -> None:
    where = f"report {report.get('issue') if isinstance(report, dict) else report}"
    need(report, where, ("integration",))
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
        if (report["integration"], action) not in actions:
            fail(f"{where}: {report['integration']} has no {action} adapter")
    for key in ("firmware", "deviceside"):
        if report.get(key) in (None, ""):
            fail(f"{where} needs {key}")
        report[key] = str(report[key])
    data.reports.append(report)


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
        elif "group" in item.lower():
            found.append(GROUP)
        else:
            raise SystemExit(f"{record.relative_to(REPO)}: can't read Device entry {item!r}")
    return found


def passing(integration: str, action: str) -> list[Path]:
    return [path for path in records(integration, action) if (m := RESULT.search(path.read_text())) and m[1] == "pass"]


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


def reports_cell(integration: str, action: str, data: Data) -> str:
    cells = []
    for report in data.reports:
        if report["integration"] != integration:
            continue
        number = ISSUE.match(report["issue"])[1]
        for key, mark in (("worked", "✅"), ("failed", "❌")):
            if action in (report.get(key) or []):
                cells.append(f"{mark} [#{number}]({report['issue']}) `{report['model']}`")
    return "<br>".join(cells)


def row(action: str, adapter, data: Data) -> str:
    found = passing(adapter.integration, action)
    level = IN_RCS if adapter.scope.experimental else "Verified" if found else NO_RECORD
    models = [GROUP if item == GROUP else f"`{item[0]}`, firmware `{item[1]}`" for item in tested(adapter, data, found)]
    records_cell = ", ".join(link(record, action) for record in found)
    reports = reports_cell(adapter.integration, action, data)
    reports_cell_text = f" {reports} " if reports else " "
    return f"| `{action}` | {level} | {'<br>'.join(models) or 'none'} | {records_cell} |{reports_cell_text}|"


def level_rows(action: str, adapter) -> list[str]:
    """A row per level below Verified that the adapter's domains, capabilities or fields hold, weakest last. They have
    no record, so no models; an experimental adapter's are in RCs only, as the rest of it is."""
    scope = adapter.scope
    rows = []
    for level, label, why in ITEM_LEVELS:
        held = []
        for items, noun in (
            (scope.domains, "entities"),
            (scope.capabilities or {}, "components"),
            (scope.fields, "fields"),
        ):
            if names := [item for item, item_level in items.items() if item_level is level]:
                held.append(f"{', '.join(names)} {noun}")
        if held:
            rows.append(
                f"| `{action}` | {IN_RCS if scope.experimental else label} | none ({why}: {'; '.join(held)}) | | |"
            )
    return rows


def by_integration(registry: AdapterRegistry) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for _, adapter in adapters(registry):
        grouped.setdefault(adapter.integration, []).append(adapter)
    return {
        key: sorted(grouped[key], key=lambda a: a.action)
        for key in sorted(grouped, key=lambda key: registry.integrations[key].title)
    }


def evidence(registry: AdapterRegistry, data: Data) -> str:
    parts = [
        EVIDENCE[0],
        "<!-- Generated by scripts/gen_compat.py from docs/test-records/, the adapters' scopes and docs/devices.yaml."
        " Do not edit; run the script. -->",
        "",
    ]
    for key, integration_adapters in by_integration(registry).items():
        parts.append(f"### {registry.integrations[key].title}\n")
        parts.append("| Action | Level | Tested models | Records | Reports |")
        parts.append("|---|---|---|---|---|")
        for adapter in integration_adapters:
            # An unflagged adapter with no Verified call ships its items behind the option: level_rows lists them.
            if adapter.scope.experimental or proven(adapter.scope):
                parts.append(row(adapter.action, adapter, data))
            parts += level_rows(adapter.action, adapter)
        if broken := [entry for entry in data.doesnt_work if key in entry["integrations"]]:
            parts += ["", "| Doesn't work | Why | Source |", "|---|---|---|"]
            parts += [f"| {entry['what']} | {entry['reason']} | [source]({entry['source']}) |" for entry in broken]
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
    best: dict[str, int] = field(default_factory=dict)  # device type -> index into OUTCOMES

    def saw(self, kind: str | None, outcome: str) -> None:
        index = [key for key, _, _ in OUTCOMES].index(outcome)
        if kind is not None:
            self.best[kind] = min(self.best.get(kind, index), index)

    def render(self) -> str:
        ordered = sorted(self.best.items(), key=lambda item: (item[1], list(TYPES).index(item[0])))
        summary = " · ".join(f"{TYPES[kind]} {OUTCOMES[index][1]}" for kind, index in ordered)
        requires = f" ({self.requires})" if self.requires else ""
        lines = ["<details>", f"<summary><b>{self.title}</b>{requires}: {summary}</summary>", ""]
        for key, icon, label in OUTCOMES:
            if self.lines.get(key):
                lines.append(f"- {icon} **{label}:** {' · '.join(self.lines[key])}")
        lines += ["", "</details>"]
        return "\n".join(lines)


def classes(key: str, integration_adapters: list, level: Level, data: Data) -> dict[str, set[str]]:
    """Each domain or capability the shipping adapters hold at the level, with the actions that hold it there, in
    first-seen order."""
    held: dict[str, set[str]] = {}
    for adapter in integration_adapters:
        if adapter.scope.experimental:
            continue
        for items in (adapter.scope.domains, adapter.scope.capabilities or {}):
            for item, item_level in items.items():
                if item_level is level:
                    if item not in data.capabilities.get(key, {}):
                        fail(f"capabilities: no entry for {key} {item}, which a scope holds as {level.name.title()}")
                    held.setdefault(item, set()).add(adapter.action)
    return held


def class_entries(card: Card, outcome: str, key: str, held: dict[str, set[str]], data: Data) -> list[str]:
    """Classes with the same features share one entry: "dimmers, CCT LED controllers (turn on with timer)"."""
    grouped: dict[tuple[str, ...], list[str]] = {}
    for item, actions in held.items():
        entry = data.capabilities[key][item]
        card.saw(entry["type"], outcome)
        grouped.setdefault(features(actions), []).append(anchor(entry["phrase"], entry["section"]))
    return [f"{', '.join(links)} ({', '.join(names)})" for names, links in grouped.items()]


def works(card: Card, key: str, integration_adapters: list, data: Data) -> list[str]:
    """The models the shipping adapters' records tested, then those only users report, by device type, then first
    seen, then native groups. A rig-tested model shows bare; a reported one shows 👥, linked to each report."""
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
    for name in sorted(names, key=lambda name: list(TYPES).index(by_name[name]["type"])):
        card.saw(by_name[name]["type"], "works")
        badges = "" if name in tested_names else "".join(f" [👥]({issue})" for issue in reported[name])
        lines.append(anchor(name, by_name[name]["section"]) + badges)
    if groups:
        card.saw("group or scene", "works")
        lines.append(anchor(*GROUPS_ENTRY))
    return lines


def card(key: str, registry: AdapterRegistry, integration_adapters: list, data: Data) -> Card:
    result = Card(registry.integrations[key].title, data.requires.get(key))
    result.lines["works"] = works(result, key, integration_adapters, data)
    for outcome, level in (("should", Level.DOCUMENTED), ("help", Level.EXPERIMENTAL)):
        held = classes(key, integration_adapters, level, data)
        result.lines[outcome] = class_entries(result, outcome, key, held, data)
    result.lines["no"] = []
    for entry in data.doesnt_work:
        if key in entry["integrations"]:
            result.saw(entry.get("type"), "no")
            result.lines["no"].append(anchor(entry["what"], entry["section"]))
    return result


def cards(registry: AdapterRegistry, data: Data) -> str:
    parts = [CARDS[0], "<!-- Generated by scripts/gen_compat.py. Do not edit; run the script. -->", ""]
    for key, integration_adapters in by_integration(registry).items():
        parts += [card(key, registry, integration_adapters, data).render(), ""]
    parts.append(CARDS[1])
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
