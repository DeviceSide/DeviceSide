# Rename the Experimental level to Labs, in code and rules

## Coordination

Intent: one name for the lowest level everywhere. The level, its option and its flag are called Labs in what users see,
in the code, in the stored option key and in the rule text, so contributors stop translating.
Touches: custom_components/deviceside/**, tests/**, scripts/gen_compat.py, scripts/gen_features.py,
scripts/check_release.py, .github/ISSUE_TEMPLATE/device_report.yml, .github/pull_request_template.md, docs/evidence.md,
docs/design.md, docs/action-behavior.md, docs/device-compatibility.md, docs/internals.md, docs/icons/README.md,
CLAUDE.md, CONTRIBUTING.md, TODO.md, README.md (regenerated)

## Why

The README said Experimental, on trial and untested for one thing. The user-facing half is done: the option, cards,
report form and user docs say Labs. Code and rules still say Experimental, and "on trial" survives in the evidence
rules. Two names for one thing leak back into user docs with every contributor PR (the user-facing commit fixed about
35 such lines). Before v0.1.0 is the cheap time to rename (CLAUDE.md).

## Decisions

1. **Labs is the third level.** "A scope item is Verified, Documented or in Labs." `Level.LABS` replaces
   `Level.EXPERIMENTAL` in the enum (same value, 0); every rule keeps its structure, only the words change.
2. **Phrasing:** "in Labs" as a predicate ("the class is in Labs", "an item in Labs is refused"), "Labs" as an
   attributive ("a Labs item", "Labs lines"). Matches the user docs already on the branch.
3. **"Trial" goes.** No "trial", "on trial" or "trials" as the name of the level or of a class's stay in it. The
   evidence.md section "No known method, not built yet, on trial" becomes "No known method, not built yet, in Labs";
   its bullet "On trial (Experimental)" becomes "In Labs". "A trial admits only what its evidence names" becomes "Labs
   admits only what its evidence names"; "the user's consent to its trials" becomes "the user's consent to what's in
   it". The anchor changes to `#no-known-method-not-built-yet-in-labs`: every link to the old anchor moves with it,
   outside research files (Decision 6). Plain-English "trial" that isn't the level's name (none known) may stay.
4. **Flag/lift stays, with Labs named at first use.** "The Labs flag" and "lifting the flag" stay. Tenet 8 in
   CLAUDE.md says "lifting a Labs flag", and so does its echo in `docs/evidence.md` (the release-gate decision list,
   "*lifting a Labs flag*"), as agents read the tenet on its own. Where a document first says "flag", it says "the Labs flag" (or otherwise ties the
   flag to Labs in that sentence); later uses may say "the flag". The evidence.md section "The experimental flag"
   becomes "The Labs flag" (`#the-labs-flag`).
5. **Migrate the stored key.** The option `experimental_features` becomes `labs` in config-entry options, via a
   config-entry minor-version migration (below). A rollback to an older build sees no `experimental_features` and
   reads Labs as off, the safe default; accepted.
6. **History keeps its words; only research is never edited.** Research files (`docs/research/**`,
   `docs/integrations/*/research/**`) are dated sources, never edited (CLAUDE.md, Where facts go): the one link in them
   to a renamed anchor (`docs/research/2026-11-14-timer-units-at-scale.md`, `#the-experimental-flag`) goes stale and
   lands at the top of evidence.md; accepted. Earlier plans, `docs/audits/*` and test records keep their wording, as
   rewriting what they said then gains nothing; they hold no link to a renamed anchor today, and any found is fixed.
7. **Response and error key.** The refusal key `experimental_off` (`core/errors.py` `EXPERIMENTAL_OFF`, the
   `exceptions` translation key, the reason `docs/action-behavior.md` names) becomes `labs_off`. It reaches users'
   responses and logs, so it is named in the release notes; pre-v0.1.0, so no alias.
8. **Report form field id** `experimental_features` becomes `labs` (`device_report.yml` and `config_flow.py`
   `_VERSION_FIELDS`). Report links built by older installs pre-fill a field that no longer exists, so that answer
   arrives blank; accepted.
9. **The scope marker:** `experimental(...)` becomes `labs(...)`, beside `verified(...)` and `documented(...)`;
   `AdapterScope.all_experimental` becomes `all_labs`.

## Name map (settled; don't redesign)

| Now | Becomes |
|---|---|
| `Level.EXPERIMENTAL` | `Level.LABS` |
| `experimental(...)` (`core/scope.py`) | `labs(...)` |
| `AdapterScope.all_experimental` | `all_labs` |
| `CONF_EXPERIMENTAL = "experimental_features"` | `CONF_LABS = "labs"` |
| `EXPERIMENTAL_DEFAULT` | `LABS_DEFAULT` |
| `Runtime.experimental_features` | `Runtime.labs` |
| `EXPERIMENTAL_OFF = "experimental_off"` | `LABS_OFF = "labs_off"` |
| translation keys `experimental_features`, `experimental_off` | `labs`, `labs_off` |
| report form field id `experimental_features` | `labs` |
| `EXPERIMENTAL_SHARE_MAX` (`gen_compat.py`) | `LABS_SHARE_MAX` |
| `TRIAL`, `Line.on_trial` (`gen_compat.py`) | `LABS`, `Line.in_labs` |
| `gen_compat.py` status key `"experimental"` and `TIER` value | `"labs"` |
| local names: `experimental_on`, `experimental_option`, `_experimental` | `labs_on`, `labs_option`, `_labs` |
| test helper `allow_experimental` (`tests/conftest.py`) | `allow_labs` |
| test names containing `experimental` / `on_trial` | the same with `labs` / `in_labs` |
| comments and docstrings: "Experimental", "the experimental flag", "on trial", "Experimental features (option)" | per Decisions 1 to 4 |

Find what's left with `rg -n -i --hidden 'experimental|on.trial|\btrials?\b' --glob '!.git/**' --glob '!docs/plans/**'
--glob '!**/research/**' --glob '!docs/audits/**' --glob '!**/test-records/**'`; after step 3 the only hits are this
plan, `CONF_`-era names in the migration (step 1) and its tests, `TODO.md`'s ticked items, and `TODO.md`'s link to
`docs/plans/2026-11-18-experimental-listing.md` (a filename, Decision 6).

## Steps

### Step 1: the option key and its migration (risky: data)

- `config_flow.py`: add `MINOR_VERSION = 2` beside `VERSION = 1`; the options form writes `CONF_LABS`.
- `__init__.py`: `async_migrate_entry`. An entry at version 1, minor 1 has its options' `experimental_features`
  moved to `labs` (value kept; absent stays absent), then `async_update_entry(..., options=..., minor_version=2)`.
  An entry at a version above 1 returns False (HA's downgrade guard). Entry setup reads `CONF_LABS`.
- Keep the old key's literal only in the migration, as a named constant with a comment that it is v0.1.0rc's key and
  goes once no rc install is left (v0.2.0, matching `migrations.py`'s own deletion note).
- Families' and integrations' packages (`families/*/__init__.py`, `refusals.py`, `classes.py`) change in step 2, so
  their maintainers hear of it through `owner-notice.yml` when the PR opens; no family logic changes.
- Rename per the map: `CONF_*`, `*_DEFAULT`, `Runtime` field, report-form field id and `_VERSION_FIELDS`, the
  translation `data`/`data_description` keys in `strings.json` and `translations/en.json`.
- Tests (`tests/test_config_flow.py`, `tests/test_init.py` or a new `tests/test_entry_migration.py`): migrates on;
  migrates off; an entry with no options gets none; an entry already at minor 2 is untouched; a future major version
  refuses; the options form shows and saves `labs`; a report prefills `labs=on`. `tests/test_issue_templates.py`
  passes with the new id.
- Model: **opus** (data migration; a wrong one silently resets users' choice and no hardware check would catch it).
- Gets an `/audit-code` of its range (risky).

### Step 2: the mechanical rename in code, scripts and tests

- Everything else in the name map, across `custom_components/deviceside/**`, `scripts/gen_compat.py`,
  `scripts/gen_features.py`, `scripts/check_release.py` and `tests/**`, including comments and docstrings, worded per
  Decisions 1 to 4. Error key `labs_off` (`core/errors.py`, `dispatcher.py`, both string files).
- Behavior unchanged: transcripts must not change (`--transcripts=check` passes with no regenerated transcript).
- Regenerate README and `docs/device-compatibility.md`'s generated block (`gen_features.py`, `gen_compat.py`); the
  evidence table's level column now reads Labs.
- Model: **sonnet** (settled map; tests, transcripts and the generators' `--check` catch a miss).

### Step 3: rule and contributor text

- `docs/evidence.md`: Levels; "No known method, not built yet, in Labs" (heading, bullet, every "trial"); "The Labs
  flag" (heading, first use names Labs, `labs(...)` and `verified(...)` in lifting); the cards paragraph, which still
  says folding into one "⚪ on trial" line (stale since e2d0dfa: the folded line has no label now); every other
  "Experimental" and "on trial".
- `docs/design.md`: glossary. Merge the Experimental, Experimental features and (new) Labs entries into one **Labs**
  entry (the level, the flag `labs(...)` and the option `labs`, off by default, only the dispatcher reads it), and
  fix the glossary's links to the renamed anchors.
- `CLAUDE.md`: line 8 "`experimental` flag" → "Labs flag"; tenet 8 "lifting a Labs flag" (Decision 4); line 69 levels
  "(Verified, Documented, Labs)"; the
  binding-rule surface line names "the Labs flag (`labs(...)`)". No other change to rule text.
- `CONTRIBUTING.md` step 4 ("Ship behind `labs`", first use names the Labs flag) and step 6; `docs/action-behavior.md`
  (`labs_off`); `docs/internals.md`, `docs/icons/README.md`, `TODO.md`'s
  undated lines (TODO.md's ticked items describe what shipped and may keep their wording); every link to
  `#no-known-method-not-built-yet-on-trial` or `#the-experimental-flag` outside research files (Decision 6).
- Model: **opus** (binding rule text; no check proves wording).

## Checks (every step)

- `.venv/bin/pytest -n auto --transcripts=check`
- `uvx pre-commit run --all-files`
- `.venv/bin/python scripts/gen_features.py --check` and `.venv/bin/python scripts/gen_compat.py --check` (after
  step 2)
- The `rg` in Name map: hits only where this plan allows.

## Review and audit

- A fresh `plan-reviewer` per step, **opus**.
- The PR's `/audit-code` runs on the whole diff when it's marked ready, with an **Opus** auditor (binding-rule
  surface: `docs/evidence.md`, the flag, `AdapterScope`, CLAUDE.md rule text), then `owner-findings`.
- Release notes: the option's on-screen name is Labs, the stored key migrates, and the refusal key is `labs_off`.
