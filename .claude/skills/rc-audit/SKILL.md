---
name: rc-audit
description: Audit the code a release candidate ships and write or extend its record, docs/audits/vX.Y.ZrcN.md, which the cut-release-candidate workflow checks before tagging. Use when the user runs /rc-audit vX.Y.ZrcN [--fix-pass] or asks to audit an RC.
---

Arguments: `vX.Y.ZrcN`, optionally `--fix-pass`. `scripts/check_audit.py` enforces the rules below; this skill
only runs the audit and writes the record.

## Rules

- **Goal:** no `vX.Y.ZrcN` tag unless `audit-code` has covered every commit it ships and no Critical or High finding
  is left open.
- **Where it runs:** locally, in a repo maintainer's Claude session. CI only checks the committed record, so it needs
  no API key and no vendored copy of `audit-code`.
- **Range:** from the previous RC tag of the same version; for rc1, from the latest release tag that is an ancestor
  of the head (the root commit if none). A `release/vX.Y.Z` branch cut from an RC tag has that RC as an
  ancestor.
- **What blocks:** a Critical or High with status `open`. `waived` needs a `reason`; `fixed` needs a `fixed_in`
  commit inside a later pass. Medium and Low on low-frequency paths never block.
- **Fixes get their own pass.** A fix changes code after the audit, so `--fix-pass` audits just the new commits
  rather than re-running the whole range, reading past its hunks for what the fix broke (§ Fix pass, step 2).
  Passes chain from `base`, and nothing outside `docs/audits/` may change after the last one.
- **Tagging:** `cut-release-candidate` (a `workflow_dispatch`) checks green CI on the head and the record, then
  tags. A failed check means no tag.

## First pass (no `--fix-pass`)

1. `.venv/bin/python scripts/check_audit.py --base <rc>` prints the base: the previous RC tag of this version, or for
   rc1 the latest release under `HEAD`. Refuse if `docs/audits/<rc>.md` already exists; that's a `--fix-pass`.
2. Run the project's `audit-code` skill on `<base>..HEAD`.
3. Write `docs/audits/<rc>.md`: the frontmatter below, then the audit report under `## Pass 1`.

   ```yaml
   ---
   rc: <rc>
   base: <base, short sha>
   passes:
     - from: <base, short sha>
       to: <HEAD, short sha>
   findings:            # Critical and High only; Medium and Low stay in the prose
     - id: H1
       severity: high   # critical | high
       status: open     # open | fixed | waived
       fixed_in: ""     # the fixing commit, once fixed
       reason: ""       # why, when waived
   ---
   ```

## Fix pass (`--fix-pass`)

1. Read the record. The new pass runs from the last pass's `to` to `HEAD`; stop if `HEAD` is that commit.
2. Run `audit-code` on that range, scoped as follows. Append `## Pass <n>` with its report and the pass to `passes`.
   - **Verify** every `open` Critical and High in the record against the range: `fixed`, `not fixed` or
     `regressed`, quoting the code. The last two stay `open` in the record.
   - **Read beyond the hunks**, since a fix's defects often lie outside its diff:
     - the callers, tests and docs of every symbol the range changes (`rg` each);
     - an `rg` across docs, comments and every agent-instructions file for each term the range renames or whose
       behavior it changes. Gitignored ones (`CLAUDE.local.md`) count: name them explicitly, as plain `rg` skips
       them;
     - the repo's binding rules (`CLAUDE.md`, `CLAUDE.local.md`), as audit criteria.
   - **Test** with only the tests that cover the changed code; CI runs the full suite before tagging.
   - **Report** a verification table and a findings table, not the six-section report.
3. Mark each finding the range fixes as `fixed` with its `fixed_in` commit, and add any new Critical or High as
   `open`.

## Then

Run `.venv/bin/python scripts/check_audit.py <rc> HEAD` and list every problem it reports, then list each Critical
and High still `open`. Tell a repo maintainer to merge the PR carrying the record and its fixes with a merge commit
(`--merge`), never squash or rebase: the record cites that branch's commits as `to` and `fixed_in`, and a rewrite
takes them out from under the RC head, so the check fails and the tag is refused. Fixing or waiving is the repo
maintainers' decision: never mark one `waived` yourself. Once the check passes, the record is committed, and CI is green,
a repo maintainer dispatches `cut-release-candidate` with `rc: <rc>` from the branch.
