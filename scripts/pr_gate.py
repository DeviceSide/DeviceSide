#!/usr/bin/env python3
"""Close an outside pull request unless its author is assigned to an issue it references.

New devices and integrations come through the "Propose a device or integration" issue form; the maintainer approves a
proposal by assigning the issue to whoever will build it. A pull request passes when its author is among the assignees
of an issue it references: a closing reference (keyword or sidebar link) or a bare `#N` or issue URL in its body, so
`Part of #N` counts. References to pull requests don't count.

Exempt: authors with write access (`OWNER`, `MEMBER`, `COLLABORATOR`), bot accounts, a reopen by a maintainer (an
override), and prose-only changes: every changed file is Markdown and none is binding (`BINDING`).

A failing open pull request gets a comment and is closed. A pull request the gate closed reopens once an edit makes it
pass: its author can't reopen a pull request someone else closed. Nothing else is touched, so a run is idempotent.

The pr-gate workflow runs this from the base branch on `pull_request_target`; it never checks out or runs PR code.

Usage: scripts/pr_gate.py --pr N [--repo owner/name] [--sender login] [--dry-run]
"""

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from fnmatch import fnmatchcase

MAINTAINERS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
WRITE = frozenset({"admin", "maintain", "write"})
GATE = "github-actions[bot]"  # the account GITHUB_TOKEN acts as, so the one a gate close shows
# Markdown that binds behavior, scope or the release rules: a change to it is gated like code.
BINDING = (
    "CLAUDE.md",
    "*/CLAUDE.md",
    "docs/design.md",
    "docs/action-behavior.md",
    "docs/device-compatibility.md",
    "docs/test-records/*",
    "docs/audits/*",
    ".github/*",
)
MAX_REFS = 20  # issues looked up per pull request; a body listing more is unusual and costs API calls
FORM = "propose_device_or_integration.yml"

COMMENT = """\
Thanks for the pull request! DeviceSide accepts outside pull requests only for an issue assigned to their author, so \
that each new device or integration is agreed before anyone spends time building it.

To propose one, [open a proposal]({url}/issues/new?template={form}) and say you'd like to build it. Once the issue is \
assigned to you, reference it in this pull request's description (`Closes #N` or `Part of #N`) and the pull request \
reopens automatically. [CONTRIBUTING.md]({url}/blob/main/CONTRIBUTING.md) has the details.
"""


@dataclass(frozen=True)
class Issue:
    is_pr: bool
    assignees: frozenset[str] = frozenset()


@dataclass
class PullRequest:
    number: int
    author: str
    author_type: str  # "User" or "Bot"
    association: str  # author_association
    files: list[str]  # changed paths, a rename's old path included
    body: str
    closing: list[int] = field(default_factory=list)  # closing issue references in this repository
    state: str = "open"  # "open", "closed" or "merged"


@dataclass(frozen=True)
class Verdict:
    outcome: str  # "pass", "exempt" or "close"
    reason: str


def prose_only(files: list[str]) -> bool:
    """Every file is Markdown and none is binding."""
    return bool(files) and all(
        path.endswith(".md") and not any(fnmatchcase(path, pattern) for pattern in BINDING) for path in files
    )


def referenced(body: str, closing: list[int], repo: str) -> list[int]:
    """Issue numbers the pull request references, closing references first, without repeats."""
    url = re.compile(rf"https://github\.com/{re.escape(repo)}/(?:issues|pull)/(\d+)\b", re.IGNORECASE)
    bare = re.compile(r"(?<![\w/#&])#(\d+)\b")
    found = [*closing, *(int(n) for n in url.findall(body or "")), *(int(n) for n in bare.findall(body or ""))]
    return list(dict.fromkeys(found))


def decide(pr: PullRequest, issues: dict[int, Issue], reopened_by_maintainer: bool = False) -> Verdict:
    """The verdict on pr, given the referenced numbers that exist, each an issue or a pull request."""
    if pr.association in MAINTAINERS:
        return Verdict("exempt", f"author association {pr.association}")
    if pr.author_type == "Bot":
        return Verdict("exempt", "bot author")
    if reopened_by_maintainer:
        return Verdict("exempt", "reopened by a maintainer")
    if prose_only(pr.files):
        return Verdict("exempt", "prose-only change")
    for number, issue in issues.items():
        if not issue.is_pr and pr.author in issue.assignees:
            return Verdict("pass", f"author is assigned to #{number}")
    return Verdict("close", "no assigned issue referenced")


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def fetch(repo: str, number: int) -> PullRequest:
    pull = json.loads(gh("api", f"repos/{repo}/pulls/{number}"))
    files = []
    for page in json.loads(gh("api", "--paginate", "--slurp", f"repos/{repo}/pulls/{number}/files")):
        for changed in page:
            files += [changed["filename"]] + (
                [changed["previous_filename"]] if changed.get("previous_filename") else []
            )
    owner, name = repo.split("/")
    query = """query($owner: String!, $name: String!, $number: Int!) {
      repository(owner: $owner, name: $name) { pullRequest(number: $number) {
        closingIssuesReferences(first: 25) { nodes { number repository { nameWithOwner } } } } } }"""
    fields = {"query": query, "owner": owner, "name": name}
    args = [arg for key, value in fields.items() for arg in ("-f", f"{key}={value}")]
    graph = json.loads(gh("api", "graphql", *args, "-F", f"number={number}"))
    nodes = graph["data"]["repository"]["pullRequest"]["closingIssuesReferences"]["nodes"]
    return PullRequest(
        number=number,
        author=pull["user"]["login"],
        author_type=pull["user"]["type"],
        association=pull["author_association"],
        files=files,
        body=pull.get("body") or "",
        closing=[node["number"] for node in nodes if node["repository"]["nameWithOwner"].lower() == repo.lower()],
        state="merged" if pull.get("merged") else pull["state"],
    )


def fetch_issues(repo: str, numbers: list[int]) -> dict[int, Issue]:
    """Each number that exists, as an issue or a pull request; a missing one is left out."""
    issues = {}
    for number in numbers[:MAX_REFS]:
        try:
            issue = json.loads(gh("api", f"repos/{repo}/issues/{number}"))
        except subprocess.CalledProcessError:
            continue
        issues[number] = Issue("pull_request" in issue, frozenset(a["login"] for a in issue.get("assignees") or []))
    return issues


def has_write(repo: str, login: str) -> bool:
    try:
        return json.loads(gh("api", f"repos/{repo}/collaborators/{login}/permission"))["permission"] in WRITE
    except subprocess.CalledProcessError, KeyError, ValueError:
        return False


def closed_by_gate(repo: str, number: int) -> bool:
    """The pull request's latest close was the gate's."""
    events = [
        e
        for page in json.loads(gh("api", "--paginate", "--slurp", f"repos/{repo}/issues/{number}/events"))
        for e in page
    ]
    closes = [e for e in events if e.get("event") == "closed"]
    return bool(closes) and (closes[-1].get("actor") or {}).get("login") == GATE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--sender", help="who triggered a reopen; a maintainer's reopen is an override")
    parser.add_argument("--dry-run", action="store_true", help="print the verdict only")
    args = parser.parse_args(argv)
    if not args.repo:
        parser.error("--repo or GITHUB_REPOSITORY is required")

    pr = fetch(args.repo, args.pr)
    if pr.state == "merged":
        print(f"#{pr.number}: merged, nothing to do")
        return 0
    override = bool(args.sender) and args.sender != pr.author and has_write(args.repo, args.sender)
    verdict = decide(pr, fetch_issues(args.repo, referenced(pr.body, pr.closing, args.repo)), override)
    print(f"#{pr.number} by {pr.author}: {verdict.outcome} ({verdict.reason})")
    if args.dry_run:
        return 0

    if verdict.outcome == "close" and pr.state == "open":
        url = f"https://github.com/{args.repo}"
        gh("pr", "comment", str(pr.number), "--repo", args.repo, "--body", COMMENT.format(url=url, form=FORM))
        gh("pr", "close", str(pr.number), "--repo", args.repo)
        print(f"#{pr.number}: commented and closed")
    elif verdict.outcome == "pass" and pr.state == "closed" and closed_by_gate(args.repo, pr.number):
        gh("pr", "reopen", str(pr.number), "--repo", args.repo)
        print(f"#{pr.number}: reopened")
    return 0


if __name__ == "__main__":
    sys.exit(main())
