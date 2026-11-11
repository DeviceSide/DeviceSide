#!/usr/bin/env python3
"""Check the adapters against the release gates: the coverage bar, no experimental adapter in a release, and test
records that pass and are as new as the code they prove.

The release flag and the levels are defined in CLAUDE.md § Release flag. --release fails on the flag, not on an
Experimental item, and on the Stale tests mark (below); --records weighs an adapter with a Verified call against its
records, and one without against its retests (below).
Records live in each integration's bundle (`test_records_dir`).

An adapter's code (`adapter_code`) is its module and what that module and its integration package import, followed
into `core/`, so a shared helper counts for every adapter that reaches it: its coverage is held to the bar and a
change to it stales those adapters' records. `actions/` and imports made only for type checking are not followed.

Exits 1 on any integration that failed to import, whatever the options; with --coverage, any module of an adapter's
code, bar `__init__.py`, under 95% line coverage; with --release, any experimental adapter or a Stale tests mismatch;
with --records, any `_manual.md` error, or any released adapter with a Verified call that lacks `<action>.md` or an
`<action>-<option>.md` for one of its scope's options, a record whose Result is not `pass`, or code changed after the
commit one of its records cites. Each record holds the latest run of its call or option. Setting or clearing
`experimental`, `unmaintained` or `stale_tests`, or changing an integration's `maintainers`, is not a change to the
code: no call reads them (setup reads `unmaintained` and `stale_tests` only to warn, and registration checks
`maintainers`).

**Retests.** An adapter with no Verified call has no rig coverage, so a record can't gate it; it still needs a retest
as new as its code once it holds a call that ships on (Documented or better; an adapter whose calls are all
Experimental needs none). A retest is any of: a passing record of the adapter (as above); a line of the integration's
`test-records/_manual.md` by one of its maintainers; an accepted working report in its devices.yaml whose `deviceside`
version is a tag (`v<version>`) and whose `item` the adapter ships (Documented or better). Each is fresh when the
adapter's code is unchanged, bar the flags, between the commit it names (a manual line's, the report's tag) and HEAD.
An adapter with a Verified call keeps needing its records.

A `_manual.md` line is a table row: date, commit, tester, devices, what passed.

    | Date | Commit | Tester | Devices | Passed |
    |---|---|---|---|---|
    | 2026-11-11 | `1a2b3c4` | @handle | `LCA001`, `SNSPL-10` | `turn_on_for`, `set_auto_off` |

Devices are model ids (docs/models.yaml), never a household's device names; Passed names the actions that worked,
each covering that integration's adapter for the action. Prose and headings around the table are ignored; any other
`|` line is an error under --records, as is a tester who is not one of the integration's maintainers.

**Shared code.** A change to a `core/` module counts against no adapter's records or retests once one run proved it:
a record that passed, of a released adapter with a Verified call (any integration's), whose cited commit holds the
module as HEAD does, and whose run executed a line of each clause the change touches (`needed_headers`: a statement,
`except` or `case` clause, from its first decorator to the line before its body; a function's decorators and signature
need its first statement, a lambda's body its body; a comment, blank line or docstring needs none, and removed code
needs the code on each side of it). The rest of that run's adapter may have changed since. A change to a module's or
class's own statements (a constant, a class attribute, an import), which every run executes at import, and a change
inside an integration's package are never cleared this way. The rig writes the run's coverage into the record,
the modules relative to the component and the lines as coverage.py's executed lines:

    ## Shared coverage

    | Module | Executed lines |
    |---|---|
    | `core/dispatcher.py` | 12-40, 55 |

In a record that can prove shared code, other `|` lines in that section, or a second section, are errors under
--records; the section ends at the next `## ` heading.

**Stale tests.** --records lists each adapter that needs a retest and has none fresh. --release fails on one unless
its scope sets `stale_tests` (it then ships live, marked ⚠️ Stale tests), and on a `stale_tests` adapter that has a
fresh retest or needs none, as that retest clears the mark. --notes writes the release notes' call for testers: each
adapter --records lists, marked or not (an RC lists them before they are), with a link to the device report form;
empty when there are none.

Usage: scripts/check_release.py [--coverage coverage.json] [--release] [--records] [--notes notes.md]
"""

import argparse
import ast
import functools
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
CORE_DIR = "custom_components/deviceside/core/"
SHARED_HEADING = re.compile(r"^## Shared coverage[ \t]*$", re.MULTILINE)
SHARED_HEADER = ("| Module | Executed lines |", "|---|---|")
LINE_RANGES = r"\d+(?:-\d+)?(?:, \d+(?:-\d+)?)*"
SHARED_ROW = re.compile(rf"\| `(core/[\w/]+\.py)` \| ({LINE_RANGES}) \|")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)


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
    "stale_tests": (str, type(None)),
    "maintainers": (tuple,),
}


def is_flag(keyword: ast.keyword) -> bool:
    """`experimental=True` or `=False`, `unmaintained` or `stale_tests` `="<reason>"` or `=None`,
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


def record_errors(registry: AdapterRegistry, shared: SharedIndex | None = None) -> list[str]:
    """A released adapter missing its base record or one of its options' records, or with a record that did not pass
    or is stale (a `core/` change the shared coverage clears aside), is an error. Experimental adapters are exempt, as
    no release has them, and so are adapters with no Verified call, as no record proves them."""
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
            if problem := staleness(record, code, shared):
                errors.append(f"{name}: {label} {problem}")
    return errors


def staleness(record: Path, code: list[str], shared: SharedIndex | None = None) -> str | None:
    """Why the record is stale: it cites no commit or one git can't find, or the code differs between the cited commit
    and HEAD by more than its flags (`FLAGS`). Trees are compared, not history, so a record citing
    a squash-merged branch counts. None if it is fresh."""
    if not (cited := CITED_COMMIT.search(record.read_text())):
        return "cites no commit"
    return changed_since(cited[1], code, shared)


def changed_since(commit: str, code: list[str], shared: SharedIndex | None = None) -> str | None:
    """Why code tested at the commit (a hash or a tag) is not the code at HEAD: git can't find the commit, or the code
    differs between the two by more than its flags, bar `core/` modules whose change the shared coverage clears
    (`shared_clears`). None if it is the same."""
    if git("rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}").returncode:
        return f"cites commit {commit}, which git can't find"
    if (diff := git("diff", "--name-only", commit, "HEAD", "--", *code)).returncode:
        raise SystemExit(f"git diff {commit} HEAD failed: {diff.stderr.strip()}")
    changed = changed_code(commit, diff.stdout.split())
    if changed := [path for path in changed if not shared_clears(commit, path, shared or {})]:
        return f"cites {commit}; changed since: {', '.join(changed)}"
    return None


@dataclass(frozen=True)
class SharedCoverage:
    """A record's run, at its cited commit, executed these lines of a `core/` module."""

    source: str  # the record, for messages
    commit: str
    executed: frozenset[int]


# Each `core/` module, as a path relative to the repository, and the runs that covered it.
SharedIndex = dict[str, list[SharedCoverage]]


def parse_ranges(text: str) -> frozenset[int]:
    """`12-40, 55` as the lines it names."""
    lines: set[int] = set()
    for part in text.split(", "):
        first, _, last = part.partition("-")
        lines.update(range(int(first), int(last or first) + 1))
    return frozenset(lines)


def shared_rows(record: Path, commit: str) -> tuple[list[tuple[str, SharedCoverage]], list[str]]:
    """The record's `## Shared coverage` rows, each as its module's path and coverage, and the errors in the section:
    a `|` line that is neither the header nor a row of the format, a range that runs backwards, or a second section.
    A row in error covers nothing. A record without the section has none."""
    text = record.read_text()
    if not (heading := SHARED_HEADING.search(text)):
        return [], []
    label = record.relative_to(REPO)
    start = text.count("\n", 0, heading.end()) + 2
    rows, errors = [], []
    for again in list(SHARED_HEADING.finditer(text))[1:]:
        errors.append(f"{label}:{text.count(chr(10), 0, again.start()) + 1}: a second `## Shared coverage` section")
    for number, line in enumerate(text[heading.end() :].splitlines()[1:], start):
        line = line.strip()
        if line.startswith("## "):
            break
        if not line.startswith("|") or line in SHARED_HEADER:
            continue
        row = SHARED_ROW.fullmatch(line)
        if not row or any(int(a) > int(b) for a, b in re.findall(r"(\d+)-(\d+)", row[2])):
            errors.append(f"{label}:{number}: not a row of `{SHARED_HEADER[0]}`: {line}")
            continue
        rows.append(
            (f"custom_components/deviceside/{row[1]}", SharedCoverage(str(label), commit, parse_ranges(row[2])))
        )
    return rows, errors


def shared_coverage(registry) -> tuple[SharedIndex, list[str]]:
    """The `core/` coverage of every record that can prove shared code, and the errors in their sections. A record
    can when it passed and cites a commit, and its adapter is released with a Verified call; the rest of its
    adapter's code may have changed since."""
    index: SharedIndex = {}
    errors: list[str] = []
    for _, adapter in adapters(registry):
        if adapter.scope.experimental or not proven(adapter.scope):
            continue
        for record in records(adapter.integration, adapter.action):
            if result(record) != "pass" or not (cited := CITED_COMMIT.search(record.read_text())):
                continue
            rows, problems = shared_rows(record, cited[1])
            errors += problems
            for module, covered in rows:
                index.setdefault(module, []).append(covered)
    return index, errors


def is_docstring(node: ast.stmt) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def docstring_lines(tree: ast.Module) -> set[int]:
    """The lines of the module's, its classes' and its functions' docstrings."""
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            if is_docstring(first := node.body[0]):
                lines.update(range(first.lineno, first.end_lineno + 1))
    return lines


def code_lines(text: str) -> set[int]:
    """The lines that hold code: any token bar comments and line ends, a multi-line string holding every line it
    spans."""
    skip = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER}
    lines: set[int] = set()
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type not in skip:
            lines.update(range(token.start[0], token.end[0] + 1))
    return lines


def header(node: ast.stmt | ast.excepthandler | ast.match_case) -> range:
    """The lines of a clause one of which coverage.py marks executed when it runs: a compound clause's from its first
    decorator to the line before its body, a simple statement's whole span."""
    line = node.pattern.lineno if isinstance(node, ast.match_case) else node.lineno
    first = min([line, *(decorator.lineno for decorator in getattr(node, "decorator_list", []))])
    body = getattr(node, "body", None)
    return range(first, (max(line, body[0].lineno - 1) if body else node.end_lineno) + 1)


def clauses(tree: ast.Module) -> list[tuple[range, range]]:
    """Each clause, as its span and the lines one of which a run must execute to show the clause's change exercised.

    A statement, `except` or `case` clause needs its header (`header`); a function's own header (decorators and
    signature) is executed at import, so it needs its first statement bar a docstring, the call. A lambda's or
    generator expression's body runs only when called, so it is a clause of its own, needing its body's lines bar the
    line it starts on, which the enclosing statement executes. A clause needing no line can't be cleared."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Lambda | ast.GeneratorExp):
            inner = node.body if isinstance(node, ast.Lambda) else node.elt
            body = range(max(inner.lineno, node.lineno + 1), inner.end_lineno + 1)
            found.append((range(node.lineno, node.end_lineno + 1), body))
            continue
        if not isinstance(node, ast.stmt | ast.excepthandler | ast.match_case):
            continue
        head = header(node)
        last = node.body[-1].end_lineno if isinstance(node, ast.match_case) else node.end_lineno
        span = range(head.start, last + 1)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            calls = [statement for statement in node.body if not is_docstring(statement)]
            head = header(calls[0]) if calls else range(0)
        found.append((span, head))
    return found


def deferred_lines(tree: ast.Module) -> set[int]:
    """The lines that run only when called: each function's, from its first decorator, and each lambda's and
    generator expression's. The rest, a module's or class's own statements, runs at import."""
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            lines.update(range(header(node).start, node.end_lineno + 1))
        elif isinstance(node, ast.Lambda | ast.GeneratorExp):
            lines.update(range(node.lineno, node.end_lineno + 1))
    return lines


@functools.cache
def needed_headers(commit: str, head: str, path: str) -> list[range] | None:
    """The lines the module's change from the commit to the head (both full hashes, for the cache) needs a run to
    execute, one of each range: those of the innermost clause (`clauses`) around each changed code line, a comment,
    blank line or docstring needing none; for a hunk that removes more code than it adds, those of the nearest code
    line on each side too. None if the change can't be cleared: the head's module can't be parsed, or the change
    touches a module's or class's own statements (`deferred_lines`), which every run that imports the module
    executes."""
    if (diff := git("diff", "-U0", commit, head, "--", path)).returncode:
        raise SystemExit(f"git diff {commit} HEAD failed: {diff.stderr.strip()}")
    text = git("show", f"{head}:{path}").stdout
    try:
        tree = ast.parse(text)
        code = code_lines(text) - docstring_lines(tree)
    except SyntaxError, tokenize.TokenError:
        return None
    old = git("show", f"{commit}:{path}").stdout
    try:
        old_code = code_lines(old) - docstring_lines(ast.parse(old))
    except SyntaxError, tokenize.TokenError:
        old_code = set(range(1, old.count("\n") + 2))
    lines: set[int] = set()
    for hunk in HUNK.finditer(diff.stdout):
        old_start, old_count = int(hunk[1]), int(hunk[2] if hunk[2] is not None else 1)
        start, count = int(hunk[3]), int(hunk[4] if hunk[4] is not None else 1)
        added = {line for line in range(start, start + count) if line in code}
        lines |= added
        removed = len(old_code.intersection(range(old_start, old_start + old_count)))
        if removed > len(added):
            # With no new lines, git numbers the hunk by the line before the deletion.
            last = start + count - 1 if count else start
            before = [line for line in code if line < start or (not count and line == start)]
            after = [line for line in code if line > last]
            lines.update([max(before)] if before else [])
            lines.update([min(after)] if after else [])
    if lines - deferred_lines(tree):
        return None
    spans = clauses(tree)
    headers = []
    for line in sorted(lines):
        # The innermost: the shortest span, and of equal ones the deepest, which `ast.walk` yields last.
        around = [(span, head) for span, head in reversed(spans) if line in span]
        if not around or not (needed := min(around, key=lambda clause: len(clause[0]))[1]):
            return None
        headers.append(needed)
    return list(dict.fromkeys(headers))


@functools.cache
def blob(commit: str, path: str) -> str | None:
    """The path's blob at the commit (a full hash, for the cache), or None where it has none."""
    found = git("rev-parse", "--verify", "--quiet", f"{commit}:{path}")
    return None if found.returncode else found.stdout.strip()


def resolve(commit: str) -> str:
    return git("rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}").stdout.strip()


def shared_clears(commit: str, path: str, shared: SharedIndex) -> bool:
    """Whether the change to a `core/` module since the commit is proven for every adapter that reaches it: a run that
    can prove shared code (`shared_coverage`) covered the module at a commit where it is the same as at HEAD, and
    executed a line of each range the change needs (`needed_headers`)."""
    if not path.startswith(CORE_DIR) or not (runs := shared.get(path)):
        return False
    head = resolve("HEAD")
    if (now := blob(head, path)) is None:
        return False
    matching = [run for run in runs if (cited := resolve(run.commit)) and blob(cited, path) == now]
    if not matching or (headers := needed_headers(resolve(commit), head, path)) is None:
        return False
    return any(all(run.executed.intersection(header) for header in headers) for run in matching)


@dataclass(frozen=True)
class Retest:
    """A test of some of an integration's actions at a commit, outside a rig record: a manual line or a report."""

    source: str  # where it is, for messages: `<file>:<line>` or the report's issue
    commit: str  # a hash, or a version tag
    actions: frozenset[str]
    item: str | None = None  # a report's item, which the adapter must ship; None for a manual line


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
        Retest(
            str(report.get("issue")),
            f"v{str(report['deviceside']).removeprefix('v')}",
            frozenset(worked),
            str(report.get("item")),
        )
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


def shipping_items(scope) -> set[str]:
    """The items a report can retest the adapter through: its capabilities when the scope lists them, else its
    domains, each Documented or better."""
    held = scope.capabilities if scope.capabilities is not None else scope.domains
    return {item for item, level in held.items() if level >= Level.DOCUMENTED}


def fresh_retest(adapter, retests: list[Retest], shared: SharedIndex | None = None) -> str | None:
    """Where a fresh retest of the adapter is: a passing record of it as new as its code, or a manual line or report
    naming its action (a report, on an item it ships) at a commit its code is unchanged since. None if it has none."""
    code = code_of(adapter)
    for record in records(adapter.integration, adapter.action):
        if result(record) == "pass" and staleness(record, code, shared) is None:
            return str(record.relative_to(REPO))
    items = shipping_items(adapter.scope)
    for retest in retests:
        if (
            adapter.action in retest.actions
            and (retest.item is None or retest.item in items)
            and changed_since(retest.commit, code, shared) is None
        ):
            return retest.source
    return None


def retest_errors(registry, shared: SharedIndex | None = None) -> tuple[list[str], list[str]]:
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
        if needs_retest(adapter.scope) and fresh_retest(adapter, retests.get(adapter.integration, []), shared) is None
    ]
    return errors, untested


def stale_tests_errors(registry, untested: Collection[str]) -> list[str]:
    """For a release: an adapter needing a retest with none fresh must be marked `stale_tests`, and one with a fresh
    retest (or none needed) must not be."""
    errors = []
    for name, adapter in adapters(registry):
        if name in untested and not adapter.scope.stale_tests:
            errors.append(f"{name} changed since its last retest; retest it, or set stale_tests to ship it marked")
        elif name not in untested and adapter.scope.stale_tests:
            why = "has a fresh retest" if needs_retest(adapter.scope) else "needs none (records gate a Verified call)"
            errors.append(f"{name} sets stale_tests but {why}; clear stale_tests")
    return errors


def release_notes(registry, untested: Collection[str]) -> str:
    """The release notes' call for testers: each adapter shipping without a fresh retest, and the report form. At a
    release each is marked `stale_tests`; an RC lists them before they are, so a report at its tag can retest them."""
    names = [name for name, _ in adapters(registry) if name in untested]
    if not names:
        return ""
    return (
        "## ⚠️ Stale tests\n\nThese changed since anyone last tested them on a device. They ship live; if you use one,"
        f" please [report whether it works]({DEVICE_REPORT}).\n\n" + "".join(f"- {name}\n" for name in names)
    )


def retest_checks(args: argparse.Namespace, registry) -> tuple[list[str], list[str]]:
    """The records (with --records) and Stale tests (with --release) errors, and the untested adapters, writing the
    release notes with --notes. Nothing is checked without one of the three."""
    if not (args.records or args.release or args.notes):
        return [], []
    shared, shared_errors = shared_coverage(registry)
    manual_errors, untested = retest_errors(registry, shared)
    errors = record_errors(registry, shared) + manual_errors + shared_errors if args.records else []
    if args.release:
        errors += stale_tests_errors(registry, untested)
    if args.notes:
        args.notes.write_text(release_notes(registry, untested))
    return errors, untested


def main(argv: list[str] | None = None, registry: AdapterRegistry | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--coverage", type=Path, help="coverage.json from pytest --cov-report=json")
    parser.add_argument(
        "--release",
        action="store_true",
        help="fail on any experimental adapter, or an untested one not marked stale_tests",
    )
    parser.add_argument(
        "--records",
        action="store_true",
        help="fail on any released adapter whose test records did not pass or predate its code, or a _manual.md error",
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
            marks.append("stale tests" if adapter.scope.stale_tests else "untested since its code changed")
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
