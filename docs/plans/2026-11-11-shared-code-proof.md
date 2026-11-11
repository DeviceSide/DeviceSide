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

## Decisions (interview, 2026-11-11)

- **Format.** A record's `## Shared coverage` section: a `| Module | Executed lines |` table, one row per `core/`
  module the run reached, the module named relative to the component (`` `core/dispatch.py` ``), the lines as
  coverage.py's `executed_lines` at the record's cited commit, as ranges (`12-40, 55`). The rig writes it (tracked in
  the rig repo); this repo defines and reads it, in `check_release.py`'s docstring. A malformed row is an error under
  --records.
- **Changed lines.** `git diff -U0 <stale commit> HEAD` of the module, HEAD side. Each changed line maps to the
  innermost statement (or `except`/`case` clause) around it, which is covered when any line of its header (first
  decorator through the line before its body; a simple statement's whole span) is executed. A line with no code
  (comment, blank) or inside a docstring needs nothing. A hunk that removes code not replaced line for line at the
  same indentation (a deletion, or code moved across a block) also needs the nearest code line on each side covered.
- **Import-time lines (Jason, 2026-11-11, after audit 1): never cleared.** A line added, changed or removed in a
  module's or class's own statements stales every adapter that reaches it. A changed decorator or `def` signature needs the function's first
  non-docstring statement executed (the call). A lambda's or generator expression's body is its own clause, needing
  its body's lines bar the one it starts on; one that needs no line can't be cleared.
- **Coverer.** Any record with Result `pass` of an adapter not flagged experimental and with a Verified call, whose
  cited commit holds the module byte-identical to HEAD (so its line numbers apply). The rest of its adapter's code may
  have moved on.
- **Where it applies.** `changed_since`, so both record staleness and #374's retests clear a covered core/ change.
- Rule text: CLAUDE.md § Release flag ("Proof follows the call") and § Releasing; design.md Release gates.

## Steps

1. Finish the interview on the open decisions (`AskUserQuestion`), write them here.
2. `pr-draft` this plan in this worktree.
3. Implement in `check_release.py` with tests; rule text; TODO item.
4. Audit (binding-rule surface: Opus auditor), `gh pr ready`, `merge-green`.

## Handoff (2026-11-11)

**Done:** steps 1-3. Decisions above; #374 merged in (`origin/wt/evidence-levels`); draft PR #377; check_release.py
shared coverage (`shared_coverage`, `needed_headers`, `clauses`, `shared_clears`, `shared` threaded through
`changed_since`), 26 new tests, rule text (CLAUDE.md "Shared code is proven once", design.md Release gates, the
script's docstring), TODO item (unticked until the rig writes the table). Branch `wt/shared-code-proof`, worktree
`~/projects/ha/deviceside-wt/shared-code-proof`, pushed at ce402d5.

**Audit report 1: NOT-CLEAN** (h=2 m=1 l=4); fixed in 2e42822.
**Audit report 2: NOT-CLEAN** (h=1 m=1 l=3): removed module/class statements were cleared; an equal-count hunk moving
code across a block dropped the removal's neighbors; a one-line def ran at import. Fixed in the commit after 2e42822
(M1 by the narrower option: neighbors unless each removed code line is replaced in order at the same indentation).
**Audit report 3: NOT-CLEAN** (m=1 l=2): module/class-level multi-line lambdas and genexps counted as deferred;
an insert-only hunk needed neighbors; docstring wording. Fixed in the commit after ef94c68.
L2 (multi-line list/set/dict comprehensions folded into their statement) left open: Jason's call. Gate is at HANDOFF
(two NOT-CLEAN in a row): Jason runs `audit-gate accept` or asks for audit 3; then `gh pr ready`, `merge-green 377
--squash --delete-branch` (repo opts in).
