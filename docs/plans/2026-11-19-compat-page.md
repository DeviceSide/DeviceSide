# Device compatibility page: one generated, device-first page

## Context

`docs/device-compatibility.md` is hard to read. Its hand-written prose repeats `docs/evidence.md` and the README legend,
two of its sections are empty, the Tuya TS011F is written up four times, and its generated evidence block is an audit
dump (action keys, class keys, an "Items" column of internal jargon, refusal rows repeated per integration). The
integration pages make it worse: their headings ("Tested devices", "Should work", "Try it: Labs") state levels in
prose, which goes stale whenever a level changes in code.

Goal: minimal drift. Every device fact on a generated page comes from code, devices.yaml, models.yaml or records, and
`--check` proves it; the README cards and the page render from one model; hand-written pages give reasons, never
levels; every mark on the page links to its proof in one click.

Post-v0.1.0: this is a binding surface for contributors now, so keep the generator's inputs unchanged where possible
(no new devices.yaml fields beyond those named here).

## Decisions

1. Option 2: one generated page, device-first. No separate proof page; a later one would be one more render of the
   same model.
2. Page shape: **Tested devices** (a heading per tested model, generated) → **By integration** (class × feature
   matrix per integration) → **Not supported** (one merged table).
3. The per-action Items rows go. A field whose level is weaker than its action's goes in a footnote under its
   integration's matrix.
4. A short hand-written intro sits above the start marker. It is the one home of the user wording for the marks
   (levels, Labs, ⚠️ Unmaintained, 🔧 Untested fix, how to report), under a `## Levels of proof` heading so the
   existing `#levels-of-proof` links keep working.
5. Every matrix cell links its proof: 🟢 → its record(s) (rig JSON or `_manual.json`); 🟡/⚪ → the class's section on
   its integration page (the reason, or what was tried, with its source); 🔴 → its Not supported row. The generator
   fails when a 🟡 or ⚪ class has no section.
6. Integration pages never state levels. Each class has a `###` under `## Device classes` saying what sets it apart
   and why it inherits or was admitted, with its source. Level-word headings are removed, and a check fails them.
7. Model headings live only on the generated page. Cards always link a model there (this drops check_sections'
   "integration page first, else any page" lookup for models).
8. User reports become proof through a `_manual.json` row carrying them: a new optional `reports` field (issue URLs in
   this repo), with `commit` and `calls` taken from the release the reporters ran. The page shows "by report", linking
   the issues. No count is enforced (tenet 7).
9. `tester` is renamed `signed_by`: the maintainer who vouches for the row. With `reports`, they signed off on other
   people's runs.
10. Control4 (`docs/integrations/control4/`, @skialpine's) is split into a PR of its own: its page tidy and the
    `signed_by` rename of its `_manual.json`. Until that PR merges, the schema accepts `tester` as well as `signed_by`.
    This PR leaves Control4's page working, and its links still resolve.

## Steps

### 1. One compat model (no output change)

In `scripts/gen_compat.py`, put the card lines in a model before `fold()` runs: each line's class phrase, section,
domain, variant parent, per-feature status, tested models (rig/by hand), and caveats. `cards()` renders from it.
Check: `scripts/gen_compat.py --check` passes with the README unchanged, along with the existing card tests.

### 2. Render the page from the model

Replace `evidence()`/`rows()`/`level_rows()`/`named()` (keep `items()`, which `card_evidence` uses) with:
- **Tested devices:** a `###` per tested model (name from models.yaml/devices.yaml; ids, with Zigbee2MQTT's product
  code where listed). Then a table: Integration | Features tested (each linking its record) | Firmware (distinct
  values) | How (✔ rig, by hand). Also a `### Native groups` heading with per-integration features.
- **By integration:** a `###` per integration (title, as today, so `#shelly` and the others keep resolving), the card's
  caveats under it, then a matrix. Rows are the unfolded card lines (variant children indented under their parent;
  native groups first). Columns are the integration's features in README order (`card_features()`). Cells hold the mark
  plus a link, per Decision 5, and split features show parts ("🟢 down · ⚪ up"). The field footnote goes under the matrix.
- **Not supported:** `no_known_method` and `not_built` entries merged across integrations. Columns: Devices |
  Integrations | Features | Why | Source. Rows are deduplicated by (what, reason, source).
- `check_sections`: models and native groups resolve to this page's generated headings, classes to their integration
  page. Fail when a 🟡/⚪ class has no section.
- Rewrite the docstring sections Evidence block, Links and Data. Replace the evidence-block tests in
  `tests/scripts/test_gen_compat.py` (the `rows`/levels tests, around lines 271–430 and 930) with tests of the matrix
  cells and links, the tested-devices table and the merged refusals.
- Keep the marker names (`evidence:start`/`end`), so `check_maintainer_merge.py`'s BLOCKS and `owners.py` need no change.
  Confirm in their tests.

### 3. The page's hand prose, and links into it

- Replace everything outside the markers with the intro (Decision 4). Delete the Maintainers, Should work, Try it:
  Labs, Not built yet, Zigbee plugs and switches and Tuya TS011F sections, and the per-model prose.
- Move these facts home first, checking that each isn't already there:
  - The Hue mid-fade reports are already in `hue/internals.md` (Tested behavior): delete.
  - LCA016's color mode override, which is unit-tested only for turning it off → `zigbee2mqtt/index.md`.
  - Native groups: Hue room writes are already in `hue/index.md`. ZHA's missing groupcast feedback goes in
    `zha/index.md`'s group bullet if it's user-facing (it's already in `zha/internals.md`).
  - The plugs/TS011F prose is already in `docs/integrations.md#zigbee-plugs-and-switches`, `zigbee2mqtt/index.md#tuya-ts011f-plugs`
    and `zha/index.md#tuya-plugs-and-switches`.
- Redirect the inbound links (`rg -n "device-compatibility\.md#"`):
  - `#zigbee-plugs-and-switches` → `integrations.md#zigbee-plugs-and-switches`. For integrations.md's own links, point
    at the Zigbee2MQTT/ZHA sections.
  - `#tuya-ts011f` (integrations.md, defects.md, Zigbee2MQTT/ZHA pages) → the integration's TS011F section.
  - `#try-it-labs` (Zigbee2MQTT/ZHA pages, TODO.md if still present) → the class section, or `#levels-of-proof`.
  - `#maintainers` (design.md:47) → `#levels-of-proof`.
  - `#levels-of-proof`, `#tested-devices`, `#native-groups` and `#shelly` keep resolving: confirm.
- `scripts/gen_features.py` LEGEND anchors and `tests/scripts/test_gen_features.py:315`: keep valid.

### 4. Integration pages (not Control4)

- Shelly: replace Tested devices / Should work / Try it: Labs with `## Device classes`: relays and plugs, multicolor
  bulbs, dimmers, LED controllers. Each says what sets it apart and why it inherits (Shelly Light API) or what was tried
  (the DimStop report), with no level words. Gen4 "same `Switch` component as Gen3" goes in the relay class. Update
  `shelly/devices.yaml` `section`s.
- Matter: the WiZ Smart Plug's "never reports its running timer" → `## Turn on with timer`, or `internals.md` if it's
  already there. Remove the WiZ heading and `## Should work`. Matter lights become a class section.
- Hue, ZHA, Zigbee2MQTT, Matter: drop the "Every feature says how well it is proven for each (levels of proof)"
  boilerplate and the bullets saying a class "is tested" ("every feature on this page has passed on them"). The matrix
  says that.
- Check (in `gen_compat.py`, run by `--check`): an `index.md` heading matching Tested devices|Should work|Try it|Labs|
  Verified|Documented fails, naming the file. Control4 is exempt until its split PR merges; remove the exemption there.
- `CLAUDE.md` "Where facts go": the shared home of models' user-facing facts is now the generated page from
  models.yaml/devices.yaml. The `index.md` shape line: replace "Shelly's for Try it" with the class-section rule
  (Decision 6). This is binding rule text, so it needs an Opus audit.

### 5. Reports in sign-offs (binding surface: Opus audit, repo maintainer)

- `docs/test-records.schema.json` `manual_row`: add `reports` (optional array of `https://github.com/DeviceSide/DeviceSide/issues/<n>`
  URLs, unique, minItems 1), rename `tester` → `signed_by` and accept either until step 6 merges, and add optional
  `firmware` to `manual_device`.
- `scripts/signoff.py`: add `--reports <url>...` and `--at <tag>` (commit and transcript blobs from that tag, not HEAD).
- `scripts/check_release.py` reads `signed_by` or `tester`. `gen_compat.py` renders "by report" with the issue links.
- `docs/evidence.md` Sign-off format and The Labs flag: a report-backed row replaces "PR body cites them".
- Check that the device report issue form collects the DeviceSide version, model ID, manufacturer string, the class the
  result reported, and firmware. Add whichever are missing.
- Rename `tester` in every `_manual.json` except Control4's.

### 6. Control4 PR (separate, @skialpine reviews)

Its page tidy (as in step 4) and its `_manual.json` rename. Then drop `tester` from the schema and remove the
heading-check exemption. The PR body opens with this, filling in the main PR's number (first person; no single em-dashes):

> @skialpine, this brings Control4's page in line with a change I made across every integration (#<main PR>).
>
> **Why:** the integration pages stated each device's level in hand-written headings ("Tested devices", "Try it:
> Labs"). Each time a level changed in code, that prose went stale, and the compatibility page had become hard to read.
>
> **What changes for Control4:**
> - Your page keeps the reasons (what sets each class apart, and what was tried on what) and drops the level headings.
>   The generated [compatibility page](docs/device-compatibility.md) now shows each class's level, and each mark links
>   to its proof.
> - The LTD010 downlight's heading moves to that page, which builds it from your `_manual.json` sign-off.
> - `tester` becomes `signed_by` in `_manual.json`. A sign-off can now carry users' reports (`reports`, linking their
>   issues), so working reports from Control4 users can lift a Labs flag with their proof on the page.
>
> **The upshot:** when you lift a flag or add a device, the page updates itself and CI proves it, so nothing you wrote
> goes stale, and a user is one click from the evidence behind every mark.

### 7. Follow-ups, as issues

- ha-rig: Zigbee2MQTT records write the Zigbee2MQTT version as firmware (`"Zigbee2MQTT 2.14.3"` in
  `zigbee2mqtt/test-records/turn_on_for.json` and `get_attributes.json`). Don't hand-edit the records.
- `integrations/zigbee2mqtt/refusals.py` / ZHA's: the `_TZ3000_gjnozsaz` entry is named two ways, and Zigbee2MQTT's
  reason starts lowercase ("its maker string…"). Align them in step 2 if the merged table shows it.

## Verification

- `.venv/bin/pytest -n auto --transcripts=check`, and `scripts/gen_compat.py --check` and `scripts/gen_features.py --check`
  clean.
- After step 1: the README is byte-identical.
- Render the page on GitHub (a draft PR's file view). Every matrix cell's link resolves, and each model heading is
  reachable from its card.
- Check that no link targets a missing anchor: run `rg -no "device-compatibility\.md#[a-z0-9-]+"` and check each against
  the page's headings. Do the same for the moved targets on integration pages.
- Step 5: a test row with `reports` and `--at` validates, credits its class, and renders "by report". A `tester` row
  still validates.

## Coordination

Intent: Replace docs/device-compatibility.md with a generated, device-first page whose every mark links its proof;
strip levels from the integration pages; let a sign-off carry user reports.
Touches: scripts/gen_compat.py, scripts/gen_features.py, scripts/signoff.py, scripts/check_release.py,
tests/scripts/test_gen_compat.py, tests/scripts/test_gen_features.py, docs/device-compatibility.md, README.md,
docs/integrations.md, docs/defects.md, docs/design.md, docs/evidence.md, docs/test-records.schema.json,
docs/integrations/{hue,zha,zigbee2mqtt,shelly,matter}/index.md, docs/integrations/*/devices.yaml,
docs/integrations/*/test-records/_manual.json (not control4), .github/ISSUE_TEMPLATE/device_report.yml, CLAUDE.md
