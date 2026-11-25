# Standard-call route: Zigbee2MQTT's standard lights to Documented (v0.2.0 step 3)

2026-11-25. The sub-plan for step 3 of [the v0.2.0 plan](2026-11-25-v0.2.0-backlog.md), which holds the Decisions
(1 and 5-16) this builds; settled in step 2's grilling with Jason. Don't redesign them: what they don't settle comes to
Jason and is recorded there as a numbered Decision. Evidence: [the converter survey](../research/2026-11-25-z2m-converter-survey.md).

## Coordination

Intent: A new Zigbee2MQTT class, other brands' standard lights, keyed on a committed table of ZHC light definitions on
the standard converters, is Documented on nine light actions with Labs off; evidence.md gains the route; a ZHC bump
becomes the first step of each RC.
Touches: docs/evidence.md, docs/design.md, CLAUDE.md, CONTRIBUTING.md, scripts/check_maintainer_merge.py, tests/scripts/**, docs/plans/2026-11-25-standard-call-route.md, docs/research/2026-11-25-z2m-converter-survey.md, custom_components/deviceside/core/scope.py, custom_components/deviceside/core/registry.py, tests/core/test_registry.py, custom_components/deviceside/zigbee/standard_lights.py, tests/zigbee/**, scripts/owners.py, scripts/gen_codeowners.py, .github/CODEOWNERS, .pre-commit-config.yaml, custom_components/deviceside/integrations/zigbee2mqtt/**, tests/integrations/zigbee2mqtt/**, docs/integrations/zigbee2mqtt/**, scripts/zhc_table.py, scripts/zhc_table/**, scripts/check_audit.py, tests/scripts/**, .github/workflows/tests.yml, .github/workflows/cut-release-candidate.yml, .claude/skills/release/SKILL.md, docs/device-compatibility.md, README.md
Depends-on: #613

## What is settled

- **The class** (Decisions 6, 15). One class, carved out of `other` by one rule placed after every family in
  `families/__init__.py`'s order: a light whose `definition_model` (`rules.py`, DEFINITION) is a table member, not
  excluded. Light domain only. It belongs to the integration, as `other` does, so its levels live in
  `integrations/zigbee2mqtt/classes.py` beside `OTHER_LEVELS`. Families still win: a Hue, IKEA or Tuya light never
  lands here.
- **Membership** (Decisions 5, 6, 9). A ZHC light definition, resolved with ZHC's own `prepareDefinition` as the
  survey's Part A did, whose converters for every key DeviceSide sends are ZHC's standard ones, with no `meta` flag
  or `toZigbee` override touching a DeviceSide call. `turnsOffAtBrightness1` keeps a definition out (#613 owns the
  floor). A definition exposing `color_hs` without `supportsHueAndSaturation` is out (survey Part 4: its saturation
  fade isn't the call on record). The survey's count at its pin is 642; a different count at the new pin is reported in
  the PR body, not a failure.
- **Levels** (Decisions 7, 8, 15). `documented(...)` on the new class for `raise_brightness`, `lower_brightness`,
  `stop`, `raise_hue`, `lower_hue`, `raise_saturation`, `lower_saturation`, `set_attributes` and
  `get_attributes`. Every other action stays as `other` has it: `turn_on_for` gets the same `NotBuilt` entry
  (`OTHER_TIMER_REASON`) in `refusals.py`, as its call harms some lights; the rest not built. `other` keeps its
  levels. ZHA is untouched.
- **Hue and saturation**: `zigbee2mqtt/fade.py`'s `color_hs` check already answers `unchanged` with
  `fields_dropped` for a light without it; a unit test pins that for the new class. No second class.
- **The table** is a generated Python module, `zigbee/standard_lights.py` in the Zigbee catalog (Decision 21), loaded
  at import with no file I/O:
  - generated, between markers: the ZHC release tag pinned, and `MODELS`, one entry per definition model (vendor,
    whether it exposes `color_hs`, its Zigbee model IDs and fingerprints);
  - hand-kept, outside the markers, preserved by every regeneration: `EXCLUDED`, one row per split-off (the identity:
    a definition model by default, or Zigbee manufacturer and model ID, plus firmware where the report narrows it; the
    action the report concerns; its source), and `KEPT`, a departure a maintainer kept, with the reason
    (Decisions 10-12). An excluded model stays in `other`, at its levels.
  The implementer may pick another committed format if a reason comes up (an import-time cost, a check that can't read
  it); it reports the reason.
- **Step 3's split-offs** (Decision 10, survey Part 4's rows no flag catches), each in `EXCLUDED` with its source:
  dresden FLS-PP3; Paulmann 924.70; Müller Licht GU10; AwoX, EGLO EGLO_ZM_RGB_TW and Iluminize 5120.1100; Müller
  Licht tint on older firmware (45327, 45328, 404065). The flagged and overridden rows of Part 4 fall out of
  membership by themselves; a test asserts each named one is not a member.
- **The generator** (Decision 16): `scripts/zhc_table.py`.
  - `--pin <ZHC release tag>` clones ZHC to a temp dir, builds it and resolves the definitions (a node helper under
    `scripts/zhc_table/`; the survey's Part A is the method), rewrites the generated block, and prints the proposal:
    additions; departures, each **review** when the model is a member in the table at the last full-release tag
    (`git show vX.Y.Z:…`), else **leaves**; trait changes on family models' definitions, flagged, never classifying.
    A departure is applied by the regeneration; a reviewed one the maintainer keeps goes in `KEPT`.
  - `--check`, with no network: the module loads, every `EXCLUDED` and `KEPT` row has a source or reason, no row
    is both, and `docs/integrations/zigbee2mqtt/standard-lights.md` matches what it renders. A step in
    `tests.yml` beside `gen_compat.py --check`.
  - Pin this PR's table to ZHC's latest release when the step runs.
- **The page** (Decision 14): `standard-lights.md`, generated: a row per member (vendor, model, smooth hue and
  saturation yes/no), then the excluded rows with their sources, the ZHC release at the top. No level is stated on it
  (gen_compat's rule); it says what the list is and links `index.md`.
- **Card and docs** (Decisions 13, 14):
  - `devices.yaml` `capabilities`: the class, phrase "other brands' standard lights", section "Standard lights",
    light domain.
  - `index.md`: `### Standard lights` under Device classes, in Hue's page shape: what sets the class apart, why it
    is Documented (Z2M's own users send the same calls through the same converters, and no report names a departure;
    the survey is the source), that hue and saturation moves need a light exposing `color_hs`, and how to check: the
    light's Model on its Zigbee2MQTT page, against the list. `### Other brands` gains a sentence pointing there for
    the lights that left it.
  - `internals.md`: the membership predicate, the table, the bump and why ZHC's options 0/0 against DeviceSide's 1/1
    doesn't matter for the two raw-command actions (Decision 8), linking the survey.
  - `gen_compat.py` and its fold are unchanged; regenerate README and `docs/device-compatibility.md`.
- **evidence.md** (Decision 1, as Decision 5 rekeys it): under Levels, Documented, a third bullet, **a standard
  converter's call**, which says:
  - the route covers Zigbee2MQTT lights only, as a light write's failure is low harm and Z2M's usage is the evidence
    (ZHA's is not: Decision 7);
  - the class keys on a ZHC definition whose converters for the action are ZHC's standard ones, with no flag or override
    touching the call, from a committed table naming the ZHC release it was built from;
  - an action DeviceSide builds as a raw command qualifies only where every known failure is visible to the caller;
  - split-offs: a ZHC flag or override takes a model out at the next bump; a Z2M or ZHC issue or PR reporting a device
    failing DeviceSide's call excludes it on the report alone, citing it; a DeviceSide report follows Contrary evidence;
    each at the narrowest identity the report supports;
  - a bump's departure of a model whose features shipped outside Labs in a full release needs a maintainer's review,
    kept with a reason or excluded with a source.
  Plus an *Example* paragraph on the new class. Keep it in the section's terse shape; one fact, one home: the bump's
  mechanics are `internals.md`'s and the release skill's.
- **The release step** (Decision 16):
  - `.claude/skills/release/SKILL.md`, Each RC: a first item, before `/rc-audit`: run `scripts/zhc_table.py --pin
    <latest ZHC release>`, open the bump PR with the proposal as its body, review the departures there, merge.
  - The guard: `scripts/check_audit.py` (already a `cut-release-candidate` step) fails an RC cut from `main` when
    `standard_lights.py`'s pin is the same at the previous RC tag and at the head, unless the audit record holds a
    line `ZHC bump skipped: <reason>`. A `release/vX.Y.Z` branch is exempt. Git reads only: no clone.
  - No bump between an RC and its release: the release skill says so in a line.

## Decisions (step review, 2026-11-25)

Numbered on from the parent plan's 16; made by Jason after the step's plan review.

17. **The class is the integration's: `IntegrationInfo.own_classes`.** A class in no family, beside the default one,
    checked in `core/registry.py`, and said in `docs/design.md`'s Family row. It stays Z2M's to declare and level
    (Decision 7).
18. **Added transcript segments are kept.** The new class's dispatcher tests add one segment each to
    `raise_brightness`, `raise_hue` and `raise_saturation`, the wire call `other`'s segment already has. No existing
    segment changes; the release sign-off covers the added ones.
19. **Split-offs key on the definition model only.** The rules don't read firmware, so the Müller Licht tint report
    excludes its whole definition (404036/45327/45317/45328), on every firmware. Narrow it once the rules read firmware.
20. **Membership is stricter than the survey, kept.** Meta is an allowlist (an unknown flag keeps a definition out),
    and `on_off` counts as standard only on a light with no brightness converter. Both err toward Labs.
21. **The table is shared: the Zigbee catalog.** It moves to `custom_components/deviceside/zigbee/standard_lights.py`
    with the `STANDARD_LIGHT` name, and the generator writes there. Each definition gains its fingerprints (Zigbee
    model and manufacturer) so another Zigbee integration can key on them; only Z2M declares the class today.
    Its owners are the maintainers of every integration that imports it, as `zigbee/reasons.py`'s are of the
    integrations using it: `CLAUDE.md`'s Maintainers, `scripts/owners.py` and CODEOWNERS follow.
    The member count lives in the PR body, not `internals.md` (it changes each bump).
22. **Another integration keys on a Zigbee pair, decided per pair.** The generator emits each (model ID,
    manufacturer) pair as a member only when every definition it can resolve to is a member and none is excluded,
    with `color_hs` only when all of them expose it; a pair touching a non-member or a split-off is out. No ZHC matcher
    is reproduced. A member with no Zigbee strings can't be keyed outside Zigbee2MQTT, and the table says so.
23. **A `LUMI`-reporting Aqara light on the table is a standard light** (audit report 1's M1). The Aqara family's
    rule reads the string `Aqara`, so a `LUMI` light falls past it to the class; the texts saying it stays with other
    brands are reworded, and a snapshot row pins it. The Aqara T2's get_attributes Labs isn't contrary evidence: its
    rig case `keeps_and_reads_hs_while_off` needs hs mode, which the bulb lacks. #614 limits that case to the hue
    class and lifts the family's get_attributes, closing the gap between the two strings.
24. **A standard light's bottom is a raw level 2** (after #613 merged in; Jason, on brightness-floor's recommendation).
    #613 found an unflagged light switches off at a lower to 0.4 %, as the converter sends level 1 with On/Off, and
    every standard light is unflagged. So a lower to the lowest level sends standard lights a raw `moveToLevel` (no
    On/Off) to level 2, through `fade.py`'s `raw_bottom`, with the level a parameter: below a light's MinLevel it
    clamps there and leaves OnOff alone, so it holds any MinLevel lit. Level 2 (0.8 %), not 1, as no standard light has
    been probed at 1. Each class's owner declares its bottom level: Hue and Aqara 1 (their families), `standard_light`
    2 (`zigbee/standard_lights.py`); `fade.py` composes them. A group gets one raw groupcast only when every reached
    light is in a raw class, at the highest level any member declares (Hue + Aqara: 1; with a standard light: 2); any
    `other` member keeps the converter. `set_attributes`' kept-level skip stays Hue's (#613's Decision 7). Said, not
    silent: index.md's Lowest brightness gains "standard lights stop at 0.8 %", pointed to from `### Standard lights`;
    internals.md (`fade`) gives the why and what reopens it (a probe of a standard light holding level 1 on the raw
    call). The raw call keeps lower_brightness Documented under evidence.md's raw-command clause: `moveToLevel` is a
    command every Zigbee 3.0 dimmable light must take, and its known failure, a rejection, reaches the caller. Unit
    tests pin the raw payloads as literals: a standard light alone (2), standard + Hue (2), Hue + Aqara (1), standard
    + `other` (converter). Transcript: added segments only, as Decision 18.

## Steps

One step: one implementer (`opus`: a binding-rule change, public text), then a fresh `plan-reviewer` (`opus`), then
an `/audit-code` of its range, as the step is a binding-rule change. Branch `wt/standard-call-route` off `main`,
its own worktree, its first act `pr-draft docs/plans/2026-11-25-standard-call-route.md`.

Order inside the step, committed as it goes:
1. The generator and the table at ZHC's latest release; `--check`, its tests and the `tests.yml` step.
2. The class, its rule, its levels and refusal entry, the split-offs; the classification snapshot rows (a member, an
   excluded one, a family model that is also a ZHC member, a `turnsOffAtBrightness1` one).
3. `devices.yaml`, `index.md`, `internals.md`, the generated page; regenerate README and the compat page.
4. The evidence.md bullet.
5. The release skill item and the `check_audit.py` guard, with tests.

The implementer must not mark the PR ready, merge, or start another step; it reports its judgment calls and anything
it wasn't sure of. #613 must merge first (`Depends-on`); build on `main` and merge `main` in when it lands.

## Verification

- `.venv/bin/pytest -n auto --transcripts=check`; `scripts/gen_compat.py --check`; `scripts/zhc_table.py --check`.
  No call or reply handling changes, so no existing transcript segment changes; a change there is a finding. The new
  class's tests add segments (Decision 18).
- A scope test: with the Labs option off, a member light is Documented on the nine actions; an `other` light is still
  refused on them; an `other` switch is still refused; an `EXCLUDED` model and a `turnsOffAtBrightness1` one land in
  `other`; a member on `turn_on_for` is refused with the `NotBuilt` reason.
- A fade test: a member light without `color_hs` answers `unchanged` with `fields_dropped` on a hue move.
- Guard tests: an unchanged pin fails; a changed pin passes; the skip line passes; a fix branch is exempt.
- The README's Zigbee2MQTT card shows "other brands' standard lights" on its own 🟡 line, and other brands' lights
  still in the ⚪ fold.
- No hardware run: the route is Documented on evidence, and step 6's full Z2M run is the release's (tenet 8).

## Handoff

2026-11-25. **Done:** the step, its two plan reviews and three PR audits (report 3 CLEAN, delta). Decisions 17-22 are recorded above. #615 is marked ready and its body holds the summary and the counts. Branch `wt/standard-call-route`, worktree `/Users/jason/projects/ha/deviceside-wt/standard-call-route`.

**Next:**
1. Wait on #613 (`wait-pr 613`). When it merges, merge `origin/main` in (merge, never rebase). It overlaps on `docs/evidence.md`, the Z2M `index.md` and `internals.md`, `fade.py`, and the `raise_brightness` transcript. Then rerun `.venv/bin/pytest -n auto --transcripts=check`, `scripts/gen_compat.py --check` and `scripts/zhc_table.py --check` (regenerate README and the compat page if needed), push, and run `audit-gate status` and the audit it asks for.
2. The merge into `main` is Jason's unless the repo opts in to `merge-green` (check its header).

**Settled since:** audit report 1's M1, as Decision 23: reworded here, with a snapshot row. Overlaps: #614 (the
same Aqara `index.md` paragraph and `families/aqara/__init__.py`; whichever merges second resolves) and #611
(`core/registry.py`, `core/scope.py`).
