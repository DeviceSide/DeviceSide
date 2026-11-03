# Slice 7c: Hue `move` for color temp (7c1) and saturation (7c2)

## Context

7c is the last open slice of the Hue port (`docs/plans/2026-10-25-hue-port.md`, 7c). Hue `move` and `stop` handle
brightness only (`integrations/hue/move.py`, `stop.py`, scope fields `brightness`, `brightness_limit`); the
`move` action already parses `color_temp`, `saturation` and their limits (`actions/move.py`). The echo spike
(Q9 to Q11, `docs/plans/2026-10-26-hue-echo-spike.md`) found color temp behaves like brightness: the end value
is reported at once, stop reports come late or never, interpolation is exact, and zone transitions work.
Still open (repo plan, open item 12): whether separate brightness and color temp writes run independently.

**Save this plan to the repo** as `docs/plans/2026-10-27-hue-move-color.md` in the first commit of 7c1, then
build it in a fresh session (worktree `wt/hue-move-color-temp` off `release/v0.0.2`).

## Decisions (interview 2026-10-27)

- **Two PRs.** 7c1: color temp, combined brightness + color temp moves, and `stop` for both, rig-proven now on
  the ambiance bulbs. 7c2: saturation, once the Hue color bulb is in the inventory as `light_color`.
- **Classify color, don't display it.** The report filter tells our color temp (later xy) echoes and late
  reports from a real change, and a real change forgets the light's predictions. HA is still shown the bridge's
  color reports (the end value at once); `predicted_state` stays brightness and `on`. Showing predicted color
  is a follow-up issue.
- **Off light:** a color move without `brightness: up` on a light that's off is `unchanged`, `detail: off`,
  and nothing is sent. With `brightness: up`, the light turns on and both attributes run.
- **Saturation from white** (7c2): start from the light's current xy, so a color temp white heads toward its
  own tint (warm white → amber). Only a light at the white point itself returns `unchanged`, `detail: no_hue`.
- **Color temp stop** uses the bridge's native `color_temperature_delta: {action: stop}`, through a raw CLIP v2
  PUT (aiohue has no model for it). It goes in the same PUT as `dimming_delta` stop when both run.

## 7c1: color temp

> **Superseded 2026-10-28.** Color temperature moves were dropped on every integration, as every halt of a Hue
> bulb's color temperature fade jumps visibly (`docs/plans/2026-10-28-z2m-move-stop.md`). The code below was
> removed by `docs/plans/2026-10-28-drop-color-temp-move.md`; this section is kept as history.

### Rig first: answer open item 12

Before writing the adapter, a rig probe on `light_ct` and `group` (pre-authorized on 2026-10-27/28, per memory)
sends a brightness write and a color temp write with different durations in two PUTs, then samples the bridge.
Does the second write cancel the first, and does each attribute arrive at its own time? Also check whether one
PUT with both reports one event or two. Record the answer in the repo plan's open item 12 and the Hue port
plan's 7c bullet.

- **Independent:** one write per attribute, each with its own duration.
- **Not independent:** one PUT with the longest duration, `detail: shared_duration` on the result. Each
  attribute's cache transition uses that shared duration.

### Adapter: `integrations/hue/move.py`

- Scope fields gain `color_temp` and `color_temp_limit`. A light without `color_temperature` returns
  `unsupported`, `fields_not_supported`, for a color temp move (as `dimming is None` does today).
- Work in mirek. Target = `colors.mirek(light, color_temp_limit)` (the existing helper) or the range end:
  `warmer` → `mirek_maximum`, `cooler` → `mirek_minimum`. Duration = `sweep_time` × |target − start| /
  (range span). `at_limit` when less than 1 mirek is left to travel (a new `MIN_MIREK_STEP` beside
  `MIN_BRIGHTNESS_STEP`).
- Start = `cache.value(light.id, COLOR_TEMP, light.color_temperature.mirek)` for a light in color temp mode
  (`mirek_valid`). A light in xy mode is out of 7c1: the ambiance rig can't reach it. 7c2 handles it with the
  color bulb, and until then it returns `unsupported`, `detail: not_in_color_temp_mode`.
- **Zone:** one `grouped_light` write. Target = the widest range among the members that have color temp. Each
  member's transition runs from its own start to the target clamped to its own range, over the shared duration.
  The zone's start is the average of its lit members, as for brightness. The rig checks that a member with a
  narrower range still converges over the shared duration; if it doesn't, the plan is revisited before going on.
- Refactor `execute` into a per-attribute plan (start, target, duration per light), so brightness and color temp
  share one code path and 7c2 adds saturation as a third. Keep the brightness behavior byte-for-byte: soft off,
  up turns on, `write_armed` before the write, cache only after accept.
- `end_echo` gains the color temp key: the target mirek when it differs from what the bridge holds.

### `integrations/hue/stop.py`

- Halt every attribute the cache tracks for the light. Add a `stop_deltas(api, controller, rid, attributes)`
  helper in `bridge.py` that sends one raw PUT, `api.request("put", f"clip/v2/resource/{type}/{rid}", json=…)`,
  holding `dimming_delta` stop and/or `color_temperature_delta` stop.
- During our soft off the existing cut (`on: true` + predicted brightness) also carries the color temp delta
  stop for that light.
- Record each attribute's halt with `cache.stopped(...)`.

### Cache, report filter, get_attributes

- `transition_cache.py`: add `COLOR_TEMP = "color_temp"`. Transitions are already keyed by attribute.
- `report_filter.py`: `values()` also reads `color_temperature.mirek` as `color_temp`. `classify` treats it as
  brightness: an armed echo → ECHO, on the path → PATH, otherwise REAL, which forgets the light (the existing
  `forget`). The tolerance is in mirek (1). Color values are never hidden or rewritten: the display branches
  (`predicted_state`) keep touching only `on` and `dimming`. A color temp event on a `grouped_light` follows the
  existing rule: never real while one of its lights is followed.
- `get_attributes.py`: `color_temp_kelvin` reads through the cache (light and zone rows), as brightness does.

### Tests, docs, rig

- `tests/integrations/hue/test_move.py`: warmer and cooler to the range end and to a limit; `at_limit`; the off
  light gives `off`; brightness up plus color temp from off; zone with mixed ranges; a light without color temp;
  xy mode; combined writes per the open item 12 answer. Stop for color temp alone, both, and during a soft off
  (raw PUT body asserted). Plus `test_report_filter.py` (color temp echo, path, real forgets) and
  `test_get_attributes.py` (predicted kelvin). Keep each module at ≥95 % line coverage.
- Rig `tests/rig/steps/move.yaml`/`stop.yaml` (roles `light_ct`, `group`): `warmer`, `cooler_to_a_limit`,
  `warmer_stop_warmer`, `color_temp_at_limit`, `color_temp_on_off_light`, `brighter_and_cooler`, and a stop of a
  combined move. Run with `predicted_state` on and off (both records are needed for the option). The
  fingerprints change, so the brightness steps rerun too. Color temp moves are new on device_side, so brief the
  observed steps first and run them only on Jason's go (memory: watched rig sessions).
- `docs/integrations.md` Hue section (color temp move/stop, open item 12 result); README feature table only if
  it already lists Hue `move` by attribute.
- File the follow-up issue: "Hue predicted_state: show predicted color temp and color during fades", with fix
  shape (extend the display branches in `report_filter.py` to `color_temperature`/`color`) and agent model.

## 7c2: saturation (updated 2026-11-03)

Replaces the 2026-10-27 outline, which predates the six raise/lower actions (#128) and the predicted_state changes
(#163). Branch `wt/hue-saturation` off `release/v0.0.2`; PR into it. Adapters `experimental=True`.

### Decisions (interview 2026-11-03)

- **Saturation is HA's hs saturation, as on Z2M and ZHA.** End xy = `color_hs_to_xy(hue, limit)` at the light's
  current hue (HA's `hs_color`), clamped to the bulb's gamut (`colors.clamp_to_gamut`). Same numbers as
  `hs_color` and the other integrations, so one automation behaves alike everywhere. 100 % is HA's sRGB edge, a
  little inside gamut C. The gamut-fraction scale and `no_hue` are dropped: a color temperature white has an
  `hs_color` too, so it pales or deepens from its own tint, as on ZHA.
- **A room or zone is one `grouped_light` xy write**, as brightness is, so its color lights converge together;
  the bridge clamps each light to its own gamut. The hue is the room's (mean `hs_color` of its lit color lights,
  as Z2M takes the group's). Lights at different hues end at one color. A lit light without color (White,
  ambiance) is passed by.
- **predicted_state: classify only.** `ATTRIBUTES[SATURATION]` owns the `xy` report key with `shows=None`: the
  filter takes xy reports inside the guard window as ours and a report of a key no live transition owns as real,
  but HA is shown the bridge's xy (the end color at once). Showing predicted color stays a follow-up issue.
- **Off light:** `unchanged`, `off`, nothing sent, as on Z2M and ZHA. Already at the limit: `at_limit`.
- **Hue actions stay unsupported on Hue** (not a straight line in xy).

### Adapters: `integrations/hue/raise_saturation.py`, `lower_saturation.py` over `hue/fade.py`

- Generalize `HueBrightnessFade` into one Hue fade adapter with a fade per attribute (`brightness_fade`,
  `saturation_fade`), as `zha/fade.py` does. Brightness behavior stays byte-for-byte.
- Scope: `fields={SATURATION}`, `options={"predicted_state"}` (filtering applies; display doesn't), native groups.
  A light or room with no color light: `unchanged`, `fields_dropped`.
- Start = `cache.value(light, SATURATION, hs_color[1])` per moving light, the room's start their mean. Duration =
  `sweep_time` × |end − start| / 100. Step: `MIN_BRIGHTNESS_STEP`'s 0.4 % reused as the at_limit threshold.
- The write is `color.xy` with `dynamics.duration`, no `on` (a lit light only). The cache records the SATURATION
  transition in percent, plus each light's start and end xy (Hue cache, beside `_hidden`), so a stop can write the
  xy on the straight line at the elapsed fraction.

### `stop`

- Halt per attribute tracked: `dimming_delta` stop as today; for SATURATION, the predicted xy with duration 0 (the
  bridge has no color delta stop). Both in one PUT when both run, unless the probe says otherwise. A soft off's
  `cut` carries the predicted xy too. `cache.stopped` for each; `reports.halted` is a no-op for SATURATION.
- `bridge.py`: `stops()` takes the predicted xy for SATURATION, or a new body helper beside it.

### Report filter, get_attributes

- `attributes.py`: `SATURATION: Attribute(frozenset({"xy"}), None)`. Nothing else in `report_filter.py`
  should need editing; ping the core-ha-watch session (`wt/core-ha-watch`) first if `classify`/`owned` must change.
- `get_attributes`: a light's and room's xy (and the hs/rgb derived from it) read through the prediction while
  a saturation transition is tracked, as brightness does.

### Tests, docs, rig

- Unit tests per module (`test_raise_saturation.py`, `test_lower_saturation.py`, the shared fade in `test_fade.py`,
  `test_stop.py`, `test_report_filter.py`, `test_get_attributes.py`): end xy and gamut clamp, at_limit, off,
  fields_dropped, room hue and passed-by white lights, stop xy at a fraction, combined stop body. ≥95 % per module.
- `services.yaml`: saturation actions target `hue` too (`*hue_mqtt_zha`).
- Rig: drop `only: [zigbee2mqtt, zha]` from the saturation cases in `raise_saturation.yaml`,
  `lower_saturation.yaml` and `stop.yaml` where the Hue behavior matches; add Hue-only expectations where it
  doesn't. Runs in the Hue A60 run (13k step 2), which writes the records and clears `experimental`.
- `docs/integrations.md` Hue raise/lower section: saturation as above, its stop and its sharp edges.

### A60 probe (before the adapter)

Scratch script, rig lock held, direct CLIP v2, results recorded below: (1) the bridge's xy reports during and
after a fade; (2) an xy fade's bulb reports against the straight line in time, which is what a predicted-xy stop
relies on to not jump; (3) whether an xy write and a brightness write run independently; (4) one PUT with a
dimming stop and an xy write; (5) a zone `grouped_light` xy fade and stop with a color and an ambiance member.

## Every PR

`.venv/bin/pytest`, `pre-commit run --all-files`, `uv run scripts/check_tiers.py` (Hue stays `experimental`),
`/audit-code` on the diff by a fresh subagent, rig run with records written to `docs/test-records/hue/`. Then PR into
`release/v0.0.2`, `ci-green`, squash-merge, remove the worktree.

## Verification

- Unit tests above green. `check_tiers.py` shows the new fingerprints and the `color_temp` and
  `color_temp_limit` fields covered by current records.
- Rig: `uv run scripts/rig.py` passes for the `move` and `stop` steps on `light_ct` and `group`, both
  `predicted_state` modes. Test records `move.md`, `move-predicted_state.md`, `stop.md` and
  `stop-predicted_state.md` list `color_temp` and `color_temp_limit`.
- Observed: a hold-to-warm then release halts with no snap, and a following warmer continues from the halt.

## Result (7c1)

**Open item 12, probed 2026-10-27** on the rig's single bulb and two-bulb zone (same hardware and versions as
the echo spike). Writes 0.5 s apart, a stop part way, reports logged for 35 s:

| Trial | Writes | What came back |
|---|---|---|
| Light | brightness 10 s, then color temp 3 s | 3 s in, one report each: 40.3 % (path 41 %) and 440 mirek (path 447): both still fading |
| Light | color temp 10 s, then brightness 3 s; color temp stop | no stop report within 35 s (2 runs) |
| Light | one PUT with both, 10 s; both stops in one PUT | two events per PUT, one per attribute; stop report 34 s later: 50.6 % and 326 mirek (straight line: 50.2, 326) |
| Zone | brightness 10 s, then color temp 3 s | members' end values at once; a member's mid-fade 23.3 % on its path |
| Zone | color temp 10 s, then brightness 3 s; both stops in one PUT | 2 s in, a member at 60.9 % and 270 mirek (paths 62, 270); color temp stop report 358 (path 357), after the brightness fade had ended |

**Independent:** a second write for the other attribute neither cancels nor reshapes the first, in either
order, on a light or a zone. Each attribute gets its own write and duration; `shared_duration` isn't needed. The
bridge takes `dimming_delta` and `color_temperature_delta` stops in one PUT, on a light and a zone.

Not checked: a zone member with a narrower mirek range than the others. The rig's bulbs share one range (153 to
454), so the unit tests cover it.

**Built against the report filter as PR #89 left it** (keyed by attribute, every report of an owned key ours
inside the guard window), not the path and tolerance this plan names: color temperature owns the `mirek` report
key, and the filter strips only the keys of attributes HA is shown predictions of.

### Result (A60 probe, 2026-11-03)

The A60 (gamut C) on the bridge, direct CLIP v2 writes, every light and grouped_light event logged. Setup before
each trial: 70 %, xy at hs (200°, 90 %); the fades head to hs (200°, 10 %).

| Trial | What came back |
|---|---|
| xy fade 20 s | the end xy within 0.2 s, then nothing for 35 s |
| xy fade 20 s, predicted xy written at 8 s, duration 0 | the end at once; one bulb report at 4.2 s, 10 % of the way where a straight line in time says 21 % (a bulb report is late, so this doesn't settle the path); the written xy at once, then nothing for 27 s |
| brightness 10 s, xy 3 s 0.5 s later; and the other way round | each write's end at once, no mid-fade reports |
| brightness and xy over 10 s; at 4 s one PUT with `dimming_delta` stop, the predicted xy and duration 0 | accepted; the xy at once; brightness 48.6 % 17 s later (straight line: 48 %) |
| zone of the A60 and an ambiance bulb, `grouped_light` xy fade 10 s, predicted xy written to it at 4 s | both writes accepted; the A60 took each, the ambiance bulb was left as it was |

- **Like brightness:** the bridge reports an xy fade's end at once, and a stop's xy write at once. No late report
  follows, so a halt's xy stands.
- **One PUT** carries a dimming stop and an xy write; the brightness halted where the straight line put it, so an
  xy write 0.05 s after a brightness write didn't cancel the brightness fade.
- **Zone:** an xy write to a `grouped_light` with a member that has no color works, and leaves that member alone.
- **Not settled unattended:** whether the predicted-xy stop jumps visibly (the bulb's own path in time), and
  whether a brightness write leaves a running xy fade alone. Both become observed cases in the Hue A60 run (13k
  step 2, already attended): `saturation_down_stop` and `halts_brightness_and_saturation` on Hue, watched. If the
  stop jumps, revisit before clearing `experimental`.
