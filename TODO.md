# TODO: road to v0.1.0

What is left before v0.1.0. The design is in [`docs/design.md`](docs/design.md). Tick items off in the PR that
finishes them. The v0.1.0 release PR deletes "To go"; "After v0.1.0" stays until its items are done or filed
as issues.

## Releases

`v0.0.1` is out, and HACS accepted the submission ([hacs/default#12611](https://github.com/hacs/default/pull/12611))
on 4 Nov 2026. v0.1.0 is next: everything lands on `main`, and release candidates are cut from it. It ships under the
[evidence rules](docs/evidence.md): one sign-off per integration changed since v0.0.1. The
[evidence-rules plan](docs/plans/2026-11-12-evidence-rules.md) lifted the freeze at `075895f`; with its step 5
landed, the old gates are gone and RCs can be cut again. The items below run in this order.

## To go

- [x] **RC audit**: `/rc-audit v0.1.0rc1` over `a518efe..a43bc1e`, in the four passes its record lists (rc1 was never
  tagged), fixes landed (#316). A second pass before the RC covers what lands after it.
- [x] **Docs sign-off** by the repo maintainers, before the freeze, as it may change the design: README,
  `CONTRIBUTING.md`, `docs/device-compatibility.md` and its "Help us test", `docs/integrations.md`, `docs/design.md`,
  `docs/action-behavior.md`; the GitHub issue flows end to end (`.github/ISSUE_TEMPLATE/`, and the options flow's
  "Report a device" step as a user meets it in HA); the forum draft (#319–#322). Each design change it raised landed
  before the freeze.
- [x] **Z2M `turn_on_for` late off**: `bulb_transition_then_off[light_dimmable]` was a step-file timing bug (the off
  window closed before DeviceSide's end read), not the bulb or DeviceSide; fixed in ha-rig #47.
- [x] **Freeze** at `075895f`; lifted by the evidence-rules plan.
- [x] **Evidence rules**, one PR per step of the [plan](docs/plans/2026-11-12-evidence-rules.md):
  - [x] 1. Rules, docs only (`docs/evidence.md`).
  - [x] 2. Runtime: two levels, the `experimental` gate, `caveat`; the seven release-flagged adapters lose the flag;
    the code comments citing CLAUDE.md's "Release flag" or "Default to Documented" point to `docs/evidence.md`.
  - [x] 3. Rig (ha-rig): drop the wire and scope taps, `Covers`, observed lending and the firmware-fact ledger.
  - [x] 3b. Step files move to DeviceSide (`tests/rig/steps/`, `tests/integrations/<x>/rig/`), the rig reading them
    from the checkout under test.
  - [x] 4. Release gate: `check_release.py --signoffs`; drop `--release` and the rest of `--records`; the
    docstring's CLAUDE.md citations and CLAUDE.md's Layout line on release checks.
  - [x] 5. Cards: `gen_compat.py` tiers for two levels, the flag and caveats, and the docstring's CLAUDE.md citations.
  - [x] 6. Sign-offs by the Package tree records cite, not commit ancestry, so a run on a PR branch counts (#408).
- [x] **Device classes**, by the [plan](docs/plans/2026-11-14-device-classes.md), in five PRs (its Decision 90),
  before the sign-offs below, as it moves non-Hue bulbs on Zigbee2MQTT, ZHA and Hue behind `experimental`. A step is
  ticked when its PR merges; no step waits on a rig run, and each integration runs once, as its sign-off below (plan
  Decision 89; `docs/evidence.md`, tenet 8):
  - [x] 1. Rules and design, docs only (`docs/evidence.md`, `docs/design.md`).
  - [x] 2. Rig (ha-rig): the records' Capability column (its format in `docs/evidence.md`, and `gen_compat`'s parser
    taking it, land in DeviceSide alongside); the rig reads the class from each result (the second rig change, given
    to Jason directly), before any rig run on step 4's branch or later. The Shelly rerun on it is its sign-off below.
  - [x] 3. Lab probe: registry strings, the TS011F, the Sengled
    ([results](docs/integrations/zigbee2mqtt/research/2026-11-14-lab-probe.md)).
  - [x] 4. Core: `IntegrationInfo.capability` and `classes`, `no_known_method`, `not_built` (and
    `docs/integrations.md`'s mention); Shelly moves to it; `gen_compat`'s tiers and coverage check (warning), failing
    in `check_release --signoffs`; `_manual.md`'s Capabilities column; "one fact, one home, in code" in
    `docs/evidence.md`, with CLAUDE.md's devices.yaml row; the Not built yet tier on
    `docs/device-compatibility.md`; how a group test or a manual row credits the classes it lists; the Capability
    column's "until that lands" clause; the class in each result (plan Decision 6); `other` never Verified
    (Decision 5).
  - [x] 5. Zigbee2MQTT classes, after the TS011F probe and the Tuya detection probe; the first default class, so
    `docs/device-compatibility.md` regains "and so does a device DeviceSide can't place in a known class".
    Built on `claude/device-classes-5-z2m` (classes `hue`, `tuya_zcl`, `tuya_ts011f`, `tuya_mcu`, `sengled`,
    `gledopto`, `other`; the Tuya classes not built yet on `turn_on_for`, with `harms`, which refuses unknown
    (step 6); `other` Documented on brightness fades and stop). Parts 1 and 2 landed with #431, and part 3, the
    TS011F countdown (plan Decision 72), with #441. The Zigbee2MQTT sign-off run restores the card's Works line and
    clears the coverage warnings; part 3's plugs, one per maker string, join it.
  - [x] 5b. Test records as JSON, format 2 (`docs/test-records.schema.json`): a device per test with its class,
    validated in CI; the markdown records converted to format 1, which `check_release --signoffs` rejects; the
    rig's paired change writes format 2.
  - [x] 6. Core fix-ups. The harm rule in core
    (`NoKnownMethod.harms`, `Unplaced`), and a group with a member not yet placed falling back to its members; v0.1.0's
    scope (plan Decisions 70 to 76): the two labels redefined, `NotBuilt.harms`, and the Z2M Tuya classes re-sorted
    as not built yet.
  - [x] 7. ZHA classes (#439).
  - [x] 7a. Units groundwork (plan Decision 69): the report form's Zigbee manufacturer string, ZHA's OnTime
    read-back in `turn_on_for`'s DEBUG line, and the mined converter seed list
    ([research](docs/integrations/zigbee2mqtt/research/2026-11-15-converter-seed-list.md), Decision 78).
  - [x] 8. Hue classes, the `smart_scene` check moved to them, and the v1 bridge refused as a separate integration
    (plan Decision 32) (#432).
  - [x] 9. Matter classes (#436).
  - [x] 10. Close out: `models.yaml`'s shared entries removed (step 7 moves ZHA's TS011F, its last, into ZHA's code),
    README regenerated. No #350 comment: Control4 ships Experimental (plan, step 10).
- [x] **TS011F refusal on ZHA and Z2M** (device-classes plan, Decisions 16 and 70): a not built yet entry with
  `harms` for today's `turn_on_for` call, holding with Experimental on. Without it, ZHA's 0x42 in tenths switches a `_TZ3000_typdpbpg`
  plug on about 10× later than asked, and Z2M leaves the plug on with no timer
  ([probe](docs/integrations/zigbee2mqtt/research/2026-11-14-lab-probe.md)). Z2M in step 5 (#441), ZHA in step 7 (#439,
  not built yet with `harms`, plan Decision 74); blocks v0.1.0 even if step 7 slips.
- [x] **Z2M direct target on a multi-light device** (#429): named by itself, a device's second light (a two-gang's
  `light.<gang_2>`) got its call on the device topic, which Z2M applies to the device's default endpoint, gang 1.
  Every light or switch of a device with several in its domain is now refused as `not_addressable`
  ([internals](docs/integrations/zigbee2mqtt/internals.md#addressing)). Future work: address each
  endpoint, by its topic with the endpoint names Z2M 2.6.0+ publishes, and read its suffixed state keys back.
- [x] **A group's stand-in member gets no entry** (#440's re-review): a Zigbee2MQTT light group holding a plug Z2M
  shows as a switch (its stand-in, classed by its device) falls back for the plug's class, and the fallback plans only
  available members, so the plug gets neither the call nor a skip: `turn_on_for` on the group turns its lights on for
  the time asked and leaves the plug as it was, with no warning saying so. The fix is in core's fallback (`_fallback`),
  so every integration's stand-ins: skip one with its class's refusal, or `not_addressable`, as an unaddressable
  member is. Fixed: the plug is skipped, named as a member device of the group, and a group with no other runnable
  member raises the plug's reason.
- [x] **Z2M saturation fade** (#443, #411): MoveToSaturation, as ZHA's #442, so a stop of a saturation fade doesn't
  jump. Before the Zigbee2MQTT runs, which watch it (`saturation_down_stop`) and would reopen if it landed after.
- [x] **Family seam**, by its plan (`docs/plans/2026-11-16-family-seam.md`, landing with it): vendor families inside
  Zigbee2MQTT and ZHA, each with its own maintainers, and the rename of the two not-supported kinds. Before the runs,
  as it reshapes both Zigbee packages. The rename touches Hue's `classes.py` and `set_scene.py`, so its PR carries a
  Hue `no_call_changed` row (no `actions`) rather than a Hue rerun.
- [x] **Require `pytest-without-family-tests`**: in the ruleset's required checks (`docs/repo-maintainers.md`), so a
  family's test code can't silence the integration's on a `/merge`.
- [x] **Shared Zigbee fade planning**, after the family seam, which moves both files (pre-run audit, Medium): ZHA's
  ramp and Zigbee2MQTT's fade duplicate `MIN_STEP`, `SETTLE_SECONDS`, the starts/movers/at-limit prelude and the
  hue-rate clamp, and have drifted (Z2M doesn't cap a transition at the ZCL uint16). Lift the planning into
  `core/zcl_fade.py`, not `core/transition.py` (the cache Hue and Shelly use too). Before the runs, as it changes
  both packages' fades. `SETTLE_SECONDS` stays per integration (declined): each 2.0 s cites its own integration's
  measurement.
- [ ] **Integration lifecycle hooks**, after the family seam (pre-run audit, Medium): the component root starts
  Zigbee2MQTT's bridge cache, color modes and restore journal itself, so every integration with a lifecycle edits a
  repo-maintainer file. Add `IntegrationInfo` setup and teardown hooks. Before the runs.
- [x] **Pre-run audit**: `/rc-audit` over `b025363..HEAD`, its record replacing `docs/audits/v0.1.0rc1.md`, and its
  fixes landed, so no run repeats for a fix the audit would have found. The RC's second pass covers what lands after.
- [ ] **Sign-offs** for v0.1.0, one per integration changed since v0.0.1 (`check_release.py --signoffs`), each a rig run
  from ha-rig `main` (its records are format 2; format 1 records, converted from markdown, count for none). The runs for
  the formerly release-flagged adapters need these `--profile lab` cases, run watched, the A60 visiting each network:
  Hue `saturation_down_stop`, `halts_brightness_and_saturation` and `sets_color_while_off`; ZHA `hue_cycle_stop`,
  `saturation_down_stop` and `sets_color_while_off`; Z2M `halts_a_lower_to_off`, `hue_cycle_stop`,
  `saturation_down_stop` and `sets_color_while_off`. Unattended alongside: Z2M `lower_hue`
  `cycles_down_the_wheel[group_color]` (#222). In this order; a fix a run finds reruns only the suites it reopens
  (`--reruns`):
  - [x] Hue: the lab run at `bc27094`, landed with #432.
  - [ ] ZHA
  - [ ] Zigbee2MQTT, run A: every suite but `turn_on_for`, `get_attributes` and `config_entry`, with the watched A60 cases.
    A record is one run of one suite, so the split falls between suites. Needs ha-rig to run a chosen set of suites.
  - [ ] Matter
  - [ ] Shelly. Accepted until then: `check_release --signoffs` fails on Shelly's class coverage gaps, as its
    records are format 1, with no class per test; no release is cut before its house rerun.
  - [ ] Zigbee2MQTT, run B: `turn_on_for` and `get_attributes` (the bulb, and part 3's plugs, one per maker string),
    and `config_entry`, which any package change reopens. No Zigbee2MQTT change between runs A and B.
  - [ ] Control4: skialpine's `_manual.json` row, asked for once the runs' fixes have landed, so no fix sends
    the contributor back to a first submission; it cites a `main` commit holding the release's Control4 package.
- [x] **Partial reruns** (`docs/evidence.md`, tenet 9): `check_release.py --signoffs` judges each record by its own
  package tree, which stands while only other adapters' modules changed since; a `no_call_changed` row may name the
  `actions` whose records it carries across its commit's change; `--reruns` lists the suites to rerun. Open, in
  ha-rig: its run selection reads `--json`, the integrations; reading `--reruns` instead lets it rerun only the
  reopened suites.
- [ ] **Release notes**: hand-written v0.1.0 notes in `notes/`, signed off by the repo maintainers, after the RC
  installs cleanly and before `cut-release`, so they describe what the RC ships.
- [ ] **v0.1.0**: the `/rc-audit` second pass over what landed after the pre-run audit, the RC and its HACS install,
  then `cut-release` with every integration signed off (`check_release.py --signoffs`). The release steps are in the
  `release` skill; the release body gets the signed-off notes.
  After the release, remove CLAUDE.md's "Until v0.1.0 ships, fix the architecture now" paragraph.
- [x] **Raise/lower rig run**: the six actions and `stop` on Hue and Z2M, rerun in the lab reruns (#297, #299).
- [x] **Lab rerun**: the first lab run's failures fixed (#160–#163, #172) and rerun (#297, #299); the Z2M failures
  it found fixed by #302.
- [x] **Persistent auto-off/auto-on** (PR #305): `set_`/`clear_auto_off`/`_on`, Shelly; records clear the flag.
- [x] **Shelly `set_attributes`** (#284, PR #287): RGBCCT, with `min_brightness`/`max_brightness`; the record clears
  the flag.
- [x] **Shelly smooth dimming** (PR #289): `raise_brightness`, `lower_brightness` and `stop` on Shelly lights,
  brightness only: each move one `<Component>.Set` with `transition_duration`, halted by `DimStop` (the
  `DimUp`/`DimDown` ramps are stepped and have no `sweep_time` mapping). Findings:
  [`docs/integrations/shelly/research/2026-11-08-dimming.md`](docs/integrations/shelly/research/2026-11-08-dimming.md).
  RGBCCT; the records clear the flag.
- [x] **Device support, part 1** (#262): support levels and contribution lanes in `CONTRIBUTING.md`, the README's "Will
  it work with my device?", and the device report, device request and bug issue forms.
- [x] **Device support, part 2**: `scripts/gen_compat.py` generates `docs/compatibility.md` (levels and tested
  models per action and integration) and CI checks it is current. The README table, its "Will it work with my
  device?", `CONTRIBUTING.md` and the bug and device report forms link to it instead of `docs/test-records/`.
- [x] **Device support, part 3**: a "Report a device" step in DeviceSide's options that opens a prefilled device
  report.
- [x] **Documented support level** (#267): a `Level` per scope item; Shelly Light, CCT, RGB and RGBW components and
  Matter lights ship Documented, and Matter confirms a timer only with OnOff on.
- [x] **Experimental features option and Reported level** (#307): Experimental scope items ship in stable releases,
  refused until the option is on; Zigbee switches for `turn_on_for` and `get_attributes`, and Shelly Light, CCT, RGB
  and RGBW dimming, are Experimental.
- [x] **Device compatibility cards** (#309): a generated card per integration in the README, from the records, scopes
  and `docs/devices.yaml`, backed by `docs/device-compatibility.md`, which replaces `docs/compatibility.md` and
  `docs/hardware-the-rig-lacks.md`.
- [x] **Single report form** (#313): one device report form for results and bugs, several devices per report; the
  Support field and the options flow's action step are gone.
- [x] **Maintainers per integration** (#359): `IntegrationInfo.maintainers` on the cards, `.github/CODEOWNERS` and
  issue routing; `Support` retired; ⚠️ Unmaintained.
- [x] **Docs bundles** (#362): each integration's user page, internals, device data, research and test records in
  `docs/integrations/<integration>/`, which its maintainers own; shared pages keep what spans integrations, and
  `docs/models.yaml` the models.
- [x] **Code-owner enforcement** (#370): outside maintainers hold Triage, and CODEOWNERS keeps naming them; review
  requests go out by hand until that becomes a bottleneck.
- [x] **Fast track** (#370): a contributor who builds and tests on their own hardware opens a PR directly, with no issue
  (CONTRIBUTING, PR template); an Experimental item moves to Reported, on its maintainer's request, after five working
  reports from other users.
- [x] **Retests and Stale tests** (#374): every changed adapter is retested before release (a rig record, a maintainer's
  `_manual.json` row or an accepted report at a release); one left untested at the cut ships live, marked ⚠️ Stale
  tests, with a call for testers in the release notes.
- [x] **Shared code proof** (#377): superseded by the evidence rules, under which `core/` changes need no device
  sign-off.

## After v0.1.0

- [ ] **Per-family test records and docs**: a family's maintainers own its code, unit tests and new research, while the
  test records, `index.md`, `internals.md` and `devices.yaml` stay whole and the integration's
  ([CLAUDE.md](CLAUDE.md#maintainers)). Split them by family once a family maintainer signs off their own classes:
  the record layout and `docs/test-records.schema.json`, `check_release.py --signoffs` and `gen_compat.py` reading
  them, and the paths added to `FAMILY_PATHS` (`scripts/gen_codeowners.py`).
- [ ] **Family seam audit, tracked** (#447's audit findings, fixes backed out under the audit-fix rule; each fix only
  with evidence its failure happens):
  - Medium: the gate treats a catalog file new on a PR as its family's, so one stack's maintainer can open a catalog
    module alone. Fix shape: `package_of` returns None for a catalog path absent on the base branch.
  - Medium: Zigbee2MQTT's classification snapshot has no row on each side of the countdown / `tuya_ts011f` edge (a
    ZOT60 and a per-gang TS011F), so a Tuya family edit that moves one into `tuya_countdown` lifts a harm refusal
    with only family tests to catch it. Fix shape: two `DEVICES` rows.
  - Low: CLAUDE.md doesn't list a new class or family among what a family maintainer can't merge alone (the gate
    already refuses both). Fix shape: name them in the Maintainers paragraph.
- [x] **Code comments cite the bundles** (pre-run audit): each comment that cited `docs/integration-internals.md` or
  `docs/integrations.md` points at its bundle, and `tests/scripts/test_doc_anchors.py` checks page-only citations too.

- [ ] **Forum announcement**, once v0.1.0 ships: refresh the draft's testers-wanted list from [Try it: Experimental
  features](docs/device-compatibility.md#try-it-experimental-features) and check every link resolves (the issue forms,
  `docs/device-compatibility.md`), then post it. After posting, point the "Getting involved" testers link at the
  heading's anchor, which Discourse names after the post id.
- [ ] **Forum thread links**: add the thread URL as the contact link in `.github/ISSUE_TEMPLATE/config.yml` and set
  `blank_issues_enabled: false` there, and link the thread from `CONTRIBUTING.md` and the README's Contributing
  section.
- [ ] **Shelly RGB and RGBW color**: port core's conversions (`light/helper.py` rgb to rgbw with the white split,
  kelvin to color) so RGB and RGBW take color instead of dropping it (`get_attributes` already reads their color).
- **9b** Maintained adapters: the rig kit, so maintainers can commit records for hardware the rig lacks
  (`docs/design.md`, Release gates). Until then, they sign off by hand (`docs/evidence.md`).
