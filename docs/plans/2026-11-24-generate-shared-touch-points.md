# Generate the three shared touch points a new integration edits by hand (#416)

## Context

A new integration's PR hand-edits three shared files, so it needs a repo maintainer for each:

- `custom_components/deviceside/services.yaml`: its HA domain in each action's `target:` list. The lists share
  anchors named after the integrations they hold (`&hue_mqtt_shelly_zha`), which rot with every addition.
- `docs/integrations.md`: a link to its page in the intro sentence.
- `.github/ISSUE_TEMPLATE/device_report.yml`: its title in the Integration dropdown.

All three are derivable from the registry. This plan generates them, proves them with `--check` in CI, takes them
off CONTRIBUTING's shared-files list, and lets a maintainer's `/merge` carry the regenerated parts.

No integration's package changes. Control4 is already registered and already in all three files; the generators
reproduce it.

## Coordination

Intent: Generate `services.yaml` target lists, the `docs/integrations.md` page links and the device-report
Integration dropdown from the registry, so a new integration edits none of them by hand.

Touches: scripts/gen_services.py, scripts/gen_compat.py, scripts/gen_codeowners.py, scripts/owners.py,
scripts/check_maintainer_merge.py, custom_components/deviceside/services.yaml, docs/integrations.md,
.github/ISSUE_TEMPLATE/device_report.yml, .github/workflows/tests.yml, tests/scripts/test_gen_services.py,
tests/scripts/test_gen_compat.py, tests/scripts/test_gen_codeowners.py, tests/scripts/test_check_maintainer_merge.py,
tests/core/test_actions_setup.py, tests/test_issue_templates.py, CONTRIBUTING.md, CLAUDE.md, docs/design.md

## Decisions

Settled in the interview (don't redesign):

1. **Check wiring:** `--check` runs as a step in the `pytest` job of `.github/workflows/tests.yml`, beside the other
   generators. No pre-commit hook (none of the generators has one; the issue's "like gen_codeowners.py" was wrong
   about that).
2. **Pin tests are replaced, not kept.** `test_target_filter_lists_exactly_the_integrations_and_domains_served`
   goes; a "checked-in file matches the generator" test takes its place. Same for the options comparison in
   `test_the_device_report_lists_every_integration_for_routing` (its `label == route_issue.LABEL` assertion stays).
3. **Intro links are a bullet list** between `<!-- integrations:start -->` / `<!-- integrations:end -->`, in card
   order (`gen_features.columns`: Zigbee2MQTT, ZHA, Shelly, Hue, Matter, Control4).
4. **The dropdown is in scope.**

Mine, from the code (say so at approval if you want them otherwise):

5. **Labs scopes are included** in target lists: the generator uses `served_domains(adapter, info)`
   (`core/registry.py`), the same derivation the pin test uses today, so the generated lists equal today's as sets.
6. **`services.yaml` is rewritten as text, not round-tripped.** PyYAML would drop the hand-written field anchors
   (`&duration`, `&dimmable`, ...). The generator replaces each action's `target:` line and its deeper-indented
   lines; everything else is byte-identical. No new dependency.
7. **The dropdown is written by `gen_codeowners.py`**, not a fourth script: it already writes `.github/` routing
   output from the registry and checks `manifest.json` in the same run, and the dropdown is what `route_issue.py`
   routes on. Its options sit between YAML comment markers `# integrations:start` / `# integrations:end`.
8. **Merge check:** the three files join `owners.GENERATED`; `check_maintainer_merge.py` refuses a change outside
   their generated parts, as it does for README.

## Steps

### 0. Set up

Copy this plan to `docs/plans/2026-11-24-generate-shared-touch-points.md`, worktree `wt/gen-shared-touch-points`
off `main`, `pr-draft <plan>`.

### 1. `scripts/gen_services.py` (implementer: sonnet)

New script, modeled on `scripts/gen_codeowners.py` (`sys.path` insert, `AdapterRegistry.discover()`,
`main(argv, registry, repo)`, `--check` returns 1 with `error: ... out of date; run scripts/gen_services.py`).

- `targets(registry) -> dict[action_key, dict[ha_domain, set[domain]]]`: over `registry.matrix()`, for each adapter
  that isn't `None`, `served_domains(adapter, registry.integrations[integration])` grouped by `info.ha_domain`
  (lift the loop from `tests/core/test_actions_setup.py:40-45`).
- `block(entries) -> str`: one entry per HA domain, sorted by HA domain; `domain:` a scalar for one domain, a sorted
  flow list for several; no anchors:
  ```yaml
    target:
      entity:
        - domain: [light, switch]
          integration: shelly
  ```
- `generate(text, registry) -> str`: for each top-level action key, replace its `  target:` line plus the
  deeper-indented lines after it (an alias line `target: *name` is the one-line case). `SystemExit` when an action
  has no `target:`, or the file's action keys differ from the registry's.
- Self-check in `generate`: `yaml.safe_load` of the result with every `target` popped equals the input's, and each
  `target.entity` equals `targets()`. Fails loudly on a bad splice.
- `authored(text) -> str`: the text with each target block removed, for step 4.
- Regenerate `services.yaml`. Expected diff: the three target anchors and six aliases expand, entries re-sort;
  `yaml.safe_load` before and after are equal apart from entry order.
- `tests/scripts/test_gen_services.py`: block shapes (scalar, flow list, order), alias and anchor targets replaced,
  hand-written field anchors untouched, missing-target and key-mismatch errors, `--check` stale then clean, and
  `test_the_checked_in_services_yaml_matches_the_registry`.
- `tests/core/test_actions_setup.py`: delete the target-filter test (Decision 2); keep the other two.
- `tests.yml`: add `Check services.yaml targets are current` after the CODEOWNERS step.

### 2. Intro links in `gen_compat.py` (implementer: sonnet)

- New marker pair `INTEGRATIONS = ("<!-- integrations:start -->", "<!-- integrations:end -->")` beside `CARDS` and
  `EVIDENCE`; reuse `splice()` (`gen_compat.py:1730`).
- Block: `- [<IntegrationInfo.title>](integrations/<key>/index.md)` per integration, ordered by
  `gen_features.columns`. Relative links (the file is in `docs/`), not `Data.url`'s absolute ones.
- `main` adds `docs/integrations.md` to the files it computes, writes and `--check`s.
- Edit `docs/integrations.md` lines 3-9 into the approved shape: the sentence ends "...what DeviceSide changes in
  your setup:", the marked list, then "Which devices each feature is proven on..." as its own paragraph. Links in
  the body (lines 37-61) stay hand-written.
- `tests/scripts/test_gen_compat.py`: block content and order, stale then regenerated, and extend the real-data test
  to the third file.

### 3. Dropdown in `gen_codeowners.py` (implementer: sonnet)

- Wrap the integration titles in `device_report.yml` with `# integrations:start` / `# integrations:end` comment
  lines; `Other or not sure` (`route_issue.OTHER`) stays hand-written after the end marker.
- Generator writes `sorted(info.title for info in registry.available_integrations())` between them; `--check`
  covers both files. Update the template's comment (lines 6-7) and the script's docstring to name the generator.
- `tests/scripts/test_gen_codeowners.py`: options written and sorted, stale `--check`, checked-in file matches.
- `tests/test_issue_templates.py`: drop the options comparison, keep the label assertion (Decision 2).

### 4. Merge check and rules (implementer: opus; risky step, gets its own `/audit-code`)

Opus because this decides who may merge without a repo maintainer, and a too-loose strip passes every other check.

- `scripts/owners.py`: add the three paths to `GENERATED`; update its comment.
- `scripts/check_maintainer_merge.py`: `BLOCKS` becomes path -> authored function: the existing HTML-marker strip
  for README, the compat page and `docs/integrations.md`; `gen_services.authored` for `services.yaml`; a
  `# name:start`/`# name:end` strip for `device_report.yml`. Refusal text unchanged in shape. Update the docstring's
  generated-output bullets.
- `tests/scripts/test_check_maintainer_merge.py`: for each new file, a regenerated-part-only change merges with
  owned files; a change outside the generated part is refused (a field edit in `services.yaml`, body text in
  `docs/integrations.md`, another form field in the template).
- `CONTRIBUTING.md`: remove the three bullets (lines 91-93) from "These shared files"; say which generators to run
  instead; fix line 79/81's wording on target filters.
- `CLAUDE.md` Maintainers: add the three to the "regenerated output" list (line 84).
- `docs/design.md` 219-227: target filters are generated by `gen_services.py`; drop the pin test's name.

Rule text in `CLAUDE.md` changes, so the PR audit runs with an Opus auditor (CLAUDE.md, Pull requests).

## Verification

- `.venv/bin/pytest -n auto --transcripts=check` green.
- Each generator's `--check` exits 0 on the tree, and exits 1 after hand-editing its output (one target entry, one
  link, one dropdown option).
- `services.yaml`: `yaml.safe_load` of `main`'s copy and the regenerated one are equal once each `target.entity` is
  sorted by integration; `git diff` shows only target blocks.
- `device_report.yml` options and their order are unchanged; `docs/integrations.md` body below the intro unchanged.
- Hassfest workflow green on the PR (it reads `services.yaml`).
- No rig run: no call or reply handling changes.

## Launch

`sonnet` for the session (the plan settles the calls; `--check`, the real-data tests and the diff catch a wrong
one), with step 4's implementer on `opus`:

`cd ~/projects/ha/deviceside && claude --model sonnet 'Implement the plan at ~/.claude/plans/rustling-pondering-newt-of-a6f62d68-415e-45ca-8664-831a4651ce36.md, starting at step 0.'`
