#!/usr/bin/env python3
"""Decide whether a maintainer's `/merge` may merge a PR without a repo maintainer.

A PR is its commenter's to merge when they own every file it changes (CLAUDE.md, Maintainers). Each file's owners are
read on the base branch, so a PR can't name its own merger:

- in a family (`FAMILY_PATHS` in `scripts/gen_codeowners.py`): that family's maintainers and its integration's;
- in the catalog (`CATALOG_PATHS`): the maintainers of every family of that key, and of those families' integrations;
- elsewhere in an integration's package (`PATHS`), its `refusals.py` included: the integration's maintainers;
- generated output that CI's `--check` proves (`.github/CODEOWNERS`, and `README.md` and
  `docs/device-compatibility.md` inside their generated blocks): anyone who owns the rest;
- anything else: nobody.

A family's path whose family isn't on the base branch is its integration's. This refuses a PR that:

- changes nothing, a file nobody owns, or only generated output;
- changes a file of an integration that isn't on the base branch yet, or one the commenter doesn't own;
- changes the `maintainers=` of any `IntegrationInfo(...)` or `Family(...)` call in a Python file outside `tests/`,
  bound to `INTEGRATION` or `FAMILY` or not (the unsupported integration `integrations/hue/v1.py` declares), adds or
  removes such a call, or leaves an integration's or family's maintainers unreadable (a repo maintainer's, as is
  appointing one);
- changes `README.md` or `docs/device-compatibility.md` outside its generated blocks;
- sets or clears a `caveat` (a repo maintainer's, `docs/evidence.md`).

No rule here names a refusal entry (`NoKnownMethod`, `NotBuilt`): an integration with families keeps them in its
`refusals.py`, outside every family, so ownership by path keeps them from a family maintainer (CLAUDE.md,
Maintainers).

The ruleset on `main` still requires green, up-to-date checks, so this doesn't look at CI. Like
`check_protected.py`, it runs from the base branch on the standard library alone, and reads the PR's files with
`git show`, as data: the integrations and families are parsed, never imported. It compares calls and keywords by
name, so it can't see:

- a caveat set other than as a `caveat=` keyword or a `Caveat(...)` call;
- a family's rule change that moves devices between classes, out of a refused class or in from another family's (a
  family's rule group can run before another's): only the integration's classification snapshot
  (`tests/integrations/<x>/test_classification.py`) catches the devices it lists;
- a family's product code written in bad faith: the integration's tests import it, into their own process, so it
  can make any of them pass. Its test code can't silence them once the ruleset requires the CI job that runs them
  with every family's and the catalog's tests left out (`tests.yml`, `pytest-without-family-tests`;
  docs/repo-maintainers.md). The gate trusts an appointed maintainer not to, and the release candidate's audit
  reviews every merged change.

Usage: scripts/check_maintainer_merge.py <base> <head> --commenter <login>

Exits 1 when the PR may not merge this way, with the reason on stdout and as `reason=` in `$GITHUB_OUTPUT` when set.
"""

import argparse
import ast
import functools
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.check_protected import README, authored, git, show  # noqa: E402
from scripts.route_issue import called, parse, parse_family  # noqa: E402

CODEOWNERS_SCRIPT = REPO / "scripts" / "gen_codeowners.py"
INTEGRATIONS = "custom_components/deviceside/integrations/"
INIT = INTEGRATIONS + "{key}/__init__.py"
FAMILY_INIT = INTEGRATIONS + "{key}/families/{family}/__init__.py"
COMPAT = "docs/device-compatibility.md"
# Generated output: CODEOWNERS wholly, the other two inside their marked blocks (`BLOCKS`).
GENERATED = frozenset({README, COMPAT, ".github/CODEOWNERS"})
BLOCKS = (README, COMPAT)
# What a path template's `{key}` and `{family}` match: an integration's package name, and a family's as the registry
# shapes it (core/registry.py, FAMILY_KEY; tests/scripts/test_check_maintainer_merge.py pins them equal), which no
# `__init__.py` or `__pycache__` beside the families is.
NAMES = {"key": r"[a-z0-9_]+", "family": r"[a-z][a-z0-9_]*"}
# The calls whose `maintainers=` name owners.
DECLARES = frozenset({"IntegrationInfo", "Family"})


class Refused(Exception):
    """Why the PR may not merge this way."""


class Templates(NamedTuple):
    """The path templates of `gen_codeowners.py`: `PATHS`, `FAMILY_PATHS` and `CATALOG_PATHS`."""

    integration: tuple[str, ...]
    family: tuple[str, ...]
    catalog: tuple[str, ...]


@dataclass(frozen=True)
class Package:
    """What holds a changed file: an integration's package (`key`), a family of it (`key` and `family`), or the
    catalog file of a family key (`family` alone)."""

    key: str | None
    family: str | None = None

    def __str__(self) -> str:
        if self.key is None:
            return f"the `{self.family}` catalog"
        return f"`{self.key}`" + (f"'s `{self.family}` family" if self.family else "")

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


def package_of(path: str, base: str, templates: Templates) -> Package | None:
    """What holds `path`, or None for a file nobody but a repo maintainer owns. A family that isn't on the base branch
    has no owners of its own yet, so its paths are its integration's; a catalog file no family there shares, or that
    isn't there yet, is nobody's."""
    if (found := match(path, templates.family)) and family_maintainers(base, **found) is not None:
        return Package(**found)
    if found := match(path, templates.integration):
        return Package(found["key"])
    # A catalog file new on this PR is nobody's: it gives the other integration's family code this one imports.
    if (found := match(path, templates.catalog)) and integrations_with(base, found["family"]) and show(base, path):
        return Package(None, found["family"])
    return None


def integrations_of(package: Package, base: str) -> tuple[str, ...]:
    """The integrations whose maintainers own the package: its own, or for the catalog each that shares it."""
    return (package.key,) if package.key else integrations_with(base, package.family)


def owners(package: Package, base: str) -> set[str]:
    """Who may merge a change to the package, on the base branch; raises Refused for an integration not there yet."""
    found: set[str] = set()
    for key in integrations_of(package, base):
        if (theirs := maintainers(base, key)) is None:
            raise Refused(f"`{key}` isn't an integration on the base branch yet")
        found.update(theirs)
        if package.family:
            found.update(family_maintainers(base, key, package.family) or ())
    return found


class Marks(NamedTuple):
    """What a Python file holds that a maintainer doesn't change alone, as AST dumps: every `caveat=` keyword and
    `Caveat(...)` call, and, outside `tests/` (a test builds its own), the `maintainers=` keyword of every
    `IntegrationInfo(...)` and `Family(...)` call, or None for such a call without one."""

    caveats: list[str]
    maintainers: list[str | None]


def marks(text: str, path: str) -> Marks:
    try:
        tree = ast.parse(text)
    except SyntaxError as err:
        raise Refused(f"{path} doesn't parse ({err.msg})") from None
    nodes = list(ast.walk(tree))
    calls = [(called(node), node) for node in nodes if isinstance(node, ast.Call)]
    caveats = [ast.dump(node) for node in nodes if isinstance(node, ast.keyword) and node.arg == "caveat"]
    caveats += [ast.dump(node) for name, node in calls if name == "Caveat"]
    declared = [] if path.startswith("tests/") else [node for name, node in calls if name in DECLARES]
    return Marks(
        sorted(caveats),
        [next((ast.dump(kw.value) for kw in node.keywords if kw.arg == "maintainers"), None) for node in declared],
    )


def held_by(files: list[str], base: str, commenter: str, templates: Templates) -> dict[str, Package]:
    """The package holding each changed file, generated output aside; raises Refused unless the commenter owns each."""
    found = {path: package_of(path, base, templates) for path in files if path not in GENERATED}
    if outside := [path for path, package in found.items() if package is None]:
        raise Refused(f"it changes files outside an integration's package: {', '.join(outside[:5])}")
    if not found:
        raise Refused("it changes no integration's package")
    for package in dict.fromkeys(found.values()):
        if commenter not in owners(package, base):
            raise Refused(f"@{commenter} isn't a maintainer of {package.owned_by()}")
    return found


def check_maintainers(packages: list[Package], head: str, before: dict[str, Marks], after: dict[str, Marks]) -> None:
    """Refuses a PR that changes an integration's or family's `maintainers=` value, wherever it is declared, or leaves
    a package's unreadable at its head."""
    for path in before:
        if before[path].maintainers != after[path].maintainers:
            raise Refused(f"it changes a `maintainers` value in {path}")
    for package in packages:
        if package.key and maintainers(head, package.key) is None:
            raise Refused(f"it leaves `{package.key}`'s maintainers unreadable")
        if package.key and package.family and family_maintainers(head, package.key, package.family) is None:
            raise Refused(f"it leaves the maintainers of {package} unreadable")


def check(base: str, head: str, commenter: str, templates: Templates) -> list[Package]:
    """The packages the PR changes, when it may merge this way; raises Refused otherwise."""
    # As commits, so what is read at each is cached by content, whatever the names point to next.
    base, head = (git("rev-parse", "--verify", f"{rev}^{{commit}}").strip() for rev in (base, head))
    merge_base = git("merge-base", base, head).strip()
    files = [path for path in git("diff", "-z", "--name-only", "--no-renames", merge_base, head).split("\0") if path]
    if not files:
        raise Refused("it changes nothing")
    held = held_by(files, base, commenter, templates)
    packages = sorted(set(held.values()), key=lambda package: (package.key or "", package.family or ""))
    before = {path: marks(show(merge_base, path), path) for path in files if path.endswith(".py")}
    after = {path: marks(show(head, path), path) for path in before}
    check_maintainers(packages, head, before, after)
    for path in BLOCKS:
        if path in files and authored(show(merge_base, path)) != authored(show(head, path)):
            raise Refused(f"it changes {path} outside its generated blocks")
    for path in before:
        if before[path].caveats != after[path].caveats:
            raise Refused(f"it sets or clears a caveat in {path}")
    return packages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base")
    parser.add_argument("head")
    parser.add_argument("--commenter", required=True)
    args = parser.parse_args(argv)
    try:
        packages = check(args.base, args.head, args.commenter, package_paths())
    except Refused as refused:
        # On one line: the reason names the PR's paths, and a newline in one would add a line to `$GITHUB_OUTPUT`.
        message = " ".join(f"A repo maintainer needs to merge this: {refused}.".splitlines())
        if output := os.environ.get("GITHUB_OUTPUT"):
            with open(output, "a") as file:
                file.write(f"reason={message}\n")
        print(message)
        return 1
    print(f"Every file it changes is in {', '.join(map(str, packages))}, which @{args.commenter} owns.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
