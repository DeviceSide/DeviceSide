#!/usr/bin/env python3
"""Refuse a commit whose files or message name the household's private details.

The repo is public, so the blocklist cannot live in it. Terms come from gitignored files in the main checkout, so a
linked worktree is checked too: .private-terms (one term per line, for names, hostnames and anything else) and
.private-terms.rig, which the rig rewrites on each run with its profiles' entity IDs and IEEEs and its HA host and
token. A line of either may be `term<TAB>label`, reported by its label: a secret is never echoed.
Where neither exists (CI, a contributor's clone) the check passes.

Usage: scripts/check_private.py FILE ...   (pre-commit passes staged files, or the message file at commit-msg)
"""

import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main_checkout(repo: Path = REPO) -> Path:
    """The main checkout, which holds the gitignored household files for every linked worktree; else `repo`."""
    try:
        common = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except OSError, subprocess.CalledProcessError:
        return repo
    return Path(common).parent


MAIN_CHECKOUT = main_checkout()
TERMS_FILES = (MAIN_CHECKOUT / ".private-terms", MAIN_CHECKOUT / ".private-terms.rig")


def private_terms(files: Iterable[Path] = TERMS_FILES) -> dict[str, str]:
    """Lowercased term -> label to report."""
    terms: dict[str, str] = {}
    for path in files:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            term, _, label = line.partition("\t")
            if (term := term.strip()) and not term.startswith("#"):
                terms[term.lower()] = label.strip() or term
    return terms


def find(paths: list[Path], terms: dict[str, str]) -> list[str]:
    hits = []
    for path in paths:
        try:
            lines = path.read_text().splitlines()
        except UnicodeDecodeError, FileNotFoundError:
            continue
        for number, line in enumerate(lines, 1):
            lowered = line.lower()
            hits.extend(f"{path}:{number}: {label}" for term, label in terms.items() if term in lowered)
    return hits


def main(argv: list[str]) -> int:
    if not (terms := private_terms()):
        return 0
    if hits := find([Path(arg) for arg in argv], terms):
        print("Private details in a public repo:", *hits, sep="\n  ")
        print("Remove them, or move them to a gitignored file (CLAUDE.local.md, notes/, .private-terms).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
