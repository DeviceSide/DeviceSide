# TODO: road to v0.1.0

What is left before v0.1.0. The design is in [`docs/design.md`](docs/design.md). Tick items off in the PR that
finishes them. The v0.1.0 release PR deletes "To go"; "After v0.1.0" stays until its items are done or filed
as issues.

## Releases

`v0.0.1` is out, and HACS accepted the submission ([hacs/default#12611](https://github.com/hacs/default/pull/12611))
on 4 Nov 2026. v0.1.0 is next: everything lands on `main`, and release candidates are cut from it. v0.1.0 ships every
adapter passing its tests, no soak. An RC also needs a rig run since each released adapter's last code change
(`check_release.py --records`): today every released adapter's records predate its code.

## To go

- [ ] **Raise/lower rig run**: unattended, the six actions and `stop` on Hue and Z2M. It rewrites the `stop*.md`
  records and measures the new hue, saturation and two-call stop ranges for the first time.
- [ ] **Lab rerun**: the first lab run's failures are fixed (#160–#163, #172); the rerun also retries Z2M
  `not_stored` with `hue_native_control` on and the single readings, then fixes what repeats.
- [ ] **Watched lab session**, `--profile lab`, the A60 visiting each network: Hue `saturation_down_stop`,
  `halts_brightness_and_saturation`, `sets_color_while_off`; ZHA `hue_cycle_stop`, `saturation_down_stop`,
  `sets_color_while_off`; Z2M `halts_a_lower_to_off`, `hue_cycle_stop`, `saturation_down_stop`,
  `sets_color_while_off`. Unattended alongside: Z2M `lower_hue` `cycles_down_the_wheel[group_color]` (failed twice,
  #222) and ZHA `lower_brightness`. Then the PR clearing the last flags: every `set_attributes` and `stop`, Z2M
  `lower_hue` and ZHA `lower_brightness`.
- [ ] **Persistent auto-off/auto-on**: `set_`/`clear_auto_off`/`_on`, Shelly; records clear the flag.
- [ ] **9d** Rig coverage sweep for the non-color scope; the watched session covers the color part.
- [x] **Device support, part 1** (#262): support levels and contribution lanes in `CONTRIBUTING.md`, the README's "Will it
  work with my device?", and the device report, device request and bug issue forms.
- [x] **Device support, part 2**: `scripts/gen_compat.py` generates `docs/compatibility.md` (levels and tested
  models per action and integration) and CI checks it is current. The README table, its "Will it work with my
  device?", `CONTRIBUTING.md` and the bug and device report forms link to it instead of `docs/test-records/`.
- [x] **Device support, part 3**: a "Report a device" step in DeviceSide's options that opens a prefilled device
  report.
- [x] **Documented support level** (#267): a `Level` per scope item; Shelly Light, CCT, RGB and RGBW components and
  Matter lights ship Documented, and Matter confirms a timer only with OnOff on.
- [ ] **12** v0.1.0: no adapter left `experimental` (`scripts/check_release.py --release`); README feature table
  current. The release steps are in `CLAUDE.md` (Releasing).

## After v0.1.0

- [ ] **Forum announcement**, once v0.1.0 ships: refresh the draft's testers-wanted list from
  [the list](docs/hardware-the-rig-lacks.md) and check every link resolves (the issue forms,
  `docs/compatibility.md`), then post it. After posting, point the "Getting involved" testers link at the heading's
  anchor, which Discourse names after the post id.
- [ ] **Forum thread links**: add the thread URL as the contact link in `.github/ISSUE_TEMPLATE/config.yml` and set
  `blank_issues_enabled: false` there, and link the thread from `CONTRIBUTING.md` and the README's Contributing
  section.
- [ ] **Shelly RGB and RGBW color**: port core's conversions (`light/helper.py` rgb to rgbw with the white split,
  kelvin to color) so RGB and RGBW take color instead of dropping it, and give `status_row` a branch per component
  so `get_attributes` reads Light, CCT, RGB and RGBW light state.
- **9b** Remote tester flow, once an adapter needs hardware the rig lacks
  ([the list](docs/hardware-the-rig-lacks.md)). It includes the Community support level's code, waiting for the
  first contributor: a maintainer per adapter, reading a record's source, checking the record came from an RC
  installed through HACS, and the public test checklist. A stale Community record could drop its item to
  Documented, when the Documented conditions hold, instead of blocking the release.
