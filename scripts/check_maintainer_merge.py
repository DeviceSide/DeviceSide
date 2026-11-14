#!/usr/bin/env python3
"""Decide whether an integration maintainer's `/merge` may merge a PR without a repo maintainer.

A PR confined to one integration's package is its maintainers' to merge (CONTRIBUTING's "Maintaining an integration").
This passes a PR when:

- every file it changes is in one integration's package (`PATHS` in `scripts/gen_codeowners.py`), or is generated
  output that CI's `--check` proves (`docs/device-compatibility.md`, `.github/CODEOWNERS`, and `README.md` inside its
  generated blocks);
- the commenter is one of that integration's maintainers on the base branch, so a PR can't name its own merger;
- it leaves the maintainers alone, and sets or clears no `caveat` (a repo maintainer's, `docs/evidence.md`).

The ruleset on `main` still requires green, up-to-date checks, so this doesn't look at CI. Like
`check_protected.py`, it runs from the base branch on the standard library alone, and reads the PR's files with
`git show`, as data: the integrations are parsed, never imported. A caveat set other than as a `caveat=` keyword or a
`Caveat(...)` call isn't seen; the release candidate's audit reviews every merged change.

Usage: scripts/check_maintainer_merge.py <base> <head> --commenter <login>

Exits 1 when the PR may not merge this way, with the reason on stdout and as `reason=` in `$GITHUB_OUTPUT` when set.
"""

import argparse
import ast
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.check_protected import README, authored, git, show  # noqa: E402
from scripts.route_issue import parse  # noqa: E402

CODEOWNERS_SCRIPT = REPO / "scripts" / "gen_codeowners.py"
INIT = "custom_components/deviceside/integrations/{key}/__init__.py"
GENERATED = frozenset({README, "docs/device-compatibility.md", ".github/CODEOWNERS"})


class Refused(Exception):
    """Why the PR may not merge this way."""


def package_paths(script: Path = CODEOWNERS_SCRIPT) -> tuple[str, ...]:
    """`PATHS` from `gen_codeowners.py`, read without importing it (that imports the integrations)."""
    for node in ast.parse(script.read_text()).body:
        if isinstance(node, ast.Assign) and [getattr(t, "id", None) for t in node.targets] == ["PATHS"]:
            return tuple(ast.literal_eval(node.value))
    raise SystemExit(f"no PATHS in {script}")


def package_of(path: str, templates: tuple[str, ...]) -> str | None:
    """The integration key whose package holds `path`, or None."""
    for template in templates:
        prefix, suffix = template.split("{key}")
        pattern = re.escape(prefix) + r"([a-z0-9_]+)" + (re.escape(suffix) + ("" if suffix.endswith("/") else "$"))
        if match := re.match(pattern, path):
            return match[1]
    return None


def maintainers(rev: str, key: str) -> tuple[str, ...] | None:
    """The integration's maintainers at `rev`, or None when it has no readable `__init__.py` there."""
    init = INIT.format(key=key)
    if not (text := show(rev, init)):
        return None
    try:
        return parse(text, init).maintainers
    except SyntaxError, SystemExit:
        return None


def caveats(text: str, path: str) -> list[str]:
    """Every `caveat=` keyword and `Caveat(...)` call in a Python file, as AST dumps."""
    try:
        tree = ast.parse(text)
    except SyntaxError as err:
        raise Refused(f"{path} doesn't parse ({err.msg})") from None
    found = [ast.dump(node) for node in ast.walk(tree) if isinstance(node, ast.keyword) and node.arg == "caveat"]
    found += [
        ast.dump(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "Caveat"
    ]
    return sorted(found)


def check(base: str, head: str, commenter: str, templates: tuple[str, ...]) -> str:
    """The integration key when the PR may merge this way; raises Refused otherwise."""
    merge_base = git("merge-base", base, head).strip()
    files = git("diff", "--name-only", "--no-renames", merge_base, head).split()
    if not files:
        raise Refused("it changes nothing")
    keys = {key for path in files if (key := package_of(path, templates))}
    if outside := [path for path in files if not package_of(path, templates) and path not in GENERATED]:
        raise Refused(f"it changes files outside an integration's package: {', '.join(outside[:5])}")
    if len(keys) != 1:
        raise Refused(f"it changes {'no' if not keys else 'more than one'} integration's package")
    key = keys.pop()
    owners = maintainers(base, key)
    if owners is None:
        raise Refused(f"`{key}` isn't an integration on the base branch yet")
    if commenter not in owners:
        raise Refused(f"@{commenter} isn't a maintainer of `{key}`")
    if maintainers(head, key) != owners:
        raise Refused(f"it changes `{key}`'s maintainers")
    if README in files and authored(show(merge_base, README)) != authored(show(head, README)):
        raise Refused("it changes README.md outside its generated blocks")
    for path in files:
        if path.endswith(".py") and caveats(show(merge_base, path), path) != caveats(show(head, path), path):
            raise Refused(f"it sets or clears a caveat in {path}")
    return key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base")
    parser.add_argument("head")
    parser.add_argument("--commenter", required=True)
    args = parser.parse_args(argv)
    try:
        key = check(args.base, args.head, args.commenter, package_paths())
    except Refused as refused:
        message = f"A repo maintainer needs to merge this: {refused}."
        if output := os.environ.get("GITHUB_OUTPUT"):
            with open(output, "a") as file:
                file.write(f"reason={message}\n")
        print(message)
        return 1
    print(f"Confined to `{key}`'s package, and @{args.commenter} maintains it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
