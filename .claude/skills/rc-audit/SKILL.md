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
  commit inside a later pass. Medium and Low never block.
- **Fixes get their own pass.** A fix changes code after the audit, so `--fix-pass` audits just the new commits
  rather than re-running the whole range, reading past its hunks for what the fix broke (§ Fix pass, step 2).
  Passes chain from `base`, and nothing outside `docs/audits/` may change after the last one.
- **Someone else's code:** a finding in a package or family the runner doesn't maintain is its owner's to hear of
  first (CLAUDE.md, Maintainers); § Someone else's code says what the runner chooses.
- **Tagging:** `cut-release-candidate` (a `workflow_dispatch`) checks green CI on the head and the record, then
  tags. A failed check means no tag.

## First pass (no `--fix-pass`)

1. `.venv/bin/python scripts/check_audit.py --base <rc>` prints the base: the previous RC tag of this version, or for
   rc1 the latest release under `HEAD`. Refuse if `docs/audits/<rc>.md` already exists; that's a `--fix-pass`.
2. Run the project's `audit-code` skill on `<base>..HEAD`, with owners read at the branch the RC is cut from
   (`origin/main`, or `origin/release/vX.Y.Z`) and the runner resolved as it says (§1, Owners).
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
       owner: ""        # someone else's package: `scripts/owners.py`'s owner (control4, zigbee2mqtt/tuya, zigbee/tuya)
   ---
   ```
4. Settle the findings in someone else's code (below).

## Someone else's code

For each owner the report's **In code you don't maintain** lists, ask the runner once, naming the owner's handles and
its Criticals and Highs: "`control4` (@handles): H2, H4. Owner fixes, I fix, or waive?" They may choose differently
for any one finding. Record each finding's `owner`, and its choice in the pass's prose:

- **The owner fixes it:** file the owner's issue (below). The finding stays `open`, so the RC waits.
- **The runner fixes it:** no issue; the owner notice on the fix PR (`owner-notice.yml`) is the owner's warning. The
  fix PR names the owner, and the runner sets ⚠️ Untested fix when nobody can test the owner's device before the
  release (`docs/evidence.md`, Caveats).
- **Waived**, with the runner's reason: still the repo maintainers' decision (§ Then).

Each owner gets one issue, drafted as `audit-code` drafts it, holding the findings the runner doesn't fix: Criticals
and Highs the owner fixes, and its Mediums and Lows to track. An owner whose findings the runner fixes, every one, gets
none. File it with the runner's go-ahead.

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
   - **Someone else's code:** a commit in the range that changes code the runner doesn't maintain is a High, as it
     breaches CLAUDE.md's rule for changing someone else's code, unless the commit is that code's owner's, or fixes a
     finding the record says the runner fixes.
3. Mark each finding the range fixes as `fixed` with its `fixed_in` commit, and add any new Critical or High as
   `open`, settling the new ones in someone else's code as above.

## Then

Run `.venv/bin/python scripts/check_audit.py <rc> HEAD` and list every problem it reports, then list each Critical
and High still `open`. Tell a repo maintainer to merge the PR carrying the record and its fixes with a merge commit
(`--merge`), never squash or rebase: the record cites that branch's commits as `to` and `fixed_in`, and a rewrite
takes them out from under the RC head, so the check fails and the tag is refused. Fixing or waiving is the repo
maintainers' decision: never mark one `waived` yourself. Fix only Criticals and Highs: Mediums and Lows stay in the
record's prose, unless a fix is a line a Critical or High fix already touches, and a fix pass's Mediums and Lows never
start another round. Once the check passes, the record is committed, and CI is green,
a repo maintainer dispatches `cut-release-candidate` with `rc: <rc>` from the branch.
