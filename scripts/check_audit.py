#!/usr/bin/env python3
"""Check an RC's audit record: every commit since the previous RC audited, no Critical or High left open.

The record is `docs/audits/<rc>.md`: YAML frontmatter (rc, base, passes, findings), then the audit-code report.
- `base` is the previous RC tag of the same version, or for rc1 the latest release tag that is an ancestor of the
  head (the root commit if none). A release/vX.Y.Z branch cut from an RC tag has that RC as an ancestor.
- Passes chain from it (`passes[0].from == base`, each `from` the previous `to`); each `to` is an ancestor of the head.
- Nothing outside `docs/audits/` changed after the last pass.
- A Critical or High finding is `fixed` (`fixed_in` inside a pass after the first) or `waived` (with a `reason`).
- An RC cut from main has bumped the standard lights table's ZHC pin since the previous RC tag, or its record holds a
  line `ZHC bump skipped: <reason>` (the release skill; scripts/zhc_table.py's docstring).
  A release/vX.Y.Z branch is exempt, as no bump lands between an RC and its release. Git reads only.
See .claude/skills/rc-audit/SKILL.md.

Usage: scripts/check_audit.py <rc> <head-sha> [<branch>]   (the branch it is cut from; the checked-out one when left
       out, main on a detached head)
       scripts/check_audit.py --base <rc>   (print the base /rc-audit starts rc1 or a new RC from)
"""

import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.check_tag import RC, git, name, releases  # noqa: E402
from scripts.zhc_table import TABLE, load  # noqa: E402

AUDITS = Path("docs") / "audits"
# The standard lights table, where scripts/zhc_table.py keeps it; its pin is the module's ZHC_RELEASE.
ZHC_TABLE = TABLE.as_posix()
ZHC_SKIPPED = re.compile(r"^ZHC bump skipped: \S", re.MULTILINE)
SEVERITIES = frozenset({"critical", "high"})
# A squash or rebase merge replaces the commits a record cites, so they are no longer under the head.
REWRITTEN = "; was the audit PR squashed or rebased? Merge it with a merge commit"


def sha(repo: Path, rev: str) -> str | None:
    return git(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}", check=False) or None


def is_ancestor(repo: Path, ancestor: str, head: str) -> bool:
    command = ["git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, head]
    return subprocess.run(command, capture_output=True).returncode == 0


def expected_base(repo: Path, rc: str, head: str) -> str:
    """The previous RC tag of the same version, else the latest release tag under head, else the root commit."""
    match = RC.match(rc)
    version, number = tuple(map(int, match.groups()[:3])), int(match[4])
    earlier = [
        (int(found[4]), tag)
        for tag in git(repo, "tag", "--list", f"{name(version)}rc*", "--merged", head).split()
        if (found := RC.match(tag)) and int(found[4]) < number
    ]
    if earlier:
        return sha(repo, max(earlier)[1])
    if ancestors := releases(repo, merged_into=head):
        return sha(repo, ancestors[-1][1])
    return git(repo, "rev-list", "--max-parents=0", head).split()[-1]


def frontmatter(path: Path) -> dict:
    text = path.read_text()
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise ValueError(f"{path} has no YAML frontmatter between --- lines")
    # BaseLoader keeps every scalar a string: a short sha like 0123456 would otherwise load as an octal int.
    data = yaml.load(text[4:].split("\n---\n", 1)[0], Loader=yaml.BaseLoader)
    if not isinstance(data, dict):
        raise ValueError(f"{path}'s frontmatter is not a mapping")
    return data


def previous_rc(repo: Path, rc: str, head: str) -> str | None:
    """The latest RC tag under head other than `rc`, by version then number, or None."""
    found = [
        (tuple(map(int, match.groups())), tag)
        for tag in git(repo, "tag", "--list", "v*rc*", "--merged", head).split()
        if (match := RC.match(tag)) and tag != rc
    ]
    return max(found)[1] if found else None


def zhc_pin(repo: Path, rev: str) -> str | None:
    """The standard lights table's ZHC pin at rev, or None where the table isn't there; raises ValueError where it is
    but its pin doesn't parse, as the guard would pass unchecked."""
    if not git(repo, "ls-tree", "--name-only", rev, "--", ZHC_TABLE).strip():
        return None
    try:
        pin = load(git(repo, "show", f"{rev}:{ZHC_TABLE}")).ZHC_RELEASE
    except Exception as err:  # noqa: BLE001 - a table that won't load has no pin to compare
        raise ValueError(f"{ZHC_TABLE} at {rev} has no ZHC_RELEASE: {err}") from err
    if not isinstance(pin, str):
        raise ValueError(f"{ZHC_TABLE} at {rev} has no ZHC_RELEASE string")
    return pin


def zhc_bump_errors(repo: Path, rc: str, head: str, branch: str, text: str) -> list[str]:
    """An RC from main whose table pin is the previous RC tag's, with no skip line in its record `text`."""
    if branch.startswith("release/") or ZHC_SKIPPED.search(text) or (previous := previous_rc(repo, rc, head)) is None:
        return []
    if (pin := zhc_pin(repo, head)) is None or pin != zhc_pin(repo, previous):
        return []
    return [
        f"the ZHC table is pinned to {pin}, as at {previous}: bump it (scripts/zhc_table.py --pin, the release skill),"
        f" or add a line `ZHC bump skipped: <reason>` to {AUDITS.as_posix()}/{rc}.md"
    ]


def errors(repo: Path, rc: str, head: str, branch: str = "main") -> list[str]:
    if not RC.match(rc):
        return [f"{rc} is not vX.Y.ZrcN"]
    if (head := sha(repo, head)) is None:
        return ["the head is not a commit"]
    path = repo / AUDITS / f"{rc}.md"
    if not path.exists():
        return [f"{AUDITS / path.name} is missing; run /rc-audit {rc}"]
    try:
        record = frontmatter(path)
    except (ValueError, yaml.YAMLError) as err:
        return [str(err)]

    problems = []
    if record.get("rc") != rc:
        problems.append(f"rc is {record.get('rc')!r}, not {rc}")
    base = expected_base(repo, rc, head)
    if sha(repo, str(record.get("base"))) != base:
        problems.append(f"base is {record.get('base')!r}, not {base[:7]}")

    passes = record.get("passes") or []
    if not passes:
        return [*problems, "no passes"]
    ranges = pass_ranges(repo, passes, base, head, problems)
    if code := unaudited(repo, ranges[-1][1], head):
        problems.append(f"changed after the last pass: {', '.join(code)}; run /rc-audit {rc} --fix-pass")

    for finding in record.get("findings") or []:
        problems += finding_errors(repo, finding, ranges[1:], head)
    return problems + zhc_bump_errors(repo, rc, head, branch, path.read_text())


def unaudited(repo: Path, last: str | None, head: str) -> list[str]:
    """Files outside docs/audits/ changed between the last pass and the head; nothing to say if the chain is broken."""
    if not last or not is_ancestor(repo, last, head):
        return []
    changed = git(repo, "diff", "--name-only", last, head).splitlines()
    return [file for file in changed if not file.startswith(f"{AUDITS.as_posix()}/")]


def pass_ranges(repo: Path, passes: list[dict], base: str, head: str, problems: list[str]) -> list[tuple]:
    """Each pass as (from, to) full shas (None where unresolvable), appending a problem per broken link."""
    ranges = []
    previous = base
    for index, audit_pass in enumerate(passes, 1):
        start, end = sha(repo, str(audit_pass.get("from"))), sha(repo, str(audit_pass.get("to")))
        if start != previous:
            problems.append(f"pass {index} starts at {audit_pass.get('from')!r}, not {(previous or '?')[:7]}")
        if end is None or not is_ancestor(repo, end, head):
            problems.append(f"pass {index} ends at {audit_pass.get('to')!r}, not an ancestor of the head{REWRITTEN}")
        ranges.append((start, end))
        previous = end
    return ranges


def finding_errors(repo: Path, finding: dict, later: list[tuple[str | None, str | None]], head: str) -> list[str]:
    label = f"finding {finding.get('id', '?')}"
    severity, status = finding.get("severity"), finding.get("status")
    if severity not in SEVERITIES:
        return [f"{label}: severity {severity!r} is not critical or high"]
    if status == "open":
        return [f"{label} ({severity}) is open"]
    if status == "waived":
        return [] if str(finding.get("reason") or "").strip() else [f"{label} is waived without a reason"]
    if status != "fixed":
        return [f"{label}: status {status!r} is not open, fixed or waived"]
    fixed_in = sha(repo, str(finding.get("fixed_in")))
    inside = fixed_in is not None and any(
        start and end and fixed_in != start and is_ancestor(repo, start, fixed_in) and is_ancestor(repo, fixed_in, end)
        for start, end in later
    )
    if inside:
        return []
    rewritten = finding.get("fixed_in") and (fixed_in is None or not is_ancestor(repo, fixed_in, head))
    error = f"{label}: fixed_in {finding.get('fixed_in')!r} is not inside a pass after the first"
    return [error + (REWRITTEN if rewritten else "")]


def main(argv: list[str] | None = None, repo: Path = REPO) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 2 and argv[0] == "--base" and RC.match(argv[1]):
        print(expected_base(repo, argv[1], "HEAD"))
        return 0
    if len(argv) not in (2, 3) or argv[0] == "--base":
        print(__doc__.split("Usage: ", 1)[1].strip(), file=sys.stderr)
        return 2
    # rc-audit's local run passes no branch; on a release/vX.Y.Z fix branch the pin can't have moved.
    branch = argv[2] if len(argv) == 3 else git(repo, "branch", "--show-current").strip() or "main"
    problems = errors(repo, argv[0], argv[1], branch)
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    if not problems:
        print(f"{argv[0]}: audit record covers every commit to the head; no open Critical or High.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
