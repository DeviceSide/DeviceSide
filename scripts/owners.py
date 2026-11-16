#!/usr/bin/env python3
"""Say who owns a path: the one owner lookup the merge gate, issue routing, the PR notice and the audit skills share.

What holds a path, read at a rev (CLAUDE.md, Maintainers; the templates are `gen_codeowners.py`'s):

- in a family (`FAMILY_PATHS`), on the rev: that family;
- in the catalog (`CATALOG_PATHS`), there on the rev and shared by a family of its key: that key's catalog;
- elsewhere in an integration's package (`PATHS`): the integration (a family not on the rev is its integration's);
- generated output (`GENERATED`): nothing, as it follows its inputs;
- anything else: shared code, the repo maintainers'.

Each holder has one *owner group*, or for the catalog one per family of its key: `direct`, the most specific
maintainers (the family's, or the integration's when the family names none), and `enclosing`, the family's
integration's maintainers when the family names its own. The gate's owner set is every group's handles; the notice
and the skills call a group someone else's when its `direct` handles don't include them (`foreign`), so an
integration maintainer changing their own family is warned too. An integration not on the rev yet has no owners of
its own: its paths are shared code.

It runs on the standard library alone and reads every file at the rev with `git show`, never importing an
integration, so the workflows can run it from the base branch on a PR's files. The repo maintainers and the path
templates are read from `gen_codeowners.py` in the working tree, not at the rev: the workflows check out the base, and
a local run on a branch that changes them reads the branch's.

Usage: scripts/owners.py [--rev REV] [--as LOGIN] [--json | --issue] PATH...

Prints one line per owner group of the paths; with `--as`, only the groups that aren't that login's. `--json` prints
the rows for the skills; `--issue` the `labels=` and `assignees=` lines an issue routed to them takes.
"""

import argparse
import ast
import functools
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parents[1]
CODEOWNERS_SCRIPT = REPO / "scripts" / "gen_codeowners.py"
INTEGRATIONS = "custom_components/deviceside/integrations/"
INIT = INTEGRATIONS + "{key}/__init__.py"
FAMILY_INIT = INTEGRATIONS + "{key}/families/{family}/__init__.py"
README = "README.md"
COMPAT = "docs/device-compatibility.md"
# Generated output: CODEOWNERS wholly, the other two inside their marked blocks (check_maintainer_merge.py, BLOCKS).
GENERATED = frozenset({README, COMPAT, ".github/CODEOWNERS"})
# What a path template's `{key}` and `{family}` match: an integration's package name, and a family's as the registry
# shapes it (core/registry.py, FAMILY_KEY; tests/scripts/test_owners.py pins them equal), which no `__init__.py` or
# `__pycache__` beside the families is.
NAMES = {"key": r"[a-z0-9_]+", "family": r"[a-z][a-z0-9_]*"}
LABEL = "integration:{key}"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def show(rev: str, path: str) -> str:
    """The file at `rev`, or "" when it doesn't exist there."""
    try:
        return git("show", f"{rev}:{path}")
    except subprocess.CalledProcessError:
        return ""


def commit(rev: str) -> str:
    """`rev` as a commit SHA, so what the cached readers below read at it is keyed by content."""
    return git("rev-parse", "--verify", f"{rev}^{{commit}}").strip()


# The literal parsers: an integration's `INTEGRATION = IntegrationInfo(...)` and a family's `FAMILY = Family(...)`.


@dataclass(frozen=True)
class Integration:
    key: str
    title: str
    maintainers: tuple[str, ...]


@dataclass(frozen=True)
class Family:
    key: str
    maintainers: tuple[str, ...]


def names(node: ast.Assign | ast.AnnAssign) -> list[str | None]:
    """The names an assignment binds."""
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [getattr(target, "id", None) for target in targets]


def listed(fields: tuple[str, ...], suffix: str = "") -> str:
    """`key=, title= and maintainers=`, for an error."""
    items = [f"{name}{suffix}" for name in fields]
    return " and ".join([", ".join(items[:-1]), items[-1]] if len(items) > 1 else items)


def called(node: ast.expr) -> str | None:
    """The name a call calls, bare or as an attribute (`scope.Family(...)`); None for anything else."""
    return getattr(node.func, "id", getattr(node.func, "attr", None)) if isinstance(node, ast.Call) else None


def literals(text: str, init: Path | str, name: str, call: str, fields: tuple[str, ...]) -> dict:
    """The literal keyword `fields` of the module's one `<name> = <call>(...)` binding (`init` names the file in
    errors): each a string, but `maintainers`, a tuple or list of them. The registry takes the last binding, so a
    second one is refused rather than read past; a call to anything else, or a value of another shape, isn't read as
    owners."""
    body = ast.parse(text).body
    bindings = [node for node in body if isinstance(node, ast.Assign | ast.AnnAssign) and name in names(node)]
    if len(bindings) > 1:
        raise SystemExit(f"{init}: {name} is bound {len(bindings)} times")
    for node in bindings:
        if isinstance(node, ast.Assign) and names(node) == [name] and called(node.value) == call:
            try:
                kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in node.value.keywords if kw.arg in fields}
            except (ValueError, TypeError) as err:
                raise SystemExit(f"{init}: {listed(fields)} must be literals ({err})") from None
            if set(kwargs) != set(fields):
                raise SystemExit(f"{init}: {name} needs {listed(fields, '=')}")
            for field, value in kwargs.items():
                if field != "maintainers" and not isinstance(value, str):
                    raise SystemExit(f"{init}: {field} must be a string")
                if field == "maintainers" and not (
                    isinstance(value, tuple | list) and all(isinstance(handle, str) for handle in value)
                ):
                    raise SystemExit(f"{init}: maintainers must be a tuple or list of strings")
            return kwargs
    raise SystemExit(f"{init}: no {name} = {call}(...)")


def parse(text: str, init: Path | str) -> Integration:
    """An integration's key, title and maintainers, from the text of its `__init__.py`."""
    kwargs = literals(text, init, "INTEGRATION", "IntegrationInfo", ("key", "title", "maintainers"))
    return Integration(kwargs["key"], kwargs["title"], tuple(kwargs["maintainers"]))


def parse_family(text: str, init: Path | str) -> Family:
    """A family's key and maintainers, from the text of its `__init__.py` (`integrations/<key>/families/<family>/`)."""
    kwargs = literals(text, init, "FAMILY", "Family", ("key", "maintainers"))
    return Family(kwargs["key"], tuple(kwargs["maintainers"]))


def repo_maintainers(script: Path = CODEOWNERS_SCRIPT) -> frozenset[str]:
    """`REPO_MAINTAINERS` from `gen_codeowners.py`, read without importing it (that imports the integrations)."""
    for node in ast.parse(script.read_text()).body:
        if isinstance(node, ast.AnnAssign | ast.Assign) and "REPO_MAINTAINERS" in names(node):
            return frozenset(ast.literal_eval(node.value))
    raise SystemExit(f"no REPO_MAINTAINERS in {script}")


# What holds a path.


class Templates(NamedTuple):
    """The path templates of `gen_codeowners.py`: `PATHS`, `FAMILY_PATHS` and `CATALOG_PATHS`."""

    integration: tuple[str, ...]
    family: tuple[str, ...]
    catalog: tuple[str, ...]


@dataclass(frozen=True)
class Package:
    """What holds a path: an integration's package (`key`), a family of it (`key` and `family`), or the catalog file
    of a family key (`family` alone)."""

    key: str | None
    family: str | None = None

    def __str__(self) -> str:
        if self.key is None:
            return f"the `{self.family}` catalog"
        return f"`{self.key}`" + (f"'s `{self.family}` family" if self.family else "")

    @property
    def slug(self) -> str:
        """`control4`, `zigbee2mqtt/tuya`, or `zigbee/tuya` for the catalog: what an audit record's `owner` holds."""
        if self.key is None:
            return f"zigbee/{self.family}"
        return self.key + (f"/{self.family}" if self.family else "")

    def owned_by(self) -> str:
        """Whose maintainers own it, for a refusal."""
        if self.key is None:
            return f"a `{self.family}` family or its integration"
        return f"`{self.key}`" + (f" or of {self}" if self.family else "")


def package_paths(script: Path = CODEOWNERS_SCRIPT) -> Templates:
    """The path templates from `gen_codeowners.py`, read without importing it (that imports the integrations)."""
    found = {}
    for node in ast.parse(script.read_text()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            found[getattr(node.targets[0], "id", None)] = node.value
    try:
        return Templates(*(tuple(ast.literal_eval(found[name])) for name in ("PATHS", "FAMILY_PATHS", "CATALOG_PATHS")))
    except KeyError as err:
        raise SystemExit(f"no {err.args[0]} in {script}") from None


def match(path: str, templates: tuple[str, ...]) -> dict[str, str] | None:
    """The `key` and `family` with which one of the templates holds `path`, or None."""
    for template in templates:
        parts = re.split(r"\{(\w+)\}", template)
        pattern = "".join(
            f"(?P<{part}>{NAMES[part]})" if index % 2 else re.escape(part) for index, part in enumerate(parts)
        )
        # A folder's template holds every path under it; a file's, that path alone (`$` would pass a trailing newline).
        if found := (re.match if template.endswith("/") else re.fullmatch)(pattern, path):
            return found.groupdict()
    return None


@functools.cache
def maintainers(rev: str, key: str) -> tuple[str, ...] | None:
    """The integration's maintainers at `rev`, or None when it has no readable `__init__.py` there."""
    init = INIT.format(key=key)
    if not (text := show(rev, init)):
        return None
    try:
        return parse(text, init).maintainers
    except SyntaxError, SystemExit:
        return None


@functools.cache
def family_maintainers(rev: str, key: str, family: str) -> tuple[str, ...] | None:
    """The family's maintainers at `rev`, or None when it has no readable `__init__.py` there under that key."""
    init = FAMILY_INIT.format(key=key, family=family)
    if not (text := show(rev, init)):
        return None
    try:
        found = parse_family(text, init)
    except SyntaxError, SystemExit:
        return None
    return found.maintainers if found.key == family else None


@functools.cache
def integrations_with(rev: str, family: str) -> tuple[str, ...]:
    """The integrations that hold a family of this key at `rev`."""
    listing = git("ls-tree", "-d", "-z", "--name-only", rev, INTEGRATIONS)
    keys = [Path(path).name for path in listing.split("\0") if path]
    return tuple(key for key in keys if family_maintainers(rev, key, family) is not None)


def package_of(path: str, rev: str, templates: Templates) -> Package | None:
    """What holds `path` at `rev`, or None for shared code. A family that isn't on the rev has no owners of its own
    yet, so its paths are its integration's; a catalog file no family there shares, or that isn't there yet, is
    shared code."""
    if (found := match(path, templates.family)) and family_maintainers(rev, **found) is not None:
        return Package(**found)
    if found := match(path, templates.integration):
        return Package(found["key"])
    # A catalog file new on this rev's PR is shared code: it gives the other integration's family code this one imports.
    if (found := match(path, templates.catalog)) and integrations_with(rev, found["family"]) and show(rev, path):
        return Package(None, found["family"])
    return None


# Who owns it.


class NotOnRev(Exception):
    """The integration a path is in isn't on the rev yet, so its maintainers can't be read there."""

    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


@dataclass(frozen=True)
class Group:
    """One owner group: what holds the paths (None for shared code), the integration it is read from, and its
    `direct` and `enclosing` maintainers (the module docstring says which are which)."""

    package: Package | None
    key: str | None
    direct: tuple[str, ...]
    enclosing: tuple[str, ...] = ()

    @property
    def handles(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys([*self.direct, *self.enclosing]))

    def __str__(self) -> str:
        if self.package is None:
            return "shared code"
        if self.package.key is None:
            return f"{self.package} (`{self.key}`'s `{self.package.family}` family)"
        return str(self.package)


def groups(package: Package | None, rev: str) -> tuple[Group, ...]:
    """The package's owner groups at `rev`; raises NotOnRev for an integration that isn't there."""
    if package is None:
        return (Group(None, None, tuple(sorted(repo_maintainers()))),)
    found = []
    for key in (package.key,) if package.key else integrations_with(rev, package.family):
        if (theirs := maintainers(rev, key)) is None:
            raise NotOnRev(key)
        own = family_maintainers(rev, key, package.family) if package.family else None
        found.append(Group(package, key, own, theirs) if own else Group(package, key, theirs))
    return tuple(found)


def owners(package: Package, rev: str) -> set[str]:
    """Every handle that owns the package at `rev`, repo maintainers aside: the gate's set."""
    return {handle for group in groups(package, rev) for handle in group.handles}


def owned(paths: Iterable[str], rev: str, templates: Templates) -> dict[Group, list[str]]:
    """Each owner group of the paths, generated output aside, with the paths it owns. A path in an integration that
    isn't on the rev is shared code."""
    found: dict[Group, list[str]] = {}
    for path in paths:
        if path in GENERATED:
            continue
        try:
            held = groups(package_of(path, rev, templates), rev)
        except NotOnRev:
            held = groups(None, rev)
        for group in held:
            found.setdefault(group, []).append(path)
    return found


def foreign(login: str, paths: Iterable[str], rev: str, templates: Templates) -> dict[Group, list[str]]:
    """The owner groups of the paths whose direct maintainers don't include `login`, with their paths."""
    return {group: found for group, found in owned(paths, rev, templates).items() if login not in group.direct}


def route(groups: Iterable[Group]) -> tuple[list[str], list[str]]:
    """The labels and assignees of an issue routed to the groups: `integration:<key>` each, and their direct
    maintainers (scripts/route_issue.py labels a form's issue the same way)."""
    groups = list(groups)
    labels = list(dict.fromkeys(LABEL.format(key=group.key) for group in groups if group.key))
    assignees = list(dict.fromkeys(handle for group in groups for handle in group.direct))
    return labels, assignees


def row(group: Group, paths: list[str]) -> dict:
    return {
        "owner": group.package.slug if group.package else "",
        "package": str(group),
        "integration": group.key or "",
        "direct": list(group.direct),
        "enclosing": list(group.enclosing),
        "paths": paths,
    }


def line(group: Group, paths: list[str], noun: str = "path", quiet: str | None = None) -> str:
    """`control4: @a (2 paths)`; a family's integration's maintainers follow its own. The `quiet` handle is named
    without an `@`, so it isn't mentioned."""

    def named(handles: tuple[str, ...]) -> str:
        return " ".join(f"`{handle}`" if handle == quiet else f"@{handle}" for handle in handles)

    handles = named(group.direct) or "nobody"
    if group.enclosing:
        handles += f", and `{group.key}`'s " + named(group.enclosing)
    return f"{group}: {handles} ({len(paths)} {noun}{'s' * (len(paths) != 1)})"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", metavar="PATH")
    parser.add_argument("--rev", default="HEAD", help="where to read the owners (default HEAD)")
    parser.add_argument("--as", dest="login", help="only the groups that aren't this login's")
    shape = parser.add_mutually_exclusive_group()
    shape.add_argument("--json", action="store_true", help="the rows, as JSON")
    shape.add_argument("--issue", action="store_true", help="labels= and assignees= for an issue to the groups")
    args = parser.parse_args(argv)
    rev, templates = commit(args.rev), package_paths()
    found = foreign(args.login, args.paths, rev, templates) if args.login else owned(args.paths, rev, templates)
    if args.json:
        print(json.dumps([row(group, paths) for group, paths in found.items()], indent=2))
    elif args.issue:
        labels, assignees = route(found)
        print(f"labels={','.join(labels)}\nassignees={','.join(assignees)}")
    else:
        for group, paths in found.items():
            print(line(group, paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
