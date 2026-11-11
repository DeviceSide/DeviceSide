# Evidence levels: graduation, retests and At risk

## Coordination

Intent: Replace the second-tester and Reported rules with the agreed evidence tenets: Experimental graduates on five
independent reports, every changed adapter is retested before release, and an adapter left untested at the cut ships
live marked ⚠️ At risk.
Touches: CLAUDE.md, docs/design.md, CONTRIBUTING.md, .github/ISSUE_TEMPLATE/device_report.yml,
.github/pull_request_template.md, .github/workflows/cut-release*.yml, README.md, custom_components/deviceside/__init__.py,
custom_components/deviceside/core/scope.py, tests/test_init.py,
scripts/check_release.py, scripts/gen_compat.py, docs/integrations/*/test-records/_manual.md, tests/core/**,
tests/scripts/**, TODO.md
Depends-on: #370

## The rules (settled)

1. **New work ships Experimental.** A new integration, device class, action, domain, capability or field.
2. **Graduation.** A maintainer can request moving an Experimental item to Reported once it has five accepted working
   reports from users other than the maintainer, and no open bugs. Its siblings sharing the call can move from
   Experimental to Documented on the same evidence.
3. **Staying Reported.** After a change to a Reported item's call, one working report at the new code keeps it
   Reported; the maintainer's own counts.
4. **Verified** needs a rig record; **Documented** is unchanged (same call as a Reported or Verified sibling, differing
   only in addressing, and it falls with that sibling).
5. **Every change is retested before release.** A retest is any of: a rig record; a line in the integration's
   `test-records/_manual.md` from the maintainer, in a PR; an accepted report through the device report issue
   ("Report a test").
6. **At risk.** An adapter changed since its last retest ships live at the cut, marked ⚠️ At risk on its card and in
   setup; the release notes link the device report issue to recruit testers. One accepted report at the new code clears
   it. Unmaintained stays separate: a human call about a missing maintainer.

Manual testing stays light: one `_manual.md` line (date, commit, tester, devices, what passed). Checklists derived from
the rig's tests, or a public rig, come only if user complaints call for them.

## Steps

1. `pr-draft` this plan in a `wt/evidence-levels` worktree off `main` (after #370 merges).
2. **Rule text:** rewrite CLAUDE.md's Reported paragraph and add graduation, retest and At risk rules; update the
   design.md glossary (Reported, Device report, new At risk entry); CONTRIBUTING step 5 and the maintainer section
   (graduation request, `_manual.md`); PR template Testing evidence mentions `_manual.md`.
3. **Reports:** the five-report count is the maintainer's discretion, checked in review, not by `gen_compat.py`. Say
   so in CLAUDE.md's Reported rule and CONTRIBUTING.
4. **Retests:** `check_release.py --records` accepts a `_manual.md` line or an accepted report newer than the
   adapter's code as a retest; at the cut it lists the rest as At risk instead of failing for adapters with no rig
   coverage. Define the `_manual.md` line format there and test it.
5. **At risk mark:** an `AdapterScope.at_risk` field (an issue URL or reason), set by hand, mirroring `unmaintained`
   (setup warning, card mark). `check_release.py --release` fails while a changed adapter has neither a retest newer
   than its code nor `at_risk` set; a retest PR clears it. No generated file, no write step in the cut workflows.
6. Tests, `pre-commit run --all-files`, regenerate cards/feature table, audit (binding-rule surface: Opus auditor),
   `gh pr ready`.

## Open decisions

None.

## Handoff

Branch `wt/evidence-levels`, worktree `/Users/jason/projects/ha/deviceside-wt/evidence-levels`, draft PR #374. #370 is
merged and merged into the branch. Suite (1759) and pre-commit green at `3c8eb85`.

**Done (steps 1, 4, 5, part of 6):**
- `AdapterScope.at_risk` (`core/scope.py`), in `check_release.FLAGS`; setup warns in `__init__.py` `warn_marked` (was
  `warn_unmaintained`; `tests/test_init.py`, READERS in `test_check_release.py`).
- `check_release.py`: module docstring defines Retests, the `_manual.md` row format and At risk. `needs_retest`,
  `manual_retests`, `report_retests` (report's `deviceside` → tag `v<version>`), `fresh_retest`, `retest_errors`,
  `at_risk_errors`, `release_notes`, `retest_checks`; `--notes PATH`. Adapters with a Verified call still need their rig
  records; manual lines and reports count only for adapters without one (design call: rig coverage stays the gate
  where it exists). Tests at the end of `tests/scripts/test_check_release.py`.
- `gen_compat.py`: `MARKS`, `marked()`, `mark_entries()`, `Card.marks`; ⚠️ At risk on cards, evidence rows, legend;
  README regenerated.
- Both cut workflows pass the call for testers from `check` to `tag` as a job output (main split them into two jobs)
  and `gh release create --notes-file`. RC notes too, not just releases (design call).
- Device report form: the DeviceSide version field says a report tests that release's code.

**Next:**
1. Step 2, rule text (#370 already rewrote CLAUDE.md's Reported paragraph and CONTRIBUTING step 5 for rules 2–3):
   CLAUDE.md: say the five-report count is checked in review, not by `gen_compat.py`; siblings sharing the call may
   move Experimental → Documented on the same evidence; add the retest rule (rule 5) and an **At risk** paragraph
   beside Unmaintained (rule 6, pointing at `check_release.py` for the format, not restating it); Releasing: the cut
   enforces At risk. design.md glossary: At risk entry, Device report (counts as a retest at its version), Test record
   / `_manual.md`. CONTRIBUTING: step 5 and the maintainer section (graduation request, `_manual.md` line).
   `.github/pull_request_template.md` Testing evidence: mention `_manual.md`.
2. Add a ticked TODO.md item for this work (`(#374)`), as its own commit.
3. Rerun `pr-draft docs/plans/2026-11-11-evidence-levels.md` after fixing Touches: drop `config_flow.py`; add
   `custom_components/deviceside/__init__.py`, `tests/test_init.py`, `README.md`, `.github/workflows/cut-release*.yml`.
4. Audit (binding-rule surface: Opus auditor) per global § Code audits, then `gh pr ready`, then a backgrounded
   `merge-green 374 --squash --delete-branch`.

Overlaps: #350/#351 (Control4, no live agent) touch `device_report.yml` and `docs/design.md`.
