# Shared code proof: one integration's rig run proves a core/ change for all

## Coordination

Intent: A change to `core/` is proven for every adapter that reaches it by a passing Verified rig record, on any one
integration, whose run covered every changed line of that shared code, so a core/ change needs no retest from each
integration's maintainers.
Touches: CLAUDE.md, docs/design.md, scripts/check_release.py, tests/scripts/test_check_release.py, TODO.md
Depends-on: #374

## The rule (settled with Jason, 2026-11-11)

1. **Shared code is `custom_components/deviceside/core/` only.** A module inside an integration package still stales
   only that integration's records and retests.
2. **Rig-measured coverage.** The rig measures line coverage in the live HA (coverage.py) during a run, and the record
   says which `core/` modules it covered and which lines.
3. **One run proves it for all.** When a `core/` module changed after an adapter's record (or retest) cites its
   commit, `check_release.py --records` doesn't count that change against the adapter if a passing Verified record
   of any integration covered every changed line of the module, at code where the module matches HEAD. Changes inside
   the adapter's own package still stale it as before.
4. This covers the retests of #374 too: the same core/ coverage clears a core/ change for adapters without a Verified
   call.

## Open decisions (for the planning session)

- Record format: a `Shared coverage` row (module, covered line ranges, commit), its home in the record, and how
  `check_release.py` parses it. The rig is a private repo: this repo defines the format and reads it; the rig work is
  tracked there, not here.
- "Every changed line": the lines of the module that differ between the stale record's cited commit and HEAD
  (`git diff -U0`), compared against the covering record's covered lines. Deleted-only hunks, docstring-only and
  comment-only changes: count or ignore (`changed_code` already ignores some, see its docstring).
- Whether a record of an Experimental-flagged adapter can cover shared code (probably no: Verified only).
- Rule text: CLAUDE.md § Release flag ("Proof follows the call", "A firmware fact…") and § Releasing; design.md
  Release gates.

## Steps

1. Finish the interview on the open decisions (`AskUserQuestion`), write them here.
2. `pr-draft` this plan in this worktree.
3. Implement in `check_release.py` with tests; rule text; TODO item.
4. Audit (binding-rule surface: Opus auditor), `gh pr ready`, `merge-green`.
