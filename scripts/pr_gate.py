#!/usr/bin/env python3
"""Close an outside pull request unless its author is assigned to an issue it references.

New devices and integrations come through the "Propose a device or integration" issue form; the maintainer approves a
proposal by assigning the issue to whoever will build it. A pull request passes when its author is among the assignees
of an issue it references: a closing reference (keyword or sidebar link) or a bare `#N` or issue URL in its body, so
`Part of #N` counts. References to pull requests don't count.

Exempt: authors with write access (`OWNER`, `MEMBER`, `COLLABORATOR`), bot accounts, a reopen by a maintainer (an
override), pull requests up to `HELD` on an event (`--manual` gates them), and prose-only changes: every changed
file is Markdown and none is binding (`BINDING`).

A failing open pull request gets a comment and is closed. A pull request the gate closed reopens once an edit makes it
pass: its author can't reopen a pull request someone else closed. Nothing else is touched, so a run is idempotent.

The pr-gate workflow runs this from the base branch on `pull_request_target`; it never checks out or runs PR code.

Usage: scripts/pr_gate.py --pr N [--repo owner/name] [--manual] [--dry-run]
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
# The account GITHUB_TOKEN acts as, so the one a gate close shows; no other workflow here closes pull requests.
GATE = "github-actions[bot]"
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
# Pull requests opened before the gate, held until the TODO.md item that runs it over them by hand, then 0.
HELD = 351
MAX_REFS = 20  # issues looked up per pull request; a body listing more is unusual and costs API calls
FORM = "propose_device_or_integration.yml"

COMMENT = """\
Thanks for the pull request! DeviceSide accepts outside pull requests only for an issue assigned to their author, so \
that each new device or integration is agreed before anyone spends time building it.

To propose one, [open a proposal]({url}/issues/new?template={form}) and say you'd like to build it. Once the issue is \
assigned to you, edit this pull request's description to reference it (`Closes #N` or `Part of #N`) and the pull \
request reopens automatically. An edit is what re-runs the check, so make one after the \
assignment. [CONTRIBUTING.md]({url}/blob/main/CONTRIBUTING.md) has the details.
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


def decide(
    pr: PullRequest, issues: dict[int, Issue], reopened_by_maintainer: bool = False, manual: bool = False
) -> Verdict:
    """The verdict on pr, given the referenced numbers that exist, each an issue or a pull request."""
    if pr.association in MAINTAINERS:
        return Verdict("exempt", f"author association {pr.association}")
    if pr.author_type == "Bot":
        return Verdict("exempt", "bot author")
    if pr.number <= HELD and not manual:
        return Verdict("exempt", f"opened before the gate (#{HELD} or earlier)")
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


def gone(err: subprocess.CalledProcessError) -> bool:
    """The call failed because what it asked for doesn't exist; any other failure (rate limit, outage) is raised."""
    return any(f"HTTP {code}" in (err.stderr or "") for code in (404, 410))


def fetch_issues(repo: str, numbers: list[int]) -> dict[int, Issue]:
    """Each number that exists, as an issue or a pull request; a missing one is left out."""
    issues = {}
    for number in numbers[:MAX_REFS]:
        try:
            issue = json.loads(gh("api", f"repos/{repo}/issues/{number}"))
        except subprocess.CalledProcessError as err:
            if gone(err):
                continue
            raise
        issues[number] = Issue("pull_request" in issue, frozenset(a["login"] for a in issue.get("assignees") or []))
    return issues


def has_write(repo: str, login: str) -> bool:
    try:
        return json.loads(gh("api", f"repos/{repo}/collaborators/{login}/permission"))["permission"] in WRITE
    except subprocess.CalledProcessError as err:
        if gone(err):  # not a collaborator
            return False
        raise


def fetch_events(repo: str, number: int) -> list[dict]:
    pages = json.loads(gh("api", "--paginate", "--slurp", f"repos/{repo}/issues/{number}/events"))
    return [event for page in pages for event in page]


def latest_actor(events: list[dict], kind: str) -> str | None:
    """Who did the latest event of this kind, or None if there is none."""
    found = [event for event in events if event.get("event") == kind]
    return (found[-1].get("actor") or {}).get("login") if found else None


def reopened_by_maintainer(repo: str, pr: PullRequest, events: list[dict]) -> bool:
    """The latest reopen was by someone with write access other than the author or the gate: an override that holds
    through later edits."""
    actor = latest_actor(events, "reopened")
    return actor not in (None, pr.author, GATE) and has_write(repo, actor)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--manual", action="store_true", help="a dispatched run: gates pull requests up to HELD too")
    parser.add_argument("--dry-run", action="store_true", help="print the verdict only")
    args = parser.parse_args(argv)
    if not args.repo:
        parser.error("--repo or GITHUB_REPOSITORY is required")

    pr = fetch(args.repo, args.pr)
    if pr.state == "merged":
        print(f"#{pr.number}: merged, nothing to do")
        return 0
    events = fetch_events(args.repo, pr.number)
    override = reopened_by_maintainer(args.repo, pr, events)
    verdict = decide(pr, fetch_issues(args.repo, referenced(pr.body, pr.closing, args.repo)), override, args.manual)
    print(f"#{pr.number} by {pr.author}: {verdict.outcome} ({verdict.reason})")
    if args.dry_run:
        return 0

    if verdict.outcome == "close" and pr.state == "open":
        url = f"https://github.com/{args.repo}"
        gh("pr", "comment", str(pr.number), "--repo", args.repo, "--body", COMMENT.format(url=url, form=FORM))
        gh("pr", "close", str(pr.number), "--repo", args.repo)
        print(f"#{pr.number}: commented and closed")
    elif verdict.outcome == "pass" and pr.state == "closed" and latest_actor(events, "closed") == GATE:
        gh("pr", "reopen", str(pr.number), "--repo", args.repo)
        print(f"#{pr.number}: reopened")
    return 0


if __name__ == "__main__":
    sys.exit(main())
