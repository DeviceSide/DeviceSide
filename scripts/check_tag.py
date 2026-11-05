#!/usr/bin/env python3
"""Check that a tag may be cut, and print the commit it goes on: the rules cut-release-candidate and cut-release share.

- `vX.Y.ZrcN` from `main`, or from `release/vX.Y.Z` (cut from an RC or release tag to fix one without what `main`
  has gained since). It goes on the branch head.
- `vX.Y.Z` is dispatched from `main` and goes on its latest RC's commit, never a branch head: what ships is what soaked.
- Either is above the latest release, and is never a tag that already exists.
- manifest.json's version, at the commit the tag goes on, is the tag's X.Y.Z, an RC's included: HA and HACS show the
  installed version from it.

Usage: scripts/check_tag.py <tag> <branch>
"""

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = Path("custom_components") / "deviceside" / "manifest.json"
RC = re.compile(r"^v(\d+)\.(\d+)\.(\d+)rc(\d+)$")
RELEASE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")

Version = tuple[int, int, int]


def name(version: Version) -> str:
    return "v{}.{}.{}".format(*version)


def git(repo: Path, *args: str, check: bool = True) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=check, capture_output=True, text=True).stdout.strip()


def releases(repo: Path, merged_into: str | None = None) -> list[tuple[Version, str]]:
    """Release tags (never RCs), oldest first; with merged_into, only those that are its ancestors."""
    args = ["tag", "--list", "v*"] + (["--merged", merged_into] if merged_into else [])
    found = [
        (tuple(map(int, match.groups())), tag) for tag in git(repo, *args).split() if (match := RELEASE.match(tag))
    ]
    return sorted(found)


def latest_rc(repo: Path, version: Version) -> str | None:
    """The highest-numbered RC tag of this version, or None if it has none."""
    found = [
        (int(match[4]), tag)
        for tag in git(repo, "tag", "--list", f"{name(version)}rc*").split()
        if (match := RC.match(tag))
    ]
    return max(found)[1] if found else None


def manifest_error(repo: Path, commit: str, version: Version) -> str | None:
    """Why manifest.json's version at commit isn't the tag's X.Y.Z, or None when it is."""
    shown = subprocess.run(
        ["git", "-C", str(repo), "show", f"{commit}:{MANIFEST.as_posix()}"], capture_output=True, text=True
    )
    if shown.returncode:
        return f"{MANIFEST} can't be read at {commit}: {shown.stderr.strip()}"
    try:
        found = json.loads(shown.stdout).get("version")
    except ValueError as err:
        return f"{MANIFEST} can't be read: {err}"
    expected = name(version)[1:]
    return None if found == expected else f"{MANIFEST} has version {found!r}, not {expected!r}"


def target(repo: Path, tag: str) -> tuple[str | None, list[str]]:
    """The commit tag goes on, and why it may not be cut."""
    found = releases(repo)
    latest = found[-1][0] if found else (0, 0, 0)
    problems = []
    version = commit = None
    if match := RC.match(tag):
        version = tuple(map(int, match.groups()[:3]))
        commit = "HEAD"
    elif match := RELEASE.match(tag):
        version = tuple(map(int, match.groups()))
        if (rc := latest_rc(repo, version)) is None:
            problems.append(f"{tag} has no RC to release; cut {tag}rc1 first")
        else:
            commit = rc
    else:
        problems.append(f"{tag} matches neither vX.Y.ZrcN nor vX.Y.Z")
    if version is not None and version <= latest:
        problems.append(f"{tag} is not above the latest release, {name(latest)}")
    if git(repo, "tag", "--list", tag):
        problems.append(f"{tag} already exists")
    if commit is not None and (problem := manifest_error(repo, commit, version)):
        problems.append(problem)
    return (git(repo, "rev-parse", f"{commit}^{{commit}}") if commit else None), problems


def errors(repo: Path, tag: str, branch: str) -> list[str]:
    problems = []
    if match := RC.match(tag):
        version = name(tuple(map(int, match.groups()[:3])))
        if branch not in ("main", f"release/{version}"):
            problems.append(f"{tag} must be cut from main or release/{version}, not {branch}")
    elif RELEASE.match(tag) and branch != "main":
        problems.append(f"a release is dispatched from main only, not {branch}")
    return problems + target(repo, tag)[1]


def main(argv: list[str] | None = None, repo: Path = REPO) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    problems = errors(repo, *argv)
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    if not problems:
        print(target(repo, argv[0])[0])
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
