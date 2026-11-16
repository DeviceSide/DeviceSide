#!/usr/bin/env python3
"""Check the release gates: the coverage bar, a sign-off for each integration changed since the last release, and the
classes' coverage check.

The rules are in docs/evidence.md (Release gate, Sign-off format); this is how the checks read them.

--coverage coverage.json (pytest --cov-report=json): every module under `core/` and `integrations/`, bar `__init__.py`,
needs at least 95% line coverage; one missing from the report has none.

--signoffs: an integration is changed when its package (`integrations/<key>/`) differs between the last release tag (the
latest `vX.Y.Z` that is an ancestor of HEAD; with none, every integration is changed) and HEAD, so a reverted change is
none; its last change is the latest commit touching the package. It needs a sign-off that holds the package as HEAD
does: its test records, each judged by the package tree it cites (the tree of `integrations/<key>/` at the run's commit,
so a run on a branch counts after a squash merge, even once the branch is deleted), or a `_manual.json` row, by its
commit, which is in this checkout. The records sign off when every one is format 2, passes and still stands. A record
stands while the package files changed between its tree and HEAD's are all other adapters' modules (docs/evidence.md,
tenet 9): a change to its own adapter's module, or to a module that is no adapter's (a shared helper), reopens it, as
does any change for a suite that is no action's (`lifecycle.json`), or a tree git doesn't have. A `no_call_changed` row
carries a record across the change its commit made when it names the record's action (`actions`; with none, every
action): the record must stand up to that commit's parent, and from the commit on. Every action whose adapter changed
since the last release needs a record. A reopened, format 1 (converted from markdown) or failing record, or a changed
action with none, is no sign-off until its suite is run. Without one, a ⚠️ Untested fix caveat stands in when every
changed adapter carries it: each adapter whose module changed, or all of the package's when a module that is no
adapter's changed (a shared helper). Prints a line per changed integration naming its sign-off (kind, commit, tester) or
the caveats standing in, and fails on each with neither, saying why its records and each manual row were rejected. With
--json, prints instead the changed integrations without a sign-off, as a JSON list: the rig's run selection. With
--reruns, prints instead a JSON object of those integrations, each with the suites to run (its reopened, format 1 and
failing records, and its changed actions with none), or an empty list for every suite, when it has no record. It also
runs the coverage check, failing on each gap: for an integration that names classes (`IntegrationInfo.capability`),
every class an adapter not flagged whole holds as Verified needs a passing test that reached it in a passing record of
the action (format 2: a device of the test with that class, a native group's test crediting each member's; format 1: the
test's `classes`), or a `_manual.json` row whose `passed` names the action and one of whose devices has the class.
`scripts/gen_compat.py` prints the same gaps as warnings on every run (`coverage_gaps`).

--notes notes.md: writes the release notes' call for testers, with a link to the device report form: the changed
integrations without a sign-off, and every adapter with an Untested fix caveat. Empty when there are none.

Test records are JSON, in `docs/integrations/<key>/test-records/`, each checked against docs/test-records.schema.json
(the format's one home; docs/evidence.md, Sign-off format, describes it); a file of the wrong kind for its name, or of
another integration than its folder's, is an error. A rig record per suite (`<action>.json`, `<action>-<option>.json`,
read as the action's evidence; another suite's, as `lifecycle.json`, counts only toward the run), `_manual.json`, whose
rows are manual sign-offs, and `_facts.json`, the fact cases' results, which nothing here reads. Under --signoffs, a
file there that isn't JSON (a markdown record) is no record, named; a dotfile is ignored. A manual row's tester must be
one of the integration's maintainers or a repo maintainer (`REPO_MAINTAINERS`). A manual row's devices, and a record's
tests, may name a class only on an integration that names classes (`names_classes`, which gen_compat shares). A record
names no tester: review of the PR that lands it checks who ran it. A `.json` named with a leading `_` other than those
two, or a record whose `action` or `options` its name contradicts, is an error naming the file.

Exits 1 on an integration that failed to import, whatever the options, and on any failure of the checks asked for. A
git error fails the run rather than pass a gate unseen.

Usage: scripts/check_release.py [--coverage coverage.json] [--signoffs [--json | --reruns]] [--notes notes.md]
"""

import argparse
import functools
import inspect
import json
import os
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
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
FORMAT = 2  # the format the rig writes, and the only one a sign-off takes
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


def holds(*args: str) -> bool:
    """For a command whose exit 1 means no (`diff --quiet`): whether it exited 0. Raises on any other exit, a git
    error."""
    done = run(*args)
    if done.returncode > 1:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.returncode == 0


def exists(commit: str) -> bool:
    """Whether the commit is in this checkout."""
    return run("cat-file", "-e", f"{commit}^{{commit}}").returncode == 0


def same(commit: str, *paths: str) -> bool:
    """Whether the paths are at the commit as at HEAD."""
    return holds("diff", "--quiet", commit, "HEAD", "--", *paths)


def package(integration: str) -> str:
    """The integration's package, relative to the repository."""
    return f"{(COMPONENT / 'integrations' / integration).as_posix()}/"


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


def passing(integration: str, action: str) -> list[Path]:
    """The action's passing test records: `<action>.json`, and `<action>-<option>.json` for a run with an option set
    (several options `-`-joined, sorted, as a step file's `options` are). A file is credited by its name, so one whose
    `action` or `options` say otherwise stops the run, naming it, rather than credit an action it didn't test."""
    pattern = re.compile(rf"{re.escape(action)}(?:-([^.]+))?\.json")
    found = []
    for path in records(integration):
        if not (match := pattern.fullmatch(path.name)):
            continue
        record, options = load(path), match[1].split("-") if match[1] else None
        if (record["action"], record.get("options")) != (action, options):
            held = f"action {record['action']!r}, options {record.get('options')}"
            raise SystemExit(f"{where(path)}: {held}, but its name says action {action!r}, options {options}")
        if record["result"] == "pass":
            found.append(path)
    return found


def manual(integration: str) -> list[dict]:
    """The rows of the integration's `_manual.json`; none without one."""
    path = test_records_dir(integration) / MANUAL
    return load(path)["signoffs"] if path.is_file() else []


def manual_rows(integration: str, action: str) -> list[list[tuple[str, str | None]]]:
    """The devices, as (model id, class), of each `_manual.json` row whose `passed` names the action."""
    return [
        [(device["model"], device["class"]) for device in row["devices"]]
        for row in manual(integration)
        if action in row.get("passed", ())
    ]


# The coverage check (docs/evidence.md, The coverage check).


def reached(integration: str, action: str) -> set[tuple[str, str | None]]:
    """The classes the action's evidence reached, each with the domain its test targeted: in a passing record, each
    passing test's (format 2: its devices' classes, a native group's members' each; format 1: its `classes`), and each
    `_manual.json` row's devices', whose domain is None, as a row names none. A null class credits none."""
    found: set[tuple[str | None, str | None]] = set()
    for path in passing(integration, action):
        record = load(path)
        for test in record["tests"]:
            if test["result"] != "pass":
                continue
            names = test.get("classes", ()) if record["format"] == 1 else (d["class"] for d in test["devices"])
            found.update((name, test.get("domain")) for name in names)
    for row in manual_rows(integration, action):
        found.update((cls, None) for _, cls in row)
    return {(name, domain) for name, domain in found if name is not None}


def coverage_gaps(registry) -> list[str]:
    """Each class an adapter of an integration that names classes holds as Verified, with no passing record test or
    manual row for its action that reached it: one held on every domain, in any domain; one held on some domains alone
    (OnDomains), in each of them, as a record in one domain proves nothing about another. A manual row names no domain,
    so it covers every domain (the maintainer's judgment, tenet 7). An adapter flagged whole holds none as Verified."""
    gaps = []
    for _, adapter in adapters(registry):
        if not names_classes(adapter) or adapter.scope.experimental:
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
    source: str  # the records' folder, or the manual row as `<file>:<line>`
    commit: str  # a manual row's commit; a record's most common one, for the printout
    tester: str | None = None  # a manual row's handle; a record names none
    actions: tuple[str, ...] | None = None  # a no_call_changed row's `actions`: it vouches for these alone
    vouches: bool = False  # a no_call_changed row, which can keep a reopened record


@dataclass(frozen=True)
class Gate:
    """A changed integration: its last change, its sign-off and why any other was rejected, and its changed adapters,
    split by whether they carry an Untested fix caveat."""

    integration: str
    last_change: str
    signoff: SignOff | None
    rejected: list[str]
    caveated: list[str]
    uncaveated: list[str]
    reruns: tuple[str, ...] = ()  # the suites whose records are reopened, format 1 or failing

    @property
    def passes(self) -> bool:
        return self.signoff is not None or (bool(self.caveated) and not self.uncaveated)


def last_release() -> str | None:
    """The latest release tag (never an RC) that is an ancestor of HEAD, or None if there is none."""
    found = releases(REPO, "HEAD")
    return found[-1][1] if found else None


def last_change(integration: str, base: str | None) -> str | None:
    """The latest commit touching the integration's package since the base, or None if the package is as at the
    base (or, with none, has no commit)."""
    if base and same(base, package(integration)):
        return None
    return git("log", "-1", "--format=%H", f"{base}..HEAD" if base else "HEAD", "--", package(integration)) or None


def modules(registry, integration: str) -> dict[str, str]:
    """The module of each of the integration's adapters, by action, as a path inside the package."""
    root = (REPO / package(integration)).resolve()
    return {
        adapter.action: Path(inspect.getfile(type(adapter))).resolve().relative_to(root).as_posix()
        for _, adapter in adapters(registry)
        if adapter.integration == integration
    }


def package_tree(integration: str, tree: str | None = None, commit: str | None = None) -> str | None:
    """The package's git tree: the one a record cites (`package`), in full, or the package at a commit; None when git
    doesn't have it."""
    name = f"{tree}^{{tree}}" if tree else f"{commit}:{package(integration).rstrip('/')}"
    found = run("rev-parse", "--verify", "--quiet", name)
    return None if found.returncode else found.stdout.strip()


@functools.cache
def differing(old: str | None, new: str | None) -> frozenset[str] | None:
    """The files that differ between two package trees, a rename as both its names; None when either is unknown."""
    if old is None or new is None:
        return None
    return frozenset(filter(None, git("diff", "--name-only", "--no-renames", "-z", old, new).split("\0")))


def stands(changed: Collection[str] | None, action: str, adapter_modules: Mapping[str, str]) -> bool:
    """Whether a record of the action holds through these changed files: each is another adapter's module. A suite that
    is no action's holds through none, and nothing holds across a tree git doesn't have."""
    if changed is None:
        return False
    own = adapter_modules.get(action)
    return not changed if own is None else set(changed) <= set(adapter_modules.values()) - {own}


def carried(
    ran_at: str | None, head: str | None, action: str, adapter_modules: Mapping[str, str], hops: Sequence[tuple]
) -> bool:
    """Whether a record of the action, run at one package tree, stands at HEAD's: directly, or carried across each
    change a `no_call_changed` row vouches for (`hops`: the package before the row's commit, after it, and the row's
    actions), standing up to the one and on from the other."""

    def holds_to(tree: str | None) -> bool:
        return any(stands(differing(at, tree), action, adapter_modules) for at in held)

    held, grew = {ran_at}, True
    while grew:
        grew = False
        for before, after, actions in hops:
            if after not in held and (actions is None or action in actions) and holds_to(before):
                held.add(after)
                grew = True
    return holds_to(head)


def record_signoff(
    integration: str,
    adapter_modules: Mapping[str, str] | None = None,
    vouchers: Sequence[SignOff] = (),
    changed_actions: Collection[str] = (),
) -> tuple[SignOff | None, str | None, tuple[str, ...]]:
    """The integration's test records as one sign-off when every one is format 2, passes and stands (`stands`) from
    its package tree to HEAD's, and every action whose adapter changed since the last release (`changed_actions`) has
    one; else None, why not (no reason when there are no records), and the suites to rerun. A `no_call_changed` row
    (`vouchers`) that names a record's action carries it across the change its commit made: the record must stand up
    to that commit's parent, and then from the commit on, or up to the next such row. A file in the folder that isn't
    JSON is no record, and stops the sign-off; a dotfile is none of the run's."""
    folder, adapter_modules = test_records_dir(integration), adapter_modules or {}
    if foreign := [path.name for path in listed(integration) if path.suffix != ".json"]:
        return (
            None,
            f"{', '.join(foreign)}: not test records, which are JSON (docs/test-records.schema.json); probe findings go"
            " in internals.md, manual sign-offs in _manual.json",
            (),
        )
    if not (paths := records(integration)):
        return None, None, ()
    run = {path.name: load(path) for path in paths}
    old = [name for name, record in run.items() if record["format"] != FORMAT]
    failing = [name for name, record in run.items() if record["format"] == FORMAT and record["result"] != "pass"]
    head = package_tree(integration, commit="HEAD")
    hops = [
        (package_tree(integration, commit=f"{row.commit}~1"), package_tree(integration, commit=row.commit), row.actions)
        for row in vouchers
    ]
    ran_at = {
        name: package_tree(integration, tree=record["package"])
        for name, record in run.items()
        if name not in old and name not in failing
    }
    reopened = [
        name for name, tree in ran_at.items() if not carried(tree, head, run[name]["action"], adapter_modules, hops)
    ]
    changes = set().union(
        *(
            differing(ran_at[name], head) or {f"package {run[name]['package'][:12]}, which git doesn't have"}
            for name in reopened
        )
    )
    missing = sorted(set(changed_actions) - {record["action"] for record in run.values()})
    why = []
    if old:
        why.append(f"{', '.join(old)}: format 1, converted from markdown, so no sign-off: rerun with the rig")
    if failing:
        why.append(f"{', '.join(failing)} fail{'s' * (len(failing) == 1)}")
    if reopened:
        why.append(
            f"{', '.join(reopened)}: reopened by a change since {'its' if len(reopened) == 1 else 'their'} run"
            f" ({', '.join(sorted(changes))}): rerun, or a no_call_changed row at the change's commit names the action"
        )
    if missing:
        why.append(f"{', '.join(missing)}: changed since the last release, with no record")
    if why:
        return None, "; ".join(why), tuple(Path(name).stem for name in (*old, *failing, *reopened, *missing))
    commits = Counter(record["source"]["commit"][:7] for record in run.values())
    return SignOff("record", str(folder.relative_to(REPO)), commits.most_common(1)[0][0]), None, ()


def manual_signoffs(
    integration: str, testers: tuple[str, ...], names_classes: bool = False
) -> tuple[list[SignOff], list[str]]:
    """The integration's `_manual.json` rows, and the errors in them: a class on an integration that names none, or a
    tester who may not sign off. A row in error is no sign-off; a file the schema rejects stops the run."""
    path = test_records_dir(integration) / MANUAL
    allowed = {tester.casefold() for tester in testers}
    found, errors = [], []
    for number, row in enumerate(manual(integration), 1):
        at = f"{where(path)} row {number}"
        if not names_classes and any(device["class"] is not None for device in row.get("devices", ())):
            errors.append(f"{at}: a class, but {integration} names no classes")
        elif row["tester"].casefold() not in allowed:
            errors.append(f"{at}: tester @{row['tester']} is neither a maintainer of {integration} nor a repo one")
        else:
            actions = tuple(row["actions"]) if "actions" in row else None
            found.append(
                SignOff("manual", at, row["commit"], row["tester"], actions, row.get("no_call_changed", False))
            )
    return found, errors


def rejection(signoff: SignOff, integration: str) -> str | None:
    """Why the manual row doesn't hold the integration's package as HEAD does, or None when it does: its commit must
    be in this checkout. A row naming `actions` signs off no package by itself: it only keeps their records."""
    at = f"{signoff.source} at {signoff.commit[:7]}"
    if signoff.actions is not None:
        return f"{at}: names actions, so it keeps their records and signs off no package"
    if not exists(signoff.commit):
        return f"{at}: not in this checkout; cite a commit on main"
    if not same(signoff.commit, package(integration)):
        return f"{at}: the package differs from HEAD's"
    return None


def changed_adapters(registry, integration: str, base: str | None) -> list[tuple[str, object]]:
    """The integration's adapters whose module changed since the base, or all of them when a module of the package
    that is no adapter's changed, or there is no base."""
    own = [(name, adapter) for name, adapter in adapters(registry) if adapter.integration == integration]
    if base is None:
        return own
    changed = set(git("diff", "--name-only", base, "HEAD", "--", package(integration)).split())
    modules = {
        name: Path(inspect.getsourcefile(type(adapter))).resolve().relative_to(REPO.resolve()) for name, adapter in own
    }
    if changed - {module.as_posix() for module in modules.values()}:
        return own
    return [(name, adapter) for name, adapter in own if modules[name].as_posix() in changed]


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
    """The last release tag, a gate per changed integration, and the test-records errors: a `_manual.json` row's, or a
    class named on an integration that names none."""
    base = last_release()
    found, errors = [], []
    names = classed(registry)
    for key, info in registry.integrations.items():
        manual, problems = manual_signoffs(key, (*info.maintainers, *REPO_MAINTAINERS), key in names)
        errors += problems
        if key not in names:
            errors += record_class_errors(key)
        if not (last := last_change(key, base)):
            continue
        changed = changed_adapters(registry, key, base)
        run, why, reruns = record_signoff(
            key,
            modules(registry, key),
            [row for row in manual if row.vouches],
            [adapter.action for _, adapter in changed],
        )
        signoff, rejected = run, [why] if why else []
        for candidate in () if run else manual:
            if not (why := rejection(candidate, key)):
                signoff = candidate
                break
            rejected.append(why)
        caveated, uncaveated = [], []
        for name, adapter in changed:
            caveat = adapter.scope.caveat
            (caveated if caveat is not None and caveat.kind is CaveatKind.UNTESTED_FIX else uncaveated).append(name)
        found.append(Gate(key, last, signoff, rejected, caveated, uncaveated, reruns))
    return base, found, errors


def describe(gate: Gate) -> str:
    """The gate's line: its sign-off, else the caveats standing in, else why it fails."""
    head = f"{gate.integration}: changed at {gate.last_change[:7]}"
    if signoff := gate.signoff:
        tester = f", @{signoff.tester}" if signoff.tester else ""
        return f"{head}; signed off by {signoff.kind} {signoff.source} at {signoff.commit[:7]}{tester}"
    if gate.passes:
        return f"{head}; no sign-off, Untested fix stands in on every changed adapter: {', '.join(gate.caveated)}"
    rejected = "".join(f" ({why})" for why in gate.rejected)
    bare = ", ".join(gate.uncaveated) or "any adapter"
    return f"{head}; no sign-off of its package{rejected}, and no Untested fix on {bare}"


def release_notes(registry, found: list[Gate]) -> str:
    """The release notes' call for testers: the changed integrations without a sign-off, and every adapter with an
    Untested fix caveat."""
    unsigned = [registry.integrations[gate.integration].title for gate in found if gate.signoff is None]
    untested = [
        name
        for name, adapter in adapters(registry)
        if adapter.scope.caveat is not None and adapter.scope.caveat.kind is CaveatKind.UNTESTED_FIX
    ]
    parts = []
    if unsigned:
        parts.append(
            "## Help us test\n\nThese integrations changed since the last release, and no maintainer has tested the"
            f" change on a device yet. If you use one, please [report whether it works]({DEVICE_REPORT}).\n\n"
            + "".join(f"- {title}\n" for title in unsigned)
        )
    if untested:
        parts.append(
            "## ⚠️ Untested fix\n\nThese ship a fix nobody could test before the release. If you use one, please"
            f" [report whether it works]({DEVICE_REPORT}).\n\n" + "".join(f"- {name}\n" for name in untested)
        )
    return "\n".join(parts)


def main(argv: list[str] | None = None, registry: AdapterRegistry | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--coverage", type=Path, help="coverage.json from pytest --cov-report=json")
    parser.add_argument(
        "--signoffs", action="store_true", help="fail on an integration changed since the last release with no sign-off"
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
                print(json.dumps({gate.integration: list(gate.reruns) for gate in found if gate.signoff is None}))
            elif args.json:
                print(json.dumps([gate.integration for gate in found if gate.signoff is None]))
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
