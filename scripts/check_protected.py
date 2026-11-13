#!/usr/bin/env python3
"""Guard the two files contributors leave alone: README.md, outside its generated blocks, and manifest.json.

The README is the repo maintainers' writing, bar the blocks `gen_features.py` and `gen_compat.py` regenerate, which
any PR may refresh. A PR from anyone else that changes the text outside those blocks fails. manifest.json changes by
exception (a core domain in `after_dependencies` slows HA's startup), so a change from anyone else is flagged for the
workflow to warn about on the PR, not failed. Renovate, which bumps its `requirements`, is exempt from the warning.

Both files are compared between the PR's merge base and its head, so a PR that merges `main` in isn't blamed for
`main`'s changes. The repo maintainers are `REPO_MAINTAINERS` in `scripts/gen_codeowners.py`, read without importing it
(that imports the integrations): the workflow runs this from the base branch with the standard library alone, and
reads the PR's files only as data.

Usage: scripts/check_protected.py <base> <head> --author <login>

Exits 1 when the README check fails. Writes `manifest=true|false` to `$GITHUB_OUTPUT` when set.
"""

import argparse
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

README = "README.md"
MANIFEST = "custom_components/deviceside/manifest.json"
REPO = Path(__file__).resolve().parents[1]
CODEOWNERS_SCRIPT = REPO / "scripts" / "gen_codeowners.py"
# Generated blocks: the markers stay, what's between them is the generators'.
GENERATED = re.compile(r"(<!-- (\w+):start -->).*?(<!-- \2:end -->)", re.DOTALL)
MANIFEST_EXEMPT = frozenset({"renovate[bot]"})


def repo_maintainers(script: Path = CODEOWNERS_SCRIPT) -> frozenset[str]:
    for node in ast.parse(script.read_text()).body:
        if isinstance(node, ast.AnnAssign | ast.Assign):
            targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
            if any(isinstance(t, ast.Name) and t.id == "REPO_MAINTAINERS" for t in targets):
                return frozenset(ast.literal_eval(node.value))
    raise SystemExit(f"no REPO_MAINTAINERS in {script}")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def show(rev: str, path: str) -> str:
    """The file at `rev`, or "" when it doesn't exist there."""
    try:
        return git("show", f"{rev}:{path}")
    except subprocess.CalledProcessError:
        return ""


def authored(text: str) -> str:
    return GENERATED.sub(r"\1\3", text)


def check(base: str, head: str, author: str, maintainers: frozenset[str]) -> tuple[bool, bool]:
    """(README passes, manifest needs a warning)."""
    if author in maintainers:
        return True, False
    merge_base = git("merge-base", base, head).strip()
    readme_ok = authored(show(merge_base, README)) == authored(show(head, README))
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
            file.write(f"manifest={str(manifest_changed).lower()}\n")
    if manifest_changed:
        print(f"::warning file={MANIFEST}::manifest.json changes by exception; a repo maintainer will review it")
    if not readme_ok:
        print(
            f"::error file={README}::README.md is the repo maintainers' to edit outside its generated blocks. "
            "Revert the change and say in the pull request what it should say; regenerating the blocks is fine.",
        )
        return 1
    print("README.md: no change outside its generated blocks, or a repo maintainer's PR")
    return 0


if __name__ == "__main__":
    sys.exit(main())
