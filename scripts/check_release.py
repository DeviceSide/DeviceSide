#!/usr/bin/env python3
"""Check the adapters against the release gates: the coverage bar, no experimental adapter in a release, and test
records that pass and are as new as the code they prove.

The release flag and the levels are defined in CLAUDE.md § Release flag. --release fails on the flag only, not on an
Experimental item; --records weighs only an adapter's code against its records, as items below Verified have none.
Records live in each integration's bundle (`test_records_dir`).

An adapter's code (`adapter_code`) is its module and what that module and its integration package import, followed
into `core/`, so a shared helper counts for every adapter that reaches it: its coverage is held to the bar and a
change to it stales those adapters' records. `actions/` and imports made only for type checking are not followed.

Exits 1 on any integration that failed to import, whatever the options; with --coverage, any module of an adapter's
code, bar `__init__.py`, under 95% line coverage; with --release, any experimental adapter; with --records, any
released adapter with a Verified call that lacks `<action>.md` or an `<action>-<option>.md` for one of its scope's
options, a record whose Result is not `pass`, or code changed after the commit one of its records cites. Each record
holds the latest run of its call or option. Setting or clearing `experimental`, `unmaintained` or `at_risk`, or
changing an integration's `maintainers`, is not a change to the code: no call reads them (setup reads `unmaintained`
and `at_risk` only to warn, and registration checks `maintainers`).

**Retests.** An adapter with no Verified call has no rig coverage, so a record can't gate it; it still needs a retest
as new as its code once it holds a call that ships on (Documented or better; an adapter whose calls are all
Experimental needs none). A retest is any of: a passing record of the adapter (as above); a line of the integration's
`test-records/_manual.md` by one of its maintainers; an accepted working report in its devices.yaml whose `deviceside`
version is a tag (`v<version>`). Each is fresh when the adapter's code is unchanged, bar the flags, between the commit
it names (a manual line's, the report's tag) and HEAD. An adapter with a Verified call keeps needing its records.

A `_manual.md` line is a table row: date, commit, tester, devices, what passed.

    | Date | Commit | Tester | Devices | Passed |
    |---|---|---|---|---|
    | 2026-11-11 | `1a2b3c4` | @handle | `LCA001`, `SNSPL-10` | `turn_on_for`, `set_auto_off` |

Devices are model ids (docs/models.yaml), never a household's device names; Passed names the actions that worked,
each covering that integration's adapter for the action. Prose and headings around the table are ignored; any other
`|` line is an error under --records, as is a tester who is not one of the integration's maintainers.

**At risk.** --records lists each adapter that needs a retest and has none fresh. --release fails on one unless its
scope sets `at_risk` (it then ships live, marked ⚠️ At risk), and on an `at_risk` adapter that has a fresh retest, as
that retest clears the mark. --notes writes the release notes' call for testers: the at-risk adapters, with a link to
the device report form; empty when there are none.

Usage: scripts/check_release.py [--coverage coverage.json] [--release] [--records] [--notes notes.md]
"""

import argparse
import ast
import inspect
import io
import json
import os
import re
import subprocess
import sys
import tokenize
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
COMPONENT = "custom_components.deviceside"

from custom_components.deviceside.config_flow import REPORT_URL  # noqa: E402
from custom_components.deviceside.core.registry import AdapterRegistry  # noqa: E402
from custom_components.deviceside.core.scope import Level  # noqa: E402

COVERAGE_BAR = 95.0
BUNDLES = REPO / "docs" / "integrations"
CITED_COMMIT = re.compile(r"^\| Source \|.*\bcommit `([0-9a-f]{7,40})`", re.MULTILINE)
RESULT = re.compile(r"^\| Result \| (\S+) \|", re.MULTILINE)
MANUAL = "_manual.md"
MANUAL_HEADER = ("| Date | Commit | Tester | Devices | Passed |", "|---|---|---|---|---|")
BACKTICKED = r"`[^`|]+`(?:, `[^`|]+`)*"
MANUAL_ROW = re.compile(
    rf"\| (\d{{4}}-\d{{2}}-\d{{2}}) \| `([0-9a-f]{{7,40}})` \| @([A-Za-z0-9-]+) \| ({BACKTICKED}) \| ({BACKTICKED}) \|"
)
DEVICE_REPORT = f"{REPORT_URL}?template=device_report.yml"


def adapters(registry: AdapterRegistry) -> list[tuple[str, object]]:
    """Every adapter, named `integration / action`."""
    return [
        (f"{integration} / {action}", adapter)
        for action, integration, adapter in registry.matrix()
        if adapter is not None
    ]


def coverage_errors(registry: AdapterRegistry, coverage: dict) -> list[str]:
    """A module of any adapter's code, bar the package's `__init__.py`, under the bar or absent from the report is an
    error, once per module, naming the adapters whose code it is."""
    percent = {}
    for name, entry in coverage["files"].items():
        summary = entry["summary"]
        statements = summary["num_statements"]
        percent[(REPO / name).resolve()] = 100.0 * summary["covered_lines"] / statements if statements else 100.0
    users: dict[Path, list[str]] = {}
    for name, adapter in adapters(registry):
        for path in adapter_code(Path(inspect.getsourcefile(type(adapter)))):
            if path.name != "__init__.py":
                users.setdefault(path.resolve(), []).append(name)
    errors = []
    for path, names in sorted(users.items()):
        if (covered := percent.get(path, 0.0)) < COVERAGE_BAR:
            errors.append(
                f"{path.relative_to(REPO)}: {covered:.1f}% line coverage, under {COVERAGE_BAR:.0f}%"
                f" (code of {', '.join(names)})"
            )
    return errors


def type_checking(node: ast.AST) -> bool:
    """`if TYPE_CHECKING:` or `if typing.TYPE_CHECKING:`, whose body never runs."""
    return isinstance(node, ast.If) and (
        (isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING")
        or (isinstance(node.test, ast.Attribute) and node.test.attr == "TYPE_CHECKING")
    )


def run_time_nodes(tree: ast.AST) -> Iterator[ast.AST]:
    """`ast.walk`, bar the body of each `if TYPE_CHECKING:` block."""
    todo = [tree]
    while todo:
        node = todo.pop()
        yield node
        if type_checking(node):
            todo += [node.test, *node.orelse]
        else:
            todo += ast.iter_child_nodes(node)


def absolute_component_imports(node: ast.AST) -> list[str]:
    """The component modules an `import` or a level-0 `from` names absolutely: `custom_components.deviceside...`,
    `from custom_components import deviceside` included."""
    if isinstance(node, ast.Import):
        names = [alias.name for alias in node.names]
    elif isinstance(node, ast.ImportFrom) and not node.level and node.module == COMPONENT.partition(".")[0]:
        names = [f"{node.module}.{alias.name}" for alias in node.names]
    elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
        names = [node.module]
    else:
        return []
    return [name for name in names if name == COMPONENT or name.startswith(f"{COMPONENT}.")]


def relative_imports(path: Path) -> list[tuple[ast.ImportFrom, Path]]:
    """Each relative import the module runs, function bodies included and `if TYPE_CHECKING:` blocks left out, with
    the path its `from` part names, resolved by its level against the module's package: `from ...core.x import a` in
    `integrations/hue/fade.py` names `<deviceside>/core/x`, without a suffix, as it may be a module or a package.
    Raises ValueError on an absolute import of the component, which the check doesn't follow, so it would drop code
    from the check unseen."""
    imports = []
    for node in run_time_nodes(ast.parse(path.read_text(), str(path))):
        # Component code only: the tests' fake registries point the walk at test modules, which import absolutely.
        if "custom_components" in path.parts and (absolute := absolute_component_imports(node)):
            raise ValueError(f"{path}: absolute import of `{absolute[0]}`; make it relative so the check follows it")
        if isinstance(node, ast.ImportFrom) and node.level:
            base = path.parents[node.level - 1]
            imports.append((node, base.joinpath(*node.module.split(".")) if node.module else base))
    return imports


def imported_modules(importer: Path, node: ast.ImportFrom, target: Path, roots: Collection[Path]) -> list[Path]:
    """The modules an import runs, if it lands in one of the roots: the module it names, or, for a package, each
    submodule it imports, with the `__init__.py` of every package on the way down from the root. An import landing
    outside the roots runs no code the check follows. Raises ValueError on one inside a root that names no module, as
    that would drop code from the check unseen."""
    if not (root := next((root for root in roots if target.is_relative_to(root)), None)):
        return []
    dots = "." * node.level + (node.module or "")
    if target.with_suffix(".py").is_file():
        found = [target.with_suffix(".py")]
    elif target.is_dir():
        found = []
        for alias in node.names:
            if not (module := target / f"{alias.name}.py").is_file():
                raise ValueError(
                    f"{importer}: can't resolve `from {dots}{'.' if node.module else ''}{alias.name}`"
                    f" to a module of {target}"
                )
            found.append(module)
    else:
        raise ValueError(f"{importer}: can't resolve `from {dots}` to a module of {root}")
    package = found[0].parent
    while package.is_relative_to(root):
        if (init := package / "__init__.py").is_file():
            found.append(init)
        package = package.parent
    return found


def adapter_names(init: Path) -> set[str]:
    """The names the package's `ADAPTERS = [...]` lists."""
    for node in ast.walk(ast.parse(init.read_text(), str(init))):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ADAPTERS" for t in node.targets):
            return {element.id for element in getattr(node.value, "elts", []) if isinstance(element, ast.Name)}
    return set()


def adapter_code(module: Path) -> list[Path]:
    """The adapter's module, its integration package's `__init__.py`, and every module of that package or of `core/`
    either imports, directly or through another: the code behind the call it sends, the group expansion, call resolver
    and shared helpers included. The sibling adapter modules `__init__.py` imports for `ADAPTERS` are left out, unless
    the adapter's own code reaches them. `actions/` (the action surface, not the call), other integrations and the
    rest of the component are left out. Raises ValueError on a relative import into the package or `core/` that names
    no module, or an absolute import of the component, either of which would otherwise drop code from the check
    unseen."""
    package = module.parent
    roots = (package, package.parents[1] / "core")
    init = package / "__init__.py"
    adapters = adapter_names(init)

    def modules(importer: Path, skip: set[str] | frozenset[str] = frozenset()) -> list[Path]:
        return [
            path
            for node, target in relative_imports(importer)
            if skip.isdisjoint(alias.name for alias in node.names)
            for path in imported_modules(importer, node, target, roots)
        ]

    found: set[Path] = {init}
    todo = [module, *modules(init, adapters)]
    while todo:
        if (path := todo.pop()) in found:
            continue
        found.add(path)
        todo += modules(path)
    return sorted(found)


def code_of(adapter) -> list[str]:
    """The adapter's code (`adapter_code`), as paths relative to the repository."""
    return [str(path.relative_to(REPO)) for path in adapter_code(Path(inspect.getsourcefile(type(adapter))))]


def test_records_dir(integration: str) -> Path:
    """Where the integration's test records live: `docs/integrations/<integration>/test-records/`. The rig writes
    there."""
    return BUNDLES / integration / "test-records"


def records(integration: str, action: str) -> list[Path]:
    """The adapter's test records: `<action>.md`, and `<action>-<option>.md` for a run with an option set."""
    pattern = re.compile(rf"{re.escape(action)}(-[^.]+)?\.md")
    return sorted(path for path in test_records_dir(integration).glob("*.md") if pattern.fullmatch(path.name))


def record_names(action: str, options: Collection[str] = ()) -> list[str]:
    """The records an adapter needs: `<action>.md`, then `<action>-<option>.md` for each option, as `records` names
    them."""
    return [f"{action}.md", *(f"{action}-{option}.md" for option in sorted(options))]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


# The arguments no call reads, each with the literal types it takes: setting or clearing one is not a change.
# `maintainers` is an `IntegrationInfo` argument, a tuple of handles; the others are `AdapterScope`'s.
FLAGS = {
    "experimental": (bool,),
    "unmaintained": (str, type(None)),
    "at_risk": (str, type(None)),
    "maintainers": (tuple,),
}


def is_flag(keyword: ast.keyword) -> bool:
    """`experimental=True` or `=False`, `unmaintained` or `at_risk` `="<reason>"` or `=None`,
    `maintainers=("<handle>", ...)`, or a parameter of the flag's name passed straight on."""
    if keyword.arg not in FLAGS:
        return False
    if isinstance(keyword.value, ast.Name):
        return keyword.value.id == keyword.arg
    try:
        literal = ast.literal_eval(keyword.value)
    except ValueError, TypeError, SyntaxError:
        return False
    return isinstance(literal, FLAGS[keyword.arg]) and (
        not isinstance(literal, tuple) or all(isinstance(item, str) for item in literal)
    )


def runtime_shape(text: str) -> tuple[str, list[str]]:
    """The module's syntax tree with every flag argument dropped, and its comments: what a change must alter to count.
    Layout is ignored, so a call reflowed by the formatter when the flag goes still matches."""
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            node.keywords = [keyword for keyword in node.keywords if not is_flag(keyword)]
    tokens = tokenize.generate_tokens(io.StringIO(text).readline)
    return ast.dump(tree), [token.string for token in tokens if token.type == tokenize.COMMENT]


def changed_code(cited: str, paths: list[str]) -> list[str]:
    """Of the paths that differ between the cited commit and HEAD, those whose change is more than the flags."""
    changed = []
    for path in paths:
        before, after = git("show", f"{cited}:{path}"), git("show", f"HEAD:{path}")
        try:
            same = not (before.returncode or after.returncode) and runtime_shape(before.stdout) == runtime_shape(
                after.stdout
            )
        except SyntaxError, tokenize.TokenError:
            same = False
        if not same:
            changed.append(path)
    return changed


def proven(scope) -> bool:
    """Whether the adapter has a Verified call, which a record must prove: a Verified domain and, when the scope lists
    capabilities, a Verified one. Reported and Experimental items have no record to age."""
    if Level.VERIFIED not in scope.domains.values():
        return False
    return scope.capabilities is None or Level.VERIFIED in scope.capabilities.values()


def result(record: Path) -> str | None:
    """The record's Result row (`pass`, `fail`, ...), or None if it has none."""
    return m[1] if (m := RESULT.search(record.read_text())) else None


def record_errors(registry: AdapterRegistry) -> list[str]:
    """A released adapter missing its base record or one of its options' records, or with a record that did not pass
    or is stale, is an error. Experimental adapters are exempt, as no release has them, and so are adapters with no
    Verified call, as no record proves them."""
    errors = []
    for name, adapter in adapters(registry):
        if adapter.scope.experimental or not proven(adapter.scope):
            continue
        found = records(adapter.integration, adapter.action)
        have = {record.name for record in found}
        folder = test_records_dir(adapter.integration).relative_to(REPO)
        errors += [
            f"{name}: no test record {folder}/{file}"
            for file in record_names(adapter.action, adapter.scope.options)
            if file not in have
        ]
        code = code_of(adapter)
        for record in found:
            label = record.relative_to(REPO)
            if (outcome := result(record)) is None:
                errors.append(f"{name}: {label} has no readable Result row")
            elif outcome != "pass":
                errors.append(f"{name}: {label} did not pass (result: {outcome})")
            if problem := staleness(record, code):
                errors.append(f"{name}: {label} {problem}")
    return errors


def staleness(record: Path, code: list[str]) -> str | None:
    """Why the record is stale: it cites no commit or one git can't find, or the code differs between the cited commit
    and HEAD by more than its flags (`FLAGS`). Trees are compared, not history, so a record citing
    a squash-merged branch counts. None if it is fresh."""
    if not (cited := CITED_COMMIT.search(record.read_text())):
        return "cites no commit"
    return changed_since(cited[1], code)


def changed_since(commit: str, code: list[str]) -> str | None:
    """Why code tested at the commit (a hash or a tag) is not the code at HEAD: git can't find the commit, or the code
    differs between the two by more than its flags. None if it is the same."""
    if git("rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}").returncode:
        return f"cites commit {commit}, which git can't find"
    if (diff := git("diff", "--name-only", commit, "HEAD", "--", *code)).returncode:
        raise SystemExit(f"git diff {commit} HEAD failed: {diff.stderr.strip()}")
    if changed := changed_code(commit, diff.stdout.split()):
        return f"cites {commit}; changed since: {', '.join(changed)}"
    return None


@dataclass(frozen=True)
class Retest:
    """A test of some of an integration's actions at a commit, outside a rig record: a manual line or a report."""

    source: str  # where it is, for messages: `<file>:<line>` or the report's issue
    commit: str  # a hash, or a version tag
    actions: frozenset[str]


def manual_retests(integration: str, maintainers: Collection[str]) -> tuple[list[Retest], list[str]]:
    """The integration's `_manual.md` lines, and the errors in it: a `|` line that is neither the header nor a row of
    the format, or a row whose tester is not one of the maintainers. A row in error is no retest."""
    path = test_records_dir(integration) / MANUAL
    if not path.is_file():
        return [], []
    label = path.relative_to(REPO)
    retests, errors = [], []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line.startswith("|") or line in MANUAL_HEADER:
            continue
        if not (row := MANUAL_ROW.fullmatch(line)):
            errors.append(f"{label}:{number}: not a row of `{MANUAL_HEADER[0]}`: {line}")
        elif row[3] not in maintainers:
            errors.append(f"{label}:{number}: tester @{row[3]} is not a maintainer of {integration}")
        else:
            actions = frozenset(re.findall(r"`([^`]+)`", row[5]))
            retests.append(Retest(f"{label}:{number}", row[2], actions))
    return retests, errors


def report_retests(integration: str) -> list[Retest]:
    """The accepted working reports in the integration's devices.yaml, each at its DeviceSide version's tag.
    gen_compat checks their shape; one this can't read is left for it to fail on."""
    path = BUNDLES / integration / "devices.yaml"
    if not path.is_file():
        return []
    reports = (yaml.safe_load(path.read_text()) or {}).get("reports") or []
    return [
        Retest(str(report.get("issue")), f"v{str(report['deviceside']).removeprefix('v')}", frozenset(worked))
        for report in reports
        if isinstance(report, dict) and report.get("deviceside") and (worked := report.get("worked"))
    ]


def needs_retest(scope) -> bool:
    """Whether a released adapter without a Verified call holds a call that ships on: a domain and, when the scope
    lists capabilities, a capability, each Documented or better. One whose calls are all Experimental needs none."""
    if scope.experimental or proven(scope):
        return False
    shipping = [level for level in scope.domains.values() if level >= Level.DOCUMENTED]
    return bool(shipping) and (
        scope.capabilities is None or any(level >= Level.DOCUMENTED for level in scope.capabilities.values())
    )


def fresh_retest(adapter, retests: list[Retest]) -> str | None:
    """Where a fresh retest of the adapter is: a passing record of it as new as its code, or a manual line or report
    naming its action at a commit its code is unchanged since. None if it has none."""
    code = code_of(adapter)
    for record in records(adapter.integration, adapter.action):
        if result(record) == "pass" and staleness(record, code) is None:
            return str(record.relative_to(REPO))
    for retest in retests:
        if adapter.action in retest.actions and changed_since(retest.commit, code) is None:
            return retest.source
    return None


def retest_errors(registry) -> tuple[list[str], list[str]]:
    """The `_manual.md` errors, and the adapters that need a retest and have no fresh one, named."""
    errors: list[str] = []
    retests: dict[str, list[Retest]] = {}
    for key, info in registry.integrations.items():
        manual, problems = manual_retests(key, info.maintainers)
        retests[key] = manual + report_retests(key)
        errors += problems
    untested = [
        name
        for name, adapter in adapters(registry)
        if needs_retest(adapter.scope) and fresh_retest(adapter, retests.get(adapter.integration, [])) is None
    ]
    return errors, untested


def at_risk_errors(registry, untested: Collection[str]) -> list[str]:
    """For a release: an adapter needing a retest with none fresh must be marked `at_risk`, and one with a fresh retest
    (or none needed) must not be."""
    errors = []
    for name, adapter in adapters(registry):
        if name in untested and not adapter.scope.at_risk:
            errors.append(f"{name} changed since its last retest; retest it, or set at_risk to ship it marked")
        elif name not in untested and adapter.scope.at_risk:
            errors.append(f"{name} is at_risk but needs no retest or has a fresh one; clear at_risk")
    return errors


def release_notes(registry, untested: Collection[str]) -> str:
    """The release notes' call for testers: each adapter shipping marked at risk, and the report form."""
    names = [name for name, adapter in adapters(registry) if name in untested and adapter.scope.at_risk]
    if not names:
        return ""
    return (
        "## ⚠️ At risk\n\nThese changed since anyone last tested them on a device. They ship live; if you use one,"
        f" please [report whether it works]({DEVICE_REPORT}).\n\n" + "".join(f"- {name}\n" for name in names)
    )


def retest_checks(args: argparse.Namespace, registry) -> tuple[list[str], list[str]]:
    """The records (with --records) and At risk (with --release) errors, and the untested adapters, writing the release
    notes with --notes. Nothing is checked without one of the three."""
    if not (args.records or args.release or args.notes):
        return [], []
    manual_errors, untested = retest_errors(registry)
    errors = record_errors(registry) + manual_errors if args.records else []
    if args.release:
        errors += at_risk_errors(registry, untested)
    if args.notes:
        args.notes.write_text(release_notes(registry, untested))
    return errors, untested


def main(argv: list[str] | None = None, registry: AdapterRegistry | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--coverage", type=Path, help="coverage.json from pytest --cov-report=json")
    parser.add_argument(
        "--release",
        action="store_true",
        help="fail on any experimental adapter, or an untested one not marked at_risk",
    )
    parser.add_argument(
        "--records",
        action="store_true",
        help="fail on any released adapter whose test records did not pass or predate its code",
    )
    parser.add_argument("--notes", type=Path, help="write the release notes' call for testers here")
    args = parser.parse_args(argv)

    registry = registry or AdapterRegistry.discover()
    found = adapters(registry)
    # An integration that failed to import has no adapters to check, so every gate would pass it unseen.
    errors = [
        f"{key}: failed to import ({info.unavailable_reason})"
        for key, info in registry.integrations.items()
        if not info.available
    ]
    if args.coverage:
        errors += coverage_errors(registry, json.loads(args.coverage.read_text()))
    if args.release:
        errors += [
            f"{name} is experimental; a release has none" for name, adapter in found if adapter.scope.experimental
        ]
    retest_problems, untested = retest_checks(args, registry)
    errors += retest_problems

    def status(name: str, adapter) -> str:
        marks = ["experimental"] if adapter.scope.experimental else []
        if name in untested:
            marks.append("at risk" if adapter.scope.at_risk else "untested since its code changed")
        return ", ".join(marks)

    width = max((len(name) for name, _ in found), default=0)
    for name, adapter in found:
        print(f"{name:{width}}  {status(name, adapter)}".rstrip())
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        rows = [f"| {name} | {status(name, adapter)} |" for name, adapter in found]
        with open(summary, "a") as handle:
            handle.write("## Adapters\n\n| Adapter | Status |\n|---|---|\n" + "\n".join(rows) + "\n")
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
