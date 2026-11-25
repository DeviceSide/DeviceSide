#!/usr/bin/env python3
"""Guard the two files contributors leave alone: README.md, outside its generated blocks, and manifest.json.

The README is the repo maintainers' writing, bar the block `gen_compat.py` regenerates (the device cards), which
any PR may refresh. A PR from anyone else that changes the text outside that block fails unless README.md is all it
changes: a typo fix stands alone and is easy to review, while a code PR can't slip prose in. (Hand edits inside the
blocks fail the generators' `--check` in tests.yml, so this doesn't look at them.) manifest.json changes by
exception (a core domain in `after_dependencies` slows HA's startup), so a change from anyone else is flagged for the
workflow to warn about on the PR, not failed. Renovate, which bumps its `requirements`, is exempt from the warning.

Both files are compared between the PR's merge base and its head, so a PR that merges `main` in isn't blamed for
`main`'s changes. The repo maintainers are `REPO_MAINTAINERS` in `scripts/gen_codeowners.py`, read by
`scripts/owners.py` without importing it (that imports the integrations): the workflow runs this from the base branch
with the standard library alone, and reads the PR's files only as data.

Usage: scripts/check_protected.py <base> <head> --author <login>

Exits 1 when the README check fails. Writes `readme=true|false` (it failed) and `manifest=true|false` (warn) to
`$GITHUB_OUTPUT` when set, for the workflow's comments.
"""

import argparse
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.owners import README, git, repo_maintainers, show  # noqa: E402

MANIFEST = "custom_components/deviceside/manifest.json"
# Generated blocks: the markers stay, what's between them is the generators'.
GENERATED = re.compile(r"(<!-- (\w+):start -->).*?(<!-- \2:end -->)", re.DOTALL)
MANIFEST_EXEMPT = frozenset({"renovate[bot]"})


def authored(text: str) -> str:
    return GENERATED.sub(r"\1\3", text)


def check(base: str, head: str, author: str, maintainers: frozenset[str]) -> tuple[bool, bool]:
    """(README passes, manifest needs a warning)."""
    if author in maintainers:
        return True, False
    merge_base = git("merge-base", base, head).strip()
    readme_only = git("diff", "--name-only", merge_base, head).split() == [README]
    readme_ok = readme_only or authored(show(merge_base, README)) == authored(show(head, README))
    manifest_changed = author not in MANIFEST_EXEMPT and show(merge_base, MANIFEST) != show(head, MANIFEST)
    return readme_ok, manifest_changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base")
    parser.add_argument("head")
    parser.add_argument("--author", required=True)
    args = parser.parse_args(argv)
    readme_ok, manifest_changed = check(args.base, args.head, args.author, repo_maintainers())
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a") as file:
            file.write(f"readme={str(not readme_ok).lower()}\nmanifest={str(manifest_changed).lower()}\n")
    if manifest_changed:
        print(f"::warning file={MANIFEST}::manifest.json changes by exception; a repo maintainer will review it")
    if not readme_ok:
        print(
            f"::error file={README}::This pull request changes README.md outside its generated blocks alongside other "
            "files. Move the README.md change to a pull request of its own; regenerating the blocks here is fine.",
        )
        return 1
    print("README.md: unchanged outside its generated blocks, a README-only PR, or a repo maintainer's")
    return 0


if __name__ == "__main__":
    sys.exit(main())
