#!/usr/bin/env python3
"""Check the adapters against the release gates: the coverage bar, no experimental adapter in a release, and test
records that pass and are as new as the code they prove.

`experimental=True` on an adapter's scope means it is not in a stable release yet. It is cleared by a PR citing a
passing test record that covers the scope. An Experimental scope item (`Level.EXPERIMENTAL`) is not the flag: it ships
in a stable release, refused at runtime until the user turns on Experimental features, so --release passes it.
Reported and Experimental items have no record to age, so --records weighs only the adapter's code against its
records.

Exits 1 on any integration that failed to import, whatever the options; with --coverage, any module of an adapter's
code (`adapter_code`, bar `__init__.py`) under 95% line coverage; with --release, any experimental adapter; with
--records, any released adapter with a Verified call that lacks `<action>.md` or an `<action>-<option>.md` for one
of its scope's options, a record whose Result is not `pass`, or code changed after the commit one of its records
cites. Each record holds the latest run of its call or option. Setting or
clearing `experimental` is not a change to the code: nothing reads it at runtime.

Usage: scripts/check_release.py [--coverage coverage.json] [--release] [--records]
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
from collections.abc import Collection
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from custom_components.deviceside.core.registry import AdapterRegistry  # noqa: E402
from custom_components.deviceside.core.scope import Level  # noqa: E402

COVERAGE_BAR = 95.0
BUNDLES = REPO / "docs" / "integrations"
CITED_COMMIT = re.compile(r"^\| Source \|.*\bcommit `([0-9a-f]{7,40})`", re.MULTILINE)
RESULT = re.compile(r"^\| Result \| (\S+) \|", re.MULTILINE)


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


def relative_imports(path: Path) -> list[tuple[str, list[str]]]:
    """Each `from .x import a, b` in the module, as `("x", ["a", "b"])`, and each `from . import x` as `("x", [])`."""
    imports = []
    for node in ast.walk(ast.parse(path.read_text(), str(path))):
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            if node.module:
                imports.append((node.module.partition(".")[0], [alias.name for alias in node.names]))
            else:
                imports += [(alias.name, []) for alias in node.names]
    return imports


def adapter_names(init: Path) -> set[str]:
    """The names the package's `ADAPTERS = [...]` lists."""
    for node in ast.walk(ast.parse(init.read_text(), str(init))):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ADAPTERS" for t in node.targets):
            return {element.id for element in getattr(node.value, "elts", []) if isinstance(element, ast.Name)}
    return set()


def adapter_code(module: Path) -> list[Path]:
    """The adapter's module, its integration package's `__init__.py`, and every module of that package either imports,
    directly or through another: the code behind the call it sends, the group expansion and call resolver included.
    The sibling adapter modules `__init__.py` imports for `ADAPTERS` are left out, unless the adapter's own code
    reaches them. `core/` and `actions/` are left out. Raises ValueError on a relative import that names no module of
    the package, which would otherwise drop code from the check unseen."""
    package = module.parent
    init = package / "__init__.py"
    adapters = adapter_names(init)

    def modules(importer: Path, names: list[str]) -> list[Path]:
        paths = [package / f"{name}.py" for name in names]
        for name, path in zip(names, paths, strict=True):
            if not path.is_file():
                raise ValueError(f"{importer}: can't resolve `from .{name}` to a module of {package}")
        return paths

    found: set[Path] = {init}
    todo = [
        module,
        *modules(init, [name for name, names in relative_imports(init) if not adapters.intersection(names)]),
    ]
    while todo:
        if (path := todo.pop()) in found:
            continue
        found.add(path)
        todo += modules(path, [name for name, _ in relative_imports(path)])
    return sorted(found)


def code_of(adapter) -> list[str]:
    """The adapter's code (`adapter_code`), as paths relative to the repository."""
    return [str(path.relative_to(REPO)) for path in adapter_code(Path(inspect.getsourcefile(type(adapter))))]


def record_dir(integration: str) -> Path:
    """Where the integration's test records live: `docs/integrations/<integration>/records/`. The rig writes there."""
    return BUNDLES / integration / "records"


def records(integration: str, action: str) -> list[Path]:
    """The adapter's test records: `<action>.md`, and `<action>-<option>.md` for a run with an option set."""
    pattern = re.compile(rf"{re.escape(action)}(-[^.]+)?\.md")
    return sorted(path for path in record_dir(integration).glob("*.md") if pattern.fullmatch(path.name))


def record_names(action: str, options: Collection[str] = ()) -> list[str]:
    """The records an adapter needs: `<action>.md`, then `<action>-<option>.md` for each option, as `records` names
    them."""
    return [f"{action}.md", *(f"{action}-{option}.md" for option in sorted(options))]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


def is_flag(keyword: ast.keyword) -> bool:
    """`experimental=True`, `=False`, or a parameter of that name passed straight on."""
    value = keyword.value
    return keyword.arg == "experimental" and (
        (isinstance(value, ast.Constant) and isinstance(value.value, bool))
        or (isinstance(value, ast.Name) and value.id == "experimental")
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
    """Of the paths that differ between the cited commit and HEAD, those whose change is more than the flag."""
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
        folder = record_dir(adapter.integration).relative_to(REPO)
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
    and HEAD by more than its `experimental` flag. Trees are compared, not history, so a record citing a squash-merged
    branch counts. None if it is fresh."""
    if not (cited := CITED_COMMIT.search(record.read_text())):
        return "cites no commit"
    if git("rev-parse", "--verify", "--quiet", f"{cited[1]}^{{commit}}").returncode:
        return f"cites commit {cited[1]}, which git can't find"
    if (diff := git("diff", "--name-only", cited[1], "HEAD", "--", *code)).returncode:
        raise SystemExit(f"git diff {cited[1]} HEAD failed: {diff.stderr.strip()}")
    if changed := changed_code(cited[1], diff.stdout.split()):
        return f"cites {cited[1]}; changed since: {', '.join(changed)}"
    return None


def main(argv: list[str] | None = None, registry: AdapterRegistry | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--coverage", type=Path, help="coverage.json from pytest --cov-report=json")
    parser.add_argument("--release", action="store_true", help="fail on any experimental adapter")
    parser.add_argument(
        "--records",
        action="store_true",
        help="fail on any released adapter whose test records did not pass or predate its code",
    )
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
    if args.records:
        errors += record_errors(registry)

    width = max((len(name) for name, _ in found), default=0)
    for name, adapter in found:
        print(f"{name:{width}}  {'experimental' if adapter.scope.experimental else ''}".rstrip())
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        rows = [f"| {name} | {'yes' if adapter.scope.experimental else ''} |" for name, adapter in found]
        with open(summary, "a") as handle:
            handle.write("## Adapters\n\n| Adapter | Experimental |\n|---|---|\n" + "\n".join(rows) + "\n")
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
