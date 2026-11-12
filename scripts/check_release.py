#!/usr/bin/env python3
"""Check the release gates: the coverage bar, and a sign-off for each integration changed since the last release.

The rules are in docs/evidence.md (Release gate, Sign-off format); this is how the checks read them.

--coverage coverage.json (pytest --cov-report=json): every module under `core/` and `integrations/`, bar `__init__.py`,
needs at least 95% line coverage; one missing from the report has none.

--signoffs: an integration is changed when its package (`integrations/<key>/`) differs between the last release tag
(the latest `vX.Y.Z` that is an ancestor of HEAD; with none, every integration is changed) and HEAD, so a reverted
change is none; its last change is the latest commit touching the package. It needs a sign-off, a test record whose
Result is `pass` or a `_manual.md` row, whose commit is in this checkout, has that last change as an ancestor
(`git merge-base --is-ancestor`) and holds the package as HEAD does. Without one, a ⚠️ Untested fix caveat stands in
when every changed adapter carries it: each adapter whose module changed, or all of the package's when a module that
is no adapter's changed (a shared helper). Prints a line per changed integration naming its sign-off (kind, commit,
tester) or the caveats standing in, and fails on each with neither, saying why each sign-off it found was rejected.
With --json, prints instead the changed integrations without a sign-off, as a JSON list: the rig's run selection.

--notes notes.md: writes the release notes' call for testers, with a link to the device report form: the changed
integrations without a sign-off, and every adapter with an Untested fix caveat. Empty when there are none.

Test records are the rig's, `docs/integrations/<key>/test-records/<action>*.md`: their Source row cites the commit
(`commit `1a2b3c4``), their Result row the outcome. A file whose name starts with `_` is no record (`_facts.md`), bar
`_manual.md`, whose table rows are manual sign-offs:

    | Date | Commit | Tester | Devices | Passed |
    |---|---|---|---|---|
    | 2026-11-12 | `1a2b3c4` | @handle | `S3SW-001X8EU`, `S3BL-C010007AEU` | `turn_on_for`, `set_auto_off` |
    | 2026-11-12 | `1a2b3c4` | @handle | - | no call changed |

Prose and headings around the table are ignored. Under --signoffs, any other `|` line is an error, as is a tester who
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
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from custom_components.deviceside.config_flow import REPORT_URL  # noqa: E402
from custom_components.deviceside.core.registry import AdapterRegistry  # noqa: E402
from custom_components.deviceside.core.scope import CaveatKind  # noqa: E402
from scripts.check_tag import git as git_in  # noqa: E402
from scripts.check_tag import releases  # noqa: E402
from scripts.gen_codeowners import REPO_MAINTAINERS  # noqa: E402

COVERAGE_BAR = 95.0
COMPONENT = Path("custom_components") / "deviceside"
BUNDLES = REPO / "docs" / "integrations"
CITED_COMMIT = re.compile(r"^\| Source \|.*\bcommit `([0-9a-f]{7,40})`", re.MULTILINE)
RESULT = re.compile(r"^\| Result \| (\S+) \|", re.MULTILINE)
MANUAL = "_manual.md"
MANUAL_HEADER = ("| Date | Commit | Tester | Devices | Passed |", "|---|---|---|---|---|")
BACKTICKED = r"`[^`|]+`(?:, `[^`|]+`)*"
MANUAL_ROW = re.compile(
    rf"\| \d{{4}}-\d{{2}}-\d{{2}} \| `([0-9a-f]{{7,40}})` \| @([A-Za-z0-9-]+)"
    rf" \| (?:{BACKTICKED} \| {BACKTICKED}|- \| no call changed) \|"
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
    """For a command whose exit 1 means no (`merge-base --is-ancestor`, `diff --quiet`): whether it exited 0. Raises on
    any other exit, a git error."""
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
    source: str  # the record, or the manual row as `<file>:<line>`
    commit: str
    tester: str | None = None  # a manual row's handle; a record names none


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


def record_signoffs(integration: str) -> list[SignOff]:
    """The integration's passing test records that cite a commit. `_`-prefixed files are not records."""
    found = []
    for path in sorted(test_records_dir(integration).glob("*.md")):
        if path.name.startswith("_"):
            continue
        if result(path) == "pass" and (cited := CITED_COMMIT.search(path.read_text())):
            found.append(SignOff("record", str(path.relative_to(REPO)), cited[1]))
    return found


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


def rejection(signoff: SignOff, integration: str, last: str) -> str | None:
    """Why the sign-off doesn't sign off the integration's last change, or None when it does."""
    at = f"{signoff.source} at {signoff.commit[:7]}"
    if not exists(signoff.commit):
        return f"{at}: not in this checkout; cite a commit on main"
    if not holds("merge-base", "--is-ancestor", last, signoff.commit):
        return f"{at}: predates the last change {last[:7]}"
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
        signoff, rejected = None, []
        for candidate in [*record_signoffs(key), *manual]:
            if not (why := rejection(candidate, key, last)):
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
    return f"{head}; no sign-off at or after it{rejected}, and no Untested fix on {bare}"


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
