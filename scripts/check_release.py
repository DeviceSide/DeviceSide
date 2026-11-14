#!/usr/bin/env python3
"""Check the release gates: the coverage bar, a sign-off for each integration changed since the last release, and the
classes' coverage check.

The rules are in docs/evidence.md (Release gate, Sign-off format); this is how the checks read them.

--coverage coverage.json (pytest --cov-report=json): every module under `core/` and `integrations/`, bar `__init__.py`,
needs at least 95% line coverage; one missing from the report has none.

--signoffs: an integration is changed when its package (`integrations/<key>/`) differs between the last release tag (the
latest `vX.Y.Z` that is an ancestor of HEAD; with none, every integration is changed) and HEAD, so a reverted change is
none; its last change is the latest commit touching the package. It needs a sign-off that holds the package as HEAD
does: its test records as one run, by the Package tree they cite (the tree of `integrations/<key>/` at the run's commit,
compared to HEAD's, so a run on a branch counts after a squash merge, even once the branch is deleted), or a
`_manual.md` row, by its commit, which is in this checkout. The records are one run when every one cites the same
Package tree, whatever commit it ran at, and passes; a partial run (records citing different trees), a record with no
Package row or a failing record is none, until a rerun of the missing or failing actions completes it. Without one, a ⚠️
Untested fix caveat stands in when every changed adapter carries it: each adapter whose module changed, or all of the
package's when a module that is no adapter's changed (a shared helper). Prints a line per changed integration naming its
sign-off (kind, commit, tester) or the caveats standing in, and fails on each with neither, saying why its records and
each manual row were rejected. With --json, prints instead the changed integrations without a sign-off, as a JSON list:
the rig's run selection. It also runs the coverage check, failing on each gap: for an integration that names classes
(`IntegrationInfo.capability`), every class an adapter not flagged whole holds as Verified needs a passing test that
reached it in a passing record of the action (the Tests table's Capability cell; a native group's credits each class it
lists, a dash none), or a `_manual.md` row whose Passed names the action and whose Capabilities lists it.
`scripts/gen_compat.py` prints the same gaps as warnings on every run (`coverage_gaps`).

--notes notes.md: writes the release notes' call for testers, with a link to the device report form: the changed
integrations without a sign-off, and every adapter with an Untested fix caveat. Empty when there are none.

Test records are the rig's, `docs/integrations/<key>/test-records/<action>*.md`: their Source row cites the commit
(`commit `1a2b3c4``), their Package row the package tree (`| Package | `0123456789ab` |`), their Result row the outcome.
A file whose name starts with `_` is no record (`_facts.md`), bar `_manual.md`, whose table rows are manual sign-offs.
Under --signoffs, any other file is an error, named: a record without the rig's Source row (`| Source | rig run
(`scripts/rig.py`), commit `1a2b3c4` |`) is no rig record. Probe findings go in internals.md, manual sign-offs in
`_manual.md`:

    | Date | Commit | Tester | Devices | Passed |
    |---|---|---|---|---|
    | 2026-11-12 | `1a2b3c4` | @handle | `S3SW-001X8EU`, `S3BL-C010007AEU` | `turn_on_for`, `set_auto_off` |
    | 2026-11-12 | `1a2b3c4` | @handle | - | no call changed |

An integration that names classes adds a Capabilities column before Passed: the classes the row's tests reached, or a
dash for none (`| Date | Commit | Tester | Devices | Capabilities | Passed |`; `| - | - | no call changed |`). Prose and
headings around the table are ignored. Under --signoffs, any other `|` line is an error, as is a tester who
is neither one of the integration's maintainers nor a repo maintainer (`REPO_MAINTAINERS`). A record names no tester:
review of the PR that lands it checks who ran it.

Exits 1 on an integration that failed to import, whatever the options, and on any failure of the checks asked for. A
git error fails the run rather than pass a gate unseen.

Usage: scripts/check_release.py [--coverage coverage.json] [--signoffs [--json]] [--notes notes.md]
"""

import argparse
import inspect
import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

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
RIG_SOURCE = re.compile(r"^\| Source \| rig run \(`scripts/rig\.py`\), commit `[0-9a-f]{7,40}` \|", re.MULTILINE)
CITED_COMMIT = re.compile(r"^\| Source \|.*\bcommit `([0-9a-f]{7,40})`", re.MULTILINE)
CITED_TREE = re.compile(r"^\| Package \| `([0-9a-f]{12,40})` \|", re.MULTILINE)
RESULT = re.compile(r"^\| Result \| (\S+) \|", re.MULTILINE)
MANUAL = "_manual.md"
# The header and its rule, without and with the Capabilities column of an integration that names classes.
MANUAL_HEADER = (
    "| Date | Commit | Tester | Devices | Passed |",
    "|---|---|---|---|---|",
    "| Date | Commit | Tester | Devices | Capabilities | Passed |",
    "|---|---|---|---|---|---|",
)
BACKTICKED = r"`[^`|]+`(?:, `[^`|]+`)*"
# Groups: commit, tester, then the Devices, Capabilities and Passed cells (None for a "no call changed" row, and
# Capabilities for a row without the column).
MANUAL_ROW = re.compile(
    rf"\| \d{{4}}-\d{{2}}-\d{{2}} \| `([0-9a-f]{{7,40}})` \| @([A-Za-z0-9-]+)"
    rf" \| (?:({BACKTICKED})(?: \| ({BACKTICKED}|-))? \| ({BACKTICKED})|-(?: \| -)? \| no call changed) \|"
)
BACKTICKS = re.compile(r"`([^`]+)`")
# A passing row of a record's Tests table: | `test` | `domain` (role) | pass |, or with the Capability column
# (docs/evidence.md, Sign-off format): | `test` | `domain` (role) | `class`, ... | pass |, or a dash for none.
PASSED = re.compile(
    r"^\| `[^`]+` \| (?P<target>[^|\n]*) \|(?: (?P<capability>`[^`|\n]+`(?:, `[^`|\n]+`)*|-) \|)? pass \|$",
    re.MULTILINE,
)
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


def result(record: Path) -> str | None:
    """The record's Result row (`pass`, `fail`, ...), or None if it has none."""
    return m[1] if (m := RESULT.search(record.read_text())) else None


def passing(integration: str, action: str) -> list[Path]:
    """The adapter's passing test records: `<action>.md`, and `<action>-<option>.md` for a run with an option set."""
    pattern = re.compile(rf"{re.escape(action)}(-[^.]+)?\.md")
    found = (path for path in test_records_dir(integration).glob("*.md") if pattern.fullmatch(path.name))
    return sorted(path for path in found if result(path) == "pass")


def manual_rows(integration: str, action: str) -> list[tuple[list[str], set[str]]]:
    """The model ids and classes of each `_manual.md` row whose Passed names the action. A line that is no row of the
    format is skipped: `--signoffs` reports it."""
    path = test_records_dir(integration) / MANUAL
    rows = []
    for line in path.read_text().splitlines() if path.is_file() else []:
        if (row := MANUAL_ROW.fullmatch(line.strip())) and row[5] and action in BACKTICKS.findall(row[5]):
            rows.append((BACKTICKS.findall(row[3]), set(BACKTICKS.findall(row[4] or ""))))
    return rows


# The coverage check (docs/evidence.md, The coverage check).


def reached(integration: str, action: str) -> set[str]:
    """The classes the action's evidence reached: each passing test's Capability cell in a passing record, and each
    `_manual.md` row's Capabilities. A group's cell credits every class it lists; a dash credits none."""
    found = set()
    for record in passing(integration, action):
        for row in PASSED.finditer(record.read_text()):
            found.update(BACKTICKS.findall(row["capability"] or ""))
    for _, classes in manual_rows(integration, action):
        found |= classes
    return found


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
    """The integration's test records as one sign-off when they are one passing run, every record citing the same
    package tree; else None and why not, or no reason when there are no records. `_`-prefixed files are not records; a
    file without the rig's Source row is an error."""
    folder = test_records_dir(integration)
    if not (records := [path for path in sorted(folder.glob("*.md")) if not path.name.startswith("_")]):
        return None, None
    if foreign := [path.name for path in records if not RIG_SOURCE.search(path.read_text())]:
        return None, (
            f"{', '.join(foreign)}: not rig records; probe findings go in internals.md, manual sign-offs in _manual.md"
        )
    if missing := [path.name for path in records if not CITED_TREE.search(path.read_text())]:
        return None, f"{', '.join(missing)}: no Package row: rerun with the rig"
    trees = Counter(CITED_TREE.search(path.read_text())[1][:12] for path in records)
    if len(trees) > 1:
        counts = ", ".join(f"{tree}: {n}" for tree, n in trees.most_common())
        return None, f"records cover {len(trees)} package versions ({counts}); a sign-off is one run of one package"
    (tree,) = trees
    if failing := [path.name for path in records if result(path) != "pass"]:
        return None, f"{', '.join(failing)} fail{'s' * (len(failing) == 1)} at package {tree}"
    commits = Counter(m[1][:7] for path in records if (m := CITED_COMMIT.search(path.read_text())))
    return SignOff("record", str(folder.relative_to(REPO)), commits.most_common(1)[0][0], tree=tree), None


def manual_signoffs(integration: str, testers: tuple[str, ...]) -> tuple[list[SignOff], list[str]]:
    """The integration's `_manual.md` rows, and the errors in it: a `|` line that is neither the header nor a row of
    the format, or a row whose tester may not sign off. A row in error is no sign-off."""
    path = test_records_dir(integration) / MANUAL
    if not path.is_file():
        return [], []
    label = path.relative_to(REPO)
    allowed = {tester.casefold() for tester in testers}
    found, errors = [], []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line.startswith("|") or line in MANUAL_HEADER:
            continue
        if not (row := MANUAL_ROW.fullmatch(line)):
            errors.append(f"{label}:{number}: not a row of `{MANUAL_HEADER[0]}`: {line}")
        elif row[2].casefold() not in allowed:
            errors.append(f"{label}:{number}: tester @{row[2]} is neither a maintainer of {integration} nor a repo one")
        else:
            found.append(SignOff("manual", f"{label}:{number}", row[1], row[2]))
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
    """The last release tag, a gate per changed integration, and the `_manual.md` errors."""
    base = last_release()
    found, errors = [], []
    for key, info in registry.integrations.items():
        manual, problems = manual_signoffs(key, (*info.maintainers, *REPO_MAINTAINERS))
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
