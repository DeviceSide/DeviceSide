#!/usr/bin/env python3
"""Decide whether a maintainer's `/merge` may merge a PR without a repo maintainer.

A PR is its commenter's to merge when they own every file it changes (CLAUDE.md, Maintainers). Each file's owners are
read on the base branch by `scripts/owners.py`, the one owner lookup, so a PR can't name its own merger:

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

The ruleset's merge queue on `main` still requires green checks on the PR merged onto current `main`, so this
doesn't look at CI. Like `check_protected.py`, it runs from the base branch on the standard library alone, and reads
the PR's files with `git show`, as data: the integrations and families are parsed, never imported. It compares calls
and keywords by name, so it can't see:

- a caveat set other than as a `caveat=` keyword or a `Caveat(...)` call;
- a family's rule change that moves devices between classes, out of a refused class or in from another family's (a
  family's rule group can run before another's): only the integration's classification snapshot
  (`tests/integrations/<x>/test_classification.py`) catches the devices it lists;
- a family's product code written in bad faith: the integration's tests import it, into their own process, so it
  can make any of them pass. Its test code can't silence them: a required CI job runs them with every family's and
  the catalog's tests left out (`tests.yml`, `pytest-without-family-tests`; docs/repo-maintainers.md). The gate
  trusts an appointed maintainer not to, and the release candidate's audit reviews every merged change.

Usage: scripts/check_maintainer_merge.py <base> <head> --commenter <login>

Exits 1 when the PR may not merge this way, with the reason on stdout and as `reason=` in `$GITHUB_OUTPUT` when set.
"""

import argparse
import ast
import os
import sys
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts import owners as lookup  # noqa: E402
from scripts.check_protected import authored  # noqa: E402
from scripts.owners import (  # noqa: E402
    COMPAT,
    GENERATED,
    README,
    Package,
    Templates,
    called,
    commit,
    family_maintainers,
    git,
    maintainers,
    package_of,
    package_paths,
    show,
)

BLOCKS = (README, COMPAT)
# The calls whose `maintainers=` name owners.
DECLARES = frozenset({"IntegrationInfo", "Family"})


class Refused(Exception):
    """Why the PR may not merge this way."""


def owners(package: Package, base: str) -> set[str]:
    """Who may merge a change to the package, on the base branch; raises Refused for an integration not there yet."""
    try:
        return lookup.owners(package, base)
    except lookup.NotOnRev as err:
        raise Refused(f"`{err.key}` isn't an integration on the base branch yet") from None


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
    base, head = commit(base), commit(head)
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
