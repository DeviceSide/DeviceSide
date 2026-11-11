# Evidence levels: graduation, retests and Stale tests

## Coordination

Intent: Replace the second-tester and Reported rules with the agreed evidence tenets: Experimental graduates on five
independent reports, every changed adapter is retested before release, and an adapter left untested at the cut ships
live marked ⚠️ Stale tests.
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
6. **Stale tests.** An adapter changed since its last retest ships live at the cut, marked ⚠️ Stale tests on its card and in
   setup; the release notes link the device report issue to recruit testers. One accepted report at the new code clears
   it. Unmaintained stays separate: a human call about a missing maintainer.

Manual testing stays light: one `_manual.md` line (date, commit, tester, devices, what passed). Checklists derived from
the rig's tests, or a public rig, come only if user complaints call for them.

## Steps

1. `pr-draft` this plan in a `wt/evidence-levels` worktree off `main` (after #370 merges).
2. **Rule text:** rewrite CLAUDE.md's Reported paragraph and add graduation, retest and Stale tests rules; update the
   design.md glossary (Reported, Device report, new Stale tests entry); CONTRIBUTING step 5 and the maintainer section
   (graduation request, `_manual.md`); PR template Testing evidence mentions `_manual.md`.
3. **Reports:** the five-report count is the maintainer's discretion, checked in review, not by `gen_compat.py`. Say
   so in CLAUDE.md's Reported rule and CONTRIBUTING.
4. **Retests:** `check_release.py --records` accepts a `_manual.md` line or an accepted report newer than the
   adapter's code as a retest; at the cut it lists the rest as Stale tests instead of failing for adapters with no rig
   coverage. Define the `_manual.md` line format there and test it.
5. **Stale tests mark:** an `AdapterScope.stale_tests` field (an issue URL or reason), set by hand, mirroring `unmaintained`
   (setup warning, card mark). `check_release.py --release` fails while a changed adapter has neither a retest newer
   than its code nor `stale_tests` set; a retest PR clears it. No generated file, no write step in the cut workflows.
6. Tests, `pre-commit run --all-files`, regenerate cards/feature table, audit (binding-rule surface: Opus auditor),
   `gh pr ready`.

## Open decisions

None.

## Handoff

Branch `wt/evidence-levels`, draft PR #374, head `a533c1b`; suite (1761) and pre-commit green. All steps are done,
including the rule text, TODO item, Touches, the rename At risk → Stale tests (`AdapterScope.stale_tests`, Jason's
call) and fixes for audits 1 and 2. audit-gate is at HANDOFF (two NOT-CLEAN audits in a row). Audit 2's Mediums are
fixed in `a533c1b`: a report retests only through an item the adapter ships; RC report versions; the docstring now agrees.

**Next:** Jason's call: `audit-gate accept`, or let a third audit run (`audit-gate brief pr`). Then `gh pr ready`
and a backgrounded `merge-green 374 --squash --delete-branch`.

Follow-up: the shared-code proof rule is in its own plan and PR (#377, `wt/shared-code-proof`).
