# TODO: road to v0.1.0

What is left before v0.1.0. The design is in [`docs/design.md`](docs/design.md). Tick items off in the PR that
finishes them. Delete this file in the v0.1.0 release PR.

## Releases

`v0.0.1` is out, and the HACS submission ([hacs/default#12611](https://github.com/hacs/default/pull/12611)) is
waiting for review. Until it is accepted, no release or RC is cut. Everything lands on `release/v0.0.2`, and
v0.1.0 is the next release.

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
- [ ] **9d** Rig coverage sweep for the non-color scope; the watched session covers the color part.
- [ ] **12** v0.1.0: no adapter left `experimental` (`scripts/check_release.py --release`); README feature table
  current; release checklist adapted from hue_dimmer; `predicted_state` default reviewed against the rig runs and
  regression issues since #77.
