# Owner findings: a DeviceSide helper that routes audit findings to their owners

Date: 2026-11-16. Status: built and wired in. Follows `docs/plans/2026-11-16-owner-notices.md` (controls 1 and 2), replacing
its edits to `audit-code` and `rc-audit`: `audit-code` is shared with other repos, and skill wording changes go
through an issue. Built on `claude/owner-notices-plan`, after `scripts/owners.py`.

## Why

An audit can propose fixes in a package or family the person running it doesn't maintain, and nothing tells them it
is someone else's before a fix is discussed. `scripts/owners.py` answers "whose is this path", but no step of an audit
asks it. This plan adds that step as a small skill that only DeviceSide has, so the shared `audit-code` stays as it is.

Evidence 6: prevents a fix to a device class the fixer can't test shipping without its maintainer seeing it (the repo
maintainer's example: an RC audit proposing changes to the `control4` package). Replaces the owner-blind fix batches
an audit ends with, and, in an RC, `rc-audit`'s choice between fix and waive for a finding in someone else's code.

## Decisions

1. **A skill of its own, `owner-findings`** (`.claude/skills/owner-findings/SKILL.md`), run after an audit report
   exists. It reads the report and never edits code. `audit-code` and `rc-audit` are not changed.
2. **The rule says when to run it, in one home.** `CLAUDE.md`, Maintainers, "Changing someone else's code": run
   `owner-findings` on every audit report before acting on a finding, including inside `rc-audit`. Pull requests,
   Audits points to it. `CLAUDE.md` is loaded in every session, so an RC audit picks it up without `rc-audit`'s text
   changing.
3. **No workflow change.** No workflow runs an audit: `cut-release-candidate` checks only the committed record
   (`scripts/check_audit.py`), which reads no owner (owner-notices plan, question 4). The PR notice already covers
   every fix PR.
4. **The runner:** `--as <login>`, else `gh api user --jq .login`, else ask once; with no answer, the runner owns
   nothing, and the skill says so (owner-notices plan, question 5).
5. **Owners are read at the base** the fixes would merge into: the audited target's base branch, else `origin/main`;
   for an RC, the branch it is cut from (`origin/main` or `origin/release/vX.Y.Z`). Fetch it first.
6. **One question per owner, in an RC.** Choices: the owner fixes (the finding stays `open`, the RC waits); the runner
   fixes (no issue, as the PR notice warns the owner; ⚠️ Untested fix when nobody can test the device before the
   release); waived with the runner's reason. The runner may choose differently for any one finding. There is no
   `--fix-pass` rule against commits to someone else's code: it would block RCs that pass today.
7. **The record gains `owner:`** on each Critical or High in someone else's code (`Package.slug`: `control4`,
   `zigbee2mqtt/tuya`, `zigbee/tuya`). The choice is its status, as now. `check_audit.py` ignores the key, and a test
   pins that.

## Design: the skill

Frontmatter `name: owner-findings`; the description says to use it after any `audit-code` report in this repo,
including the one `rc-audit` writes, or when asked whose code an audit's findings are in. Arguments: optionally the
report (a path such as `docs/audits/<rc>.md`, else the audit report just produced in the session), `--as <login>`,
`--base <rev>`.

Steps:

1. **Resolve** the runner (Decision 4) and the base (Decision 5). Say both in one line.
2. **Look up owners**: collect each reported finding's files from its `file:line` references and run
   `scripts/owners.py --rev <base> --as <login> --json <paths>` once. A row is an owner group: `owner` (its slug, or
   `""` for shared code), `package`, `direct` and `enclosing` handles, and `paths`. A finding is in someone else's
   code when any of its files is in a row.
3. **Amend the report**:
   - an Owner column in every findings table: the package and `@` its direct handles, blank for the runner's own;
   - a section **In code you don't maintain**, right after the verdict: one entry per owner group, the package, its
     handles (direct, then the integration's), and the finding ids. Left out when there are none.
   - The fix batches drop those findings, and each owner gets a drafted issue instead.
4. **Draft one issue per owner group**: a title naming the package and the audit; the findings, each with its
   `file:line`, severity and the fix the audit proposed; the labels and assignees from
   `scripts/owners.py --rev <base> --as <login> --issue <that group's paths>`. Show the drafts. File them only when
   the runner says to, creating a missing `integration:<key>` label the way `route-issue.yml` does
   (`gh label create <label> --color c5def5 --description "Routed to the integration's maintainers" --force`).
5. **In an RC** (the report is `docs/audits/<rc>.md`): for each owner group with a Critical or High, ask once, naming
   the package, the handles and the finding ids (Decision 6). Then:
   - write `owner: <slug>` on each such finding in the frontmatter, and each finding's choice in the current pass's
     prose;
   - the owner fixes it: its issue is filed; the status stays `open`;
   - the runner fixes it: no issue for it; the fix PR names the owner; the runner decides on ⚠️ Untested fix;
   - waived: `status: waived` with the runner's reason, as the runner gives it. The skill never picks the choice.
   - That group's Mediums and Lows go in its issue unless the runner fixes them; a group whose findings the runner
     fixes, every one, gets no issue.
6. **Report** what it changed: the owner groups, the choices, the issues filed or still drafted.

It points to `CLAUDE.md`, Maintainers, for the rule, and restates none of it.

## Stages

1. **Build** (implementer subagent): the skill file, and in `tests/scripts/test_check_audit.py` a test that a record
   whose finding carries `owner: control4` passes.
2. **Check** (a second subagent, read-only): the build against this plan's intent checks.
3. **Wire in**: `CLAUDE.md`'s paragraph and the Audits bullet (Decision 2); the owner-notices plan points here for
   its skills section.

Each stage ends with `.venv/bin/pytest` and `pre-commit run --all-files` green. No device call changes.

## Intent checks

- `audit-code` and `rc-audit` are unchanged.
- The skill never edits code, never files an issue or waives a finding without the runner's word, and asks one
  question per owner group, not per finding.
- Every `scripts/owners.py` flag and JSON field the skill names exists and means what the skill says.
- The rule lives once, in `CLAUDE.md`; the skill and the Audits bullet point to it.
- A record with `owner:` passes `check_audit.py`; nothing new can fail an RC tag that passes today.
- No household names, device names or hostnames; American English; the glossary's terms.
