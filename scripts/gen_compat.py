#!/usr/bin/env python3
"""Generate the README's device table and the evidence block of docs/device-compatibility.md, from the test records,
the adapters' scopes, docs/models.yaml and each integration's bundle, docs/integrations/<integration>/. The rules
the cards show (levels, the `experimental` flag, caveats) are in docs/evidence.md.

**Evidence** for an action is its passing test records (`<action>.json`, `<action>-<option>.json`, read by check_release
against docs/test-records.schema.json) and the `_manual.json` rows whose `passed` names it. A format 2 record gives each
passing test's devices, each a model with its firmware and the class it reached (and its manufacturer, which the cards
don't show yet); a native group's or a scene's test (`group`, its devices the members) shows as "group", never as its
members' models. Where the integration names classes, a device with a null class credits nothing, flagged or not, and a
group with one none either: it is on no card and no row. A format 1 record (converted from markdown) gives the run's
devices, not which test reached which, and its tests the classes they reached, if it recorded them. A manual row's
devices are model ids, each with its class. A level comes from the scope alone (verify, then trust): a record never
ages.

**Cards.** One collapsed section between the README's devices markers, the legend first and a link to the integrations
page last, with a card per integration: its name, linked to its page (the bundle's index.md), and maintainers
(`IntegrationInfo.maintainers`; "⚠️ Unmaintained · formerly maintained by" when every adapter is), then the features
of the adapters with each `caveat` (⚠️ Untested fix, then ⚠️ Unmaintained, linking its reason), then a bullet per tier:
- Works: the models the evidence tested (rig-tested ones end ✔), and native groups. A pass on a flagged item never
  puts a model here: an adapter flagged whole, or on any field, adds no models. One flagged on a domain or class adds,
  from a format 2 record, each model a passing test reached on an unflagged domain and, with a class flagged, an
  unflagged class (a null one is none), and native groups when every member's class is unflagged; from a format 1
  record, which doesn't say which test reached which model, the run's models only when every passing test targets an
  unflagged domain and, with a class flagged, names unflagged classes only; and, unless a domain is flagged (a manual
  row names none), each `_manual.json` model whose class is unflagged. A model can still reach Works through another
  adapter's evidence.
- Should work: the classes (devices.yaml `capabilities`) unflagged adapters hold as Documented.
- Experimental features: the classes held as `experimental(...)`, and the features of adapters flagged whole
  (`experimental=True`), whatever their evidence.
- Not built yet: the classes the integration declares (`IntegrationInfo.classes`) that an adapter holds in
  neither its `capabilities` nor its `no_known_method`, and so refuses; only those devices.yaml gives a phrase. Then
  docs/models.yaml's `not_built` entries, by their `what`.
- No known method: the scopes' `no_known_method`, with the features whose adapters list them, then devices.yaml's.
  A scope's `not_built` entry (core/scope.py, NotBuilt, one today's call harms) is listed as not built yet, as
  above; the evidence block adds a table of them and of models.yaml's, with why and the source.
Classes with the same features share an entry, and those of one page section a link. A model or blocker drops the
integration's name where it leads, as the card's name already gives it. Cards show features, not fields: a flagged or
Documented field shows on the integration's page and in the evidence block only.

**Evidence block.** Per integration, a row per action and level its domains, capabilities and fields hold (an adapter
flagged whole has one), the first with the evidence's records; each row carries the adapter's caveat. A model tested on
a class is listed with it, on the row of the weakest level the scope holds its class and its test's domain at, so each
class lists only the models that reached it, with their firmware, and a group goes by its test's domain; the rest (a
format 1 record's, which names no device's test, and items the scope doesn't hold) are on the first row. Every model a
test-records file names must be in docs/models.yaml or its bundle's devices.yaml, whatever its test's result
(`check_models`). The prose outside the evidence markers is kept as written.

**The coverage check** (`check_release.coverage_gaps`, docs/evidence.md) prints a warning per Verified class no
record reaches on every run, `--check` included, and never fails here: `check_release.py --signoffs` fails on it at
the cut.

**Data.** docs/models.yaml holds what integrations share: `models`, one entry per physical model (`name`, `ids` across
integrations, `type`, optional `section`; a model only one integration names is in its bundle's devices.yaml), and
`no_known_method` and `not_built` entries that name their `integrations` (`what`, `reason`, `source`, optional
`section`), a `not_built` one for a device today's call harms on an integration that doesn't class it yet, as an
unharmed one needs no entry. Each bundle's devices.yaml holds its integration's: `models` (as above), `column` and
`column_order` (the README feature table's, read by gen_features), `requires` (shown after the card's name),
`capabilities` (a `phrase` and `section` per domain or class the scopes hold below Verified, and per class to name as
not built yet) and `no_known_method` (`what`, `reason`, `source`, optional `section`: devices that fail the call
DeviceSide sends, not what isn't built). A scope's `no_known_method` (core/scope.py, NoKnownMethod) and `not_built`
(NotBuilt) are the code's home for these, and join them here; the devices.yaml and models.yaml entries move to them,
class by class. Every integration needs a bundle.

**Links.** A card links each model, class or blocker to the heading its `section` names (default: the model's
`name`, the blocker's `what`): on the card's integration page when that has the heading; a model's or native groups'
heading may be on any integration's page; else on docs/device-compatibility.md outside the evidence block. A heading
none of them has is an error.

Usage: scripts/gen_compat.py [--check]

--check exits 1 when the README or the page differs from what this generates.
"""

import argparse
import copy
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from custom_components.deviceside.core.registry import AdapterRegistry  # noqa: E402
from custom_components.deviceside.core.scope import CaveatKind, Level  # noqa: E402
from scripts.check_release import (  # noqa: E402
    MANUAL,
    adapters,
    classed,
    coverage_gaps,
    listed,
    manual_rows,
    names_classes,
    passing,
    record_class_errors,
    test_records_dir,
)
from scripts.check_release import load as read_record  # noqa: E402
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

REPORT_URL = "https://github.com/DeviceSide/DeviceSide/issues/new?template=device_report.yml"
NOUNS = ("entities", "classes", "fields")  # for a scope's domains, capabilities and fields

# Device types, in a card's order for its Works models.
TYPES = ("bulb", "relay", "plug", "dimmer", "LED controller")
# Tiers, in a card's order: (key, icon, legend).
OUTCOMES = (
    ("works", "🟢", "works"),
    ("should", "🟡", "should work: same call pattern as a tested device"),
    (
        "experimental",
        "🧪",
        f"experimental: enable in DeviceSide's Configure > Settings; please [report how it goes]({REPORT_URL})",
    ),
    ("not_built", "🚧", "not built yet: needs a command DeviceSide doesn't have yet"),
    ("no_known_method", "🔴", "no known method: no known command works on it"),
)
VERIFIED = "✔"
UNMAINTAINED = "⚠️ Unmaintained"
UNTESTED_FIX = "⚠️ Untested fix"
# The scope's caveats, as (kind, label), in a card's order.
MARKS = ((CaveatKind.UNTESTED_FIX, UNTESTED_FIX), (CaveatKind.UNMAINTAINED, UNMAINTAINED))
CARDS_LEGEND = " · ".join(
    [
        f"{OUTCOMES[0][1]} {OUTCOMES[0][2]}",
        f"{VERIFIED} verified on automated rig",
        *(f"{icon} {legend}" for _, icon, legend in OUTCOMES[1:]),
        f"⚠️ untested fix: changed, not yet tested; please [report whether it works]({REPORT_URL})",
        "⚠️ unmaintained: no one is fixing it; use at your own risk",
    ]
)
GITHUB = "https://github.com/"
INTEGRATIONS_URL = "https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations.md"
# The keys each devices.yaml entry may hold, so a typo fails instead of being ignored.
SHARED_KEYS = {"models", "no_known_method", "not_built"}  # each a list
BUNDLE_KEYS = {"column", "column_order", "requires", "capabilities", "models", "no_known_method"}
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
    """docs/models.yaml and the bundles' devices.yaml, merged and validated (a model is in either)."""

    requires: dict[str, str]
    models: dict[str, dict]  # by each of its ids
    capabilities: dict[str, dict[str, dict]]
    no_known_method: list[dict]
    # models.yaml's devices not built yet that today's call harms, on integrations whose code doesn't class them yet.
    not_built: list[dict] = field(default_factory=list)
    # Every heading an entry links to, with the integration whose card links it (None: any card, as for a model).
    sections: set[tuple[str | None, str]] = field(default_factory=set)
    # The heading anchors of each integration's page; a section on none of them is on PAGE.
    pages: dict[str, set[str]] = field(default_factory=dict)
    # The bundle each model id is listed in (None: docs/models.yaml), so a record names only its own bundle's.
    owner: dict[str, str | None] = field(default_factory=dict)

    def model(self, model_id: str, where: str, integration: str | None = None) -> dict:
        """The model, which a record of `integration` may name only from docs/models.yaml or its own bundle."""
        if model_id not in self.models:
            raise SystemExit(
                f"{where}: model {model_id!r} is in neither docs/models.yaml nor a bundle's devices.yaml; "
                "add it to `models`"
            )
        if integration is not None and (owner := self.owner.get(model_id)) not in (None, integration):
            raise SystemExit(
                f"{where}: model {model_id!r} is in docs/integrations/{owner}/devices.yaml; a model two "
                "integrations name goes in docs/models.yaml"
            )
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
    `no_known_method` entries are its own, so they take no `integrations` key."""
    need(shared, "docs/models.yaml", lists=tuple(sorted(SHARED_KEYS & set(shared))), keys=SHARED_KEYS)
    raw: dict = {"requires": {}, "capabilities": {}, "models": list(shared.get("models") or []), "bundle_models": {}}
    raw["no_known_method"] = list(shared.get("no_known_method") or [])
    raw["not_built"] = list(shared.get("not_built") or [])
    for key, data in bundles.items():
        where = f"docs/integrations/{key}/devices.yaml"
        if extra := set(data) - BUNDLE_KEYS:
            fail(f"{where}: unknown key {', '.join(sorted(extra))}")
        if "requires" in data:
            need(data, where, ("requires",))
            raw["requires"][key] = data["requires"]
        if data.get("capabilities"):
            raw["capabilities"][key] = data["capabilities"]
        if not isinstance(models := data.get("models") or [], list):
            fail(f"{where}: models must be a list")
        raw["bundle_models"][key] = models
        if not isinstance(broken := data.get("no_known_method") or [], list):
            fail(f"{where}: no_known_method must be a list")
        for entry in broken:
            if isinstance(entry, dict) and "integrations" in entry:
                fail(f"{where}: a no_known_method entry is {key}'s own; drop its integrations")
            raw["no_known_method"].append({**entry, "integrations": [key]} if isinstance(entry, dict) else entry)
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


def load_raw(raw: dict, registry: AdapterRegistry) -> Data:
    """The merged mapping (`merge`), its entries validated and their defaults filled in."""
    raw = copy.deepcopy(raw)  # defaults are filled in place
    data = Data(raw["requires"], {}, raw["capabilities"], [])
    for model in raw["models"]:
        load_model(model, data, None)
    for key, models in raw.get("bundle_models", {}).items():
        for model in models:
            load_model(model, data, key)
    data.sections.add((None, GROUPS_ENTRY[1]))  # every card with groups links it, as it does a model
    for key, items in data.capabilities.items():
        need(items, f"capabilities {key}")
        for item, entry in items.items():
            need(entry, f"capabilities {key} {item}", ("phrase", "section"), keys=CLASS_KEYS)
            data.sections.add((key, entry["section"]))
    for entry in raw["no_known_method"]:
        load_broken(entry, set(registry.integrations), data)
    for entry, actions in code_broken(registry):
        load_broken(entry, set(registry.integrations), data, actions)
    for entry in raw.get("not_built") or []:
        load_broken(entry, set(registry.integrations), data, kind="not_built")
    return data


def code_broken(registry: AdapterRegistry) -> list[tuple[dict, set[str]]]:
    """The scopes' no_known_method entries as devices.yaml's are, one per integration and entry, each with the actions
    whose adapters list it, in the order the registry gives them."""
    found: dict[tuple, tuple[dict, set[str]]] = {}
    for _, adapter in adapters(registry):
        for broken in adapter.scope.no_known_method.values():
            entry = {"what": broken.what, "reason": broken.reason, "source": broken.source}
            key = (adapter.integration, *entry.values())
            found.setdefault(key, ({**entry, "integrations": [adapter.integration]}, set()))[1].add(adapter.action)
    return list(found.values())


def code_unbuilt(key: str, integration_adapters: list, data: Data) -> list[dict]:
    """The scopes' not_built entries (core/scope.py, NotBuilt, each one today's call harms), each named by
    its class's devices.yaml phrase, with the actions whose adapters list it, for the evidence block: the card lists
    the class as not built yet, as it does any other, and this keeps the harm's source. One per class, reason and
    source."""
    found: dict[tuple, dict] = {}
    for adapter in integration_adapters:
        for name, entry in adapter.scope.not_built.items():
            if not entry.source.startswith("https://"):
                fail(f"not_built {key} {name}: source must be an https URL")
            if not entry.reason:
                fail(f"not_built {key} {name} needs a reason")
            if name not in data.capabilities.get(key, {}):
                fail(f"capabilities: no entry for {key} {name}, which a scope lists as not built yet")
            what = data.capabilities[key][name]["phrase"]
            row = {"what": what, "reason": entry.reason, "source": entry.source, "actions": set()}
            found.setdefault((name, entry.reason, entry.source), row)["actions"].add(adapter.action)
    return list(found.values())


def load_model(model: dict, data: Data, owner: str | None) -> None:
    need(model, f"model {model.get('name') if isinstance(model, dict) else model!r}", ("name",), ("ids",), MODEL_KEYS)
    if any(other["name"] == model["name"] for other in data.models.values()):
        fail(f"model name {model['name']!r} is listed twice")
    if model.get("type") not in TYPES:
        fail(f"model {model['name']!r}: type {model.get('type')!r} is not one of {', '.join(TYPES)}")
    model.setdefault("section", model["name"])
    for model_id in model["ids"]:
        if not isinstance(model_id, str):
            fail(f"model {model['name']!r}: id {model_id!r} must be a string; quote it")
        if model_id in data.models:
            fail(f"model id {model_id!r} is listed twice: in {source(data.owner[model_id])} and {source(owner)}")
        data.models[model_id] = model
        data.owner[model_id] = owner
    data.sections.add((None, model["section"]))


def source(owner: str | None) -> str:
    return "docs/models.yaml" if owner is None else f"docs/integrations/{owner}/devices.yaml"


def load_broken(
    entry: dict, known: set[str], data: Data, actions: set[str] | None = None, kind: str = "no_known_method"
) -> None:
    """A no_known_method entry (or, with `kind`, a models.yaml not_built one, of the same shape) validated, with the
    actions whose adapters list it when it comes from a scope."""
    need(
        entry,
        f"{kind} {entry.get('what') if isinstance(entry, dict) else entry!r}",
        ("what",),
        ("integrations",),
        BROKEN_KEYS,
    )
    if not str(entry.get("source", "")).startswith("https://"):
        fail(f"{kind} {entry['what']!r}: source must be an https URL")
    if unknown := set(entry["integrations"]) - known:
        fail(f"{kind} {entry['what']!r}: no integration {', '.join(sorted(unknown))}")
    for key in ("reason", "source"):
        if not entry.get(key):
            fail(f"{kind} {entry['what']!r} needs a {key}")
    entry.setdefault("section", entry["what"])
    data.sections.update((key, entry["section"]) for key in entry["integrations"])
    getattr(data, kind).append({**entry, "actions": actions} if actions else entry)


@dataclass(frozen=True)
class Tested:
    """A device the evidence tested: its model with its firmware and the class it reached (None: none named), or a
    native group (no model). `rig` for a record's; a manual row's names no firmware. `domain` is the domain a format 2
    test targeted; a format 1 record and a manual row name none per device."""

    model: str | None
    firmware: str | None = None
    cls: str | None = None
    rig: bool = True
    domain: str | None = None

    @property
    def group(self) -> bool:
        return self.model is None


GROUP = Tested(None)  # a format 1 record's native group; a format 2 one carries its test's domain
# Whether a passing test counts toward Works, by the domain it targeted and the classes it reached (a null class is in
# the set as None; a format 1 test's are its `classes`).
Clean = Callable[[str | None, set[str | None]], bool]


def tested(record: dict, clean: Clean | None = None, classed: bool = False) -> list[Tested]:
    """The devices the record's passing tests tested, in its order; with `clean`, only those it accepts. Format 2: each
    test's devices, each with its class, or a group for a native group's or a scene's test (`group`), judged by its
    members' classes; `classed` (the integration names classes) drops a device with a null class, and a group with
    one, as a null class credits nothing. Format 1 names a run's devices, not which test reached which, so `clean`
    takes all of them or none: all only when the record has a passing test and it accepts every one."""
    passed = [test for test in record["tests"] if test["result"] == "pass"]
    if record["format"] == 1:
        if clean and not (passed and all(clean(test.get("domain"), set(test.get("classes", ()))) for test in passed)):
            return []
        return [GROUP if item.get("group") else Tested(item["model"], item["firmware"]) for item in record["devices"]]
    found = []
    for test in passed:
        domain = test["domain"]
        if test.get("group"):
            reached = {item["class"] for item in test["devices"]}
            if not (classed and None in reached) and (clean is None or clean(domain, reached)):
                found.append(Tested(None, domain=domain))
            continue
        found += [
            Tested(item["model"], item["firmware"], item["class"], domain=domain)
            for item in test["devices"]
            if not (classed and item["class"] is None) and (clean is None or clean(domain, {item["class"]}))
        ]
    return found


@dataclass
class Evidence:
    """An action's evidence on one integration: its passing records, and what they and the `_manual.json` rows naming
    it tested, each with where it came from."""

    records: list[Path]
    tested: list[tuple[str, Tested]]

    @classmethod
    def of(cls, adapter, clean: Clean | None = None, by_hand: Callable[[str | None], bool] | None = None) -> Evidence:
        """The adapter's evidence: with `clean`, only the record tests it accepts; with `by_hand`, only the manual
        devices whose class it accepts. Where the integration names classes (`names_classes`), a device with a
        null class credits nothing, flagged or not (docs/evidence.md, The coverage check), so it is left out."""
        names = names_classes(adapter)
        records = passing(adapter.integration, adapter.action)
        found = [
            (path.relative_to(REPO).as_posix(), item)
            for path in records
            for item in tested(read_record(path), clean, names)
        ]
        found += [
            (MANUAL, Tested(model, None, cls, rig=False))
            for row in manual_rows(adapter.integration, adapter.action)
            for model, cls in row
            if not (names and cls is None) and (by_hand is None or by_hand(cls))
        ]
        return cls(records, found)

    def devices(self) -> list[Tested]:
        """What was tested, each once: the records' first, then the manual rows', groups last. `check_models` has
        checked every model against docs/models.yaml and the bundles' devices.yaml."""
        found: list[Tested] = []
        for _, item in self.tested:
            if item not in found:
                found.append(item)
        found.sort(key=lambda item: item.group)
        return found


def check_models(registry: AdapterRegistry, data: Data) -> None:
    """Every model a test-records file names is in docs/models.yaml or its own bundle's devices.yaml: each device of
    every record, whatever its test's result or class, and of `_manual.json` and `_facts.json`, so a model missing from
    it fails on the PR that lands the file, not later, when a test of it first credits a card. And, as check_release
    does at the cut, no record of an integration that names no classes names one (`record_class_errors`), so it fails
    on the PR too."""
    names = classed(registry)
    if errors := [
        error for key in sorted(registry.integrations) if key not in names for error in record_class_errors(key)
    ]:
        raise SystemExit("\n".join(errors))
    for key in sorted(registry.integrations):
        for path in listed(key):
            if path.suffix != ".json":
                continue  # no record: check_release --signoffs names it
            content = read_record(path)
            rows = [content, *(row for part in ("tests", "signoffs", "facts") for row in content.get(part, ()))]
            for row in rows:
                for item in row.get("devices", ()):
                    if "model" in item:  # a format 1 record's group names none
                        data.model(item["model"], path.relative_to(REPO).as_posix(), key)


def card_evidence(adapter) -> Evidence:
    """The evidence a card's Works counts. Fail-safe: none for an adapter flagged whole or on a field. For one flagged
    on a domain or class, the record tests (`tested`) that target unflagged domains and, when a class is flagged
    anywhere (an entry held on some domains alone is flagged on the rest), reach only classes unflagged in the test's
    domain; and, unless a domain is flagged (a manual row names none), the manual devices whose class is unflagged in
    some domain the adapter serves, as the coverage check lets a manual row cover any. Flagged or not, a null-class
    device of an integration that names classes counts for nothing (`Evidence.of`)."""
    scope = adapter.scope
    flagged = {noun for level, _, noun, domains in items(scope) if level is Level.EXPERIMENTAL or domains is not None}
    if scope.experimental or "fields" in flagged:
        return Evidence([], [])
    if not flagged:
        return Evidence.of(adapter)
    domains = {domain for domain, level in scope.domains.items() if level is not Level.EXPERIMENTAL}

    def unflagged(cls: str | None, domain: str) -> bool:
        return (
            cls is not None
            and cls in (scope.capabilities or {})
            and scope.class_level(cls, domain) is not Level.EXPERIMENTAL
        )

    def clean(domain: str | None, reached: set[str | None]) -> bool:
        if domain not in domains:
            return False
        return "classes" not in flagged or bool(reached) and all(unflagged(cls, domain) for cls in reached)

    def by_hand(cls: str | None) -> bool:
        # A manual row names no domain, so it counts in any domain its class is unflagged in, as the coverage check
        # lets it cover any (check_release.coverage_gaps).
        return "entities" not in flagged and ("classes" not in flagged or any(unflagged(cls, d) for d in scope.domains))

    return Evidence.of(adapter, clean, by_hand)


def items(scope) -> list[tuple[Level, str, str, frozenset[str] | None]]:
    """The scope's items, as (level, item, noun, domains), domains first: all Experimental in an adapter flagged whole.
    `domains` names those a class's level holds on alone (core/scope.py, OnDomains), else None."""
    entries = [(level, item, "entities", None) for item, level in scope.domains.items()]
    entries += [(level, item, "classes", domains) for item, level, domains in scope.class_entries()]
    entries += [(level, item, "fields", None) for item, level in scope.fields.items()]
    return [(Level.EXPERIMENTAL if scope.experimental else level, *rest) for level, *rest in entries]


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


def level_rows(scope) -> list[tuple[Level, str]]:
    """(level, items) per row: a row per level the scope holds, strongest first."""
    found = []
    for level in sorted(Level, reverse=True):
        if held := [
            (f"{item} on {', '.join(sorted(domains))}" if domains else item, noun)
            for item_level, item, noun, domains in items(scope)
            if item_level is level
        ]:
            found.append((level, named(held)))
    return found


def table_row(cells: list[str]) -> str:
    return "|" + "|".join(f" {text} " if text else " " for text in cells) + "|"


def described(item: Tested) -> str:
    """A tested item as the evidence block lists it: "`S3SW-001X8EU` (`Switch`), firmware `1.0`"."""
    if item.group:
        return "group"
    name = f"`{item.model}`" + (f" (`{item.cls}`)" if item.cls else "")
    if not item.rig:
        return f"{name}, by hand"
    return f"{name}, firmware `{item.firmware}`" if item.firmware else f"{name}, firmware unknown"


def rows(adapter) -> list[str]:
    """The action's rows: its records on the first; each tested model, and each group, on the row of the weakest
    level the scope holds its class and its test's domain at, else (neither held nor named: a format 1 record's) the
    first. A device with a null class, where the integration names classes, credits nothing (`Evidence.of`), so is on
    no row."""
    evidence = Evidence.of(adapter)
    levels = level_rows(adapter.scope)
    index = {level: number for number, (level, _) in enumerate(levels)}
    scope = adapter.scope
    entries = {name: (level, domains) for name, level, domains in scope.class_entries()}
    models: list[list[str]] = [[] for _ in levels]
    for item in evidence.devices():
        held = [scope.domains[item.domain]] if item.domain in scope.domains else []
        if item.cls in entries:
            # A format 2 test's domain decides a class held on some domains alone; one that names no domain, its level.
            held.append(scope.class_level(item.cls, item.domain) if item.domain else entries[item.cls][0])
        held = [Level.EXPERIMENTAL if scope.experimental else level for level in held]
        # A class flagged in this domain alone may have no row of its level: the scope's weakest row takes it.
        row = models[index.get(min(held), len(levels) - 1)] if held else models[0]
        if (text := described(item)) not in row:
            row.append(text)
    sources = [link(record, adapter.action) for record in evidence.records]
    if any(where == MANUAL for where, _ in evidence.tested):
        path = test_records_dir(adapter.integration) / MANUAL
        sources.append(f"[by hand]({path.relative_to(REPO / 'docs').as_posix()})")
    marks = [marked(label, reason) for kind, label in MARKS if (reason := caveat_reason(adapter.scope, kind))]
    action = " ".join([f"`{adapter.action}`", *(cell(mark) for mark in marks)])
    return [
        table_row(
            [
                action,
                level.name.title(),
                held,
                "<br>".join(models[number]) or ("none" if number == 0 else ""),
                ", ".join(sources) if number == 0 else "",
            ]
        )
        for number, (level, held) in enumerate(levels)
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
            parts += rows(adapter)
        if broken := [entry for entry in data.no_known_method if key in entry["integrations"]]:
            parts += ["", "| No known method | Why | Source |", "|---|---|---|"]
            parts += [
                f"| {cell(entry['what'])}{actions(entry)} | {cell(entry['reason'])} | [source]({entry['source']}) |"
                for entry in broken
            ]
        shared = [entry for entry in data.not_built if key in entry["integrations"]]
        if unbuilt := code_unbuilt(key, integration_adapters, data) + shared:
            parts += ["", "| Not built yet, harmed by today's call | Why | Source |", "|---|---|---|"]
            parts += [
                f"| {cell(entry['what'])}{actions(entry)} | {cell(entry['reason'])} | [source]({entry['source']}) |"
                for entry in unbuilt
            ]
        parts.append("")
    parts.append(EVIDENCE[1])
    return "\n".join(parts)


def actions(entry: dict) -> str:
    """A code entry's actions, as the evidence block names them after its `what`; nothing for a devices.yaml one,
    which names none."""
    return f" ({', '.join(f'`{action}`' for action in sorted(entry['actions']))})" if entry.get("actions") else ""


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
    # ⚠️ Untested fix, then ⚠️ Unmaintained entries: the features of the adapters so marked, by reason.
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
            if key in ("should", "experimental", "not_built"):
                lines += [f"- {icon} {entry}" for entry in self.lines.get(key, [])]
            elif self.lines.get(key):
                lines.append(f"- {icon} {' · '.join(self.lines[key])}")
        return "\n".join(lines)


def card_items(scope) -> list[tuple[Level, str, str]]:
    """The scope's items as a card shows them: a domain at most at the level of the strongest class the adapter serves,
    as a call in it runs at the weaker of the two (AdapterScope.level), so a domain whose every class is Experimental
    reads Experimental. The strongest, not the weakest: one Verified class (Zigbee2MQTT's `hue`) is enough for the
    domain's line to say so, as its other classes have lines of their own. A class whose level names domains counts
    only on those."""

    def best(domain: str) -> Level:
        held = [level for _, level, domains in scope.class_entries() if domains is None or domain in domains]
        return max(held, default=Level.EXPERIMENTAL)

    return [
        (min(level, best(item)) if noun == NOUNS[0] and scope.capabilities is not None else level, item, noun)
        for level, item, noun, _ in items(scope)
    ]


def classes(key: str, integration_adapters: list, level: Level, data: Data) -> dict[str, set[str]]:
    """Each domain or capability the unflagged adapters hold at the level (as `card_items` shows it), in first-seen
    order, with the actions that hold it there."""
    held: dict[str, set[str]] = {}
    for adapter in integration_adapters:
        if adapter.scope.experimental:
            continue
        for item_level, item, noun in card_items(adapter.scope):
            if item_level is level and noun != "fields":
                if item not in data.capabilities.get(key, {}):
                    fail(f"capabilities: no entry for {key} {item}, which a scope holds as {level.name.title()}")
                held.setdefault(item, set()).add(adapter.action)
    return held


def not_built(key: str, classes: frozenset[str], integration_adapters: list, data: Data) -> dict[str, set[str]]:
    """Each class the integration declares that an adapter holds in neither its capabilities nor its no_known_method,
    with the actions that refuse it (`not_built`), in devices.yaml's order. Only a class devices.yaml gives a phrase is
    named: Shelly's Switch has none, as a relay has no brightness or color to dim or set. A class no scope holds at
    all must have one, or the card would hide it."""
    phrased = data.capabilities.get(key, {})
    served = [
        (adapter.scope.capabilities or {}).keys() | adapter.scope.no_known_method.keys()
        for adapter in integration_adapters
    ]
    if hidden := sorted(classes - set().union(*served) - phrased.keys()):
        fail(
            f"capabilities: no entry for {key} {', '.join(hidden)}, which no scope holds, so the card lists it as not"
            " yet supported"
        )
    held: dict[str, set[str]] = {}
    for item in data.capabilities.get(key, {}):
        for adapter in integration_adapters:
            served = adapter.scope.capabilities
            if (
                item in classes
                and served is not None
                and item not in served.keys() | adapter.scope.no_known_method.keys()
            ):
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
    """Classes with the same features share one entry: "dimmers, LED controllers (CCT, RGB): turn on with timer", and
    each phrase in it once."""
    grouped: dict[tuple[str, ...], dict[str, list[str]]] = {}
    for item, actions in held.items():
        entry = data.capabilities[key][item]
        phrases = grouped.setdefault(features(actions), {}).setdefault(entry["section"], [])
        # Classes that share a phrase (Zigbee2MQTT's countdown plugs, a class per maker string) are said once.
        if entry["phrase"] not in phrases:
            phrases.append(entry["phrase"])
    return [
        f"{', '.join(merged(phrases, data.url(key, section)) for section, phrases in sections.items())}: "
        f"{', '.join(names)}"
        for names, sections in grouped.items()
    ]


def works(card: Card, key: str, integration_adapters: list, data: Data) -> list[str]:
    """The models the adapters' evidence tested (`card_evidence`), by device type, then first seen, then native
    groups. A rig-tested model and the native groups end ✔."""
    rig: set[str] = set()
    names: list[str] = []
    groups = False
    for adapter in integration_adapters:
        for item in card_evidence(adapter).devices():
            if item.group:
                groups = True
                continue
            name = data.models[item.model]["name"]
            if item.rig:
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
    for level, tier in ((Level.DOCUMENTED, "should"), (Level.EXPERIMENTAL, "experimental")):
        result.lines[tier] = class_entries(key, classes(key, integration_adapters, level, data), data)
    if flagged := {adapter.action for adapter in integration_adapters if adapter.scope.experimental}:
        result.lines["experimental"].append(", ".join(features(flagged)))
    result.lines["not_built"] = class_entries(key, not_built(key, info.classes, integration_adapters, data), data)
    result.lines["not_built"] += [
        anchor(result.short(entry["what"]), data.url(key, entry["section"]))
        for entry in data.not_built
        if key in entry["integrations"]
    ]
    result.lines["no_known_method"] = []
    for entry in data.no_known_method:
        if key in entry["integrations"]:
            label = anchor(result.short(entry["what"]), data.url(key, entry["section"]))
            result.lines["no_known_method"].append(
                f"{label}: {', '.join(features(entry['actions']))}" if entry.get("actions") else label
            )
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
    check_models(registry, data)
    # Both are computed before either is written, so a failure leaves neither half-updated.
    updates = {}
    for path, markers, block in ((page, EVIDENCE, evidence(registry, data)), (readme, CARDS, cards(registry, data))):
        text = path.read_text()
        updates[path] = (text, splice(text, markers, block, path.name))
    check_sections(updates[page][1], data)
    # The coverage check warns here, on every PR, and fails only at cut-release (check_release.py --signoffs).
    for gap in coverage_gaps(registry):
        print(f"warning: {gap}", file=sys.stderr)
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
