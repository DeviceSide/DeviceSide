# TODO: road to v0.1.0

What is left before v0.1.0. The design is in [`docs/design.md`](docs/design.md). Tick items off in the PR that
finishes them. The v0.1.0 release PR deletes "To go"; "After v0.1.0" stays until its items are done or filed
as issues.

## Releases

`v0.0.1` is out, and HACS accepted the submission ([hacs/default#12611](https://github.com/hacs/default/pull/12611))
on 4 Nov 2026. v0.1.0 is next: everything lands on `main`, and release candidates are cut from it. v0.1.0 ships every
adapter passing its tests, no soak. An RC also needs a rig run since each released adapter's last code change
(`check_release.py --records`).

**Order.** Adapter code freezes before the final rig runs: a change under `integrations/` or `core/` stales the records
of the adapters that reach it (#358), and `actions/` changes behavior without tripping the check. From the freeze until
the RC tag, only flag-only, docs, `scripts/` and rig step-file changes land. The items below run in this order.

## To go

- [x] **RC audit**: `/rc-audit v0.1.0rc1` over `967bec0..HEAD` (rc1 was never tagged), fixes landed (#316). A second
  pass before the RC covers what lands after it.
- [x] **Docs sign-off** by the repo maintainers, before the freeze, as it may change the design: README, `CONTRIBUTING.md`,
  `docs/device-compatibility.md` and its "Help us test", `docs/integrations.md`, `docs/design.md`,
  `docs/action-behavior.md`; the GitHub issue flows end to end (`.github/ISSUE_TEMPLATE/`, and the options flow's
  "Report a device" step as a user meets it in HA); the forum draft (#319–#322). Each design change it raised
  landed before the freeze.
- [x] **Z2M `turn_on_for` late off**: `bulb_transition_then_off[light_dimmable]` was a step-file timing bug (the off
  window closed before DeviceSide's end read), not the bulb or DeviceSide; fixed in ha-rig #47.
- [x] **Freeze** at `075895f`, then the rig runs below. Rig runs come from ha-rig `main`.
- [ ] **Stale records rerun**: every record `check_release.py --records` names (36 at the freeze: the wire trace,
  #329, touched each transport). Every profile: Shelly (with a watched `set_attributes` `sets_color_while_off`),
  Matter, Hue, ZHA and Z2M, and the house run for the Z2M group cases deferred from #330.
- [ ] **Watched lab session**, `--profile lab`, the A60 visiting each network: Hue `saturation_down_stop`,
  `halts_brightness_and_saturation`, `sets_color_while_off`; ZHA `hue_cycle_stop`, `saturation_down_stop`,
  `sets_color_while_off`; Z2M `halts_a_lower_to_off`, `hue_cycle_stop`, `saturation_down_stop`,
  `sets_color_while_off`. Unattended alongside: Z2M `lower_hue` `cycles_down_the_wheel[group_color]` (failed twice,
  #222). Then the PR clearing the last flags: every `set_attributes` and `stop`, and Z2M `lower_hue`.
- [ ] **9d** Final sweep, after the runs above: `rig.py --coverage` full, and `check_release.py --records` clean on
  committed code.
- [ ] **Release notes**: hand-written v0.1.0 notes in `notes/`, signed off by the repo maintainers, after the RC installs cleanly
  and before `cut-release`, so they describe what the RC ships.
- [ ] **12** v0.1.0: no adapter left `experimental` (`scripts/check_release.py --release`). The release
  steps are in `CLAUDE.md` (Releasing); the release body gets the signed-off notes.
- [x] **Raise/lower rig run**: the six actions and `stop` on Hue and Z2M, rerun in the lab reruns (#297, #299).
- [x] **Lab rerun**: the first lab run's failures fixed (#160–#163, #172) and rerun (#297, #299); the Z2M failures
  it found fixed by #302.
- [x] **Persistent auto-off/auto-on** (PR #305): `set_`/`clear_auto_off`/`_on`, Shelly; records clear the flag.
- [x] **Shelly `set_attributes`** (#284, PR #287): RGBCCT, with `min_brightness`/`max_brightness`; the record clears
  the flag.
- [x] **Shelly smooth dimming** (PR #289): `raise_brightness`, `lower_brightness` and `stop` on Shelly lights,
  brightness only: each move one `<Component>.Set` with `transition_duration`, halted by `DimStop` (the `DimUp`/`DimDown` ramps
  are stepped and have no `sweep_time` mapping). Findings: [`docs/shelly-dimming-research.md`](docs/shelly-dimming-research.md).
  RGBCCT; the records clear the flag.
- [x] **Device support, part 1** (#262): support levels and contribution lanes in `CONTRIBUTING.md`, the README's "Will it
  work with my device?", and the device report, device request and bug issue forms.
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
- [x] **Single report form** (#313): one device report form for results and bugs, several devices per report; the Support
  field and the options flow's action step are gone.
- [x] **Maintainers per integration** (#359): `IntegrationInfo.maintainers` on the cards, `.github/CODEOWNERS` and
  issue routing; `Support` retired; ⚠️ Unmaintained.
- [x] **Docs bundles** (#362): each integration's user page, internals, device data, research and test records in
  `docs/integrations/<integration>/`, which its maintainers own; shared pages keep what spans integrations, and
  `docs/models.yaml` the models.
- [x] **Code-owner enforcement** (#370): outside maintainers hold Triage, repo maintainers merge, and CODEOWNERS keeps naming
  them; review requests go out by hand until that becomes a bottleneck.
- [x] **Fast track** (#370): a contributor who builds and tests on their own hardware opens a PR directly, with no
  issue (CONTRIBUTING, PR template); an Experimental item moves to Reported, on its maintainer's request, after five working reports from other users.
- [x] **Retests and Stale tests** (#374): every changed adapter is retested before release (a rig record, a maintainer's
  `_manual.md` line or an accepted report at a release); one left untested at the cut ships live, marked ⚠️ Stale tests,
  with a call for testers in the release notes.
- [ ] **Shared code proof** (#377): a passing Verified record whose run covered a `core/` change proves it for every
  adapter, so a core change needs one rig run, not a retest per integration. Ticks once the rig writes the records'
  `## Shared coverage` table (tracked in the rig repo).
  - [ ] **Attended `--shared-coverage` run**, once the rig's coverage helper is deployed and loaded in HA: one small
    suite. The staged record has the section, it lists lines of a coroutine already running before coverage started
    (if it doesn't, the rig's docs name the gap), and `check_release.py --records` accepts it. This item's tick lands
    with that record.

## After v0.1.0

- [ ] **Code comments cite the bundles**: eight comments under `integrations/` (hue, matter, zha, zigbee2mqtt) still
  cite `docs/integration-internals.md` or `docs/integrations.md`; point each at its bundle's
  `internals.md#tested-behavior` (Z2M `addressing.py`: `index.md#sharp-edges`), which `tests/scripts/test_doc_anchors.py`
  then checks; widen that test to page-only citations (`docs/….md` with no anchor) too. Held back by the freeze: a
  comment change stales the records of the code it is in.

- [ ] **Forum announcement**, once v0.1.0 ships: refresh the draft's testers-wanted list from
  [Help us test](docs/device-compatibility.md#help-us-test) and check every link resolves (the issue forms,
  `docs/device-compatibility.md`), then post it. After posting, point the "Getting involved" testers link at the heading's
  anchor, which Discourse names after the post id.
- [ ] **Forum thread links**: add the thread URL as the contact link in `.github/ISSUE_TEMPLATE/config.yml` and set
  `blank_issues_enabled: false` there, and link the thread from `CONTRIBUTING.md` and the README's Contributing
  section.
- [ ] **Shelly RGB and RGBW color**: port core's conversions (`light/helper.py` rgb to rgbw with the white split,
  kelvin to color) so RGB and RGBW take color instead of dropping it, and give `status_row` a branch per component
  so `get_attributes` reads Light, CCT, RGB and RGBW light state.
- **9b** Maintained adapters: the rig kit, so maintainers can commit records for hardware the rig lacks
  (`docs/design.md`, Release gates). Until then, such work ships as Experimental items and earns Reported from user
  reports.
