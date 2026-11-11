# Evidence levels: graduation, retests and At risk

## Coordination

Intent: Replace the second-tester and Reported rules with the agreed evidence tenets: Experimental graduates on five
independent reports, every changed adapter is retested before release, and an adapter left untested at the cut ships
live marked ⚠️ At risk.
Touches: CLAUDE.md, docs/design.md, CONTRIBUTING.md, .github/ISSUE_TEMPLATE/device_report.yml,
.github/pull_request_template.md, custom_components/deviceside/core/scope.py, custom_components/deviceside/config_flow.py,
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
3. **Reports:** `gen_compat.py` reports gain a reporter-is-maintainer distinction (from the issue author vs
   `IntegrationInfo.maintainers`) so it can count independent reports; refuse a Reported item that left Experimental
   on fewer than five, or keep it a review check if the count can't be derived from `devices.yaml` cleanly
   (judgment call: decide and note why in the module docstring).
4. **Retests:** `check_release.py --records` accepts a `_manual.md` line or an accepted report newer than the
   adapter's code as a retest; at the cut it lists the rest as At risk instead of failing for adapters with no rig
   coverage. Define the `_manual.md` line format there and test it.
5. **At risk mark:** how it is carried (a generated list the release writes, or an `AdapterScope` field like
   `unmaintained`): pick the fewest mechanisms; setup warning and card mark mirror Unmaintained's.
6. Tests, `pre-commit run --all-files`, regenerate cards/feature table, audit (binding-rule surface: Opus auditor),
   `gh pr ready`.

## Open decisions

- Step 3: enforce the five-report count in `gen_compat.py`, or leave it to maintainer review.
- Step 5: how At risk is carried.
