#!/usr/bin/env python3
"""Check the release gates: the coverage bar, a sign-off for each action whose calls changed since the last release,
and the classes' coverage check.

The rules are in docs/evidence.md (Release gate, Sign-off format); this is how the checks read them.

--coverage coverage.json (pytest --cov-report=json): every module under `core/` and `integrations/`, bar `__init__.py`,
needs at least 95% line coverage; one missing from the report has none.

--signoffs: evidence binds to an action's call transcript, `tests/integrations/<key>/calls/<action>.json` (written by
`pytest --transcripts=write`, tests/transcripts.py): a list of segments, each a call path the unit tests pin. Evidence
cites the git blob id of the transcript it was tested against and is read back with `git cat-file`, so a run on a
branch still resolves after a squash merge that landed the transcript unchanged; a blob git doesn't have stands for
nothing. Evidence stands while every segment of its transcript occurs, unchanged, in HEAD's (`segments_hold`): a test
added, or a new call path, reopens nothing; a segment changed or removed reopens it, whatever code changed it (an
integration's package or `core/`). A changed action's evidence must also hold every segment HEAD's transcript gained
since the tag's (`Calls.gained`), so a run from before the change can't sign it off; with no tag's
transcript, standing is enough. An action is changed when HEAD's transcript of it doesn't hold every segment of the
last release tag's (the latest `vX.Y.Z` that is an ancestor of HEAD), or the tag has none, or there is no tag; its last
change is the latest commit touching its transcript. Each changed action needs a sign-off of its own: its rig records
(`<action>.json`, and each `<action>-<option>.json` there is) all format 3, passing and standing, or a format 3
`_manual.json` row whose `calls` names the action and stands, by a maintainer of the integration or a repo maintainer
(`REPO_MAINTAINERS`). A row's and a record's `commit` is provenance: nothing here checks it. A format 1 (converted from
markdown) or format 2 (bound to the package, not the calls) record, and a format 2 row (`passed`), sign off nothing.
Without a sign-off, a 🔧 Untested fix caveat on the action's adapter stands in. A suite that is no action's
(`config_entry.json`) is outside the gate. Prints a line per changed action naming its sign-off (kind, source, commit,
tester) or the caveat standing in, and fails on each with neither, saying why its records and each manual row naming it
were rejected. With --json, prints instead the integrations with a changed action that has no sign-off (caveat or not),
as a JSON list: the rig's run selection. With --reruns, prints instead a JSON object of those integrations, each with
the suites to run: for each such action, its records that are not format 3, failing or reopened, and its plain suite
when it has none. It also runs the coverage check, failing on each gap: for an integration that names classes
(`IntegrationInfo.capability`), every class an adapter not flagged whole holds as Verified needs a passing test that
reached it in a passing record of the action (format 2 and 3: a device of the test with that class, a native group's
test crediting each member's; format 1: the test's `classes`), or a `_manual.json` row naming the action (format 3: in
`calls`; format 2: in `passed`) one of whose devices has the class. `scripts/gen_compat.py` prints the same gaps as
warnings on every run (`coverage_gaps`).

--notes notes.md: writes the release notes' call for testers, with a link to the device report form: the
integrations with a changed action that has no sign-off, and every adapter with an Untested fix caveat. Empty when
there are none.

Test records are JSON, in `docs/integrations/<key>/test-records/`, each checked against docs/test-records.schema.json
(the format's one home; docs/evidence.md, Sign-off format, describes it); a file of the wrong kind for its name, or of
another integration than its folder's, is an error. A rig record per suite (`<action>.json`, `<action>-<option>.json`,
read as the action's evidence; another suite's, as `config_entry.json`, is none's), `_manual.json`, whose rows are
manual sign-offs, and `_facts.json`, the fact cases' results, which nothing here reads; a dotfile is ignored. A manual
row whose tester is neither a maintainer of the integration nor a repo maintainer is an error. A manual row's devices,
and a record's tests, may name a class only on an integration that names classes (`names_classes`, which gen_compat
shares). A record names no tester: review of the PR that lands it checks who ran it. A `.json` named with a leading `_`
other than those two, or a record whose `action` or `options` its name contradicts, is an error naming the file, as is,
under --signoffs, a file in the folder that isn't JSON (a markdown record).

Exits 1 on an integration that failed to import, whatever the options, and on any failure of the checks asked for. A
git error fails the run rather than pass a gate unseen.

Usage: scripts/check_release.py [--coverage coverage.json] [--signoffs [--json | --reruns]] [--notes notes.md]
"""

import argparse
import functools
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from custom_components.deviceside.config_flow import REPORT_URL  # noqa: E402
from custom_components.deviceside.core.registry import AdapterRegistry  # noqa: E402
from custom_components.deviceside.core.scope import CaveatKind, Level  # noqa: E402
from scripts.check_tag import git as git_in  # noqa: E402
from scripts.check_tag import releases  # noqa: E402
from scripts.gen_codeowners import REPO_MAINTAINERS  # noqa: E402

COVERAGE_BAR = 95.0
COMPONENT = Path("custom_components") / "deviceside"
BUNDLES = REPO / "docs" / "integrations"
SCHEMA = REPO / "docs" / "test-records.schema.json"
MANUAL = "_manual.json"
FACTS = "_facts.json"
FORMAT = 3  # the format the rig writes, and the only one a sign-off takes
# Where the call transcripts live: tests/integrations/<key>/calls/<action>.json (tests/transcripts.py writes them).
TRANSCRIPTS = Path("tests") / "integrations"
DEVICE_REPORT = f"{REPORT_URL}?template=device_report.yml"


def adapters(registry: AdapterRegistry) -> list[tuple[str, object]]:
    """Every adapter, named `integration / action`."""
    return [
        (f"{integration} / {action}", adapter)
        for action, integration, adapter in registry.matrix()
        if adapter is not None
    ]


def names_classes(adapter) -> bool:
    """Whether the adapter's integration names classes (`IntegrationInfo.capability`): the registry holds every
    adapter's scope to it, classes in each or in none (`check_classes`), so the scope answers for the integration. The
    one definition gen_compat and the checks here share."""
    return adapter.scope.capabilities is not None


def classed(registry) -> set[str]:
    """The integrations that name classes, by their adapters (`names_classes`)."""
    return {adapter.integration for _, adapter in adapters(registry) if names_classes(adapter)}


def git(*args: str) -> str:
    """The command's output; raises on a non-zero exit."""
    return git_in(REPO, *args)


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


def test_records_dir(integration: str) -> Path:
    """Where the integration's test records live: `docs/integrations/<integration>/test-records/`. The rig writes
    there."""
    return BUNDLES / integration / "test-records"


def where(path: Path) -> str:
    """The path as an error names it: relative to the repository."""
    return path.relative_to(REPO).as_posix() if path.is_relative_to(REPO) else str(path)


@functools.cache
def validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(SCHEMA.read_text()))


def load(path: Path) -> dict:
    """The test-records file, checked against the schema, against its name (`_manual.json` holds sign-offs,
    `_facts.json` facts, any other a rig record) and against its folder's integration. Any error names the file and
    stops the run: a file read wrong would credit or sign off unseen."""
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise SystemExit(f"{where(path)}: not JSON ({error})") from None
    if error := best_match(validator().iter_errors(data)):
        at = "/".join(map(str, error.absolute_path)) or "the top level"
        raise SystemExit(f"{where(path)}: {error.message}, at {at} (docs/test-records.schema.json)")
    kind = {MANUAL: "signoffs", FACTS: "facts"}.get(path.name, "tests")
    if kind not in data:
        raise SystemExit(f"{where(path)}: not the kind of file its name says (docs/test-records.schema.json)")
    if data["integration"] != path.parent.parent.name:
        raise SystemExit(f"{where(path)}: integration {data['integration']!r}, in {path.parent.parent.name}'s bundle")
    return data


def listed(integration: str) -> list[Path]:
    """The files in the integration's test-records folder, dotfiles (an editor's or the OS's) left out. A `.json`
    named with a leading `_` other than `_manual.json` and `_facts.json` stops the run, naming it: it is no record, and
    would drop out of the sign-off unseen."""
    folder = test_records_dir(integration)
    found = sorted(path for path in folder.glob("*") if path.is_file() and not path.name.startswith("."))
    for path in found:
        if path.suffix == ".json" and path.name.startswith("_") and path.name not in (MANUAL, FACTS):
            raise SystemExit(
                f"{where(path)}: a leading `_` is for {MANUAL} and {FACTS} only; a rig record is named for its suite"
                " (docs/test-records.schema.json)"
            )
    return found


def records(integration: str) -> list[Path]:
    """The integration's rig records, every suite's: the JSON files not named with a leading `_`."""
    return [path for path in listed(integration) if path.suffix == ".json" and not path.name.startswith("_")]


def suites(integration: str, action: str) -> list[tuple[Path, dict]]:
    """The action's test records, passing or not, each with its content: `<action>.json`, and `<action>-<option>.json`
    for a run with an option set (several options `-`-joined, sorted, as a step file's `options` are). A file is
    credited by its name, so one whose `action` or `options` say otherwise stops the run, naming it, rather than credit
    an action it didn't test."""
    pattern = re.compile(rf"{re.escape(action)}(?:-([^.]+))?\.json")
    found = []
    for path in records(integration):
        if not (match := pattern.fullmatch(path.name)):
            continue
        record, options = load(path), match[1].split("-") if match[1] else None
        if (record["action"], record.get("options")) != (action, options):
            held = f"action {record['action']!r}, options {record.get('options')}"
            raise SystemExit(f"{where(path)}: {held}, but its name says action {action!r}, options {options}")
        found.append((path, record))
    return found


def passing(integration: str, action: str) -> list[Path]:
    """The action's passing test records (`suites`)."""
    return [path for path, record in suites(integration, action) if record["result"] == "pass"]


def manual(integration: str) -> list[dict]:
    """The rows of the integration's `_manual.json`; none without one."""
    path = test_records_dir(integration) / MANUAL
    return load(path)["signoffs"] if path.is_file() else []


def row_actions(row: Mapping) -> list[str]:
    """The actions a `_manual.json` row tested: its `calls`' keys (format 3), or its `passed` (format 2, which credits
    classes and cards but signs off nothing)."""
    return list(row["calls"]) if "calls" in row else list(row["passed"])


def manual_rows(integration: str, action: str) -> list[tuple[bool, list[tuple[str, str | None]]]]:
    """Each `_manual.json` row naming the action (`row_actions`), as (whether it targeted a native group, its devices
    as (model id, class); a group's are its members)."""
    return [
        (bool(row.get("group")), [(device["model"], device["class"]) for device in row["devices"]])
        for row in manual(integration)
        if action in row_actions(row)
    ]


# The coverage check (docs/evidence.md, The coverage check).


def reached(integration: str, action: str) -> set[tuple[str, str | None]]:
    """The classes the action's evidence reached, each with the domain its test targeted: in a passing record, each
    passing test's (format 2: its devices' classes, a native group's members' each; format 1: its `classes`), and each
    `_manual.json` row's devices' (a group row's members', as a group test's), whose domain is None, as a row names
    none. A null class credits none."""
    found: set[tuple[str | None, str | None]] = set()
    for path in passing(integration, action):
        record = load(path)
        for test in record["tests"]:
            if test["result"] != "pass":
                continue
            names = test.get("classes", ()) if record["format"] == 1 else (d["class"] for d in test["devices"])
            found.update((name, test.get("domain")) for name in names)
    for _, row in manual_rows(integration, action):
        found.update((cls, None) for _, cls in row)
    return {(name, domain) for name, domain in found if name is not None}


def coverage_gaps(registry) -> list[str]:
    """Each class an adapter of an integration that names classes holds as Verified, with no passing record test or
    manual row for its action that reached it: one held on every domain, in any domain; one held on some domains alone
    (OnDomains), in each of them, as a record in one domain proves nothing about another. A manual row names no domain,
    so it covers every domain (the maintainer's judgment, tenet 7). An adapter flagged whole holds none as Verified."""
    gaps = []
    for _, adapter in adapters(registry):
        if not names_classes(adapter) or adapter.scope.all_labs:
            continue
        found = reached(adapter.integration, adapter.action)
        for item, level, domains in sorted(adapter.scope.class_entries(), key=lambda entry: entry[0]):
            if level is not Level.VERIFIED:
                continue
            if domains is None:
                if not any(name == item for name, _ in found):
                    gaps.append(
                        f"{adapter.integration} {adapter.action}: `{item}` is Verified but no record reaches it"
                    )
                continue
            prefix = f"{adapter.integration} {adapter.action}: `{item}` is Verified on"
            gaps += [
                f"{prefix} {domain} but no record reaches it there"
                for domain in sorted(domains)
                if (item, domain) not in found and (item, None) not in found
            ]
    return gaps


# Coverage.


def coverage_errors(coverage: dict) -> list[str]:
    """Each module under `core/` and `integrations/`, bar `__init__.py`, under the bar or missing from the report."""
    percent = {}
    for name, entry in coverage["files"].items():
        summary = entry["summary"]
        statements = summary["num_statements"]
        percent[Path(name).as_posix()] = 100.0 * summary["covered_lines"] / statements if statements else 100.0
    modules = sorted(
        path.relative_to(REPO).as_posix()
        for folder in ("core", "integrations")
        for path in (REPO / COMPONENT / folder).rglob("*.py")
        if path.name != "__init__.py"
    )
    return [
        f"{module}: {covered:.1f}% line coverage, under {COVERAGE_BAR:.0f}%"
        for module in modules
        if (covered := percent.get(module, 0.0)) < COVERAGE_BAR
    ]


# Sign-offs.


@dataclass(frozen=True)
class SignOff:
    kind: str  # "record" or "manual"
    source: str  # the record, or the manual row as `<file> row <n>`
    commit: str  # the commit its run or row cites: provenance, which nothing checks
    tester: str | None = None  # a manual row's handle; a record names none


@dataclass(frozen=True)
class Row:
    """A `_manual.json` row by a tester who may sign off: where it is, its commit and tester, the actions it tested,
    and the transcript blob of each (format 3), or None (format 2, which signs off nothing)."""

    at: str
    commit: str
    tester: str
    actions: tuple[str, ...]
    calls: Mapping[str, str] | None


@dataclass(frozen=True)
class Gate:
    """A changed action: its transcript's last change, its sign-off and why any other evidence was rejected, whether
    an Untested fix caveat stands in, and the suites to rerun when it has no sign-off."""

    integration: str
    action: str
    last_change: str | None
    signoff: SignOff | None
    rejected: tuple[str, ...]
    caveated: bool
    reruns: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        return f"{self.integration} / {self.action}"

    @property
    def passes(self) -> bool:
        return self.signoff is not None or self.caveated


def last_release() -> str | None:
    """The latest release tag (never an RC) that is an ancestor of HEAD, or None if there is none."""
    found = releases(REPO, "HEAD")
    return found[-1][1] if found else None


def transcript_path(integration: str, action: str) -> str:
    """The action's call transcript, relative to the repository."""
    return (TRANSCRIPTS / integration / "calls" / f"{action}.json").as_posix()


def blob_at(rev: str, integration: str, action: str) -> str | None:
    """The blob id of the action's transcript at the revision, or None when it has none there. The revision must
    resolve (`gates` checks the base)."""
    found = run("rev-parse", "--verify", "--quiet", f"{rev}:{transcript_path(integration, action)}")
    return found.stdout.strip() if found.returncode == 0 else None


def transcript(blob: str) -> list[dict] | None:
    """The segments of the transcript git holds as the blob, read with `git cat-file`; None when git doesn't have the
    blob, or it is no transcript (a non-empty JSON list of segments), so evidence citing it stands for nothing."""
    done = run("cat-file", "blob", blob)
    if done.returncode:
        return None
    try:
        segments = json.loads(done.stdout)
    except ValueError:
        return None
    if not (isinstance(segments, list) and segments and all(isinstance(segment, dict) for segment in segments)):
        return None
    return segments


def _segment(segment: Mapping) -> str:
    return json.dumps(segment, sort_keys=True, separators=(",", ":"))


def segments_hold(old: Sequence[Mapping], new: Sequence[Mapping]) -> bool:
    """Whether every segment of the old transcript occurs, unchanged, in the new: a segment added (a new test, a new
    call path) keeps the old evidence; one changed or removed reopens it."""
    return {_segment(segment) for segment in old} <= {_segment(segment) for segment in new}


@dataclass(frozen=True)
class Calls:
    """A changed action's calls: HEAD's transcript (None: HEAD has none), and the segments of it the base's lacks
    (`_segment` keys; none when the base has no transcript), added or changed since the base, which its evidence must
    hold (docs/evidence.md, Release gate)."""

    head: list[dict] | None
    gained: frozenset[str] = frozenset()
    base: str | None = None


def reopened(blob: str, calls: Calls) -> str | None:
    """Why evidence bound to the transcript blob doesn't sign off the changed action's calls, or None when it does: it
    must stand at HEAD's transcript and hold every segment HEAD's gained since the base."""
    if (old := transcript(blob)) is None:
        return f"calls {blob[:12]}, which git doesn't have as a transcript"
    if calls.head is None:
        return "HEAD has no transcript to hold its calls"
    if not segments_hold(old, calls.head):
        kept = {_segment(segment) for segment in calls.head}
        gone = sum(_segment(segment) not in kept for segment in old)
        return f"reopened: {gone} of its {len(old)} call segments changed or gone since"
    if missed := len(calls.gained - {_segment(segment) for segment in old}):
        return f"{missed} of HEAD's call segments added or changed since {calls.base} aren't in its calls"
    return None


def changed_actions(integration: str, actions: Iterable[str], base: str | None) -> dict[str, Calls]:
    """The integration's actions whose calls changed since the base, each with its `Calls`: HEAD's transcript doesn't
    hold every segment of the base's, or the base has none, or there is no base."""
    found = {}
    for action in actions:
        head_blob = blob_at("HEAD", integration, action)
        base_blob = blob_at(base, integration, action) if base else None
        if base_blob is not None and base_blob == head_blob:
            continue
        head = transcript(head_blob) if head_blob else None
        old = transcript(base_blob) if base_blob else None
        if old is not None and head is not None:
            if segments_hold(old, head):
                continue
            had = {_segment(segment) for segment in old}
            found[action] = Calls(head, frozenset(_segment(segment) for segment in head) - had, base)
        else:
            found[action] = Calls(head)
    return found


def last_change(integration: str, action: str, base: str | None) -> str | None:
    """The latest commit touching the action's transcript since the base, or None when none did."""
    span = f"{base}..HEAD" if base else "HEAD"
    return git("log", "-1", "--format=%H", span, "--", transcript_path(integration, action)) or None


def record_signoff(integration: str, action: str, calls: Calls) -> tuple[SignOff | None, list[str], list[str]]:
    """The action's rig records as its sign-off, when there is a plain one (`<action>.json`) and every one (each
    option's too) is format 3, passes and signs off its calls (`reopened`); else None, why not, and the suites to
    rerun."""
    found = suites(integration, action)
    why, reruns = [], []
    for path, record in found:
        if record["format"] == 1:
            problem = "format 1, converted from markdown"
        elif record["format"] != FORMAT:
            problem = f"format {record['format']}, bound to the package, not the calls"
        elif record["result"] != "pass":
            problem = "fails"
        else:
            problem = reopened(record["calls"], calls)
        if problem:
            why.append(f"{path.name}: {problem}")
            reruns.append(path.stem)
    plain = [(path, record) for path, record in found if not record.get("options")]
    if not plain:
        # An option's record ran the action with that option set, so the plain call needs a record of its own.
        why.append(f"{action}.json: no record")
        reruns.append(action)
    if why:
        return None, why, sorted(reruns)
    path, record = plain[0]
    return SignOff("record", where(path), record["source"]["commit"]), [], []


def manual_signoff(rows: Sequence[Row], action: str, calls: Calls) -> tuple[SignOff | None, list[str]]:
    """The first manual row naming the action whose transcript blob signs off its calls (`reopened`), as its sign-off,
    and why each one before it was rejected: a format 2 row binds no calls, and one whose calls changed is reopened."""
    rejected = []
    for row in rows:
        if action not in row.actions:
            continue
        if row.calls is None:
            rejected.append(f"{row.at}: format 2, which names the actions it passed but not their calls")
        elif why := reopened(row.calls[action], calls):
            rejected.append(f"{row.at}: {why}")
        else:
            return SignOff("manual", row.at, row.commit, row.tester), rejected
    return None, rejected


def manual_signoffs(
    integration: str, testers: tuple[str, ...], names_classes: bool = False
) -> tuple[list[Row], list[str]]:
    """The integration's `_manual.json` rows, and the errors in them: a class on an integration that names none, or a
    tester who may not sign off. A row in error is no sign-off; a file the schema rejects stops the run."""
    path = test_records_dir(integration) / MANUAL
    allowed = {tester.casefold() for tester in testers}
    found, errors = [], []
    for number, row in enumerate(manual(integration), 1):
        at = f"{where(path)} row {number}"
        if not names_classes and any(device["class"] is not None for device in row["devices"]):
            errors.append(f"{at}: a class, but {integration} names no classes")
        elif row["tester"].casefold() not in allowed:
            errors.append(f"{at}: tester @{row['tester']} is neither a maintainer of {integration} nor a repo one")
        else:
            calls = dict(row["calls"]) if "calls" in row else None
            found.append(Row(at, row["commit"], row["tester"], tuple(row_actions(row)), calls))
    return found, errors


def foreign_files(integration: str) -> list[str]:
    """An error naming the files in the integration's test-records folder that aren't JSON, when there are any: no
    record, so a markdown one would credit nothing unseen."""
    if foreign := [path.name for path in listed(integration) if path.suffix != ".json"]:
        return [
            f"{where(test_records_dir(integration))}: {', '.join(foreign)}: not test records, which are JSON"
            " (docs/test-records.schema.json); probe findings go in internals.md, manual sign-offs in _manual.json"
        ]
    return []


def record_class_errors(integration: str) -> list[str]:
    """For an integration that names no classes: each rig record test that names one, a device's `class` (format 2)
    or a `classes` entry (format 1), as `_manual.json` rows are held (`manual_signoffs`). A class there is a record
    read wrong, as nothing could have reached it."""
    errors = []
    for path in records(integration):
        record = load(path)
        for number, test in enumerate(record["tests"], 1):
            named = test.get("classes", []) + [item["class"] for item in test.get("devices", ())]
            if any(cls is not None for cls in named):
                errors.append(
                    f"{where(path)} test {number} ({test['id']}): a class, but {integration} names no classes"
                )
    return errors


def gates(registry) -> tuple[str | None, list[Gate], list[str]]:
    """The last release tag, a gate per changed action, and the test-records errors: a `_manual.json` row's, a file
    that isn't JSON, or a class named on an integration that names none."""
    base = last_release()
    if base and (done := run("rev-parse", "--verify", f"{base}^{{commit}}")).returncode:
        raise RuntimeError(f"git rev-parse {base}: {done.stderr.strip()}")
    found, errors = [], []
    names = classed(registry)
    for key, info in registry.integrations.items():
        rows, problems = manual_signoffs(key, (*info.maintainers, *REPO_MAINTAINERS), key in names)
        errors += problems + foreign_files(key)
        if key not in names:
            errors += record_class_errors(key)
        own = {adapter.action: adapter for _, adapter in adapters(registry) if adapter.integration == key}
        for action, calls in changed_actions(key, sorted(own), base).items():
            signoff, rejected, reruns = record_signoff(key, action, calls)
            if calls.head is None:
                rejected.insert(0, f"{transcript_path(key, action)}: none at HEAD, so no unit test pins its calls")
            if signoff is None:
                signoff, refused = manual_signoff(rows, action, calls)
                rejected += refused
            caveat = own[action].scope.caveat
            untested = caveat is not None and caveat.kind is CaveatKind.UNTESTED_FIX
            last = last_change(key, action, base)
            found.append(Gate(key, action, last, signoff, tuple(rejected), untested, () if signoff else tuple(reruns)))
    return base, found, errors


def describe(gate: Gate) -> str:
    """The gate's line: its sign-off, else the caveat standing in, else why it fails."""
    head = f"{gate.name}: calls changed" + (f" at {gate.last_change[:7]}" if gate.last_change else "")
    if signoff := gate.signoff:
        tester = f", @{signoff.tester}" if signoff.tester else ""
        return f"{head}; signed off by {signoff.kind} {signoff.source} at {signoff.commit[:7]}{tester}"
    if gate.passes:
        return f"{head}; no sign-off, Untested fix stands in"
    rejected = "".join(f" ({why})" for why in gate.rejected)
    return f"{head}; no sign-off{rejected}, and no Untested fix"


def unsigned(found: Sequence[Gate]) -> dict[str, list[str]]:
    """The integrations with a changed action that has no sign-off, caveated or not, each with the suites to run."""
    reruns: dict[str, set[str]] = {}
    for gate in found:
        if gate.signoff is None:
            reruns.setdefault(gate.integration, set()).update(gate.reruns)
    return {integration: sorted(suites) for integration, suites in reruns.items()}


def release_notes(registry, found: list[Gate]) -> str:
    """The release notes' call for testers: the integrations with a changed action that has no sign-off, and every
    adapter with an Untested fix caveat."""
    titles = [registry.integrations[integration].title for integration in unsigned(found)]
    untested = [
        name
        for name, adapter in adapters(registry)
        if adapter.scope.caveat is not None and adapter.scope.caveat.kind is CaveatKind.UNTESTED_FIX
    ]
    parts = []
    if titles:
        parts.append(
            "## Help us test\n\nThese integrations have an action whose calls changed since the last release, and no"
            " maintainer has tested the change on a device yet. If you use one, please"
            f" [report whether it works]({DEVICE_REPORT}).\n\n" + "".join(f"- {title}\n" for title in titles)
        )
    if untested:
        parts.append(
            "## 🔧 Untested fix\n\nThese ship a fix nobody could test before the release. If you use one, please"
            f" [report whether it works]({DEVICE_REPORT}).\n\n" + "".join(f"- {name}\n" for name in untested)
        )
    return "\n".join(parts)


def main(argv: list[str] | None = None, registry: AdapterRegistry | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--coverage", type=Path, help="coverage.json from pytest --cov-report=json")
    parser.add_argument(
        "--signoffs", action="store_true", help="fail on an action changed since the last release with no sign-off"
    )
    printed = parser.add_mutually_exclusive_group()
    printed.add_argument("--json", action="store_true", help="with --signoffs: list the integrations without one")
    printed.add_argument("--reruns", action="store_true", help="with --signoffs: those, each with the suites to rerun")
    parser.add_argument("--notes", type=Path, help="write the release notes' call for testers here")
    args = parser.parse_args(argv)
    if (args.json or args.reruns) and not args.signoffs:
        parser.error("--json and --reruns need --signoffs")

    registry = registry or AdapterRegistry.discover()
    # An integration that failed to import has no adapters to check, so every gate would pass it unseen.
    errors = [
        f"{key}: failed to import ({info.unavailable_reason})"
        for key, info in registry.integrations.items()
        if not info.available
    ]
    if args.coverage:
        errors += coverage_errors(json.loads(args.coverage.read_text()))
    if args.signoffs or args.notes:
        base, found, manual_errors = gates(registry)
        if args.notes:
            args.notes.write_text(release_notes(registry, found))
        if args.signoffs:
            errors += manual_errors
            errors += [describe(gate) for gate in found if not gate.passes]
            errors += coverage_gaps(registry)
            lines = [f"Since {base or 'the first commit'}:", *(describe(gate) for gate in found)]
            if args.reruns:
                print(json.dumps(unsigned(found)))
            elif args.json:
                print(json.dumps(list(unsigned(found))))
            else:
                print("\n".join(lines))
            if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
                with open(summary, "a") as handle:
                    handle.write("## Sign-offs\n\n" + "".join(f"- {line}\n" for line in lines))
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
