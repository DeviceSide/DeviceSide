#!/usr/bin/env python3
"""Check the release gates: the coverage bar, a sign-off for each integration changed since the last release, and the
classes' coverage check.

The rules are in docs/evidence.md (Release gate, Sign-off format); this is how the checks read them.

--coverage coverage.json (pytest --cov-report=json): every module under `core/` and `integrations/`, bar `__init__.py`,
needs at least 95% line coverage; one missing from the report has none.

--signoffs: an integration is changed when its package (`integrations/<key>/`) differs between the last release tag (the
latest `vX.Y.Z` that is an ancestor of HEAD; with none, every integration is changed) and HEAD, so a reverted change is
none; its last change is the latest commit touching the package. It needs a sign-off that holds the package as HEAD
does: its test records as one run, by the package tree they cite (the tree of `integrations/<key>/` at the run's commit,
compared to HEAD's, so a run on a branch counts after a squash merge, even once the branch is deleted), or a
`_manual.json` row, by its commit, which is in this checkout. The records are one run when every one is format 2, cites
the same package tree, whatever commit it ran at, and passes; a partial run (records citing different trees), a format 1
record (converted from markdown) or a failing record is none, until a rerun of the missing, old or failing actions
completes it. Without one, a ⚠️ Untested fix caveat stands in when every changed adapter carries it: each adapter whose
module changed, or all of the package's when a module that is no adapter's changed (a shared helper). Prints a line per
changed integration naming its sign-off (kind, commit, tester) or the caveats standing in, and fails on each with
neither, saying why its records and each manual row were rejected. With --json, prints instead the changed integrations
without a sign-off, as a JSON list: the rig's run selection. It also runs the coverage check, failing on each gap: for
an integration that names classes (`IntegrationInfo.capability`), every class an adapter not flagged whole holds as
Verified needs a passing test that reached it in a passing record of the action (format 2: a device of the test with
that class, a native group's test crediting each member's; format 1: the test's `classes`), or a `_manual.json` row
whose `passed` names the action and one of whose devices has the class. `scripts/gen_compat.py` prints the same gaps as
warnings on every run (`coverage_gaps`).

--notes notes.md: writes the release notes' call for testers, with a link to the device report form: the changed
integrations without a sign-off, and every adapter with an Untested fix caveat. Empty when there are none.

Test records are JSON, in `docs/integrations/<key>/test-records/`, each checked against docs/test-records.schema.json
(the format's one home; docs/evidence.md, Sign-off format, describes it); a file of the wrong kind for its name, or of
another integration than its folder's, is an error. A rig record per suite (`<action>.json`, `<action>-<option>.json`,
read as the action's evidence; another suite's, as `lifecycle.json`, counts only toward the run), `_manual.json`, whose
rows are manual sign-offs, and `_facts.json`, the fact cases' results, which nothing here reads. Under --signoffs, a
file there that isn't JSON (a markdown record) is no record, named. A manual row's tester must be one of the
integration's maintainers or a repo maintainer (`REPO_MAINTAINERS`), and its devices may name a class only on an
integration that names classes. A record names no tester: review of the PR that lands it checks who ran it.

Exits 1 on an integration that failed to import, whatever the options, and on any failure of the checks asked for. A
git error fails the run rather than pass a gate unseen.

Usage: scripts/check_release.py [--coverage coverage.json] [--signoffs [--json]] [--notes notes.md]
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


def records(integration: str) -> list[Path]:
    """The integration's rig records, every suite's: the JSON files not named with a leading `_`."""
    folder = test_records_dir(integration)
    return sorted(path for path in folder.glob("*.json") if not path.name.startswith("_"))


def passing(integration: str, action: str) -> list[Path]:
    """The action's passing test records: `<action>.json`, and `<action>-<option>.json` for a run with an option set."""
    pattern = re.compile(rf"{re.escape(action)}(-[^.]+)?\.json")
    return [path for path in records(integration) if pattern.fullmatch(path.name) and load(path)["result"] == "pass"]


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


def reached(integration: str, action: str) -> set[str]:
    """The classes the action's evidence reached: in a passing record, each passing test's (format 2: its devices'
    classes, a native group's members' each; format 1: its `classes`), and each `_manual.json` row's devices'. A null
    class credits none."""
    found = set()
    for path in passing(integration, action):
        record = load(path)
        for test in record["tests"]:
            if test["result"] != "pass":
                continue
            found.update(test.get("classes", ()) if record["format"] == 1 else (d["class"] for d in test["devices"]))
    for row in manual_rows(integration, action):
        found.update(cls for _, cls in row)
    return found - {None}


def coverage_gaps(registry) -> list[str]:
    """Each class an adapter of an integration that names classes holds as Verified, with no passing record test or
    manual row for its action that reached it. An adapter flagged whole holds none as Verified."""
    gaps = []
    for _, adapter in adapters(registry):
        if registry.integrations[adapter.integration].capability is None or adapter.scope.experimental:
            continue
        held = [item for item, level in adapter.scope.capabilities.items() if level is Level.VERIFIED]
        missing = sorted(set(held) - reached(adapter.integration, adapter.action))
        gaps += [
            f"{adapter.integration} {adapter.action}: `{item}` is Verified but no record reaches it" for item in missing
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
    tree: str | None = None  # a record's cited Package tree, which it is checked by; a manual row has none


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


def record_signoff(integration: str) -> tuple[SignOff | None, str | None]:
    """The integration's test records as one sign-off when they are one passing run of format 2, every record citing
    the same package tree; else None and why not, or no reason when there are no records. A file in the folder that
    isn't JSON is no record, and stops the sign-off."""
    folder = test_records_dir(integration)
    if foreign := sorted(path.name for path in folder.glob("*") if path.is_file() and path.suffix != ".json"):
        return None, (
            f"{', '.join(foreign)}: not test records, which are JSON (docs/test-records.schema.json); probe findings go"
            " in internals.md, manual sign-offs in _manual.json"
        )
    if not (paths := records(integration)):
        return None, None
    run = {path.name: load(path) for path in paths}
    if old := [name for name, record in run.items() if record["format"] != FORMAT]:
        return None, f"{', '.join(old)}: format 1, converted from markdown, so no sign-off: rerun with the rig"
    trees = Counter(record["package"][:12] for record in run.values())
    if len(trees) > 1:
        counts = ", ".join(f"{tree}: {n}" for tree, n in trees.most_common())
        return None, f"records cover {len(trees)} package versions ({counts}); a sign-off is one run of one package"
    (tree,) = trees
    if failing := [name for name, record in run.items() if record["result"] != "pass"]:
        return None, f"{', '.join(failing)} fail{'s' * (len(failing) == 1)} at package {tree}"
    commits = Counter(record["source"]["commit"][:7] for record in run.values())
    return SignOff("record", str(folder.relative_to(REPO)), commits.most_common(1)[0][0], tree=tree), None


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
            found.append(SignOff("manual", at, row["commit"], row["tester"]))
    return found, errors


def rejection(signoff: SignOff, integration: str) -> str | None:
    """Why the sign-off doesn't hold the integration's package as HEAD does, or None when it does. A record is
    checked by its Package tree, a manual row by its commit, which must be in this checkout."""
    if signoff.tree:
        if not git("rev-parse", f"HEAD:{package(integration)}").startswith(signoff.tree):
            return f"{signoff.source} at package {signoff.tree}: the package differs from HEAD's"
        return None
    at = f"{signoff.source} at {signoff.commit[:7]}"
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


def gates(registry) -> tuple[str | None, list[Gate], list[str]]:
    """The last release tag, a gate per changed integration, and the `_manual.json` errors."""
    base = last_release()
    found, errors = [], []
    for key, info in registry.integrations.items():
        manual, problems = manual_signoffs(key, (*info.maintainers, *REPO_MAINTAINERS), info.capability is not None)
        errors += problems
        if not (last := last_change(key, base)):
            continue
        run, why = record_signoff(key)
        signoff, rejected = None, [why] if why else []
        for candidate in [run, *manual] if run else manual:
            if not (why := rejection(candidate, key)):
                signoff = candidate
                break
            rejected.append(why)
        caveated, uncaveated = [], []
        for name, adapter in changed_adapters(registry, key, base):
            caveat = adapter.scope.caveat
            (caveated if caveat is not None and caveat.kind is CaveatKind.UNTESTED_FIX else uncaveated).append(name)
        found.append(Gate(key, last, signoff, rejected, caveated, uncaveated))
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
    parser.add_argument("--json", action="store_true", help="with --signoffs: list the integrations without one")
    parser.add_argument("--notes", type=Path, help="write the release notes' call for testers here")
    args = parser.parse_args(argv)
    if args.json and not args.signoffs:
        parser.error("--json needs --signoffs")

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
            if args.json:
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
