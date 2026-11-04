#!/usr/bin/env python3
"""Check that a tag may be cut from a branch: the tag rules cut-release-candidate and cut-release share.

- `vX.Y.ZrcN` from `release/vX.Y.Z`, or from `main` as a hotfix RC one patch above the latest release.
- `vX.Y.Z` from `main` only, above the latest release.
- Never a tag that already exists.
- manifest.json's version is the tag's X.Y.Z, an RC's included: HA and HACS show the installed version from it.

Usage: scripts/check_tag.py <tag> <branch>
"""

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = Path("custom_components") / "device_side" / "manifest.json"
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


def manifest_error(repo: Path, version: Version) -> str | None:
    """Why manifest.json's version isn't the tag's X.Y.Z, or None when it is."""
    try:
        found = json.loads((repo / MANIFEST).read_text()).get("version")
    except (OSError, ValueError) as err:
        return f"{MANIFEST} can't be read: {err}"
    expected = name(version)[1:]
    return None if found == expected else f"{MANIFEST} has version {found!r}, not {expected!r}"


def errors(repo: Path, tag: str, branch: str) -> list[str]:
    found = releases(repo)
    latest = found[-1][0] if found else (0, 0, 0)
    problems = []
    version = None
    if match := RC.match(tag):
        version = tuple(map(int, match.groups()[:3]))
        if branch == "main":
            hotfix = (latest[0], latest[1], latest[2] + 1)
            if version != hotfix:
                problems.append(f"a hotfix RC from main must be {name(hotfix)}rcN, not {tag}")
        elif branch != f"release/{name(version)}":
            problems.append(f"{tag} must be cut from release/{name(version)} or, as a hotfix, from main; not {branch}")
    elif match := RELEASE.match(tag):
        version = tuple(map(int, match.groups()))
        if branch != "main":
            problems.append(f"a release is cut from main only, not {branch}")
        if version <= latest:
            problems.append(f"{tag} is not above the latest release, {name(latest)}")
    else:
        problems.append(f"{tag} matches neither vX.Y.ZrcN nor vX.Y.Z")
    if git(repo, "tag", "--list", tag):
        problems.append(f"{tag} already exists")
    if version is not None and (problem := manifest_error(repo, version)):
        problems.append(problem)
    return problems


def main(argv: list[str] | None = None, repo: Path = REPO) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    problems = errors(repo, *argv)
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
