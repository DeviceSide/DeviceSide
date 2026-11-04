# Flag clearing: follow-up to the three audits

## Context

The flag audits (#201 Hue, #202 ZHA, #203 Z2M; their plans `docs/plans/2026-11-04-flag-audit-{hue,zha,z2m}.md`) cleared
18 adapters and left 10 flagged. Jason decided the open questions on 4 Nov:

1. **Composed group proof.** A native group path counts as proven when any action of the same adapter class has
   passed through it, and the command is proven on one light. Under this rule, #202 keeps ZHA's four color moves
   cleared: brightness groupcasts pass, and the color commands pass on one light. Z2M `lower_hue` still gets its
   unattended `group_color` rerun.
2. **`rgb_color` read-back.** `sets_color_while_off` reads the color after the turn-on, so an unattended run proves
   the value. Its observed case stays, for the flash of the old color.
3. **Hue saturation.** `predicted_state` comes out of the `raise_saturation` and `lower_saturation` scopes. It is
   inert there: `SATURATION.shows` is `None` in `hue/attributes.py`, so the report filter shows HA the bridge's xy
   either way, and `AdapterScope.options` is read only by the release checks. New case `saturation_stop_raise` covers
   the move after a halt, which nothing tests.
4. **ZHA's watched cases.** `hue_cycle_stop` and `saturation_down_stop` stay watched. `soft_off_keeps_level`
   (`lower_brightness.yaml`) gets `observe: only` (deducible: its check, HA's level after the plain on, is
   automated).

Plus two new cases, both unattended:

- `saturation_stop_raise` on Hue, ZHA and Z2M: saturation is a target with a transition on all three, so the second
  move depends on the prediction a stop leaves.
- `hue_stop_raise` on ZHA and Z2M: hue is a rate-based cycle (no prediction), so this catches bookkeeping after a
  stop (the `hue_moves` sets, a refused restart).

The clears in #202 and #203 of the hue and saturation adapters hold only if these pass: a failure puts the adapter
back to `experimental`.

## Steps (one PR into `release/v0.0.2`)

1. **CLAUDE.md**: one sentence in "Proof follows the call" stating rule 1. Point at this PR, nothing more.
2. **ZHA audit plan**: in `docs/plans/2026-11-04-flag-audit-zha.md`, rest the four color moves' clearance on rule 1
   (cite the brightness `[group]` cases) instead of "groups are not a scope item"; drop proposal 2's blocking
   language accordingly.
3. **`tests/rig/steps/set_attributes.yaml`** `sets_color_while_off`: after the turn-on, an `expect_state` (or
   `expect_matches_read`, whichever the engine supports for color) on the color written, with a tolerance in line
   with the other color cases. Keep the `observe:` block.
4. **Hue saturation scopes**: `hue/fade.py:74` builds one scope for brightness and saturation; give saturation no
   `options`. Unit tests for the scope split; update any doc listing the option's coverage.
5. **`saturation_stop_raise`** in `raise_saturation.yaml`, modeled on `raise_brightness.yaml`'s `raise_stop_raise`:
   from a mid saturation, raise, stop after ~3 s, sample saturation steady, raise again, sample rising with no jump
   from the halt. Roles `light_color`, `group_color`. If the engine can't sample saturation, extend it (with tests).
6. **`hue_stop_raise`** in `raise_hue.yaml`, `only: [zigbee2mqtt, zha]`: `mark_hue`, cycle, stop, hold
   (`expect_matches_read` on xy), cycle again, `expect_hue_travel` onward from the halt. Roles as `hue_cycle_stop`.
7. **`lower_brightness.yaml`** `soft_off_keeps_level`: `observe: only` per the ledger semantics in
   `docs/plans/2026-10-30-rig-coverage-sweep.md` (Observed-test ledger); add its ledger row there.
8. **Unattended lab run** from this worktree, in the background (it waits for the locks; the lab profile is
   `pre_authorized`). **Lab only: never the house profile.**

   ```
   scripts/rig.py --profile lab --unattended --action raise_saturation --action lower_saturation \
     --action raise_hue --action lower_hue --action set_attributes
   ```

   Commit the records it writes. On a failure: rerun once if it looks like the lab's known flaky read (#196); if it
   repeats, put the adapter back to `experimental`, and stop for Jason before changing any adapter code.
9. **Clear** what the run proves: Hue `raise_saturation` and `lower_saturation` (scope now has no options), and Z2M
   `lower_hue` once its `[group_color]` case passes. Cite record and case per scope item in the PR body. Every
   `set_attributes` and `stop` stays flagged: their watched cases are still owed.
10. **TODO.md**: "Done since" rows for #201, #202, #203 and this PR; replace the three A60-run items with what's
    left: one watched lab session (Hue: `saturation_down_stop`, `halts_brightness_and_saturation`,
    `sets_color_while_off`; ZHA: `hue_cycle_stop`, `saturation_down_stop`, `sets_color_while_off`; Z2M: three
    `stop` cases, `sets_color_while_off`), then the PR clearing the last flags.

## Finish

`.venv/bin/pytest`, `pre-commit run --all-files`, `/audit-code` on the diff and fix its findings. Open the PR and
stop: it clears flags, so Jason merges it.
