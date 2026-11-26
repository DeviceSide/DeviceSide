#!/usr/bin/env python3
"""Generate the README's device table, the generated block of docs/device-compatibility.md and the integration links in
docs/integrations.md's intro, from the test records,
the adapters' scopes, docs/models.yaml and each integration's bundle, docs/integrations/<integration>/. The rules
the cards show (levels, caveats) are in docs/evidence.md.

**Evidence** for an action is its passing test records (`<action>.json`, `<action>-<option>.json`, read by check_release
against docs/test-records.schema.json) and the `_manual.json` rows naming it (`check_release.row_actions`: a format 3
row's `calls`, a format 2 row's `passed`). A format 2 or 3 record gives each passing test's devices, each a model with
its firmware and the class it reached (and its manufacturer, which the cards don't show yet); a native group's or a
scene's test (`group`, its devices the members) shows as "group", never as its members' models. Where the integration
names classes, a device with a null class credits nothing, flagged or not, and a group with one none either: it is on no
card and no row. A format 1 record (converted from markdown) gives the run's devices, not which test reached which, and
its tests the classes they reached, if it recorded them. A manual row's devices are model ids, each with its class
(and its firmware, where given); with `group`, a native group's members, which show as "group, by hand". A row with
`reports` shows as "by report", linking the issues, in place of "by hand". A level comes from the scope alone (verify,
then trust): a record never ages.

**Cards.** One collapsed section between the README's devices markers: the legend, of the marks the cards use (the
three marks' entries are coverage.LEGEND's, as the Settings view words them), then a card per integration, then a link
to the compatibility page, for models, and one to the integrations page. The cards answer "will it work with my
devices?" by class: a line names its classes, never a tested model (the page lists each, with how it was
tested), and shows no ✔ and no 🔴 (the page's matrix and Not supported table hold the refusals).
A card has its name, linked to its page (the bundle's index.md), with "⚠️ Unmaintained" when every adapter is; the
features of the adapters with each `caveat` (🔧 Untested fix, then ⚠️ Unmaintained, linking its reason); then a line per
feature set, naming each class on one line, with its features by status: "Hue lights: 🟢 turn on with timer · ⚪ get
attributes". Only classes of one brand share a line (`brand`): the class's family, else other brands; an integration
with no families is one brand, its "Other brands" section the other brands. Native groups sort first, then lines by
brand, alphabetically, then other brands, then models no class line takes; within a brand, tested lines first, "other …"
lines last, the rest alphabetically, and a line's names sort the same way (`ordered`), a variant's plain words before
its maker strings.
- Statuses: a class counts on each entity domain it can be (`IntegrationInfo.classes`) that the adapter serves, at the
  level a call there runs at (AdapterScope.level): 🟢 Verified, 🟡 Documented, ⚪ Labs; 🔴 for a scope's
  `no_known_method` entry, which names a class devices.yaml gives no phrase by its `what`, on the page's matrix
  alone: a card drops a 🔴 part, and a line left with only 🔴. A feature whose actions
  differ in status names its parts ("🟡 smooth dimming down · ⚪ smooth dimming up"), so none shows twice. A feature not
  built yet on a class (in no scope, or a `not_built` entry) is left out, and a class with nothing left has no line.
  Where the integration names no classes, its domains stand in for them.
- Names: the class's devices.yaml phrase; one whose domains show different features is named per domain, by its
  `domains` phrases, so a plug never lists dimming. A scene domain is never one of them: a scene is classed by its
  lights, so its features join the class's light line ("set scene"); a class of scenes alone keeps its own.
  Classes of one page section share a link, and a line holding every class its section shows in its domains names
  the section instead, by its devices.yaml `sections` phrase.
- Variants: a section with `variants` (a model whose classes its page tells apart) is a parent line, "Tuya TS011F
  plugs: check Manufacturer …", with a child line per feature set of its classes, named by their phrases ("a, b, or
  c"). Children never merge with another section's classes.
- Tested models follow the line of the class and domain a test reached them on (else of their class; else, from a format
  1 record or a manual row naming none, a line of their own with the features tested), and native groups get a line,
  with the features a test reached them on. On a card only the model lines no class takes, and native groups, name them
  (unmarked); the page's matrix names each line's models, rig-tested ones ending ✔. A pass on a flagged item never
  credits a model: an adapter flagged whole, or on any field, credits none, nor does a class with fields in Labs on it
  alone (`class_labs`), as a record doesn't say which fields a test sent. One flagged on a domain or class credits, from
  a format 2 record, each model a passing test reached on an unflagged domain and, with a class flagged, an unflagged
  class (a null one is none), and native groups when every member's class is unflagged; from a format 1 record, which
  doesn't say which test reached which model, the run's models only when every passing test targets an unflagged
  domain and, with a class flagged, names unflagged classes only; and, unless a domain is flagged (a manual row names
  none), each `_manual.json` model whose class is unflagged.
- devices.yaml's and models.yaml's `no_known_method` entries, which name no class, are on no card (the page's matrix
  has each as a 🔴 line), nor are models.yaml's `not_built` ones. The page's Not supported table lists both, and the
  scopes' `not_built` entries, with why and the source.
A model drops the integration's name where it leads, as the card's name already gives it. Cards show
features, not fields: a flagged or Documented field shows on the integration's page and in the page's footnote only.

**The model.** `card` builds each card's model before anything is folded or rendered: `Card.entries`, the ordered,
unfolded `Line`s (class phrases and page sections, items with their domains, a variant's `parent`, `features` for
per-feature status with `stop` in its own column, `models` the tested models), `Card.reached` (each tested model's
places and actions, and per action its `Proof`: record paths, firmware, rig and by hand, each kept when both
tested it), `Card.refused`, `Card.broken` (a refused class's Not supported row), `Card.field_notes` and `Card.marks`
(the caveats). `show` renders the README's lines from it, folding last, so another render (the page's matrix) reads
the same unfolded lines, with their 🔴 parts and models.

**The fold** (docs/evidence.md, The Labs flag). A card's top-level lines that show only ⚪ (a 🔴 beside it is
dropped, as on every card line) fold, when there are two or more, into one last line, "⚪ [class] (features);
[class], [class] (features)": classes with the same features share a parenthesis, and a variants parent's children
never fold.

**The page.** The block between the evidence markers of docs/device-compatibility.md, in three parts; every device fact
in it comes from the model above, so one change in code, devices.yaml, models.yaml or a record moves the README and the
page together, and `--check` proves both.
  - *Tested devices*: a `###` per model a record row names, credited to a card or not (a hand-tested model in a Labs
  class is listed; the matrix's levels are the code's alone), headed by its `section` (its `name` by default: the
  heading every card links, `Data.model_url`), with its type and ids, then a table of Integration (linking its matrix
  below), Features tested (each linking its records, a split feature's parts apart, in the feature table's
  order), Firmware (the distinct values the records name) and How (✔ rig, by hand, by report). Then
  `### Native groups`, the same table per integration without the firmware.
- *By integration*: a `###` per integration, by its title, the card's caveats under it, then a matrix: a row per
  unfolded card line (native groups first, a variants parent's children indented under it), a column per feature in the
  feature table's order (`stop` last), a cell holding the status and its proof. 🟢 links its records (the line's tested
  models'; where none tested the action on the line, the integration's, as a scene is classed by its lights), 🟡 and ⚪
  the class's section on its integration's page, 🔴 its row under Not supported; a split feature shows its parts ("🟢
  down · ⚪ up"). Under the matrix, a footnote lists each field proven less than its feature (a field whose level is
  weaker than the strongest its action's domains and classes hold), then each field in Labs on some classes alone
  (`class_labs`), naming them by their devices.yaml phrases.
- *Not supported*: every integration's `no_known_method` and harmful `not_built` entries in one table (Devices,
  Integrations, Features, Why, Source), one row per (what, reason, source) with its integrations and actions joined; a
  no known method row has an anchor id, the heading anchor of its `section`, which a matrix cell and a card's blocker
  line link, numbered where two rows share one.
Every model a test-records file names must be in docs/models.yaml or its bundle's devices.yaml, whatever its test's
result (`check_models`). The prose outside the evidence markers is hand-written and kept as written.

**The coverage check** (`check_release.coverage_gaps`, docs/evidence.md) prints a warning per Verified class (on an
integration that names none, Verified domain) no record reaches on every run, `--check` included, and never fails
here: `check_release.py --signoffs` fails on it at the cut. It also warns (`check_release.default_class_credits`) of
each model a passing record or manual row credits in its integration's default class where that is in Labs: the pass
can never lift a flag, so the model needs a class of its own; this warning never fails anywhere.

**Data.** docs/models.yaml holds what integrations share: `models`, one entry per physical model (`name`, `ids` across
integrations, `type`, optional `section`: the model's heading on the generated page, its `name` by default; a model
only one integration names is in its bundle's devices.yaml), and `no_known_method` and `not_built` entries that name
their `integrations` (`what`, `reason`, `source`, optional `section`: the anchor id of its Not supported row, its
`what` by default), a `not_built` one for a device today's call harms on an integration that doesn't class it yet, as
an unharmed one needs no entry. Each bundle's devices.yaml holds its integration's: `models` (as above), `column` and
`column_order` (the feature table's, read by gen_features), `requires` (shown after the card's name),
`capabilities` (a `phrase` and `section` per class a card line names, or domain where the integration names no
classes, and per class a scope lists as not built yet; `section` is a heading of the integration's page, which a
Documented or Labs class must have; `domains`, a phrase per entity domain, for a class the card splits), `sections`
(optional: a `phrase`, and `domains`, per page section, for a line holding all its classes, or with `variants`, what
to check to tell its classes apart) and `no_known_method` (`what`, `reason`, `source`, optional `section`, as above:
devices that fail the call DeviceSide sends, not what isn't built). A scope's `no_known_method` (core/scope.py,
NoKnownMethod) and `not_built` (NotBuilt) are the code's home for these, and join them here; the devices.yaml and
models.yaml entries move to them, class by class. Every integration needs a bundle.

**Links.** A card links each class or blocker to the heading its `section` names (default: the blocker's `what`): on the
card's integration page when that has the heading, else the same anchor on docs/device-compatibility.md, where a Not
supported row (the blocker's) or a model's heading (a class that is one model's) answers to it. A model's or native
groups' heading is on that page alone, generated there, so a card always links it there. `check_sections` runs with
every generation and fails on a dead link: a 🟡 or ⚪ class whose section is not a heading of its integration's page;
any link of the generated block or the README's cards to a heading or anchor id of the block, to a heading of an
integration's page, or to a file under docs/ (a record, an integration page) that isn't there. The page's own links
are relative, the README's absolute (HACS renders it inside Home Assistant). An integration's page never states a
level, which only the matrix does: `check_headings` fails a heading that does, naming the file.

Usage: scripts/gen_compat.py [--check]

--check exits 1 when the README or the page differs from what this generates.
"""

import argparse
import copy
import re
import sys
from collections import Counter
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
from custom_components.deviceside.coverage import legend_entries  # noqa: E402
from scripts.check_release import (  # noqa: E402
    MANUAL,
    adapters,
    classed,
    coverage_gaps,
    default_class_credits,
    listed,
    names_classes,
    passing,
    record_class_errors,
    row_actions,
    test_records_dir,
)
from scripts.check_release import load as read_record  # noqa: E402
from scripts.check_release import manual as read_manual  # noqa: E402
from scripts.gen_codeowners import plain_title  # noqa: E402
from scripts.gen_features import FEATURES as TABLE_FEATURES  # noqa: E402
from scripts.gen_features import anchors, bundle, columns, integration_columns, page, slug  # noqa: E402

PAGE = REPO / "docs" / "device-compatibility.md"
README = REPO / "README.md"
MODELS = REPO / "docs" / "models.yaml"
INTEGRATIONS_PAGE = REPO / "docs" / "integrations.md"
# Absolute: HACS renders the README inside Home Assistant, where a relative link doesn't resolve.
PAGE_URL = f"{DOCS_URL}docs/device-compatibility.md"
CARDS = ("<!-- devices:start -->", "<!-- devices:end -->")
CARDS_TITLE = "View device compatibility by integration"
EVIDENCE = ("<!-- evidence:start -->", "<!-- evidence:end -->")
INTEGRATIONS = ("<!-- integrations:start -->", "<!-- integrations:end -->")

REPORT_URL = "https://github.com/DeviceSide/DeviceSide/issues/new?template=device_report.yml"

# Device types, in a card's order for a line's tested models.
TYPES = ("bulb", "relay", "plug", "dimmer", "LED controller")
# A line's statuses, in its order: (key, icon). Not built yet has none: a card leaves those out.
REFUSED = "no_known_method"
OUTCOMES = (
    ("works", "🟢"),
    ("should", "🟡"),
    ("labs", "⚪"),
    (REFUSED, "🔴"),
)
LABS = next(icon for key, icon in OUTCOMES if key == "labs")
TIER = {Level.VERIFIED: "works", Level.DOCUMENTED: "should", Level.LABS: "labs"}
VERIFIED = "✔"
UNMAINTAINED = "⚠️ Unmaintained"
UNTESTED_FIX = "🔧 Untested fix"
# The scope's caveats, as (kind, label), in a card's order.
MARKS = ((CaveatKind.UNTESTED_FIX, UNTESTED_FIX), (CaveatKind.UNMAINTAINED, UNMAINTAINED))
# Where the README's legend sends a reader to turn Labs on; the Settings view's says "below" (coverage.LABS_BELOW).
LABS_POINTER = "Turn on Labs in Configure > Settings to try it"
# The legend's entries beyond coverage.LEGEND's three marks, as (icon, text); `legend` lists only those a card uses.
CAVEATS = (
    ("🔧", f"untested fix: please try it and [report whether it works]({REPORT_URL})"),
    ("⚠️", "unmaintained: use at your own risk"),
)
GITHUB = "https://github.com/"
INTEGRATIONS_URL = "https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations.md"
# The keys each devices.yaml entry may hold, so a typo fails instead of being ignored.
SHARED_KEYS = {"models", "no_known_method", "not_built"}  # each a list
BUNDLE_KEYS = {
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
    """Each action's feature, as a card names it, in the feature table's order (gen_features.FEATURES). An
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

    def url(self, key: str, section: str) -> str:
        """A class's or blocker's section: its heading on the integration's page when that has it, else the same
        anchor on PAGE, where a blocker's Not supported row and a class that is a model's heading may answer to it.
        `check_sections` fails a link PAGE's generated block doesn't answer."""
        if (anchor := slug(section)) in self.pages.get(key, set()):
            return f"{DOCS_URL}{page(key)}#{anchor}"
        return f"{PAGE_URL}#{anchor}"

    def model_url(self, section: str) -> str:
        """A model's or native groups' heading, which is on PAGE alone (generated there)."""
        return f"{PAGE_URL}#{slug(section)}"


def fail(message: str) -> None:
    raise SystemExit(f"device data: {message}")


def load(registry: AdapterRegistry, models: Path = MODELS) -> Data:
    """docs/models.yaml and every integration's bundle: its devices.yaml merged in, its page's headings read and
    checked (`check_headings`)."""
    shared = yaml.safe_load(models.read_text()) or {}
    bundles = {key: bundle(key) for key in sorted(registry.integrations)}
    data = load_raw(merge(shared, bundles), registry)
    for key in bundles:
        if not (path := REPO / page(key)).is_file():
            raise SystemExit(f"no {page(key)}; add the {key} bundle's user page")
        text = path.read_text()
        check_headings(key, text)
        data.pages[key] = anchors(text)
    return data


# A heading that states a level. An integration's page gives each class's reasons under `## Device classes`; its
# levels are the generated page's alone, so a hand-written one can't go stale.
LEVEL_HEADING = re.compile(
    r"^#+ .*\b(Tested devices|Should work|Try it|Labs|Verified|Documented)\b.*$", re.MULTILINE | re.IGNORECASE
)


def check_headings(key: str, text: str) -> None:
    """Fail an integration page heading that states a level (`LEVEL_HEADING`), naming the file."""
    if found := [match.group(0) for match in LEVEL_HEADING.finditer(text)]:
        raise SystemExit(
            f"{page(key)}: {', '.join(repr(heading) for heading in found)} states a level; levels are"
            " docs/device-compatibility.md's alone, so give the class's reasons under ## Device classes"
        )


def merge(shared: dict, bundles: dict[str, dict]) -> dict:
    """The shared file and the bundles as one mapping, each bundle's entries named for its integration: a bundle's
    `no_known_method` entries are its own, so they take no `integrations` key."""
    need(shared, "docs/models.yaml", lists=tuple(sorted(SHARED_KEYS & set(shared))), keys=SHARED_KEYS)
    raw: dict = {
        "requires": {},
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
    data = Data(raw["requires"], {}, raw["capabilities"], [])
    for model in raw["models"]:
        load_model(model, data, None)
    for key, models in raw.get("bundle_models", {}).items():
        for model in models:
            load_model(model, data, key)
    for key, items in data.capabilities.items():
        need(items, f"capabilities {key}")
        for item, entry in items.items():
            need(entry, f"capabilities {key} {item}", ("phrase", "section"), keys=CLASS_KEYS)
            if "domains" in entry:
                need(entry["domains"], f"capabilities {key} {item} domains", tuple(entry["domains"]))
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
    its class's devices.yaml phrase (an entry on some domains alone, by its phrases for them), with the actions whose
    adapters list it, for the Not supported table, which keeps the harm's source: the card leaves the class's feature
    out, as it does any not built yet. One per class, reason and source."""
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
            if entry.domains is not None:  # refused on some domains alone: named by their phrases ("Hue smart plugs")
                phrases = data.capabilities[key][name].get("domains") or {}
                if missing := sorted(entry.domains - phrases.keys()):
                    fail(f"capabilities: {key} {name} needs a phrase for {', '.join(missing)}, where it is not built")
                what = ", ".join(phrases[domain] for domain in sorted(entry.domains))
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
    getattr(data, kind).append({**entry, "actions": actions} if actions else entry)


@dataclass(frozen=True)
class Tested:
    """A device the evidence tested: its model with its firmware and the class it reached (None: none named), or a
    native group (no model). `rig` for a record's; a manual row's has firmware only where the row gives it, and
    `reports`, the issues it rests on, where it has them. `domain` is the domain a format 2 test targeted; a format 1
    record and a manual row name none per device."""

    model: str | None
    firmware: str | None = None
    cls: str | None = None
    rig: bool = True
    domain: str | None = None
    reports: tuple[str, ...] = ()

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
    def of(
        cls,
        adapter,
        clean: Clean | None = None,
        by_hand: Callable[[str | None], bool] | None = None,
        listed: bool = False,
    ) -> Evidence:
        """The adapter's evidence: with `clean`, only the record tests it accepts; with `by_hand`, only the manual
        devices whose class it accepts (a group row, only when it accepts every member's). Where the integration names
        classes (`names_classes`), a device with a null class credits nothing, flagged or not (docs/evidence.md, The
        coverage check), so it is left out, as is a group with such a member. A manual group row is one group, tested
        by hand. `listed` keeps a null-class device and group too: the page lists every model a record row names,
        credited or not."""
        names = names_classes(adapter) and not listed
        records = passing(adapter.integration, adapter.action)
        found = [
            (path.relative_to(REPO).as_posix(), item)
            for path in records
            for item in tested(read_record(path), clean, names)
        ]
        for row in read_manual(adapter.integration):
            if adapter.action not in row_actions(row):
                continue
            reports = tuple(row.get("reports", ()))
            classes = [device["class"] for device in row["devices"]]
            if row.get("group"):
                # Judged as a rig group test is: a member the integration can't credit, or `by_hand` refuses, drops it.
                if not (names and None in classes) and (by_hand is None or all(map(by_hand, classes))):
                    found.append((MANUAL, Tested(None, rig=False, reports=reports)))
                continue
            found += [
                (MANUAL, Tested(device["model"], device.get("firmware"), device["class"], rig=False, reports=reports))
                for device in row["devices"]
                if not (names and device["class"] is None) and (by_hand is None or by_hand(device["class"]))
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
    unflagged in some domain the adapter serves, as the coverage check lets a manual row cover any. A class with fields
    in Labs on it (`class_labs`) counts as flagged, as a record doesn't say which fields a test sent. Flagged or not, a
    null-class device of an integration that names classes counts for nothing (`Evidence.of`)."""
    scope = adapter.scope
    flagged = {noun for level, _, noun, domains in items(scope) if level is Level.LABS or domains is not None}
    flagged |= {"classes"} if scope.class_labs else set()
    if scope.all_labs or "fields" in flagged:
        return Evidence([], [])
    if not flagged:
        return Evidence.of(adapter)
    domains = {domain for domain, level in scope.domains.items() if level is not Level.LABS}

    def unflagged(cls: str | None, domain: str) -> bool:
        return (
            cls is not None
            and cls in (scope.capabilities or {})
            and cls not in scope.class_labs
            and scope.class_level(cls, domain) is not Level.LABS
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
    """The scope's items, as (level, item, noun, domains), domains first: all in Labs in an adapter flagged whole.
    `domains` names those a class's level holds on alone (core/scope.py, OnDomains), else None."""
    entries = [(level, item, "entities", None) for item, level in scope.domains.items()]
    entries += [(level, item, "classes", domains) for item, level, domains in scope.class_entries()]
    entries += [(level, item, "fields", None) for item, level in scope.fields.items()]
    return [(Level.LABS if scope.all_labs else level, *rest) for level, *rest in entries]


# The page.


def by_integration(registry: AdapterRegistry) -> dict[str, list]:
    """The adapters per integration, in the feature table's column order, so the cards read across as it does."""
    grouped: dict[str, list] = {}
    for _, adapter in adapters(registry):
        grouped.setdefault(adapter.integration, []).append(adapter)
    return {key: sorted(grouped[key], key=lambda a: a.action) for key in columns(grouped)}


def doc_link(path: str) -> str:
    """A repo path as the page links it: relative to docs/."""
    return path.removeprefix("docs/")


def is_report(path: str) -> bool:
    """A proof that is a user's report (its issue URL, from a manual row's `reports`), not a records file."""
    return path.startswith("https://")


def report_links(urls: list[str]) -> str:
    """The words "by report" linking the one issue, or followed by each issue's number linking it."""
    if len(urls) == 1:
        return f"[by report]({urls[0]})"
    return "by report " + " ".join(f"[#{url.rsplit('/', 1)[1]}]({url})" for url in urls)


def caveat_reason(scope, kind: CaveatKind) -> str | None:
    """The reason of the scope's caveat when it is of that kind, else None."""
    return scope.caveat.reason if scope.caveat is not None and scope.caveat.kind is kind else None


def marked(label: str, reason: str) -> str:
    """A mark (⚠️ Unmaintained, 🔧 Untested fix), linking its reason when that is a URL, else giving it in brackets."""
    return f"[{label}]({reason})" if reason.startswith("https://") else f"{label} ({reason})"


def cell(text: str) -> str:
    """Text for a table cell: a pipe would start another column."""
    return text.replace("|", "\\|")


def table_row(cells: list[str]) -> str:
    return "|" + "|".join(f" {text} " if text else " " for text in cells) + "|"


def table(header: list[str], rows: list[list[str]]) -> list[str]:
    return [table_row(header), "|" + "---|" * len(header), *(table_row(row) for row in rows)]


def suffix(action: str) -> str:
    """What tells an action's record apart from its feature's others: "up" (raise_brightness), "auto-off"."""
    label = part(action)
    if label.startswith(FEATURES[action]):
        return label.removeprefix(FEATURES[action]).strip()
    return label if action.endswith(("_auto_off", "_auto_on")) else ""


def record_links(pairs: list[tuple[str, str]], *, part_named: bool = False) -> str:
    """Links to the records (action, repo path) that prove a feature: "record" for one, else the part and option each
    is for ("up", "down predicted state"), the action's words where those collide (`part_named`: the cell already
    names the part, so the options alone); every manual row of one file is one "by hand" link, and the reports rows rest
    on are "by report"."""
    pairs = list(dict.fromkeys(pairs))
    manual = [path for _, path in pairs if path.endswith(f"/{MANUAL}")]
    reports = list(dict.fromkeys(path for _, path in pairs if is_report(path)))
    rigged = [(action, path) for action, path in pairs if not path.endswith(f"/{MANUAL}") and not is_report(path)]

    def option(action: str, path: str) -> str:
        return Path(path).stem.removeprefix(action).lstrip("-").replace("_", " ")

    names = [
        " ".join(filter(None, [suffix(action) if not part_named else "", option(action, path)])) or "record"
        for action, path in rigged
    ]
    if len(set(names)) != len(names):
        names = [" ".join(filter(None, [action.replace("_", " "), option(action, path)])) for action, path in rigged]
    links = [f"[{name}]({doc_link(path)})" for name, (_, path) in zip(names, rigged, strict=True)]
    links += [f"[by hand]({doc_link(path)})" for path in dict.fromkeys(manual)]
    links += [report_links(reports)] if reports else []
    return " ".join(links)


def feature_actions(feature: str, label: str) -> list[str]:
    """The actions a (feature, label) pair of `Line.features` stands for: all the feature's, or the one part's."""
    return [
        action for action in FEATURES if FEATURES[action] == feature and (label == feature or label == part(action))
    ]


def proofs(held: list[Reached], actions: list[str]) -> list[tuple[str, str]]:
    """The (action, record path) pairs that proved these actions on the tested models `held`."""
    return [
        (action, path)
        for action in actions
        for reached in held
        if action in reached.by_action
        for path in reached.by_action[action].records
    ]


def line_proof(card: Card, line: Line) -> list[Reached]:
    """What the evidence tested on the line: native groups, or its tested models."""
    if line.native:
        return [card.groups] if card.groups else []
    return [card.reached[name] for name in line.models if name in card.reached]


def part_text(feature: str, label: str) -> str:
    """A split feature's part as a cell names it: "down" for "smooth dimming down"."""
    return "" if label == feature else label.removeprefix(feature).strip()


def status_cell(
    card: Card, line: Line, feature: str, data: Data, ids: dict[tuple[str, str, str], str], icons: dict[str, str]
) -> str:
    """The line's marks for a feature, each linking its proof (docs/plans, Decision 5): 🟢 its records, 🟡 and ⚪ the
    class's page section, 🔴 its row under Not supported."""
    held = line_proof(card, line)
    found = []
    everything = [*card.reached.values(), *([card.groups] if card.groups else [])]
    for status, label in line.features.get(feature, ()):
        text = f"{icons[status]} {part_text(feature, label)}".strip()
        if status == "works":
            actions = feature_actions(feature, label)
            # A class with no model of its own on the action (a scene is classed by its lights) takes the integration's.
            links = record_links(proofs(held, actions) or proofs(everything, actions), part_named=label != feature)
        elif status == REFUSED:
            refused = [
                card.broken[(name, action)]
                for name, _ in line.items
                for action in feature_actions(feature, label)
                if (name, action) in card.broken
            ]
            links = f"[why](#{ids[refused[0]]})" if refused and refused[0] in ids else ""
        else:
            # A line of several sections (Shelly's dimmers, LED controllers) links the first: the Class column has all.
            links = f"[why]({data.url(card.key, next(iter(line.sections)))})"
        found.append(f"{text} {links}".strip())
    return " · ".join(found)


def local(text: str) -> str:
    """The page's own links as relative ones, which a reader of the page and GitHub's file view both resolve."""
    return text.replace(f"({PAGE_URL}#", "(#").replace(f"({DOCS_URL}docs/", "(")


def matrix_rows(card: Card, columns: list[str], data: Data, ids: dict, icons: dict[str, str]) -> list[list[str]]:
    """A row per unfolded card line: its name, then a cell per feature; a variants parent's children under it."""
    rows = []
    rig = card.rig
    blank = [""] * len(columns)
    for entry in card.entries:
        if entry.note is not None:
            rows.append([cell(f"{entry.name(card, card.key, data, rig)}: {entry.note}"), *blank])
        for line in entry.children or ([] if entry.note is not None else [entry]):
            name = line.name(card, card.key, data, rig)
            cells = [status_cell(card, line, feature, data, ids, icons) for feature in columns]
            rows.append([cell(("&emsp;" if entry.note is not None else "") + name), *(cell(x) for x in cells)])
    for entry in card.refused:
        key = (entry["what"], entry["reason"], entry["source"])
        link = f"{icons[REFUSED]} [why](#{ids[key]})" if key in ids else icons[REFUSED]
        name = anchor(card.short(entry["what"]), data.url(card.key, entry["section"]))
        rows.append([cell(name), *[link] * len(columns)])
    return rows


def matrix(card: Card, data: Data, ids: dict) -> list[str]:
    """The integration's class by feature matrix, with its caveats above and its fields' footnote below."""
    icons = dict(OUTCOMES)
    columns: Features = {}
    for entry in card.entries:
        for line in (entry, *entry.children):
            columns = join_features(columns, line.features)
    names = list(columns)
    parts = [f"### {card.title}", ""]
    parts += [f"- {mark.render()}" for mark in card.marks]
    parts += [""] if card.marks else []
    parts += [local(row) for row in table(["Class", *names], matrix_rows(card, names, data, ids, icons))]
    if card.field_notes:
        parts += ["", "Fields proven less than their feature:"]
        for feature, status, fields, classes in card.field_notes:
            names = ", ".join(f"`{name}`" for name in fields)
            parts.append(local(f"- {feature}: {icons[status]} {names}{on_classes(card, data, classes)}"))
    return [*parts, ""]


def on_classes(card: Card, data: Data, classes: tuple[str, ...]) -> str:
    """Where a footnote's fields are in Labs alone: " on " and the classes' devices.yaml phrases, by section, as a
    card line names them (`merged`); nothing for a field at its level on every class."""
    if not classes:
        return ""
    sections: dict[str, list[str]] = {}
    for cls in classes:
        if (entry := data.capabilities.get(card.key, {}).get(cls)) is None:
            fail(f"capabilities: no entry for {card.key} {cls}, which the page's footnote names")
        phrases = sections.setdefault(entry["section"], [])
        phrases += [entry["phrase"]] if entry["phrase"] not in phrases else []
    return " on " + ", ".join(merged(phrases, data.url(card.key, section)) for section, phrases in sections.items())


def tested_features(held: Reached) -> str:
    """The features a model (or native groups) was tested on, in the feature table's order, each with its records."""
    by_feature: dict[str, list[str]] = {}
    for action in sorted(held.by_action, key=list(FEATURES).index):
        by_feature.setdefault(FEATURES[action], []).append(action)
    order = {feature: number for number, feature in enumerate(dict.fromkeys(FEATURES.values()))}
    found = []
    for feature in sorted(by_feature, key=order.get):
        pairs = proofs([held], by_feature[feature])
        links = record_links(pairs)
        found.append(
            f"[{feature}]({links[links.index('(') + 1 : links.index(')')]})"
            if links.count("](") == 1
            else f"{feature}: {links}"
        )
    return "<br>".join(found)


def how(held: Reached) -> str:
    reports = [report_links(held.reports)] if held.reports else []
    return ", ".join([*([f"{VERIFIED} rig"] if held.rig else []), *(["by hand"] if held.by_hand else []), *reports])


def firmware(held: Reached) -> str:
    seen = list(dict.fromkeys(value for proof in held.by_action.values() for value in proof.firmware))
    return "<br>".join(f"`{value}`" for value in seen)


def devices_section(built: list[Card], data: Data) -> list[str]:
    """A `###` per model a record row names, credited or not (`Card.listed`; by its `section`: the heading every card
    links), a table of the integrations and features that tested it; then native groups the same way. The matrix's
    levels stay as the code sets them: a model a flagged class holds is listed here and credits nothing there."""
    by_model: dict[str, list[tuple[Card, Reached]]] = {}
    for card in built:
        for name, held in card.listed.items():
            by_model.setdefault(name, []).append((card, held))
    by_name = {model["name"]: model for model in data.models.values()}
    parts = ["## Tested devices", ""]
    for name in sorted(by_model, key=lambda name: TYPES.index(by_name[name]["type"])):
        model = by_name[name]
        ids = ", ".join(f"`{model_id}`" for model_id in model["ids"])
        parts += [f"### {model['section']}", "", f"{model['type'].capitalize()}. Model IDs: {ids}.", ""]
        rows = [
            [
                f"[{card.title}](#{slug(card.title)})",
                tested_features(held),
                firmware(held),
                how(held),
            ]
            for card, held in by_model[name]
        ]
        parts += [*table(["Integration", "Features tested", "Firmware", "How"], rows), ""]
    parts += [f"### {GROUPS_ENTRY[1]}", ""]
    if grouped := [(card, card.listed_groups) for card in built if card.listed_groups]:
        rows = [[f"[{card.title}](#{slug(card.title)})", tested_features(held), how(held)] for card, held in grouped]
        parts += [*table(["Integration", "Features tested", "How"], rows), ""]
    else:
        parts += ["No native group has been tested yet.", ""]
    return parts


@dataclass
class Refusal:
    """A Not supported row: devices DeviceSide refuses, on the integrations and for the features that name them."""

    what: str
    reason: str
    source: str
    section: str
    integrations: list[str] = field(default_factory=list)
    actions: set[str] = field(default_factory=set)
    refused: bool = True  # no known method (a matrix cell links it); else not built yet, harmed by today's call
    id: str | None = None


def refusals(registry: AdapterRegistry, data: Data, built: list[Card]) -> list[Refusal]:
    """The no_known_method and harmful not_built entries of every integration, merged: one row per (what, reason,
    source), its integrations and actions joined, sorted by name. A no known method row has an anchor id, the
    heading anchor of its `section`, numbered when two rows share one."""
    rows: dict[tuple[str, str, str], Refusal] = {}

    def add(entry: dict, keys: list[str], refused: bool) -> None:
        key = (entry["what"], entry["reason"], entry["source"])
        row = rows.setdefault(key, Refusal(*key, entry["section"] if refused else entry["what"], refused=refused))
        row.integrations += [found for found in keys if found not in row.integrations]
        row.actions |= set(entry.get("actions") or ())

    for entry in data.no_known_method:
        add(entry, entry["integrations"], True)
    for entry in data.not_built:
        add(entry, entry["integrations"], False)
    for key, integration_adapters in by_integration(registry).items():
        for entry in code_unbuilt(key, integration_adapters, data):
            add({**entry, "section": entry["what"]}, [key], False)
    order = [card.key for card in built]
    found = sorted(rows.values(), key=lambda row: row.what.lower())
    taken: Counter[str] = Counter()
    for row in found:
        row.integrations.sort(key=lambda key: order.index(key) if key in order else len(order))
        if row.refused:
            base = slug(row.section)
            row.id = f"{base}-{taken[base]}" if taken[base] else base
            taken[base] += 1
    return found


def not_supported(rows: list[Refusal], registry: AdapterRegistry) -> list[str]:
    """The merged table: devices, integrations, features, why and source."""
    body = [
        [
            (f'<a id="{row.id}"></a>' if row.id else "") + cell(row.what),
            ", ".join(registry.integrations[key].title for key in row.integrations),
            ", ".join(features(row.actions, fold_stop=False)) if row.actions else "",
            cell(row.reason),
            f"[source]({row.source})",
        ]
        for row in rows
    ]
    return ["## Not supported", "", *table(["Devices", "Integrations", "Features", "Why", "Source"], body), ""]


def evidence(registry: AdapterRegistry, data: Data, built: list[Card] | None = None) -> str:
    """The page's generated block: tested devices, the matrix per integration, what is not supported."""
    built = card_list(registry, data) if built is None else built
    rows = refusals(registry, data, built)
    ids = {(row.what, row.reason, row.source): row.id for row in rows if row.id}
    parts = [
        EVIDENCE[0],
        "<!-- Generated by scripts/gen_compat.py from the bundles' records and devices.yaml, docs/models.yaml and the"
        " adapters' scopes. Do not edit; run the script. -->",
        "",
        *devices_section(built, data),
        "## By integration",
        "",
        "Each mark links its proof: 🟢 its records, 🟡 and ⚪ the class's section on its integration's page, 🔴 its row"
        " under [Not supported](#not-supported).",
        "",
    ]
    for card in built:
        parts += matrix(card, data, ids)
    parts += [*not_supported(rows, registry), EVIDENCE[1]]
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


# A card item: a class with one of the entity domains it can be, or, where the integration names no classes, a domain
# with None.
type Item = tuple[str, str | None]
# A line's features by status, in OUTCOMES order: (("works", ("turn on with timer",)), ("labs", (...))).
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


# The feature each part label (`part`) belongs to; a label that isn't one is its own feature.
PART_FEATURE = {part(action): FEATURES[action] for action in FEATURES}


# A line's features with their statuses, `stop` included: {feature: ((status, label), ...)}, in the feature table's
# order.
type Features = dict[str, tuple[tuple[str, str], ...]]


def labelled(by_status: dict[str, set[str]]) -> dict[str, tuple[str, ...]]:
    """The actions by status as labels, each feature under one status: one whose actions differ names its parts
    instead ("🟡 smooth dimming down · ⚪ smooth dimming up"). `stop` is named wherever it is."""
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
    return labels


def feature_statuses(by_status: dict[str, set[str]]) -> Features:
    """Each feature the actions hold with its status, one (status, label) pair per part for a split feature, and `stop`
    with its own status beside the others (the README line folds it; a matrix column of its own doesn't)."""
    found: dict[str, list[tuple[str, str]]] = {}
    for status, labels in labelled(by_status).items():
        for label in labels:
            found.setdefault(PART_FEATURE.get(label, label), []).append((status, label))
    return join_features({}, {feature: tuple(pairs) for feature, pairs in found.items()})


def join_features(into: Features, more: Features) -> Features:
    """`into` with `more`'s pairs added where it lacks them, in the feature table's order (then unlisted actions')."""
    joined = {feature: list(pairs) for feature, pairs in into.items()}
    for feature, pairs in more.items():
        have = joined.setdefault(feature, [])
        have += [pair for pair in pairs if pair not in have]
    order = list(dict.fromkeys(FEATURES.values()))
    rank = {feature: i for i, feature in enumerate(order)}
    return {feature: tuple(joined[feature]) for feature in sorted(joined, key=lambda x: rank.get(x, len(order)))}


def shape(by_status: dict[str, set[str]]) -> Shape:
    """The actions by status as a line names them (`labelled`), except that `stop` rides the smooth moves, so it is
    named only on a line that names nothing else."""
    labels = labelled(by_status)
    every = [label for found in labels.values() for label in found]
    if set(every) - {"stop"}:
        labels = {status: tuple(label for label in found if label != "stop") for status, found in labels.items()}
    return tuple((key, labels[key]) for key, _ in OUTCOMES if labels.get(key))


def statuses(integration_adapters: list, class_domains: ClassDomains) -> dict[Item, dict[str, set[str]]]:
    """Each item the adapters serve, with its actions by status, in first-seen order. A class counts on each entity
    domain it can be (IntegrationInfo.classes) that the adapter serves, at the level a call there runs at
    (AdapterScope.level: the weaker of the domain and the class); a class in the scope's `no_known_method` has none
    there; one the scope names in neither (not built yet) is left out. An adapter flagged whole is in Labs
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
                        held.append(((name, domain), REFUSED))
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
    # child a variant, by its classes' phrases (the page adds ✔ for a rig-tested model, which the parent already names).
    note: str | None = None
    children: list[Line] = field(default_factory=list)
    variant: bool = False
    at: dict[Item, str] = field(default_factory=dict)  # each item's page section
    parent: Line | None = field(default=None, repr=False, compare=False)  # a variant's parent line
    # Per-feature status (OUTCOMES keys), `stop` included, unlike `shape`: "smooth dimming": (("should", "smooth dimming
    # down"), ("labs", "smooth dimming up")); a feature whose actions agree has one pair holding its own label.
    features: Features = field(default_factory=dict)
    native: bool = False  # the native groups' line, whose proof is the card's `groups`

    def plain(self) -> str:
        """The name as text, for sorting."""
        return (self.label or ", ".join(text(phrases) for phrases in self.sections.values())).lower()

    @property
    def claims(self) -> Shape:
        """The shape without the refused part: what the README shows, which has no 🔴."""
        return tuple(pair for pair in self.shape if pair[0] != REFUSED)

    def name(self, card: Card, key: str, data: Data, rig: set[str], readme: bool = False) -> str:
        """The line's name. The README's (`readme`) is the classes alone: no tested models and no ✔, and a model line
        no class takes (a label) keeps its models, unmarked."""
        if self.label is not None:
            if readme and not (self.native or not self.models):
                return ", ".join(card.model(name, key, data, set()) for name in self.models)
            return self.label.removesuffix(f" {VERIFIED}") if readme else self.label
        if self.variant:
            ((section, phrases),) = self.sections.items()
            # Variants read as either: "no countdown setting, _TZ3000_a, or _TZ3000_b".
            either = f"{', '.join(phrases[:-1])}, or {phrases[-1]}" if len(phrases) > 1 else phrases[0]
            return anchor(either, data.url(key, section)) + (
                f" {VERIFIED}" if set(self.models) & rig and not readme else ""
            )
        names = ", ".join(merged(phrases, data.url(key, section)) for section, phrases in self.sections.items())
        if readme:
            return names
        tested = [card.short(name) for name in self.models]
        if len(tested) == 1 and [tested[0]] == [p for phrases in self.sections.values() for p in phrases]:
            return names + (f" {VERIFIED}" if self.models[0] in rig else "")  # a class that is its model
        if tested:
            names += f" ({', '.join(card.model(name, key, data, rig) for name in self.models)})"
        return names

    def render(self, card: Card, key: str, data: Data, rig: set[str], readme: bool = False) -> str | None:
        """The line as the page's card or, with `readme`, the README shows it: None where the README has nothing to say
        (no mark left once 🔴 goes, or a variants parent with no child left)."""
        if self.note is not None:
            kids = [child.render(card, key, data, rig, readme) for child in self.children]
            if readme and not any(kids):
                return None
            children = "".join(f"\n  - {child}" for child in kids if child)
            return f"{self.name(card, key, data, rig, readme)}: {self.note}{children}"
        icons = dict(OUTCOMES)
        found = " · ".join(
            f"{icons[status]} {', '.join(labels)}" for status, labels in (self.claims if readme else self.shape)
        )
        return f"{self.name(card, key, data, rig, readme)}: {found}" if found else None

    def in_labs(self) -> bool:
        """Shows ⚪ and no 🟢 or 🟡 (🔴 may sit beside it): a line that claims nothing yet."""
        statuses = {status for status, _ in self.shape}
        return self.note is None and "labs" in statuses and not statuses & {"works", "should"}


def fold(lines: list[Line], card: Card, key: str, data: Data) -> tuple[list[Line], str | None]:
    """Two or more top-level lines that are in Labs (`Line.in_labs`) leave `lines` for one folded line:
    "⚪ [a] (x, y); [b], [c] (z)", as the README shows it (no 🔴, no ✔, no models). Lines with the same features share a
    parenthesis, and a group sits where its last line does, so one holding an "other brands" line comes last.
    A variants parent's children, and a single such line, stay where they are."""
    labs_only = [line for line in lines if line.in_labs() and not line.variant]
    if len(labs_only) < 2:
        return lines, None
    groups: dict[Shape, list[str]] = {}
    for line in labs_only:
        groups.setdefault(line.claims, []).append(line.name(card, key, data, set(), readme=True))
    # A group sits where its last line does, so a group with an "other brands" line comes last, as on the card.
    last = {
        found: max(i for i, line in enumerate(lines) if line.claims == found and line in labs_only) for found in groups
    }
    parts = []
    for found in sorted(groups, key=last.get):
        names = groups[found]
        inside = ", ".join(label for _, labels in found for label in labels)  # only ⚪ is left
        parts.append(f"{', '.join(names)} ({inside})")
    return [line for line in lines if line not in labs_only], f"{LABS} {'; '.join(parts)}"


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
    by_item, members, full = by_home(found, class_domains)
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
                parent, children = parents.setdefault(
                    entry["section"],
                    (Line((), {entry["section"]: [parent_entry["phrase"]]}, note=parent_entry["variants"]), {}),
                )
                line = children.setdefault(found_shape, Line(found_shape, variant=True, parent=parent))
            else:
                line = lines.setdefault((brand(item, entry["section"]), found_shape), Line(found_shape))
            phrases = line.sections.setdefault(entry["section"], [])
            # Classes that share a phrase (Zigbee2MQTT's countdown plugs, a class per maker string) are said once.
            if phrase not in phrases:
                phrases.append(phrase)
            for home in homes:
                line.features = join_features(line.features, full[item][home])
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
) -> tuple[
    dict[str, dict[str | None, Shape]],
    dict[str, dict[str | None, list[str | None]]],
    dict[str, dict[str | None, Features]],
]:
    """Each item's features per domain a line names it by (`domain_home`, a scene folded into light), the domains
    each of those holds, and the same features with each one's status, `stop` included (`feature_statuses`)."""
    merged_found: dict[str, dict[str | None, dict[str, set[str]]]] = {}
    members: dict[str, dict[str | None, list[str | None]]] = {}
    for (item, domain), by_status in found.items():
        home = domain_home(class_domains.get(item, frozenset()), domain)
        members.setdefault(item, {}).setdefault(home, []).append(domain)
        into = merged_found.setdefault(item, {}).setdefault(home, {})
        for status, actions in by_status.items():
            into.setdefault(status, set()).update(actions)
    by_item: dict[str, dict[str | None, Shape]] = {}
    full: dict[str, dict[str | None, Features]] = {}
    for item, homes in merged_found.items():
        for home, by_status in homes.items():
            if found_shape := shape(by_status):
                by_item.setdefault(item, {})[home] = found_shape
                full.setdefault(item, {})[home] = feature_statuses(by_status)
    return by_item, members, full


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
    names no classes), on which actions, and what proves each: `by_action`."""

    places: list[tuple[str | None, str | None]] = field(default_factory=list)
    actions: set[str] = field(default_factory=set)
    rig: bool = False  # the rig tested it on some action (`Proof.rig`)
    by_action: dict[str, Proof] = field(default_factory=dict)

    @property
    def by_hand(self) -> bool:
        """A maintainer's `_manual.json` row tested it on some action; the rig may have too (`rig`)."""
        return any(proof.by_hand for proof in self.by_action.values())

    @property
    def reports(self) -> list[str]:
        """The users' reports a manual row rests on, on any action: their issues."""
        return list(
            dict.fromkeys(path for proof in self.by_action.values() for path in proof.records if is_report(path))
        )


@dataclass
class Proof:
    """What proves one model on one action: the passing records and manual rows that tested it (repo paths, in
    evidence order; a row's `reports` stand in for its file, as their issue URLs), the firmware they name (a manual row,
    only where it gives it), and whether the rig, a maintainer by hand, or both did (reports are neither)."""

    records: list[str] = field(default_factory=list)
    firmware: list[str] = field(default_factory=list)
    rig: bool = False
    by_hand: bool = False


def works(
    integration_adapters: list, data: Data, credit: Callable = card_evidence
) -> tuple[dict[str, Reached], Reached | None]:
    """The models the adapters' evidence tested (`credit`: `card_evidence`, what a card credits), by device type, then
    first seen, and native groups, each with where and on which actions."""
    models: dict[str, Reached] = {}
    groups: Reached | None = None
    for adapter in integration_adapters:
        evidence = credit(adapter)
        for item in evidence.devices():
            if item.group:
                groups = groups or Reached()
                tested = groups
            else:
                tested = models.setdefault(data.models[item.model]["name"], Reached())
                if (item.cls, item.domain) not in tested.places:
                    tested.places.append((item.cls, item.domain))
            tested.actions.add(adapter.action)
            tested.rig = tested.rig or item.rig
        manual = (test_records_dir(adapter.integration) / MANUAL).relative_to(REPO).as_posix()
        for path, item in evidence.tested:
            held = groups if item.group else models[data.models[item.model]["name"]]
            proof = held.by_action.setdefault(adapter.action, Proof())
            for found in item.reports or [path if path != MANUAL else manual]:
                if found not in proof.records:
                    proof.records.append(found)
            if item.firmware and item.firmware not in proof.firmware:
                proof.firmware.append(item.firmware)
            proof.rig = proof.rig or item.rig
            proof.by_hand = proof.by_hand or not (item.rig or item.reports)
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
    # 🔧 Untested fix, then ⚠️ Unmaintained: the adapters so marked, by reason.
    marks: list[Caveat] = field(default_factory=list)
    # Every adapter is unmaintained, so the heading says so.
    all_unmaintained: bool = False
    # The model, built before the fold (`card`): the unfolded lines, ordered (native groups first; a variants parent's
    # children under it, each with its `parent`), then the no_known_method entries that name no action, each a 🔴
    # line; and what the evidence tested of each model, by name (`Reached`: its places, actions, rig or by hand).
    key: str = ""
    entries: list[Line] = field(default_factory=list)
    refused: list[dict] = field(default_factory=list)
    # Each class a scope refuses (no_known_method), by its (what, reason, source): the page's Not supported row.
    broken: dict[str, tuple[str, str, str]] = field(default_factory=dict)
    # Fields proven less than their feature: (feature, status, field names), for the page's footnote.
    field_notes: list[FieldNote] = field(default_factory=list)
    reached: dict[str, Reached] = field(default_factory=dict)
    groups: Reached | None = None
    # Every model and group a record row names, credited or not (`Evidence.of`, `listed`): the page's Tested devices.
    listed: dict[str, Reached] = field(default_factory=dict)
    listed_groups: Reached | None = None
    # The rendered view (`show`), folded as the README shows it.
    lines: list[str] = field(default_factory=list)
    # What the evidence tested, as the lines name it: each model (✔ when the rig tested it), then native groups.
    tested: list[str] = field(default_factory=list)

    @property
    def rig(self) -> set[str]:
        """The tested models the rig reached."""
        return {name for name, tested in self.reached.items() if tested.rig}

    def short(self, name: str) -> str:
        """The name without the integration's, which the card's title already gives: "Hue Bridge v1" -> "Bridge v1"."""
        return name.removeprefix(f"{self.title} ")

    def model(self, name: str, key: str, data: Data, rig: set[str]) -> str:
        by_name = {model["name"]: model for model in data.models.values()}
        return anchor(self.short(name), data.model_url(by_name[name]["section"])) + (
            f" {VERIFIED}" if name in rig else ""
        )

    def render(self) -> str:
        requires = f" ({self.requires})" if self.requires else ""
        title = f"[{self.title}]({self.url})" if self.url else self.title
        status = " · ⚠️ Unmaintained" if self.all_unmaintained else ""
        lines = [f"**{title}**{requires}{status}", ""]
        lines += [f"- {entry.render()}" for entry in self.marks]
        lines += [f"- {line}" for line in self.lines]
        return "\n".join(lines)


@dataclass(frozen=True)
class Caveat:
    """A caveat mark on a card: the adapters it covers, by their actions, and its reason."""

    label: str
    reason: str
    actions: frozenset[str]

    def render(self) -> str:
        return f"{marked(self.label, self.reason)}: {', '.join(features(set(self.actions), fold_stop=False))}"


def mark_entries(integration_adapters: list) -> list[Caveat]:
    """The adapters shipping a fix no one could test, then those no one is fixing, one entry per caveat and reason."""
    entries = []
    for kind, label in MARKS:
        by_reason: dict[str, set[str]] = {}
        for adapter in integration_adapters:
            if reason := caveat_reason(adapter.scope, kind):
                by_reason.setdefault(reason, set()).add(adapter.action)
        entries += [Caveat(label, reason, frozenset(actions)) for reason, actions in by_reason.items()]
    return entries


# A footnote entry: (feature, status, field names, classes), the classes () for a field at its level on every class.
type FieldNote = tuple[str, str, tuple[str, ...], tuple[str, ...]]


def field_notes(integration_adapters: list) -> list[FieldNote]:
    """Each field whose level is weaker than its action's (the strongest its domains and classes hold), by feature and
    status, for the footnote under the integration's matrix; then each field in Labs on some classes alone
    (`class_labs`), by feature and the classes that share its fields."""
    found: dict[tuple[str, str, tuple[str, ...]], list[str]] = {}
    for adapter in integration_adapters:
        held = items(adapter.scope)
        if not (levels := [level for level, _, noun, _ in held if noun != "fields"]):
            continue
        for level, item, noun, _ in held:
            if noun == "fields" and level < max(levels):
                names = found.setdefault((FEATURES[adapter.action], TIER[level], ()), [])
                names += [item] if item not in names else []
    for adapter in integration_adapters:
        by_fields: dict[frozenset[str], list[str]] = {}
        for cls, names in adapter.scope.class_labs.items():
            by_fields.setdefault(names, []).append(cls)
        for names, classes in by_fields.items():
            noted = found.setdefault((FEATURES[adapter.action], TIER[Level.LABS], tuple(sorted(classes))), [])
            noted += [name for name in sorted(names) if name not in noted]
    return [(feature, status, tuple(names), classes) for (feature, status, classes), names in found.items()]


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
            on[0].features = join_features(on[0].features, feature_statuses({"works": tested.actions}))
        for line in on:
            line.models.append(name)
    for line in unplaced.values():
        line.label = ", ".join(result.model(name, key, data, rig) for name in line.models)
    extra = list(unplaced.values())
    result.tested = [result.model(name, key, data, rig) for name in models]
    if groups is not None:
        label = anchor(GROUPS_ENTRY[0], data.model_url(GROUPS_ENTRY[1])) + (f" {VERIFIED}" if groups.rig else "")
        extra.append(
            Line(
                shape({"works": groups.actions}),
                label=label,
                features=feature_statuses({"works": groups.actions}),
                native=True,
            )
        )
        result.tested.append(label)
    result.key = key
    result.entries = ordered([*lines, *extra], brand, rig)
    result.reached, result.groups = models, groups
    result.listed, result.listed_groups = works(
        integration_adapters, data, lambda found: Evidence.of(found, listed=True)
    )
    result.broken = {
        (name, adapter.action): (entry.what, entry.reason, entry.source)
        for adapter in integration_adapters
        for name, entry in adapter.scope.no_known_method.items()
    }
    result.field_notes = field_notes(integration_adapters)
    # devices.yaml's and models.yaml's no_known_method entries name no class or action: each a line of its own.
    result.refused = [
        entry for entry in data.no_known_method if key in entry["integrations"] and not entry.get("actions")
    ]
    show(result, data)
    return result


def show(result: Card, data: Data) -> None:
    """Render the card's model as the README shows it: the classes with their marks, no tested models, ✔ or 🔴 (the
    refused entries have no line), the fold last; the unfolded lines stay in `entries`."""
    key = result.key
    lines, folded = fold(result.entries, result, key, data)
    result.lines = [shown for line in lines if (shown := line.render(result, key, data, set(), readme=True))]
    if folded:
        result.lines.append(folded)


def legend(text: str) -> str:
    """The legend's entries for the marks the cards use, one per line: the three marks' (coverage.LEGEND, as the
    Settings view words them), then the caveats'."""
    lines = [line for mark, line in legend_entries(LABS_POINTER) if mark in text]
    lines += [f"{icon} {entry}" for icon, entry in CAVEATS if icon in text]
    return "<br>\n".join(lines)


def card_list(registry: AdapterRegistry, data: Data) -> list[Card]:
    return [card(key, registry, adapters, data) for key, adapters in by_integration(registry).items()]


def cards(built: list[Card]) -> str:
    body = []
    for entry in built:
        body += [entry.render(), ""]
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
        f"Models and how each was tested are on the [compatibility page]({PAGE_URL}). "
        f"Details per integration are in [docs/integrations.md]({INTEGRATIONS_URL}).",
        "",
        "</details>",
        "",
        CARDS[1],
    ]
    return "\n".join(parts)


# The integrations page's intro links.


def integration_links(registry: AdapterRegistry) -> str:
    """One bullet per integration, in card order, linking its page relative to `docs/integrations.md`."""
    items = [
        f"- [{plain_title(registry.integrations[key])}](integrations/{key}/index.md)"
        for key in integration_columns(registry)
    ]
    return "\n".join([INTEGRATIONS[0], *items, INTEGRATIONS[1]])


# Writing.


def splice(text: str, markers: tuple[str, str], block: str, name: str) -> str:
    start, end = markers
    if text.count(start) != 1 or text.count(end) != 1 or text.index(start) > text.index(end):
        raise SystemExit(f"{name} needs one {start} before one {end}")
    return text[: text.index(start)] + block + text[text.index(end) + len(end) :]


LINK = re.compile(r"\]\(([^)\s]+)\)")


def check_sections(block: str, shown: str, data: Data, built: list[Card]) -> None:
    """Every link the generated block (`block`) and the README's cards (`shown`) emit resolves, so a renamed heading
    fails here rather than leaving a dead link. A 🟡 or ⚪ class must have its section on its integration's page, with
    no exemption. Any other link to PAGE (a Verified class that is a model's, a blocker) answers to a heading or an
    anchor id of the generated block (a model's or native groups' heading, a Not supported row), one to an
    integration's page to a heading there, a relative one to a file of docs/ and its heading."""
    bare = sorted(
        {
            f"{section} ({card.key})"
            for card in built
            for entry in card.entries
            for line in (entry, *entry.children)
            if {status for pairs in line.features.values() for status, _ in pairs} & {"should", "labs"}
            for section in line.sections
            if slug(section) not in data.pages.get(card.key, set())
        }
    )
    if bare:
        raise SystemExit(
            f"no heading for {', '.join(bare)} on the integration's page: a Documented or Labs class links its section"
        )
    here = anchors(block) | set(re.findall(r'<a id="([^"]+)"', block))
    by_page = {f"{DOCS_URL}{page(key)}": found for key, found in data.pages.items()}
    dead = set()
    for href in LINK.findall(block) + LINK.findall(shown):
        target, _, fragment = href.partition("#")
        if href.startswith("#") or target == PAGE_URL:
            if fragment and fragment not in here:
                dead.add(fragment)
        elif target in by_page:
            if fragment and fragment not in by_page[target]:
                dead.add(href.removeprefix(DOCS_URL))
        elif not re.match(r"[a-z][a-z0-9+.-]*:", href):  # a relative link, from docs/
            path = REPO / "docs" / target
            if not path.is_file() or (fragment and path.suffix == ".md" and fragment not in anchors(path.read_text())):
                dead.add(href)
    if dead:
        raise SystemExit(
            f"no heading or file for {', '.join(sorted(dead))} on docs/device-compatibility.md, the integration's page"
            " or in docs/; add a section"
        )


def main(
    argv: list[str] | None = None,
    registry: AdapterRegistry | None = None,
    page: Path = PAGE,
    readme: Path = README,
    models: Path = MODELS,
    integrations: Path = INTEGRATIONS_PAGE,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail when the README or a page is out of date")
    args = parser.parse_args(argv)

    registry = registry or AdapterRegistry.discover()
    data = load(registry, models)
    check_models(registry, data)
    built = card_list(registry, data)
    block, shown = evidence(registry, data, built), cards(built)
    # Both are computed before either is written, so a failure leaves neither half-updated.
    updates = {}
    for path, markers, new in (
        (page, EVIDENCE, block),
        (readme, CARDS, shown),
        (integrations, INTEGRATIONS, integration_links(registry)),
    ):
        text = updates[path][1] if path in updates else path.read_text()
        updates[path] = (updates[path][0] if path in updates else text, splice(text, markers, new, path.name))
    check_sections(block, shown, data, built)
    # The coverage check warns here, on every PR, and fails only at cut-release (check_release.py --signoffs).
    for gap in [*coverage_gaps(registry), *default_class_credits(registry)]:
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
