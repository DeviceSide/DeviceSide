# TODO: road to v0.1.0

What is left before v0.1.0. The design is in [`docs/design.md`](docs/design.md). Tick items off in the PR that
finishes them. The v0.1.0 release PR deletes "To go"; "After v0.1.0" stays until its items are done or filed
as issues.

## Releases

`v0.0.1` is out, and HACS accepted the submission ([hacs/default#12611](https://github.com/hacs/default/pull/12611))
on 4 Nov 2026. v0.1.0 is next: everything lands on `main`, and release candidates are cut from it. v0.1.0 ships every
adapter passing its tests, no soak. An RC also needs a rig run since each released adapter's last code change
(`check_release.py --records`).

**Order.** Adapter code freezes before the final rig runs: a change under `integrations/` stales the records it
touches, and `core/` and `actions/` change behavior without tripping the check. From the freeze until the RC tag, only
flag-only, docs, `scripts/` and rig step-file changes land. The items below run in this order.

## To go

- [x] **RC audit**: `/rc-audit v0.1.0rc1` over `967bec0..HEAD` (rc1 was never tagged), fixes landed (#316). A second
  pass before the RC covers what lands after it.
- [x] **Docs sign-off** by Jason, before the freeze, as it may change the design: README, `CONTRIBUTING.md`,
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
- [ ] **#314**: link each rig-verified model on the device cards to its records. Any time before the RC: it touches
  `scripts/gen_compat.py` only.
- [ ] **Release notes**: hand-written v0.1.0 notes in `notes/`, signed off by Jason, after the RC installs cleanly
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

## After v0.1.0

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
- **9b** Community-maintained adapters, once a contributor offers one for hardware the rig lacks: a maintainer per
  adapter and a route to stable other than the rig, left open in `docs/design.md` (Release gates). Until then, such
  work ships as Experimental items and earns Reported from user reports.
