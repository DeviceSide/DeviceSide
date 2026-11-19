# Labs rename leftovers

## Coordination

Intent: finish the Labs rename (#541): fix the audit's leftover names and one ungrammatical rule phrase.
Touches: docs/evidence.md, tests/scripts/test_gen_compat.py

## Handoff

**Done:** #541 (Experimental → Labs in code, stored option, rules) merged by `merge-green 541 --squash
--delete-branch` (confirm with `gh pr view 541 --json state`; if it isn't MERGED, read the merge-green output and
tell Jason). Its plan: `docs/plans/2026-11-19-labs-rename.md`. Its audit's Mediums and Lows are in #541's body.
Jason also dropped the private "plans go in notes/plans/" rule; plans now live in `docs/plans/` (committed).

**Next (one small PR, no plan steps):**

1. Worktree `../deviceside-wt/labs-leftovers`, branch `wt/labs-leftovers` off `origin/main`; `uv sync`; move this file
   into the worktree's `docs/plans/` and open the draft PR with `pr-draft docs/plans/2026-11-19-labs-leftovers.md`.
2. `docs/evidence.md`: "counts as in Labs" (about lines 150-151 and 175) → "counts as a Labs item", as the rest of
   the file says. Binding rule text: the meaning must stay the same; change only the words.
3. `tests/scripts/test_gen_compat.py` (about lines 1412-1479): `trial_card` → `labs_card`, `timer_trial` →
   `timer_labs`, `test_a_mixed_line_is_no_trial_line_and_never_folds_with_one` →
   `test_a_mixed_line_is_no_labs_line_and_never_folds_with_one`. Then `rg -n -i 'trial' --glob '!docs/plans/**'
   --glob '!**/research/**' --glob '!docs/audits/**' --glob '!**/test-records/**'` for any other underscore-joined
   leftovers (the plan's `\btrials?\b` search missed these), and fix them the same way.
4. Checks: `.venv/bin/pytest -n auto --transcripts=check`, `uvx pre-commit run --all-files`,
   `.venv/bin/python scripts/gen_features.py --check`, `.venv/bin/python scripts/gen_compat.py --check`.
5. Audit and merge per CLAUDE.md (evidence.md is binding-rule surface: Opus auditor), then `owner-findings`, then
   `gh pr ready` and `merge-green <n> --squash --delete-branch`.

**Out of scope (tracked, not fixed):** `in_labs` naming in `scripts/gen_features.py`, the vague migration test name.

**Open decisions:** none.
