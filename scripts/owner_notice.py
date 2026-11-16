#!/usr/bin/env python3
"""Work out the owner notice on a PR: who maintains the code it changes, when its author doesn't (CLAUDE.md,
Maintainers).

Integration and family maintainers hold Triage, so GitHub never requests their review from CODEOWNERS. This stands
in: `owner-notice.yml` posts one comment naming each owner group `scripts/owners.py` calls foreign to the PR's author,
with its maintainers mentioned, and keeps it current on each push. Nothing here blocks a merge. Owners are read on the
base branch, so a PR that adds its author to a `maintainers` tuple still gets its notice. Generated output follows its
inputs and shared code is the repo maintainers', whom CODEOWNERS already asks, so neither is listed.

The comment opens with a marker that records who it has mentioned. A mention added by editing a comment is assumed not
to notify anyone, so a handle the notice hasn't mentioned yet gets a short comment of its own that mentions only the
new handles; the notice itself is edited in place. Only `github-actions[bot]`'s comments count, so a marker anyone else
posts changes nothing. Like the gate, this runs from the base branch on the standard library alone and reads the PR's
files with `git`, as data.

Usage: scripts/owner_notice.py <base> <head> --author <login> --posted <file> --out <dir>

`<file>` holds the PR's comments, one JSON array `[id, login, body]` per line. Writes `notice=none|create|update`,
`comment=<id>` and `mention=true|false` to `$GITHUB_OUTPUT` when set, and the bodies to `<dir>/notice.md` and
`<dir>/mention.md`.
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.owners import Group, commit, foreign, git, line, package_paths  # noqa: E402

BOT = "github-actions[bot]"
MARKER = "<!-- owner-notice mentioned={} -->"
MARKED = re.compile(r"\A<!-- owner-notice mentioned=([^ ]*) -->")
MENTION = "<!-- owner-notice:mention -->"
RULE = "CLAUDE.md, Maintainers"


@dataclass(frozen=True)
class Plan:
    """What the workflow posts: the notice to create, update or leave, and a comment mentioning new handles."""

    notice: str  # none | create | update
    comment: int | None
    body: str
    mention: str | None


def changed(base: str, head: str) -> list[str]:
    """The paths the PR changes, from its merge base, renames as a delete and an add (as the gate reads them)."""
    merge_base = git("merge-base", base, head).strip()
    return [path for path in git("diff", "-z", "--name-only", "--no-renames", merge_base, head).split("\0") if path]


def earlier(text: str) -> list[tuple[int, str]]:
    """The bot's comments, as (id, body), from the lines the workflow fetched."""
    found = []
    # Split on newlines alone: JSON leaves U+0085, U+2028 and U+2029 in a string, and `splitlines` would cut there.
    for raw in text.split("\n"):
        if raw.strip():
            comment_id, login, body = json.loads(raw)
            if login == BOT:
                found.append((int(comment_id), body))
    return found


def handles(groups: dict[Group, list[str]], author: str) -> list[str]:
    return list(dict.fromkeys(handle for group in groups for handle in group.handles if handle != author))


def render(groups: dict[Group, list[str]], author: str, mentioned: list[str]) -> str:
    head = MARKER.format(",".join(mentioned))
    if not groups:
        return f"{head}\nThis pull request now changes only code its author, `{author}`, maintains."
    rows = "\n".join(f"- {line(group, paths, 'file', quiet=author)}" for group, paths in groups.items())
    return (
        f"{head}\nThis pull request changes code that its author, `{author}`, doesn't maintain. Its maintainers may "
        f"want to review it; nothing here blocks the merge ({RULE}).\n\n{rows}"
    )


def plan(groups: dict[Group, list[str]], author: str, comments: list[tuple[int, str]]) -> Plan:
    groups = {group: paths for group, paths in groups.items() if group.package is not None}
    now = handles(groups, author)
    notices = sorted((comment_id, body) for comment_id, body in comments if MARKED.match(body))
    if not notices:
        if not groups:
            return Plan("none", None, "", None)
        return Plan("create", None, render(groups, author, now), None)
    comment_id, body = notices[0]
    mentioned = [handle for handle in MARKED.match(body)[1].split(",") if handle]
    new = [handle for handle in now if handle not in mentioned]
    text = render(groups, author, [*mentioned, *new])
    mention = None
    if new:
        mention = (
            f"{MENTION}\n{' '.join(f'@{handle}' for handle in new)}: this pull request now also changes code you "
            "maintain; the owner notice above lists it."
        )
    return Plan("none" if text == body else "update", comment_id, text, mention)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base")
    parser.add_argument("head")
    parser.add_argument("--author", required=True)
    parser.add_argument("--posted", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    base, head = commit(args.base), commit(args.head)
    groups = foreign(args.author, changed(base, head), base, package_paths())
    result = plan(groups, args.author, earlier(args.posted.read_text()))
    (args.out / "notice.md").write_text(result.body)
    (args.out / "mention.md").write_text(result.mention or "")
    outputs = (
        f"notice={result.notice}\ncomment={result.comment or ''}\nmention={str(result.mention is not None).lower()}\n"
    )
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a") as file:
            file.write(outputs)
    print(outputs + result.body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
