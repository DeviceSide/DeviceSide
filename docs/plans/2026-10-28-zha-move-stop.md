# Slice 13f: ZHA `move` and `stop`

## Context

Slice 13 (`docs/plans/2026-10-27-zigbee-parity-timer-state.md`) brings the Hue-only actions to Zigbee before
v0.1.0. 13f is ZHA's `move` (hold-to-dim: brightness, saturation and hue ramp on the bulb) and `stop` (the
release). It is the last ZHA code before the freeze and the ZHA A60 run (13k step 3).

13i's watched tests (`docs/plans/2026-10-28-z2m-move-stop.md`) showed that no halt of a color temperature fade on a
Hue bulb avoids a visible jump, so color temperature moves are dropped on every integration
(`docs/plans/2026-10-28-drop-color-temp-move.md`). 13f moves brightness, saturation and hue.

Facts this builds on:
- 13a (`docs/plans/2026-10-27-zigbee-probe.md`), on the LTA004 (ZHA `light_ct`):
  - Level `Stop` and `StopMoveStep` halt a `MoveTo…` fade part-way, and the halt holds.
  - The bulb reports brightness mid-fade, and ZHA applies it. Color is never applied without `update_entity`.
  - ExecuteIfOff (`options_mask: 1, options_override: 1`) stores a level while off; the E11-G13 drops it
    (`zha/zcl.py:DROPS_WHILE_OFF`).
- zha 2.3.1, the version HA pins (`zha/application/platforms/light/__init__.py`):
  - HA's ZHA lights are xy-only. `async_update` reads `current_x`/`current_y` in any non-CT color mode, so an
    hs-mode bulb still reads back as xy. No write-back like 13i's is needed, as long as the bulb keeps x/y current
    in hs mode (checked in the ZHA A60 run).
  - ZHA's transitioning flag is set only by HA-started `turn_on`/`turn_off`, so raw commands leave
    `update_entity` working. That is why the soft off below is raw, not `light.turn_off` + `transition`.

## Decisions (interview, 2026-10-28)

- **Color temperature:** out of scope everywhere.
- **Soft off on ZHA (down to 0 %):** a raw `MoveToLevelWithOnOff` to 0, which leaves the bulb at level 1. When
  the fade ends, if OnOff reads off, `MoveToLevel` back to the move's start level with ExecuteIfOff and no
  transition. The bulb stays off and comes back at its old level from any source (HA, a bound remote), as on Hue
  and Z2M. A stop or a new move cancels the restore. It's skipped on `DROPS_WHILE_OFF` models, which come on dim.
  An HA restart mid-fade loses the restore, so the bulb comes on dim (a documented sharp edge).
- **Saturation:** `MoveToColor`, an xy fade to the current hue at the end saturation, with a transition. It's
  halted by `StopMoveStep`, which in 13i looked dead smooth toward deep color and overshot slightly toward white.
- **Hue:** `EnhancedMoveHue`, only on bulbs whose `ColorCapabilities` report enhanced hue.

## 0. Probe findings (2026-10-28)

A scratchpad script on the LTA004 and the ZHA group, raw commands through `zha.issue_zigbee_cluster_command` and
`zha.issue_zigbee_group_command`, live reads through ZHA's admin attribute read.

- **(a) Stop halts a soft off.** `MoveToLevelWithOnOff` 200 → 0 over 6 s, level `Stop` at 3 s: CurrentLevel 100,
  OnOff on, held at +0.3, +3 and +8 s. HA showed 100 with no refresh (the bulb's report), and `update_entity` kept it.
- **(d) Groupcast.** `MoveToLevelWithOnOff` with positional args `[level, transition_time]`, and level `Stop` with
  `[]`, both work: 254 → 30 over 6 s, stopped at 3 s, the member read 144 (142 expected) and held at +4 s. Run on the
  LTA004 alone; the E11-G13 had stopped answering (last seen two hours before), so two members halting together is
  untested.
- **(e) End timing.** A 4 s `MoveToLevel` read its end level at t+3.9 s; a 4 s soft off read OnOff off, level 1, at
  t+4.3 s. An `update_entity` at fade + 0.5 s already showed the end. So the end refresh and the restore run at
  fade + 1 s (`END_REFRESH_S`).
- **(b) Restore after a soft off** and **(c) a move up from off starts at the bottom**: watched; results below.

## Rig finding and decision (2026-10-28)

The first rig run showed the core cache going stale on ZHA: a brightness change from HA during a move, or within
2 s of its end, left the next move starting from the prediction. A soft off then restored the predicted level (the
bulb came back at 94 % rather than 60 %). Hue's report filter ends a prediction on a change made elsewhere; ZHA has
no such hook, as the bulb's own reports mid-fade look the same. Decided with Jason: hold-to-dim latency comes first,
so a move is sent first and each light's CurrentLevel read after; the ramp's real start is fitted to the read at the
point the ramp had reached (timed at the middle of the read's round trip), and re-recorded. A move the prediction
says has nothing to do is planned again from HA's state. A live read before every move (about 0.2 s) was rejected
for its latency.

## Status and handoff (2026-11-02)

**Built:** `release/v0.0.2` merged in through slice 15 (the lab, rig profiles, test records). `zha/move.py` became
the shared `zha/fade.py` (`ZHARamp`, `ramp_scope`) with one adapter per raise and lower action, as on Hue and Z2M;
the steps below still say `move` and stay as written. End refreshes and the soft off's restore are keyed per light
and attribute (`end_key`), so a saturation or hue call keeps a brightness fade's restore; `stop` cancels both. ZHA
cases sit in the per-action step files (`soft_off_keeps_level` in `lower_brightness.yaml`), and the saturation, hue
and two-call stop cases run on ZHA with the `light_color` and `group_color` roles. `_CaseRun.reading` keeps the group
mean beside the dotted `_lookup`. A fresh `/audit-code` of the fit, the group sample and the split fixed one defect
(`7f56d4d`: the re-plan from HA's state forgot every attribute, so a stop sent a running saturation fade no
`StopMoveStep`). 1323 tests pass, ZHA modules at 100 %. Pushed, no PR: it waits for a passing rig run.

**Lab runs (2026-11-02, after slice 15 PR 5).** All unattended on `--profile lab`; reports in the rig's temp dir.

1. **Probe** (`-k raise`, `raise_brightness` and `stop`): `raise_from_off` (both roles) and `halts_a_raise[light_ct]`
   failed again with no E11-G13 in the lab, so the radio jam was not the cause.
2. **Fix, `93151f1`: a `light` call from HA now drops ZHA's predictions** (`watch_ha_changes` in `zha/fade.py`, as
   Hue's report filter does). Each case's setup changed the light from HA inside the previous case's prediction, and
   ZHA planned from it. Rerun: `halts_a_raise` passes on both roles; `raise_from_off` still fails. One core watch for
   every integration (Z2M has none) is the `TODO.md` 13f follow-up.
3. **Full ZHA run** (six actions and `stop`): 23 passed. Failures:
   - `raise_from_off[light_ct]`, `[group]`: as below.
   - `soft_off_keeps_level[light_ct]`: back on at 159 (`max: 158`). It may be the fit's timing risk showing for the
     first time: the ramp is timed from before the send, so a bulb that starts late reads high and a soft off's start
     fits high. Unproven, since the fit isn't logged.
   - `stop_when_idle[group]`: HA's own group state read 128, 170, 128, 128, 128 (a one-reading spike, as on the house
     runs).
   - A60 hue cases (`cycles_up_the_wheel`, `cycles_down_the_wheel`, `hue_cycle_stop`, `halts_brightness_and_hue`):
     HA's xy after the stop differs from a live read (e.g. 0.336, 0.575 against 0.297, 0.641).
   - Every `group_color` case skips: ZHA makes no entity for a one-member group.
   - `raise_saturation` and `lower_saturation` passed whole; the rig wrote their records (untracked, not committed:
     the run loaded `b880e6c`, since reverted).
4. **`raise_from_off` is the bulb, timed** (`a2a7ec0` adds each reading's offset from the call to a failed sample):
   the white ambiance bulb read 72.0 % 0.41 s after the raise was sent (the call took 0.18 s), then 77.2 % at
   1.32 s. That is a 5 s fade from its old level (about 70 %), not from level 1. On ZHA, the Hue bulb ignores the
   bottom preset sent just before `MoveToLevelWithOnOff`, both as a level 1 with `ExecuteIfOff` and (`b880e6c`,
   reverted in `fffc219`) as Z2M's on at level 1 with no transition. Z2M passes on the same bulbs because
   `hue_native_control` sends on and brightness in one write to Hue's own cluster.
5. **The light_ct bulb was stranded** going home after the timed rerun: it missed ZHA's Leave and is on no network.
   A probe run of a 0.5 s pause after the preset stopped at the replay before its gate, with nothing deployed. HA
   still runs `b880e6c`'s preset until the next deploy.

**Deep dive and full ZHA lab run (2026-11-03, HA on `2d70127`).** The deep dive's two fixes passed on the rig:
`569196e` (`get_attributes` reads the bulb's own x and y in a hue mode, as ZHA shows them; HA's hs to xy isn't the
bulb's) and `6956d00` (`stop_when_idle` waits 2 s after its set, past ZHA's report hold: a turn_on with brightness
buffers level reports for its duration + 0.5 s, then applies the last). `2d70127` replaced the hue cases' HA hs
ranges with `mark_hue`/`expect_hue_travel`, which read the bulb's own EnhancedCurrentHue: Signify's hue to xy is
nonlinear, so HA's hue (from xy) can't be ranged. The A60 now sits on ZHA between runs (`a60_zha` profile); the
full run took it home to Hue first and back to Hue at the end. All three bulbs reached Hue, rooms and scenes put
back. Records written and committed: `get_attributes`, `lower_hue`, `lower_saturation`, `raise_hue`,
`raise_saturation`, `stop`, `turn_on_for`. Failures:

- `soft_off_keeps_level[group]`: the desk came back on at 160 (`max: 158`); `[light_ct]` passed. Second time over
  by 1 to 2 (see step 3): the fit's decision for Jason, with `sync_to_bulb` logged first.
- `raise_after_soft_off[light_ct]`: one `get_attributes` read in the sample failed with an empty error (HA log
  08:06:19, `get_attributes on zha failed for <the light_ct bulb>: `); a one-off radio miss, `[group]` passed. The
  adapter's warning drops the exception's type, so the cause isn't in the log.
- `set_attributes` while off, on the lab's Hue bulbs: `sets_while_off[light_ct]` (LTA009 came on at 3984 K, not
  2700), `[group]` (the desk at 254, not 102), `sets_hs_while_off` and `sets_xy_while_off` (the A60 came on at the
  setup's blue). The ExecuteIfOff writes are ignored, as the bulbs ignore the level preset before `raise_from_off`;
  `sets_after_a_soft_off` passes on both roles. Not this branch's change (set_attributes only moved to the shared
  helpers); never run on the lab before, and the 28 Oct record passed on the house LTA004. Z2M passes through
  `hue_native_control`. Jason: its own session, after this PR; the TODO item before the ZHA A60 run holds the probe
  and the likely fix (Hue's own `0xFC03` write, as `raise_from_off` does).

**Fit logged, then guarded (2026-11-03).** `ef646cf` logs every term of `sync_to_bulb` at debug, and names the error
type of a target's failure (the empty `raise_after_soft_off` line was a message-less exception). Rerun on the lab
(`lower_brightness`, `raise_brightness`, `stop`, HA on `ef646cf`): `soft_off_keeps_level[light_ct]` on at 159,
`[group]` passed. The log showed the fit's risk, not a change made elsewhere: every 60 % soft off (1.8 s) fitted a
start of 60.6 to 62.5 %, and raises fit a shade low. The bulbs start 0.05 to 0.08 s after the send, so every read
lands behind schedule. Jason chose a deadband: a read within 0.15 s of the ramp's speed plus one level step of the
prediction keeps it (about 5.4 % on that soft off); a real change elsewhere (the unit test's 80 against 60) still
refits. Also one `raise[group]` failure, first seen: the fits show the bulbs at 100, 100 and 79.5 % when the raise was
sent, so the setup's set to 20 % hadn't landed; rerun, act only if it repeats.

**Deadband proved (2026-11-03, HA on `5f6ff4e`):** the same rerun passed `soft_off_keeps_level` on both roles, with
every 60 % soft off kept (reads 1 to 3 % behind, within ± 5.4) and restored to 60.0 %. A raise from off still refits
(the bulb reads 1 % where the ramp predicts 4 to 8 %), to the clamped start of 0, which is right. `raise_brightness`
and `stop` passed whole; their records are committed. One failure, in a setup step before any device_side call:
`light_raised_mid_room_lower[group]`'s `set` to 100 % left the desk at 200 after 3 s; it passed on every earlier run,
so rerun it with the full suite and act only if it repeats. Rerun (HA on `7d5836f`): `lower_brightness` passed
whole, `light_raised_mid_room_lower[group]` included; its record is committed.

**Next, in order** (every rig run needs Jason's go; start each in the background, one at a time behind the lock):

1. ~~Recover the light_ct bulb.~~ Done (2026-11-02): after a power cycle ZHA took it back, and `--recover` moved it
   home to Hue with its rooms and scenes.
2. ~~Rig-probe (b).~~ **Passed** (2026-11-02, 21:09, `-k raise_from_off`, HA on `492ac11`): `raise_from_off`
   on light_ct and on the group, and all three bulbs went home to Hue. Built in `53a0f88` (Jason chose it): an off light with Signify's cluster `0xFC03` is turned on
   at level 1 by `multiColor` (flags `0x0013`: on, brightness 1, fade 0; manufacturer `0x100B`), sent through
   zigpy (`zcl.hue_turn_on`) behind zha's admin check, then `MoveToLevelWithOnOff` fades it as before; other lights
   keep `MoveToLevel` with ExecuteIfOff. Untried live: the zigpy call shape (`cluster.request(False, 0x00, Struct
   of SerializableBytes, payload, manufacturer=0x100B)`) is from zigpy's source, and zigpy isn't a dev dependency.
   Probe `-k raise_from_off`. If the bulb still fades from its stored level, send the whole fade as `multiColor`
   (on, the limit, the fade time) for an off Hue light, which is what Z2M sends.
   **Deep dive brief (code only, no rig runs):** two failures from the 17:11 full ZHA lab run (HA on `b880e6c`):
   - **A60 xy after a hue stop.** `cycles_up_the_wheel`, `cycles_down_the_wheel`, `hue_cycle_stop` and
     `halts_brightness_and_hue` on `light_color` fail `expect_matches_read`. HA shows xy (0.3364, 0.5750) against a
     live read of (0.297, 0.641); (0.2382, 0.6488) against (0.171, 0.717); (0.3375, 0.5742) against (0.299, 0.640);
     (0.4148, 0.5161) against (0.403, 0.552). HA's point is always nearer white than the bulb's. Trace what refreshes HA's
     xy after the stop (`stop.py`, the `update_entity` refresh and its timing, ZHA's own color read and conversion,
     the bulb's color mode after `StopMoveStep`) and whether the gap is the rig's comparison (its tolerance, hs
     against xy, gamut) or a stale or wrongly converted state in HA.
   - **`stop_when_idle[group]` spike.** HA's own ZHA group state read 128, 170, 128, 128, 128 over the sample after
     a stop on an idle group; the house runs show one-reading spikes too. Find where a ZHA group light's brightness
     comes from (zha's group entity averaging its members, a member's report, our `update_entity` after a stop) and
     whether the rig should sample the members, as `_CaseRun.reading` does for the group mean, or the adapter sends
     something that moves a member.
   Report the cause and a proposed fix for each; fixes and any rig run wait for Jason's go.
3. ~~Decide on guarding the fit.~~ Done (2026-11-03): logged, then the deadband above. Rerun the brightness actions
   and `stop` on the lab to prove it.
4. **Investigate** the A60 hue stops' xy refresh and `stop_when_idle[group]`.
5. **Then the full ZHA lab run, and on a pass:** write `docs/test-records/zha/<action>.md` for each action that
   passed (`Profile | lab`, citing the commit HA loaded), tick 13f in `TODO.md`, pytest and pre-commit, PR into
   `release/v0.0.2`, `merge-green <n> --squash --delete-branch` in the background, then remove the worktree and
   fast-forward the main checkout. Color's observed cases wait for the ZHA A60 run (13k step 3); the E11-G13 cases
   and mixed groups are proved on the house profile's pre-release run.
6. Optional, at Jason's go: watched (b) and (c).

## 1. `zha/zcl.py` helpers

Add the constants: `MOVE_TO_LEVEL_WITH_ON_OFF = 0x04`, `STOP = 0x03`, `ENHANCED_MOVE_HUE = 0x41`,
`STOP_MOVE_STEP = 0x47`, `COLOR_CAPABILITIES = 0x400A` (`ENHANCED_HUE` bit 1). Add one
`group_command(hass, gid, cluster_id, command_id, args, context)` helper. Move the groupcast call out of
`turn_on_for.py:_groupcast` into it, as a refactor. Move `_EXECUTE_IF_OFF`/`_DROPS_WHILE_OFF` from
`set_attributes.py` to `zcl.py`, parameterizing the transition.

## 2. `zha/move.py`: `ZHAMove(Adapter[MoveRequest])`

- Scope: `experimental=True`, `domains={"light"}`, `fields={"brightness", "brightness_limit", "saturation",
  "saturation_limit", "hue"}`, `max_concurrency=2`. `supports` refuses `not_addressable` (`addressing.py`).
- Cache: `transition.transition_cache(hass, "zha", lambda: TransitionCache(SETTLE_SECONDS))`, keyed by
  entity_id. The settle window is short, about 2 s, since a refresh is right.
- Mirror `zigbee2mqtt/move.py`'s structure and rules (`plan`, `Fade`, `lit`, `at_limit`/`off`/`fields_dropped`,
  the group mean start, recording before each send), so each detail means the same on both integrations.
- **Brightness:**
  - Up sends `MoveToLevelWithOnOff(limit, t)`. Before it, each member that is off gets `MoveToLevel(1)` with
    ExecuteIfOff and t 0, unicast, so the move starts at the bottom. This is skipped on `DROPS_WHILE_OFF`, which
    is documented.
  - Down to a limit is `MoveToLevel(limit, t)`, on lit lights only.
  - Down to 0 is `MoveToLevelWithOnOff(0, t)`, then a scheduled restore per light at `t + 1 s`: read OnOff, and if
    it's off, `MoveToLevel(start level)` with ExecuteIfOff and t 0. Skipped on `DROPS_WHILE_OFF`.
  - Down on a light that's off is `unchanged`, `off`.
- **Saturation:** lit lights in a color mode. The start is `cache.value(entity, SATURATION, hs_color[1])`, and
  the end xy is `color_hs_to_xy(current hue, limit)`, sent as `MoveToColor` with t. Dropped on lights whose
  `supported_color_modes` lack xy/hs.
- **Hue:** `EnhancedMoveHue`, mode up or down, rate `round(65535 / sweep_time)`, clamped to 1–65535 steps a
  second, so a cycle is 1–65535 s. A clamped value gives `clamped_to`, per `docs/action-behavior.md`. Offered only
  where `ColorCapabilities` has enhanced hue: read from zigpy's attribute cache (it never changes), falling back
  to one live read. Otherwise the field is dropped. Record running hue moves in a `zha_hue_moves` set, as on Z2M.
- **Groups:** members expanded from one ZHA group (`turn_on_for.py:_via_zha_group`) get one groupcast per fade.
  The pre-set and the restore stay unicast, since each concerns one member's own state. Other targets are unicast.
- **End refresh:** `update_entity` per light at `t + END_REFRESH_S`, through `get_runtime(hass).schedule` keyed per
  target, so a new move or a stop replaces it. The restore rides the same job. Hue moves get none (they run until
  a stop).
- `Unauthorized` gives `REJECTED`, `admin_required`, as in the other ZHA adapters.

## 3. `zha/stop.py`: `ZHAStop(Adapter[Request])`

- Scope: `experimental=True`, `domains={"light"}`, `max_concurrency=2`.
- Lit targets, and those the cache shows fading to off, get level `Stop`. `StopMoveStep` goes where the cache
  tracks saturation or `zha_hue_moves` holds the light, and is skipped on lights with no color cluster.
  Groupcast per ZHA group, as in move.
- Record halts (`cache.stopped`). Replace the target's scheduled job, which cancels the restore: a halted soft off
  leaves the light on at the halted level, as on Hue. Then `update_entity` each light at once (raw commands leave
  ZHA's transitioning flag down).
- A light that is off with nothing fading is `unchanged`, `off`. Otherwise `SENT`.

## 4. Register both in `integrations/zha/__init__.py` `ADAPTERS`.

## 5. Unit tests

`tests/integrations/zha/test_move.py` and `test_stop.py`, with the existing ZHA service mocks and a frozen clock.
≥95% coverage.
- Each command and its params: up from on, up from off (pre-set, not on the E11-G13), down to a limit, down to 0.
- The restore: sent when OnOff reads off, skipped when on, cancelled by a stop or a new move, skipped on the
  E11-G13.
- Saturation xy end point, and the hue rate clamp edges (a test named after the rule).
- `fields_dropped` without enhanced hue or color, `at_limit`, `off`.
- One groupcast for a ZHA group's members, with per-member starts, and the unicast pre-set for off members only.
- The stop's commands per tracked attribute, the immediate refresh, and `admin_required`.
- The refactored `turn_on_for` groupcast still passes its tests.

## 6. Docs

- `docs/integrations.md`, ZHA section, a `move`/`stop` subsection: commands, the soft off restore, the
  `EnhancedMoveHue` cycle bounds; sharp edges (E11-G13: a move up from off starts at its stored level, a soft off
  leaves it at level 1; an HA restart mid-fade loses the restore); groups.
- README feature table: the ZHA move/stop cells. `TODO.md`: tick 13f, and say "ZHA code freezes".

## 7. Rig steps

- Add ZHA to the shared brightness cases in `move.yaml`/`stop.yaml` on `light_ct` and `group`: `raise`,
  `lower_to_off`, `raise_from_off`, `raise_after_soft_off`, `lower_to_a_limit`, `raise_stop_raise`,
  `halts_a_move`, `halts_a_move_to_off`, `stop_when_idle`.
- New `only: [zha]` case `soft_off_keeps_level`: fade to off, then a plain `light.turn_on` comes on at the start
  level.
- Widen 13i's `light_color` cases (`saturation_down_stop`, `hue_cycle_stop`, `saturation_to_a_limit`) to include
  ZHA. They run in the ZHA A60 run, with an added check that after a hue stop HA's `xy_color` matches a live read.
  If that fails, add an xy write-back as on Z2M.
- Brief the by-eye checks as `observe` blocks.

## 8. Rig run, then land it

`scripts/rig.py --action move --action stop` in the background. The color cases skip until the A60 is on ZHA.
Write `docs/bench/zha/move.md` and `stop.md` for the non-color scope. Then pytest, pre-commit, `/audit-code`, a PR,
and `merge-green`.

## Verification

- Unit: `.venv/bin/pytest tests/integrations/zha`, then `scripts/check_release.py --coverage`. `--release` lists the
  ZHA move/stop adapters as experimental.
- Rig: move and stop pass on ZHA `light_ct` and `group` with no Hue or Z2M regressions. `soft_off_keeps_level`
  passes.
- By eye (briefed, gated): the stop holds with no jump, a move up from off starts at the bottom, and a soft off
  comes back on at the old level.
- The color scope is proved later, in the ZHA A60 run (13k step 3), which clears `experimental`.
