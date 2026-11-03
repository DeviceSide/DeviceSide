# Slice 15 follow-up: the first lab run's 26 failures

## Context

The first unattended lab run (#157, 2026-11-02) passed 125 cases and failed 26. TODO.md tracks them as the
slice 15 follow-up, and the lab plan's findings table groups them by cause. They block the Z2M A60 run and feed the
Hue and ZHA A60 runs. Some are test bugs: the rig expects every group member to take color temperature, a case
calls an action Hue has no adapter for, and a limit is tighter than a bulb's floor. Two are real behavior bugs.
The rest are single readings that need a rerun before anyone changes code.

The goal is every failure either fixed, rerun green, or diagnosed and tracked, with the passing suites' records
reading `Profile | lab`.

**Out of scope:** ZHA raise, lower and `stop`, including their failures in today's later runs. 13f owns them in
another workspace.

**Step 0:** the implementing session copies this plan into its worktree as
`docs/plans/2026-11-02-lab-run-failures.md` (branch `wt/lab-failures` off `release/v0.0.2`). It also adds a link
to the plan from the slice 15 follow-up item in TODO.md.

## The 26, by fix

| # | Bucket | Cases (integration) | Fix |
|---|---|---|---|
| A1 | Rig: mixed group | `sets_while_off[group]` (Hue, ZHA), `reads_while_off[group]` (ZHA); the White bulb's half of `sets_after_a_soft_off[group]` (ZHA) | Engine expects a member that can't take an attribute to show it absent, and to report `fields_dropped` when a call sends it one (#160, made strict in PR 1b) |
| A2 → F | Bug: predicted start from off | `up_from_off_shows_the_dimmest[group]` (Hue): the White showed 13 | Not a test bug. device_side showed the light's `min_dim_level` (5 % on a White), which is light output, not a brightness. Show the lowest step, 0.4 %, and keep `max: 8` (PR 1c) |
| A3 | Rig: no adapter | `reads_a_running_timer[light_dimmable]` (Hue) calls `turn_on_for` | Skip a case whose `call: {action: X}` has no adapter on the suite's integration |
| B | Bug: HA's kept level | `sets_after_a_soft_off[light_ct, group]` (Hue, ZHA): 255 after the plain on | Overwrite HA's kept level after a level write while off |
| C | Bug?: ZHA color while off | ZHA `sets_while_off[light_ct]` (CT 3984), `sets_hs_while_off`, `sets_xy_while_off` (old color) | Diagnose first; probe 13a said these bulbs store all three |
| D | Rerun | 8 Z2M `set_attributes` `not_stored` on `light_ct` and `group` | `hue_native_control` has since been added to the CT bulb's options; rerun |
| E | Single readings | Hue `lower_to_off[light_ct, group]` (bulb still off 2 s after `set`, first case after the predicted_state suite); Z2M `reads_while_off[group]` 3354 K; `keeps_and_reads_hs_while_off` (read returns CT mode); `cycles_down_the_wheel[light_color]` hue 60; `halts_brightness_and_hue[light_color]` 53.1 | Rerun; fix only what repeats |

## PR 1: rig fixes (A1 to A3), no rig run needed to land

- **A1**, `tests/rig/engine.py`, `_CaseRun.await_state` (~:1147) and `_expect_response` (~:1113). Both already
  loop over `members()`. Per member, drop each wanted attribute that member's `supported_color_modes` can't carry:
  - `color_temp_kelvin` needs `color_temp`
  - `hs_color.*`, `xy_color.*` and `rgb_color` need one of hs, xy, rgb or rgbw(w)
  - `brightness` needs any mode except `onoff`
  - `state` and `timer.*` always stay.

  Put the mapping in one helper beside `_value`/`_lookup`. If an attribute would be dropped for every member, raise
  `StepFailure` ("no member of X takes color_temp_kelvin"), so a step file can't pass by checking nothing.
  `supported_color_modes` is in the state while a light is off, as the ZHA adapter already relies on. This doesn't
  apply to a Z2M group's single row (keyed on the group itself): it reads the mean over the members that report.
- **A2**, `tests/rig/steps/raise_brightness-predicted_state.yaml`: `max: 14` in both steps of
  `up_from_off_shows_the_dimmest`, with a comment that the Hue White's lowest level reads 13 (5 %).
- **A3**: `cases()` (`engine.py` ~:521) takes the set of actions the suite's integration has adapters for. `rig.py`
  builds it from the `AdapterRegistry` it already holds and passes it at every `cases()` call (`plan_lines`,
  `wait_for_targets`, `engine.run`). A test whose steps call another action that's missing is skipped with "no
  turn_on_for adapter on hue". Use `registry.adapter(action, integration)`, which `rig.py:182` already uses.
- Tests in `tests/scripts/test_rig_engine.py`, using the existing fakes:
  - a mixed group passes with the White member lacking color temperature
  - an attribute no member takes fails
  - the cross-action skip.

## PR 1b: the rig checks, not skips (A1, A2)

#160 skipped what a member couldn't take and raised the limit to 14 for every bulb. Both loosened checks that
should stay strict, since the rig exists to catch device_side's faults:

- **A1:** a member that can't carry an attribute must show it absent (None) in HA's state and in a read. After a call
  that sends it a field it can't take, its row must say `detail: fields_dropped`, unless the step names a detail.
- **A2:** range bounds took expressions, and `dimmest` read each light's `min_dim_level` from the bridge. PR 1c
  removed it: see F.

## PR 1c: the predicted start from off (F)

The 13 in A2 was device_side's own output. With predicted_state on, a raise from off showed HA the light's
`min_dim_level` (`report_filter._dimmest`), and #160 and #162 shaped the rig around it. Hue defines `min_dim_level`
as the "percentage of the maximum lumen the device outputs on minimum brightness": light output, not a brightness.

Probe, 2026-11-02, the lab's Hue White (LWA012, `min_dim_level` 5.0), on, written through the bridge:

| Wrote | Bridge reports | HA shows |
|---|---|---|
| 0.4 % | 0.4 | 1 |
| 0 % | 0.0 | 0 |
| 5 % | 5.14 | 13 |

The bridge reports levels below `min_dim_level`, and the fade starts from 0 % (`fade.brightness_fade`). So a raise from
off now shows the lowest step, 0.4 % (HA 1), on every light, and the rig's limit is `max: 8` again. The step is the
same for every bulb, so the rig has no `dimmest` and no expression bounds. With no brightness floor to report,
`get_attributes` gets no floor field.

## PR 2: HA's kept level after a soft off (B)

Cause, from HA 2026.10.2's source:
- Hue light (`hue/v2/light.py:247,321`) keeps `_last_brightness`, and the grouped light (`hue/v2/group.py:175,206`)
  keeps `_restore_brightness`. Each is set on an HA off with a transition and sent on the next plain on.
- ZHA keeps `off_brightness`/`off_with_transition` on the zha library's light entity (`zha/light.py:127,216`).

This is the same fault as Z2M's converter store (13j finding e). Decision: overwrite the kept level.

- New `core/ha_entity.py`: `ha_entity(hass, entity_id)` returns HA's live entity object from
  `hass.data["entity_components"]["light"]`, or None.
- After a level write while the light is off, set the kept level to the written level. Do it only when one is
  already set, so a light that wasn't soft-offed keeps HA's plain on.
  - **Hue**, `integrations/hue/set_attributes.py`: on the target (`_last_brightness` for a light,
    `_restore_brightness` for a grouped light, both in Hue's 0-100 scale) and on each member light of a group
    target.
  - **ZHA**, `integrations/zha/set_attributes.py`: on the HA entity's `entity_data.entity`, setting `_off_brightness`
    (0-255) on the target and each member. Check the attribute names against the zha library version HA 2026.10.2
    pins (`pip download zha==<pin>` into the scratchpad). The lib isn't in `.venv`.
- Guard every access with `getattr`/`hasattr` and log once at debug if it's missing: a rename in HA must degrade to
  today's behavior, never raise.
- Unit tests:
  - a fake entity with the attribute set gets overwritten
  - one without it is untouched
  - a missing entity is a no-op.
- Docs: `docs/integrations.md`'s Hue and ZHA `set_attributes` sections get one line each on the kept level.
  Neither adapter's experimental flag changes: both are already experimental.
- Left as a known edge, written in the docs: a light set while off whose Hue room was soft-offed as a room. The
  room's `_restore_brightness` would still apply when the room comes on. PR 2 overwrites it only when the room
  itself is the target.

## Lab run (ask Jason first, queued behind 13f's lock)

Run this after PRs 1 and 2 merge. It's one filtered, unattended run, so the bulbs make one round trip:

```
scripts/rig.py --profile lab --unattended \
  --action set_attributes --action get_attributes --action lower_brightness \
  --action raise_brightness --action lower_hue --action stop
```

Leave out `--integration`, so the Hue, ZHA and Z2M phases all run. Its ZHA `raise_brightness`/`stop` cases belong to
13f: report them to that lane and don't act on them. Start it in the background; it waits for the lock.

## Then, by what repeats

- **C (ZHA color while off).** If it still fails, run a probe (ask first): on ZHA, write CT, hs and xy while off as
  the adapter does, then read `colorTemperatureMireds`, `currentHue`/`currentSaturation`, `currentX`/`currentY` and
  `colorMode` over ZCL three times: right after the write, after `update_entity`, and after HA's plain on.
  - If the bulb holds the values and only HA's state is stale, the fix is in the refresh.
  - If the bulb drops them, refuse the fields on those models, as `_DROPS_WHILE_OFF` does for the E11-G13. That
    contradicts probe 13a, so record why.

  Write the findings into this plan. Ask Jason before any change of design.

  **Probe findings (2026-11-03, lab bulbs on ZHA, raw commands as `_wire` builds them, no deploy).** The bulbs
  store every write, and HA's plain on brings them up at it. It's HA's state that stays stale.

  | Bulb (firmware) | Write while off | ZCL 0.5 s and 3.5 s after | ZCL after HA's plain on |
  |---|---|---|---|
  | LWA012 (1.104.2) | `MoveToLevel` 102 | 102 | 102 |
  | LTA009 (1.163.1) | `MoveToLevel` 102, `MoveToColorTemp` 370 | 102, 370 | 102, 370; HA 2702 K |
  | LCA016 A60 (1.164.2) | `MoveToColor` (0.3, 0.5) | (0.3, 0.5) | (0.3, 0.5); HA the same |

  The first probe compared a plain off, a 2 s soft off and an on by `MoveToLevelWithOnOff`, and every one stored the
  writes. The second wrote 0, 0.3, 0.6, 1 and 2 s after HA's plain `turn_off` returned, and stored them at every
  delay. Probe 13a was right about the bulbs.

  **Cause: zha's transition flag.** zha 2.3.1 sets `is_transitioning` on an HA `turn_off` for its fade plus 0.5 s
  (1.5 s for a plain off), and `async_update` returns without reading while it is set (`light/__init__.py:1196`).
  The adapter's `update_entity` runs straight after its writes, and the rig calls `set_attributes` as soon as HA
  shows off, so the refresh lands inside the flag and reads nothing. ZHA applies the bulb's level reports but no
  color reports, so after the plain on HA shows the new brightness and the old color: light_ct on at 102 but
  3984 K, the A60 at the setup's xy. `sets_after_a_soft_off` waits 3 s, past the flag, and passes. The probes'
  `update_entity` ran 3.5 s after the writes. The group case's desk at 254 is the same stale refresh, seen through
  the group's assumed member state. It isn't specific to Hue bulbs: any ZHA light set within its off's flag hits it.

  The TODO item's "the bulbs ignore the writes" was wrong, and so is the `multiColor` fix it proposed. 13f's
  conclusion that a Hue bulb ignores the level preset before `raise_from_off` may need the same second look. It is
  left to 13f's lane.
- **D.** If `not_stored` persists with `hue_native_control` on, compare the read-back with the written value in
  the Z2M adapter's debug log before changing the comparison.

  **Rerun findings (2026-11-03, `--debug-logs`, Z2M `set_attributes` only).** `not_stored` repeats on the same four
  cases (`min_brightness_raises`, `max_brightness_lowers`; `light_ct` and `group`). The LTA009 stores the level; it's
  the adapter's read straight after the write that sees the old one. On air, in order: `moveToLevel` 102 and
  `moveToColorTemp` 370 (both with the override), then `_kept_level`'s publish, which `hue_native_control` turns into
  `manuSpecificPhilips2.multiColor` (brightness 102, no override), then the `currentLevel` read: 28, the old level,
  about 0.5 s after the write. Color temperature read back 370 at once. A level read 2 s later returned 102. Probe
  13j's "answers with the target even mid-fade" no longer holds for this bulb since its reset on 3 Nov, the same bulb
  and date as the TODO's Z2M stop item. Next: a probe (ask first) of the read's delay with and without the
  `multiColor`, before any change to `_stored` or `_kept_level`.
- **E.** Fix only a case that fails again:
  - Hue `lower_to_off`: the predicted_state suite's options reload finishes just before it. Check
    `OptionsSwitch.reloaded` waits long enough for Hue's entities.
  - Z2M group 3354 K: suspect a member's stale `colorTemperature` read while it's in xy/hs mode.
  - The Z2M A60 color readings: tolerance or timing, by the samples.

  A repeat that needs adapter code goes in this PR series as PR 3. A Z2M one lands before the Z2M A60 run.

## Finish

- Records for each fully passed suite are written by the run itself (`Profile | lab`); commit them in PR 3, or in a
  records-only PR if no code changed.
- TODO.md: tick the 15 follow-up item, add a "Done since v0.0.1" row, and remove any finding left open into its
  lane's item (C into the ZHA A60 run, D/E-Z2M into the Z2M A60 run).
- Lab plan's findings table: mark each cause fixed, rerun green, or open with its pointer.

## Verification

- Each PR: `.venv/bin/pytest`, `pre-commit run --all-files`, `/audit-code` on the diff, then
  `merge-green <n> --squash --delete-branch`.
- PR 1: `scripts/rig.py --profile lab --dry-run` shows `reads_a_running_timer[light_dimmable]` skipped on Hue.
- The lab run: A1 to A3 and B cases pass on Hue and ZHA, D passes or yields its debug evidence, and E shows which
  repeat.
