# predicted_state default review (slice 12)

Repo plan row 12: review the `predicted_state` default against the regression issues and rig runs since #77, and
flip it to off if flaky.

**Decision (Jason, 4 Nov): keep it on**, as recommended. In the five lab runs kept since 31 Oct, 61 rig cases ran with it on and one failed: a real bug in
the start shown for a raise from off, fixed in #163 and green in all four runs since. No issue reports a fault in it.
Off brings back the slider jumping straight to a fade's end, which is the problem #77 set out to fix.

## What it gates

Hue only (`const.PREDICTED_STATE_DEFAULT = True`; ZHA and Z2M never read it). With it on, `hue/report_filter.py`
hides the bridge's reports of our own fades from aiohue and sends HA device_side's predictions: the start while a fade
runs, the halt at a stop, the end once it has run. With it off, the filter still tells our reports from others' (to
end predictions) but hides nothing, so HA shows the end value as soon as a fade starts.

Scopes that take it: Hue `raise_brightness`, `lower_brightness`, `stop`. It was dropped from the saturation scopes
(PR #204), where it has no effect.

Costs of on, already in `docs/integrations.md`:

- A brightness change or turn on from the Hue app or a dimmer within 15 s of a fade isn't shown until the
  prediction ends.
- Hiding relies on aiohue applying events in a task (`_handle_event` being a coroutine, a private detail). If a
  future aiohue applies them at once, `applies_later` turns hiding off with a warning, so the failure mode is the
  off behavior, not wrong state.

## Issues

- No `regression` label exists, and no issue carries the `bug` label for this.
- #92 (closed): an enhancement asking for the same predictions for color temperature. Not a fault.
- #83 (closed): rig bridge step, which led to `bridge_scene_recall_mid_fade_shows_at_once`. Not a fault.
- No tester reports (`test-report` label) exist yet.

## Rig runs

Run reports kept since 31 Oct (the rig's temp report directory), Hue `-predicted_state` suites, lab profile:

| Run | Suites | Cases | Failed |
|---|---|---|---|
| 2 Nov 15:19 | all three, before #163 | 13 | 1: `up_from_off_shows_the_dimmest[group]`, the White showed 13 |
| 3 Nov 10:44 | all three | 13 | 0 |
| 3 Nov 13:59 | all three | 13 | 0 |
| 3 Nov 20:36 | `raise_brightness`, `stop` | 11 | 0 |
| 3 Nov 21:21 | `raise_brightness`, `stop` | 11 | 0 |

The one failure was device_side's bug, not flakiness: a raise from off showed the light's `min_dim_level` (light
output, 5 % on a White) as its brightness. #163 shows the lowest step instead.

Before 31 Oct, the reports are gone; the test records hold the passes (`move-predicted_state.md` and
`stop-predicted_state.md` on 28 Oct at `33932a6`, all cases). The current records (`docs/test-records/hue/*-predicted_state.md`)
pass every case, on HA 2026.10.2 with an ambiance bulb and a zone.

Next to it, one single reading: Hue `lower_to_off[light_ct, group]` failed once on 2 Nov, the first case after the
`predicted_state` suite, with the bulb still off 2 s after `set`. The lab-failures plan (bucket E) puts it on the rig's
options reload, not the adapter; it didn't repeat.

ZHA and Z2M: not applicable. Neither has the option, and the rig skips the `-predicted_state` step files for them.

## Gaps

- Only the lab's bulbs (an ambiance lamp, a White, a zone) have run it. No tester has.
- `bridge_scene_recall_mid_fade_shows_at_once[group] observed` has never been watched; the unattended assertion
  passes.
- Hiding rests on aiohue internals, guarded as above. An HA bump should rerun these three suites.
