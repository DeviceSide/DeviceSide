#!/usr/bin/env python3
"""Generate the README's device table and the evidence block of docs/device-compatibility.md, from the test records,
the adapters' scopes, docs/models.yaml and each integration's bundle, docs/integrations/<integration>/. The rules
the cards show (levels, caveats) are in docs/evidence.md.

**Evidence** for an action is its passing test records (`<action>.json`, `<action>-<option>.json`, read by check_release
against docs/test-records.schema.json) and the `_manual.json` rows whose `passed` names it. A format 2 record gives each
passing test's devices, each a model with its firmware and the class it reached (and its manufacturer, which the cards
don't show yet); a native group's or a scene's test (`group`, its devices the members) shows as "group", never as its
members' models. Where the integration names classes, a device with a null class credits nothing, flagged or not, and a
group with one none either: it is on no card and no row. A format 1 record (converted from markdown) gives the run's
devices, not which test reached which, and its tests the classes they reached, if it recorded them. A manual row's
devices are model ids, each with its class; with `group`, a native group's members, which show as "group, by hand".
A level comes from the scope alone (verify, then trust): a record never ages.

**Cards.** One collapsed section between the README's devices markers: the legend, of the marks the cards use, then a
card per integration, then a link to the integrations page. A card has its name, linked to its page (the bundle's
index.md), with "⚠️ Unmaintained" when every adapter is; the features of the adapters with each `caveat` (🔧 Untested
fix, then ⚠️ Unmaintained, linking its reason); then a line per feature set, naming each class on one line, with its
features by status: "Hue lights (Hue White A60 B22 ✔): 🟢 turn on with timer · 🌱 get attributes". Only classes of
one brand share a line (`brand`): the class's family, else other brands; an integration with no families is one brand,
its "Other brands" section the other brands. Native groups sort first, then lines by brand, alphabetically, then
other brands, then models no class line takes; within a brand, tested lines first, "other …" lines last, the rest
alphabetically, and a line's names sort the same way (`ordered`), a variant's plain words before its maker strings.
- Statuses: a class counts on each entity domain it can be (`IntegrationInfo.classes`) that the adapter serves, at the
  level a call there runs at (AdapterScope.level): 🟢 Verified, 🟡 Documented, 🌱 Experimental; 🔴 for a scope's
  `no_known_method` entry, which names a class devices.yaml gives no phrase by its `what`. A feature whose actions
  differ in status names its parts ("🟡 smooth dimming down · 🌱 smooth dimming up"), so none shows twice. A feature not
  built yet on a class (in no scope, or a `not_built` entry) is left out, and a class with nothing left has no line.
  Where the integration names no classes, its domains stand in for them.
- Names: the class's devices.yaml phrase; one whose domains show different features is named per domain, by its
  `domains` phrases, so a plug never lists dimming. A scene domain is never one of them: a scene is classed by its
  lights, so its features join the class's light line ("set scene"); a class of scenes alone keeps its own.
  Classes of one page section share a link, and a line holding every class its section shows in its domains names
  the section instead, by its devices.yaml `sections` phrase.
- Variants: a section with `variants` (a model whose classes its page tells apart) is a parent line, "Tuya TS011F
  plugs: check Manufacturer …", with a child line per feature set of its classes, named by their phrases ("a, b, or
  c") and ending ✔ for a rig-tested model, which the parent names. Children never merge with another section's classes.
- Tested models follow the line of the class and domain a test reached them on (else of their class; else, from a
  format 1 record or a manual row naming none, a line of their own with the features tested), and native groups get
  a line, with the features a test reached them on; rig-tested ones end ✔. A pass on a flagged item never credits a
  model: an adapter flagged whole, or on any field, credits none. One flagged on a domain or class credits, from a
  format 2 record, each model a passing test reached on an unflagged domain and, with a class flagged, an unflagged
  class (a null one is none), and native groups when every member's class is unflagged; from a format 1 record, which
  doesn't say which test reached which model, the run's models only when every passing test targets an unflagged
  domain and, with a class flagged, names unflagged classes only; and, unless a domain is flagged (a manual row names
  none), each `_manual.json` model whose class is unflagged.
- devices.yaml's and models.yaml's `no_known_method` entries, which name no class, each get a 🔴 line; models.yaml's
  `not_built` ones are on no card. The evidence block lists both, and the scopes' `not_built` entries, with why and
  the source.
A model or blocker drops the integration's name where it leads, as the card's name already gives it. Cards show
features, not fields: a flagged or Documented field shows on the integration's page and in the evidence block only.

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
`column_order` (the README feature table's, read by gen_features, and the Requirements line's), `requirements_name`
(optional: the Requirements line's name for the integration, its title by default), `requires` (shown after the card's
name), `capabilities` (a `phrase` and `section` per class a card line names, or domain where the integration names no
classes, and per class a scope lists as not built yet; `domains`, a phrase per entity domain, for a class the card
splits), `sections` (optional: a `phrase`, and `domains`, per page section, for a line holding all its classes, or
with `variants`, what to check to tell its classes apart) and
`no_known_method` (`what`, `reason`, `source`, optional `section`: devices that fail the call DeviceSide sends, not
what isn't built). A scope's `no_known_method` (core/scope.py, NoKnownMethod) and `not_built` (NotBuilt) are the
code's home for these, and join them here; the devices.yaml and models.yaml entries move to them, class by class.
Every integration needs a bundle.

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
from homeassistant.const import Platform

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from custom_components.deviceside.const import DOCS_URL  # noqa: E402
from custom_components.deviceside.core.registry import AdapterRegistry  # noqa: E402
from custom_components.deviceside.core.scope import CaveatKind, ClassDomains, Level  # noqa: E402
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
PAGE_URL = f"{DOCS_URL}docs/device-compatibility.md"
CARDS = ("<!-- devices:start -->", "<!-- devices:end -->")
CARDS_TITLE = "Device compatibility by integration"
REQUIREMENTS = ("<!-- requirements:start -->", "<!-- requirements:end -->")
EVIDENCE = ("<!-- evidence:start -->", "<!-- evidence:end -->")

REPORT_URL = "https://github.com/DeviceSide/DeviceSide/issues/new?template=device_report.yml"

# Device types, in a card's order for a line's tested models.
TYPES = ("bulb", "relay", "plug", "dimmer", "LED controller")
# A line's statuses, in its order: (key, icon, legend). Not built yet has none: a card leaves those out.
OUTCOMES = (
    ("works", "🟢", "works"),
    ("should", "🟡", "should work: same call pattern as a tested device"),
    (
        "experimental",
        "🌱",
        f"new or untested: enable Configure > Settings to try it out and [report whether it works]({REPORT_URL})",
    ),
    ("no_known_method", "🔴", "no known command works on it"),
)
TIER = {Level.VERIFIED: "works", Level.DOCUMENTED: "should", Level.EXPERIMENTAL: "experimental"}
VERIFIED = "✔"
UNMAINTAINED = "⚠️ Unmaintained"
UNTESTED_FIX = "🔧 Untested fix"
# The scope's caveats, as (kind, label), in a card's order.
MARKS = ((CaveatKind.UNTESTED_FIX, UNTESTED_FIX), (CaveatKind.UNMAINTAINED, UNMAINTAINED))
# The legend's entries, as (icon, text), in its order; it lists only those a card uses (`legend`).
LEGEND = (
    (OUTCOMES[0][1], OUTCOMES[0][2]),
    (VERIFIED, "verified on automated rig"),
    *((icon, text) for _, icon, text in OUTCOMES[1:]),
    ("🔧", f"untested fix: please try it and [report whether it works]({REPORT_URL})"),
    ("⚠️", "unmaintained: use at your own risk"),
)
GITHUB = "https://github.com/"
INTEGRATIONS_URL = "https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations.md"
# The keys each devices.yaml entry may hold, so a typo fails instead of being ignored.
SHARED_KEYS = {"models", "no_known_method", "not_built"}  # each a list
BUNDLE_KEYS = {
    "requirements_name",
    "column",
    "column_order",
    "requires",
    "capabilities",
    "sections",
    "models",
    "no_known_method",
}
MODEL_KEYS = {"name", "ids", "type", "section"}
CLASS_KEYS = {"phrase", "section", "domains"}  # `domains`: a phrase per entity domain, for a class the card splits
# A section's phrase, for a line that holds all its classes; with `variants`, what to check to tell its classes apart,
# and the card gives them a parent bullet of their own.
SECTION_KEYS = {"phrase", "domains", "variants"}
BROKEN_KEYS = {"what", "integrations", "reason", "source", "section"}
GROUPS_ENTRY = ("native groups", "Native groups")  # (phrase, section) for the groups a record tested
OTHER_BRANDS = "Other brands"  # the devices.yaml section of other brands' classes, on an integration with no families


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
    # Each integration's devices.yaml `sections`: a phrase (and per domain) for each page section that has one.
    section_phrases: dict[str, dict[str, dict]] = field(default_factory=dict)
    # models.yaml's devices not built yet that today's call harms, on integrations whose code doesn't class them yet.
    not_built: list[dict] = field(default_factory=list)
    # Each integration's Requirements name (devices.yaml `requirements_name`, else its title) and its `column_order`.
    names: dict[str, str] = field(default_factory=dict)
    order: dict[str, int] = field(default_factory=dict)
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
                return f"{DOCS_URL}{page(owner)}#{anchor}"
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


def read_names(raw: dict, key: str, data: dict, where: str) -> None:
    """A bundle's `requirements_name` (the Requirements line's) and `column_order`."""
    if "requirements_name" in data:
        need(data, where, ("requirements_name",))
        raw["names"][key] = data["requirements_name"]
    if isinstance(data.get("column_order"), int):
        raw["order"][key] = data["column_order"]


def merge(shared: dict, bundles: dict[str, dict]) -> dict:
    """The shared file and the bundles as one mapping, each bundle's entries named for its integration: a bundle's
    `no_known_method` entries are its own, so they take no `integrations` key."""
    need(shared, "docs/models.yaml", lists=tuple(sorted(SHARED_KEYS & set(shared))), keys=SHARED_KEYS)
    raw: dict = {
        "requires": {},
        "names": {},
        "order": {},
        "capabilities": {},
        "models": list(shared.get("models") or []),
        "bundle_models": {},
    }
    raw["no_known_method"] = list(shared.get("no_known_method") or [])
    raw["not_built"] = list(shared.get("not_built") or [])
    for key, data in bundles.items():
        where = f"docs/integrations/{key}/devices.yaml"
        if extra := set(data) - BUNDLE_KEYS:
            fail(f"{where}: unknown key {', '.join(sorted(extra))}")
        if "requires" in data:
            need(data, where, ("requires",))
            raw["requires"][key] = data["requires"]
        read_names(raw, key, data, where)
        if data.get("capabilities"):
            raw["capabilities"][key] = data["capabilities"]
        if data.get("sections"):
            raw.setdefault("sections", {})[key] = data["sections"]
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
    data = Data(raw["requires"], {}, raw["capabilities"], [], names=raw.get("names", {}), order=raw.get("order", {}))
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
            if "domains" in entry:
                need(entry["domains"], f"capabilities {key} {item} domains", tuple(entry["domains"]))
            data.sections.add((key, entry["section"]))
    load_sections(raw.get("sections") or {}, data)
    for entry in raw["no_known_method"]:
        load_broken(entry, set(registry.integrations), data)
    for entry, actions in code_broken(registry):
        load_broken(entry, set(registry.integrations), data, actions)
    for entry in raw.get("not_built") or []:
        load_broken(entry, set(registry.integrations), data, kind="not_built")
    return data


def load_sections(by_key: dict[str, dict], data: Data) -> None:
    """The bundles' `sections`, validated: each a section some class of its `capabilities` names."""
    for key, items in by_key.items():
        need(items, f"sections {key}")
        for section, entry in items.items():
            need(entry, f"sections {key} {section}", ("phrase", *({"variants"} & set(entry))), keys=SECTION_KEYS)
            if "domains" in entry:
                need(entry["domains"], f"sections {key} {section} domains", tuple(entry["domains"]))
            if section not in {item["section"] for item in data.capabilities.get(key, {}).values()}:
                fail(f"sections {key} {section}: no class in capabilities has that section")
        data.section_phrases[key] = items


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
    """The scopes' not_built entries (core/scope.py, NotBuilt, on a harmful action only), each named by
    its class's devices.yaml phrase, with the actions whose adapters list it, for the evidence block, which keeps the
    harm's source: the card leaves the class's feature out, as it does any not built yet. One per class, reason and
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
            section = data.section_phrases.get(key, {}).get(data.capabilities[key][name]["section"], {})
            if "variants" in section:  # a variant's phrase names it within its model: "no countdown setting"
                what = f"{section['phrase']} ({what})"
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
        devices whose class it accepts (a group row, only when it accepts every member's). Where the integration names
        classes (`names_classes`), a device with a null class credits nothing, flagged or not (docs/evidence.md, The
        coverage check), so it is left out, as is a group with such a member. A manual group row is one group, tested
        by hand."""
        names = names_classes(adapter)
        records = passing(adapter.integration, adapter.action)
        found = [
            (path.relative_to(REPO).as_posix(), item)
            for path in records
            for item in tested(read_record(path), clean, names)
        ]
        for group, row in manual_rows(adapter.integration, adapter.action):
            if group:
                # Judged as a rig group test is: a member the integration can't credit, or `by_hand` refuses, drops it.
                if not (names and any(cls is None for _, cls in row)) and (
                    by_hand is None or all(by_hand(cls) for _, cls in row)
                ):
                    found.append((MANUAL, Tested(None, rig=False)))
                continue
            found += [
                (MANUAL, Tested(model, None, cls, rig=False))
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
    """The evidence a card credits tested models from. Fail-safe: none for an adapter flagged whole or on a field.
    For one flagged on a domain or class, the record tests (`tested`) that target unflagged domains and, when a class
    is flagged anywhere (an entry held on some domains alone is flagged on the rest), reach only classes unflagged in
    the test's domain; and, unless a domain is flagged (a manual row names none), the manual devices whose class is
    unflagged in some domain the adapter serves, as the coverage check lets a manual row cover any. Flagged or not, a
    null-class device of an integration that names classes counts for nothing (`Evidence.of`)."""
    scope = adapter.scope
    flagged = {noun for level, _, noun, domains in items(scope) if level is Level.EXPERIMENTAL or domains is not None}
    if scope.all_experimental or "fields" in flagged:
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
    return [(Level.EXPERIMENTAL if scope.all_experimental else level, *rest) for level, *rest in entries]


# The evidence block.


def link(record: Path, action: str) -> str:
    option = record.stem.removeprefix(action).lstrip("-")
    label = option.replace("_", " ") if option else "record"
    return f"[{label}]({record.relative_to(REPO / 'docs').as_posix()})"


def caveat_reason(scope, kind: CaveatKind) -> str | None:
    """The reason of the scope's caveat when it is of that kind, else None."""
    return scope.caveat.reason if scope.caveat is not None and scope.caveat.kind is kind else None


def marked(label: str, reason: str) -> str:
    """A mark (⚠️ Unmaintained, 🔧 Untested fix), linking its reason when that is a URL, else giving it in brackets."""
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
        return "group" if item.rig else "group, by hand"
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


# A card item: a class with one of the entity domains it can be, or, where the integration names no classes, a domain
# with None.
type Item = tuple[str, str | None]
# A line's features by status, in OUTCOMES order: (("works", ("turn on with timer",)), ("experimental", (...))).
type Shape = tuple[tuple[str, tuple[str, ...]], ...]
# A class's brand, from its name and page section, as lines sort it: (0, family key) for a family's, (1, "") for other
# brands' (`brands`).
type Brand = Callable[[str, str | None], tuple[int, str]]


def part(action: str) -> str:
    """The part of its feature an action is, for a feature whose actions a line shows at different statuses: "smooth
    dimming up" (raise_brightness), "auto-off" (set_auto_off)."""
    for prefix, end in (("raise_", " up"), ("lower_", " down")):
        if action.startswith(prefix):
            return FEATURES[action] + end
    if action.endswith(("_auto_off", "_auto_on")):
        return "auto-" + action.rsplit("_", 1)[1]
    return action.replace("_", " ")


def shape(by_status: dict[str, set[str]]) -> Shape:
    """The actions by status as a line names them, each feature under one status: one whose actions differ names its
    parts instead ("🟡 smooth dimming down · 🌱 smooth dimming up"). `stop` rides the smooth moves, so it is named
    only on a line that names nothing else."""
    labels = {status: features(actions, fold_stop=False) for status, actions in by_status.items()}
    every = [label for found in labels.values() for label in found]
    split = {label for label in every if every.count(label) > 1}
    for status, found in labels.items():
        parts = [
            part(action) if label in split else label
            for label in found
            for action in (
                [a for a in FEATURES if a in by_status[status] and FEATURES[a] == label] if label in split else [None]
            )
        ]
        labels[status] = tuple(dict.fromkeys(parts))
    if set(every) - {"stop"}:
        labels = {status: tuple(label for label in found if label != "stop") for status, found in labels.items()}
    return tuple((key, labels[key]) for key, *_ in OUTCOMES if labels.get(key))


def statuses(integration_adapters: list, class_domains: ClassDomains) -> dict[Item, dict[str, set[str]]]:
    """Each item the adapters serve, with its actions by status, in first-seen order. A class counts on each entity
    domain it can be (IntegrationInfo.classes) that the adapter serves, at the level a call there runs at
    (AdapterScope.level: the weaker of the domain and the class); a class in the scope's `no_known_method` has none
    there; one the scope names in neither (not built yet) is left out. An adapter flagged whole is Experimental
    throughout."""
    found: dict[Item, dict[str, set[str]]] = {}
    for adapter in integration_adapters:
        scope = adapter.scope
        held: list[tuple[Item, str]] = []
        if not class_domains:
            held = [((domain, None), TIER[level]) for domain, level in scope.domains.items()]
        else:
            names = [name for name, _, _ in scope.class_entries()] if scope.capabilities is not None else class_domains
            for name in [*names, *scope.no_known_method]:
                for domain in reached(class_domains, name, scope):
                    if name in scope.no_known_method:
                        held.append(((name, domain), "no_known_method"))
                    else:
                        held.append(((name, domain), TIER[scope.level(domain, [name])]))
        for item, status in held:
            found.setdefault(item, {}).setdefault(status, set()).add(adapter.action)
    return found


def reached(class_domains: ClassDomains, name: str, scope) -> list[str]:
    """The domains the class can be (IntegrationInfo.classes) that the scope serves, in the scope's order, and, for a
    class it serves on some alone (OnDomains `only`), those. Never empty for a class the scope holds or refuses with
    a reason (core/registry.py, check_classes)."""
    held = name not in scope.no_known_method
    return [
        domain
        for domain in scope.domains
        if domain in class_domains.get(name, ()) and (not held or scope.admits(name, domain))
    ]


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


def text(phrases: list[str]) -> str:
    """A section's phrases as `merged` names them, without the link."""
    return merged(phrases, "")[1:-3]


@dataclass
class Line:
    """A card line: the classes (or domains) that show the same features, by page section, and the tested models a
    test reached them on."""

    shape: Shape
    sections: dict[str, list[str]] = field(default_factory=dict)  # each section's phrases, said once each
    items: list[Item] = field(default_factory=list)
    models: list[str] = field(default_factory=list)  # model names, as `works` gives them
    label: str | None = None  # a line no class names: native groups, or models no class line takes
    # A model's variants (devices.yaml `sections` with `variants`): the parent names the model and what to check, each
    # child a variant, by its classes' phrases, with ✔ for a rig-tested model, which the parent already names.
    note: str | None = None
    children: list[Line] = field(default_factory=list)
    variant: bool = False
    at: dict[Item, str] = field(default_factory=dict)  # each item's page section

    def plain(self) -> str:
        """The name as text, for sorting."""
        return (self.label or ", ".join(text(phrases) for phrases in self.sections.values())).lower()

    def name(self, card: Card, key: str, data: Data, rig: set[str]) -> str:
        if self.label is not None:
            return self.label
        if self.variant:
            ((section, phrases),) = self.sections.items()
            # Variants read as either: "no countdown setting, _TZ3000_a, or _TZ3000_b".
            either = f"{', '.join(phrases[:-1])}, or {phrases[-1]}" if len(phrases) > 1 else phrases[0]
            return anchor(either, data.url(key, section)) + (f" {VERIFIED}" if set(self.models) & rig else "")
        names = ", ".join(merged(phrases, data.url(key, section)) for section, phrases in self.sections.items())
        tested = [card.short(name) for name in self.models]
        if len(tested) == 1 and [tested[0]] == [p for phrases in self.sections.values() for p in phrases]:
            return names + (f" {VERIFIED}" if self.models[0] in rig else "")  # a class that is its model
        if tested:
            names += f" ({', '.join(card.model(name, key, data, rig) for name in self.models)})"
        return names

    def render(self, card: Card, key: str, data: Data, rig: set[str]) -> str:
        if self.note is not None:
            children = "".join(f"\n  - {child.render(card, key, data, rig)}" for child in self.children)
            return f"{self.name(card, key, data, rig)}: {self.note}{children}"
        icons = {key: icon for key, icon, _ in OUTCOMES}
        found = " · ".join(f"{icons[status]} {', '.join(labels)}" for status, labels in self.shape)
        return f"{self.name(card, key, data, rig)}: {found}"


def class_lines(
    key: str,
    found: dict[Item, dict[str, set[str]]],
    data: Data,
    class_domains: ClassDomains,
    served: list[str],
    broken: dict[str, dict],
    brand: Brand = lambda cls, section: (0, ""),
) -> list[Line]:
    """One line per brand (`brands`) and feature set, each class on one: a class named once, by its devices.yaml
    phrase, when it shows the same features on every domain it can be that the integration serves (`served`), else
    once per domain it shows on, by its `domains` phrase, so a plug never reads as dimmable. A class with no entry
    that a scope's no_known_method names is named by its `what` (`broken`). A section with `variants` gets a parent
    line, its classes child lines of their own, which never merge with another section's. Unsorted (`ordered`)."""
    by_item, members = by_home(found, class_domains)
    lines: dict[tuple[tuple, Shape], Line] = {}
    sections: dict[Item, str] = {}  # each item's page section
    found_phrases = data.section_phrases.get(key, {})
    parents: dict[str, tuple[Line, dict[Shape, Line]]] = {}
    for item, by_domain in by_item.items():
        entry = data.capabilities.get(key, {}).get(item) or broken.get(item)
        if entry is None:
            fail(f"capabilities: no entry for {key} {item}, which the card lists")
        can_be = list(
            dict.fromkeys(
                domain_home(class_domains[item], domain) for domain in served if domain in class_domains.get(item, ())
            )
        )
        for phrase, found_shape, homes in naming(key, item, entry, by_domain, can_be):
            domains = [domain for home in homes for domain in members[item][home]]
            if "variants" in (parent_entry := found_phrases.get(entry["section"], {})):
                parent = Line((), {entry["section"]: [parent_entry["phrase"]]}, note=parent_entry["variants"])
                children = parents.setdefault(entry["section"], (parent, {}))[1]
                line = children.setdefault(found_shape, Line(found_shape, variant=True))
            else:
                line = lines.setdefault((brand(item, entry["section"]), found_shape), Line(found_shape))
            phrases = line.sections.setdefault(entry["section"], [])
            # Classes that share a phrase (Zigbee2MQTT's countdown plugs, a class per maker string) are said once.
            if phrase not in phrases:
                phrases.append(phrase)
            line.items += [(item, domain) for domain in domains]
            line.at |= {(item, domain): entry["section"] for domain in domains}
            sections |= line.at
    for line in lines.values():
        section_phrases(line, sections, found_phrases)
    for parent, children in parents.values():
        parent.children = list(children.values())
        parent.items = [item for child in parent.children for item in child.items]
        parent.at = {item: at for child in parent.children for item, at in child.at.items()}
    return [*lines.values(), *(parent for parent, _ in parents.values())]


def domain_home(domains: frozenset, domain: str | None) -> str | None:
    """The domain a class's card line names `domain` by: a scene's is light, where the class can be a light."""
    return Platform.LIGHT if domain == Platform.SCENE and Platform.LIGHT in domains else domain


def by_home(
    found: dict[Item, dict[str, set[str]]], class_domains: ClassDomains
) -> tuple[dict[str, dict[str | None, Shape]], dict[str, dict[str | None, list[str | None]]]]:
    """Each item's features per domain a line names it by (`domain_home`, a scene folded into light), and the domains
    each of those holds."""
    merged_found: dict[str, dict[str | None, dict[str, set[str]]]] = {}
    members: dict[str, dict[str | None, list[str | None]]] = {}
    for (item, domain), by_status in found.items():
        home = domain_home(class_domains.get(item, frozenset()), domain)
        members.setdefault(item, {}).setdefault(home, []).append(domain)
        into = merged_found.setdefault(item, {}).setdefault(home, {})
        for status, actions in by_status.items():
            into.setdefault(status, set()).update(actions)
    by_item: dict[str, dict[str | None, Shape]] = {}
    for item, homes in merged_found.items():
        for home, by_status in homes.items():
            if found_shape := shape(by_status):
                by_item.setdefault(item, {})[home] = found_shape
    return by_item, members


def naming(
    key: str, item: str, entry: dict, by_domain: dict[str | None, Shape], domains: list[str]
) -> list[tuple[str, Shape, list[str | None]]]:
    """The item as its lines name it, (phrase, features, domains): once, by its phrase, when it shows the same features
    on every domain it can be, else once per domain it shows on, by its `domains` phrase."""
    if None in by_domain or (set(by_domain) == set(domains) and len(set(by_domain.values())) == 1):
        return [(entry["phrase"], next(iter(by_domain.values())), list(by_domain))]
    for domain in by_domain:
        if domain not in entry.get("domains", {}):
            fail(
                f"capabilities: {key} {item} shows other features on each of its domains, so its card line"
                f" splits: give it a phrase for {domain} (`domains`)"
            )
    return [(entry["domains"][domain], found_shape, [domain]) for domain, found_shape in by_domain.items()]


def section_phrases(line: Line, sections: dict[Item, str], phrases: dict[str, dict]) -> None:
    """A line that holds every class a section shows on the card in its domains names the section, by its devices.yaml
    `sections` phrase (its domain's, where it gives one), instead of each class."""
    for section, names in line.sections.items():
        mine = {item for item in line.items if sections.get(item) == section}
        domains = {domain for _, domain in mine}
        every = {item for item, at in sections.items() if at == section and item[1] in domains}
        if len(names) > 1 and mine == every and (entry := phrases.get(section)):
            (only,) = domains if len(domains) == 1 else (None,)
            names[:] = [entry.get("domains", {}).get(only, entry["phrase"])]


@dataclass
class Reached:
    """What a card's evidence tested of one model: where (its class and domain, a domain alone where the integration
    names no classes), on which actions, and whether the rig did."""

    places: list[tuple[str | None, str | None]] = field(default_factory=list)
    actions: set[str] = field(default_factory=set)
    rig: bool = False


def works(integration_adapters: list, data: Data) -> tuple[dict[str, Reached], Reached | None]:
    """The models the adapters' evidence tested (`card_evidence`), by device type, then first seen, and native groups,
    each with where and on which actions."""
    models: dict[str, Reached] = {}
    groups: Reached | None = None
    for adapter in integration_adapters:
        for item in card_evidence(adapter).devices():
            if item.group:
                groups = groups or Reached()
                tested = groups
            else:
                tested = models.setdefault(data.models[item.model]["name"], Reached())
                if (item.cls, item.domain) not in tested.places:
                    tested.places.append((item.cls, item.domain))
            tested.actions.add(adapter.action)
            tested.rig = tested.rig or item.rig
    by_name = {model["name"]: model for model in data.models.values()}
    ordered = sorted(models, key=lambda name: TYPES.index(by_name[name]["type"]))
    return {name: models[name] for name in ordered}, groups


def place(lines: list[Line], tested: Reached, classed: bool) -> list[Line]:
    """The lines a tested model goes on: each holding the class and domain a test reached it on (the domain alone where
    the integration names no classes), else, for a test whose domain the class shows on no line (a relay Shelly shows
    as a light), each holding its class. None for a test that named neither (a format 1 record's, a manual row's on an
    integration that names no classes)."""
    found = []
    lines = [line for held in lines for line in (held.children or [held])]
    for cls, domain in tested.places:
        item = (cls, domain) if classed else (domain, None)
        if item[0] is None:
            continue
        on = [line for line in lines if item in line.items] or (
            [line for line in lines if any(held == cls for held, _ in line.items)] if classed else []
        )
        found += [line for line in on if line not in found]
    return found


def brands(info) -> Brand:
    """The class's family (IntegrationInfo.families), else other brands; an integration with no families is one brand,
    its devices.yaml "Other brands" section the other brands."""
    families = getattr(info, "families", ())
    by_class = {cls: family.key.lower() for family in families for cls in family.classes}

    def brand(cls: str, section: str | None) -> tuple[int, str]:
        if families:
            return (0, by_class[cls]) if cls in by_class else (1, "")
        return (1, "") if section == OTHER_BRANDS else (0, "")

    return brand


def ordered(lines: list[Line], brand: Brand, rig: set[str]) -> list[Line]:
    """Native groups first, then lines by brand (`brands`), alphabetically, then other
    brands, then models no class line takes. Within a brand, lines with a rig-tested model first, those named
    "other …" last, the rest alphabetically; a line's sections and their phrases, and a parent's children, sort the
    same way, except that plain words come before maker strings ("_TZ3000_…")."""

    def name_key(name: str) -> tuple:
        return (name.lower().startswith("other"), name.startswith("_"), name.lower())

    def brand_of(line: Line, items: list[Item]) -> tuple:
        return min((brand(cls, line.at.get((cls, domain))) for cls, domain in items), default=(0, ""))

    def key(line: Line) -> tuple:
        if line.label is not None:
            group = (-1, "") if line.models == [] else (2, "")  # native groups, or models no class line takes
        else:
            group = brand_of(line, line.items)
        held = {name for child in (line.children or [line]) for name in child.models}
        return (*group, not held & rig, *name_key(line.plain()))

    for line in lines:
        line.children = ordered(line.children, brand, rig)
        if line.note is None and line.label is None:
            for phrases in line.sections.values():
                phrases.sort(key=name_key)
            line.sections = dict(
                sorted(
                    line.sections.items(),
                    key=lambda pair: (
                        *brand_of(line, [item for item in line.items if line.at.get(item) == pair[0]]),
                        *name_key(text(pair[1])),
                    ),
                )
            )
    return sorted(lines, key=key)


@dataclass
class Card:
    title: str
    requires: str | None = None
    url: str | None = None  # the integration's page
    maintainers: tuple[str, ...] = ()
    # 🔧 Untested fix, then ⚠️ Unmaintained entries: the features of the adapters so marked, by reason.
    marks: list[str] = field(default_factory=list)
    # Every adapter is unmaintained, so the heading says so.
    all_unmaintained: bool = False
    lines: list[str] = field(default_factory=list)
    # What the evidence tested, as the lines name it: each model (✔ when the rig tested it), then native groups.
    tested: list[str] = field(default_factory=list)

    def short(self, name: str) -> str:
        """The name without the integration's, which the card's title already gives: "Hue Bridge v1" -> "Bridge v1"."""
        return name.removeprefix(f"{self.title} ")

    def model(self, name: str, key: str, data: Data, rig: set[str]) -> str:
        by_name = {model["name"]: model for model in data.models.values()}
        return anchor(self.short(name), data.url(key, by_name[name]["section"])) + (
            f" {VERIFIED}" if name in rig else ""
        )

    def render(self) -> str:
        requires = f" ({self.requires})" if self.requires else ""
        title = f"[{self.title}]({self.url})" if self.url else self.title
        status = " · ⚠️ Unmaintained" if self.all_unmaintained else ""
        lines = [f"**{title}**{requires}{status}", ""]
        lines += [f"- {entry}" for entry in self.marks]
        lines += [f"- {line}" for line in self.lines]
        return "\n".join(lines)


def mark_entries(integration_adapters: list) -> list[str]:
    """The adapters shipping a fix no one could test, then those no one is fixing, as their features, one entry per
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
        url=f"{DOCS_URL}{page(key)}" if key in data.pages else None,
        maintainers=info.maintainers,
        marks=mark_entries(integration_adapters),
        all_unmaintained=bool(integration_adapters)
        and all(caveat_reason(adapter.scope, CaveatKind.UNMAINTAINED) for adapter in integration_adapters),
    )
    broken = {
        name: {"phrase": result.short(entry.what), "section": entry.what}
        for adapter in integration_adapters
        for name, entry in adapter.scope.no_known_method.items()
    }
    # The domains the integration's adapters serve, in first-seen order: those a class's line is split by.
    served = list(dict.fromkeys(domain for adapter in integration_adapters for domain in adapter.scope.domains))
    brand = brands(info)
    lines = class_lines(key, statuses(integration_adapters, info.classes), data, info.classes, served, broken, brand)
    models, groups = works(integration_adapters, data)
    rig = {name for name, tested in models.items() if tested.rig}
    # A model no class line takes gets a line of its own per feature set, with the features it was tested on.
    unplaced: dict[Shape, Line] = {}
    for name, tested in models.items():
        on = place(lines, tested, bool(info.classes))
        if not on:
            found_shape = shape({"works": tested.actions})
            on = [unplaced.setdefault(found_shape, Line(found_shape))]
        for line in on:
            line.models.append(name)
    for line in unplaced.values():
        line.label = ", ".join(result.model(name, key, data, rig) for name in line.models)
    extra = list(unplaced.values())
    result.tested = [result.model(name, key, data, rig) for name in models]
    if groups is not None:
        label = anchor(GROUPS_ENTRY[0], data.url(key, GROUPS_ENTRY[1])) + (f" {VERIFIED}" if groups.rig else "")
        extra.append(Line(shape({"works": groups.actions}), label=label))
        result.tested.append(label)
    lines = ordered([*lines, *extra], brand, rig)
    result.lines = [line.render(result, key, data, rig) for line in lines]
    # devices.yaml's and models.yaml's no_known_method entries name no class or action: each a line of its own.
    result.lines += [
        f"{anchor(result.short(entry['what']), data.url(key, entry['section']))}: {OUTCOMES[-1][1]}"
        for entry in data.no_known_method
        if key in entry["integrations"] and not entry.get("actions")
    ]
    return result


def legend(text: str) -> str:
    """The legend's entries for the marks the cards use, one per line. Verified qualifies works, so it shares its
    line."""
    lines: list[str] = []
    for icon, entry in LEGEND:
        if icon not in text:
            continue
        if icon == VERIFIED and lines and lines[-1].startswith(OUTCOMES[0][1]):
            lines[-1] += f" · {icon} {entry}"
        else:
            lines.append(f"{icon} {entry}")
    return "<br>\n".join(lines)


def cards(registry: AdapterRegistry, data: Data) -> str:
    body = []
    for key, integration_adapters in by_integration(registry).items():
        body += [card(key, registry, integration_adapters, data).render(), ""]
    parts = [
        CARDS[0],
        "<!-- Generated by scripts/gen_compat.py. Do not edit; run the script. -->",
        "",
        "<details>",
        f"<summary><b>{CARDS_TITLE}</b></summary>",
        "",
        legend("\n".join(body)),
        "",
        *body,
        f"Details per integration are in [docs/integrations.md]({INTEGRATIONS_URL}).",
        "",
        "</details>",
        "",
        CARDS[1],
    ]
    return "\n".join(parts)


def requirements(registry: AdapterRegistry, data: Data) -> str:
    """The README's Requirements line: each integration's `requirements_name` or title, in `column_order`, no "or"."""
    names = [
        data.names.get(key, info.title)
        for key, info in sorted(registry.integrations.items(), key=lambda item: data.order.get(item[0], 0))
        if key in data.order
    ]
    return "\n".join(
        [
            REQUIREMENTS[0],
            "<!-- Generated by scripts/gen_compat.py. Do not edit; run the script. -->",
            f"* One of these integrations installed: {', '.join(names)}.",
            REQUIREMENTS[1],
        ]
    )


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
    for path, markers, block in (
        (page, EVIDENCE, evidence(registry, data)),
        (readme, CARDS, cards(registry, data)),
        (readme, REQUIREMENTS, requirements(registry, data)),
    ):
        text = updates[path][1] if path in updates else path.read_text()
        updates[path] = (updates[path][0] if path in updates else text, splice(text, markers, block, path.name))
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
