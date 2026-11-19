# One translation file: drop strings.json

## Coordination

Intent: Make `custom_components/deviceside/translations/en.json` the only English strings file, deleting
`strings.json`, so UI text has one home and an edit to it reaches users.
Touches: custom_components/deviceside/strings.json, tests/core/test_actions_setup.py,
tests/integrations/zigbee2mqtt/test_classes.py, docs/design.md, CONTRIBUTING.md

## Context

`strings.json` is HA core's source file: core's `script.translations develop` resolves its `[%key:...%]` references
and generates `translations/en.json`. A custom integration gets no such build. HA loads only `translations/<lang>.json`
at runtime, and hassfest validates `translations/en.json` when run with `--integration-path`, as the hassfest action
does. This repo uses no `[%key%]` references, so `strings.json` is a byte-for-byte copy held equal by
`test_translation_is_a_copy_of_strings`.

The cost showed in #545: the edit went to `strings.json`, the file that looks like the source, changed nothing a user
sees, and failed CI until the copy was made. One file removes the trap, the sync test and the double edit. Under
CLAUDE.md's "fix the architecture now" rule this lands before v0.1.0, and before the v0.1.0rc3 audit restarts so the
audit covers it.

## Step 1 (the only step)

1. `git rm custom_components/deviceside/strings.json`. `translations/en.json` is already identical (#545 made it so;
   confirm with `cmp` before deleting).
2. `tests/core/test_actions_setup.py`: load `translations/en.json` as `STRINGS`; delete
   `test_translation_is_a_copy_of_strings`; docstring says `translations/en.json`. `test_strings_match_actions` stays,
   now against the shipped file.
3. `tests/integrations/zigbee2mqtt/test_classes.py:30`: `STRINGS` points at `translations/en.json`.
4. `docs/design.md:220,225` and `CONTRIBUTING.md:81,97`: `strings.json` becomes `translations/en.json`; line 97's
   "`strings.json` and `translations/en.json`" becomes the one file.
5. `rg -n --hidden 'strings\.json'` (excluding `docs/audits/`, `docs/plans/`, research) returns nothing. Gitignored
   `notes/` plans are historical and stay as they are.

Not changed: no generator or pre-commit hook (nothing to sync); other languages, if ever added, are their own
`translations/<lang>.json`.

## Verification

- `.venv/bin/pytest -n auto --transcripts=check` and `pre-commit run --all-files`.
- CI's "Validate with hassfest" job green on the PR: it validates `translations/en.json` for a custom integration, so
  the schema check carries over to the one file.
- No rig run: no call or reply handling changes (evidence tenet 9).

## Delivery

Branch `wt/single-translation-file`, draft PR via `pr-draft <this plan>`, one implementer (`sonnet`: settled, and
tests plus hassfest catch a miss). Code audit per the global rule before ready. Shared files (`core` tests, design.md,
CONTRIBUTING), so a repo maintainer merges: `merge-green <n> --squash --delete-branch`. Then restart the v0.1.0rc3
audit from the new `main`.
