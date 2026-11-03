# TODO: road to v0.1.0

Progress against the delivery sequence in
[`docs/plans/2026-10-23-device-side-repo-plan.md`](docs/plans/2026-10-23-device-side-repo-plan.md). The plans
hold the design; this file only tracks what is done and what is left. Tick items off in the PR that finishes them.
Delete this file in the v0.1.0 release PR.

## Releases

`v0.0.1` is out, and the HACS submission ([hacs/default#12611](https://github.com/hacs/default/pull/12611)) is
waiting for review. Until it is accepted, no release or RC is cut. Everything lands on `release/v0.0.2`, and
v0.1.0 is the next release.

## Done since v0.0.1

| Slice | What | PRs |
|---|---|---|
| 9a | Rig step files | #26, #27 |
| 6 | Z2M `turn_on_for` | #22, #23, #25 |
| 11 | Matter `turn_on_for` (plugs out of experimental) | #24, #90, #91 |
| 10 | ZHA `turn_on_for` | #31, #32, #34, #39 |
| 9c | Release gates (tiers later replaced by the release flag) | #33, #35, #36, #37, #94 |
| 7a | Hue `set_attributes`, `get_attributes`, `set_scene` | #45 |
| 7b | Hue `move`/`stop` for brightness | #48, #55 |
| 7c1 | Hue `move`/`stop` for color temp (removed in #125) | #95 |
| 9e | Native groups: decision, ZHA groupcast `turn_on_for`, core `resolve_members` | #97, #104, #106 |
| 9f | Core-aligned failure behavior | #99 |
| 13a | Zigbee probe findings | #98, #100 |
| 13b | `get_attributes` contract: switches and timer row | #101 |
| 13c | Shelly `get_attributes` | #105 |
| 13d | Matter `get_attributes` | #112 |
| 13e | ZHA `get_attributes` (experimental until the ZHA A60 run) | #114 |
| 13h | Z2M `get_attributes` | #117 |
| 13g | ZHA `set_attributes` (experimental until the ZHA A60 run) | #120 |
| — | `Transition` cache moved to core, kept per integration | #118, #119 |
| 13i | Z2M `move`/`stop` | #124 |
| 14 | Z2M color modes fixed for HA, on by default | #126 |
| — | Color temperature moves dropped on every integration: no halt of a Hue bulb's fade is clean | #125 |
| — | Six raise and lower actions replace `move` | #128 |
| 13j | Z2M `set_attributes` (experimental; rig run and test record still to do) | #130 |
| 9d (PR 1 of 3) | Rig coverage sweep: `group_color` role, `observe: roles`, color step cases for 13k | #132 |
| 9d (PR 2 of 3) | Observed-test ledger: observe only the four never-seen cases, `observe: only` | #134 |
| 9d (rig fix) | Rig waits up to 60 s for unavailable targets, then stops before changing anything | #136 |
| 13k (step 1, part) | Z2M hue and saturation test records on the A60 (`light_color`; `group_color` still to do) | #138 |
| 9d (A0) | A60 move probe: join windows self-close on Z2M and Hue; all three moves scripted (Hue by CLIP v2 only) | #142, #144 |
| — | Bench records renamed test records (`docs/test-records/`) | #146 |
| 15 (PR 1 of 5) | Rig profiles: `tests/rig/profiles/<name>.yaml`, `--profile`, `pause:` replaces `RIG_PAUSE` | #147 |
| 15 (PR 2 of 5) | Rig network clients: CLIP v2 verbs, ZHA and Z2M permit/remove/groups, registry rename, `device_by_ieee`; fakes | #149 |
| 15 (PR 3 of 5) | Rig roaming: lab bulbs move Hue → ZHA → Z2M → Hue within a run, suites in phases, fixed entity IDs, Hue home restored, `--recover` and `--roam-check` | #151 |
| 15 (PR 4 of 5) | Rig-made `ds-rig-*` groups, zones and scenes: made on each visit from `roam.groups`, renamed to fixed entity IDs, removed before each move and by `--recover`; Hue group and scene cases are lab-only | #154 |
| 15 (follow-up) | Roaming: a second Hue search only for a bulb still missing; a stranger that joins a search is named and left | #153 |
| 15 (PR 5 of 5) | Lab bring-up: direct moves, bulbs released last joined first, no one-member ZHA groups; first lab run's 12 records (`Profile \| lab`), its 26 failures a follow-up | #157 |

## To go, in order

Slice 13 detail lives in [`2026-10-27-zigbee-parity-timer-state.md`](docs/plans/2026-10-27-zigbee-parity-timer-state.md).
The A60 (the rig's only color bulb) moves into the lab (15), whose runs move it Hue → ZHA → Z2M and home, so the
A60 runs are lab runs (`--profile lab`). Each integration's code freezes before its A60 run.

Three lanes run in parallel, each in order: Z2M (`Transition` PR, 13i, 13j, 14, its A60 run), ZHA (13f),
and Hue (7c2, its A60 run). The lab lands before the first A60 run. The rig lock is shared.

- [x] **`Transition` to core**: refactor PR moving `hue/transition_cache.py` into `core/`. Unblocks 13i and 13f.
- [x] **13i** Z2M `move`/`stop`, with the hue/saturation stop probe on the A60.
- [x] **Raise and lower**: six actions, one per attribute and direction, replace `move`
  ([`2026-10-30-raise-lower.md`](docs/plans/2026-10-30-raise-lower.md)). Lands before 13j's freeze and the Z2M A60
  run.
- [ ] **Raise/lower rig run**: unattended, the six actions and `stop` on Hue and Z2M. Its records replace
  `docs/test-records/{hue,zigbee2mqtt}/move*.md` and rewrite `stop*.md`; it measures the new hue, saturation and two-call
  stop ranges for the first time.
- [ ] **13j** Z2M `set_attributes` while off. Z2M code freezes.
  Code, tests and docs merged in #130, experimental. Still to do: its rig run
  (`scripts/rig.py --action set_attributes`, with the new `sets_after_a_soft_off` case, which also runs on Hue and
  ZHA) and `docs/test-records/zigbee2mqtt/set_attributes.md`, both in the pre-release full rig run. Tick when the
  record is in.
- [x] **14** Z2M color modes fixed for HA, on by default, and 13i's xy write-back backed out
  ([`2026-10-28-z2m-color-modes.md`](docs/plans/2026-10-28-z2m-color-modes.md)). Counts toward the Z2M freeze.
- [x] **15** The lab ([`2026-11-01-lab.md`](docs/plans/2026-11-01-lab.md)): three Hue bulbs in the maintainer's room,
  the A60 among them, that a run moves directly between Hue, ZHA and Z2M, with Hue as their home network.
  - [x] PR 1: profiles (`tests/rig/profiles/<name>.yaml`, `--profile`, `pause:` replacing `RIG_PAUSE`), #147.
  - [x] PR 2: network clients (Hue CLIP v2 reads and deletes, ZHA and Z2M join and remove, registry renames), #149.
  - [x] PR 3: roaming (moves, fixed entity IDs, Hue home saved and restored, `--recover` moves the bulbs home), #151.
  - [x] PR 4: rig-made `ds-rig-*` groups, zones and scenes on each visit, #154.
  - [x] PR 5: lab bring-up (attended): the A60 moves into the lab, `profiles/lab.yaml`, a `--roam-check` round trip
    that probes the two new bulbs, #157.
- [ ] **15 follow-up** The first lab run's 26 failures (#157; findings in the lab plan; fixes in
  `docs/plans/2026-11-02-lab-run-failures.md`): group cases that expect every
  member to take color temperature (the lab group holds the White bulb), Z2M `not_stored` on the white ambiance
  bulb (`hue_native_control` since added to its options; to be rerun), a Hue `get_attributes` case that calls `turn_on_for` where Hue has
  no adapter, ZHA not keeping a setting made while off, a full-brightness power-on after a soft off, and single
  readings on the A60 and the White bulb.
- [ ] **Z2M A60 run** (13k step 1): full Z2M suite on the lab, with the `group_color` cases on its rig-made group
  holding only the A60. Attended for its four
  observed cases (9d ledger in the [plan](docs/plans/2026-10-30-rig-coverage-sweep.md)). Clears `experimental` on the
  Z2M adapters it proves.
- [ ] **7c2** Hue `raise_saturation`/`lower_saturation`, built against the A60
  ([`2026-10-27-hue-move-color.md`](docs/plans/2026-10-27-hue-move-color.md)).
- [ ] **Hue A60 run** (13k step 2), on the lab: `set_attributes` color (rgb, hs and xy) and gamut clamp, the `get_attributes`
  color read, 7c saturation, with no `light_color` skips. Attended for `sets_color_while_off`. Hue code freezes. Clears `experimental` on the Hue adapters it proves.
- [x] **13f** ZHA raise, lower and `stop`, after the `Transition` PR. ZHA code freezes. Built on `wt/zha-move-stop`
  over the six raise and lower actions; lab runs and records in its
  [handoff note](docs/plans/2026-10-28-zha-move-stop.md#status-and-handoff-2026-11-02).
- [ ] **13f follow-up** One core watch for light calls from HA, which drop the predictions of the lights a call names:
  a listener in `core/` with a resolver per integration (call entities to cache entries, plus a hook after the
  forget). Hue's (`hue/report_filter.py`, which also hands back its `predicted_state` ends) and ZHA's
  (`watch_ha_changes` in `zha/fade.py`) move onto it, and Z2M, which has none, gets one: a fix for a prediction left
  stale by a change from HA mid-fade, as 13f's lab probe found on ZHA. Rig run on Hue's predicted-state cases and Z2M's
  raise, lower and `stop` before it lands. `opus`: it changes released Hue behavior.
- [ ] **ZHA `set_attributes` while off on Hue bulbs** (bucket C of
  [`2026-11-02-lab-run-failures.md`](docs/plans/2026-11-02-lab-run-failures.md)): the lab's three Hue bulbs on ZHA
  ignore the `MoveTo*` writes the adapter sends while they're off (ExecuteIfOff), and come back on at their old values.
  It failed on two lab runs (2 Nov, and 3 Nov with HA on `2d70127`): `sets_while_off[light_ct]` (LTA009 on at 3984 K,
  not 2700), `[group]` (the White at 254, not 102), `sets_hs_while_off` and `sets_xy_while_off` (the A60 on at the
  setup's blue). `sets_after_a_soft_off` passes on both roles, and the 28 Oct record passed on the house LTA004, so
  it isn't every Hue bulb or every off; probe 13a also said these bulbs store all three. They ignore the level preset
  before `raise_from_off` the same way, which 13f fixed with Hue's own `0xFC03` `multiColor` write (`zcl.hue_turn_on`),
  and Z2M passes on the same bulbs because `hue_native_control` writes there.
  1. Probe first (ask Jason): on ZHA, write CT, hs and xy while off as the adapter does, and read the Color cluster
     (`ColorTemperatureMireds`, `CurrentX`/`CurrentY`, `ColorMode`) and `CurrentLevel` right after, then after HA's
     plain on. That tells a dropped write from one HA's on overrides.
  2. If they're dropped: for an off light with cluster `0xFC03`, send the stored values as one `multiColor` write
     without the on flag (Z2M's encoding: brightness, mireds or xy, no fade), via zigpy as `zcl.hue_turn_on` does;
     other lights keep ExecuteIfOff. Probe the write on one bulb before building. If the bulbs won't store even that,
     refuse the fields on those models, as `DROPS_WHILE_OFF` does for the E11-G13, and record why.
  3. Rig: `--profile lab --integration zha --action set_attributes`. `opus`: a design call on what the adapter sends,
     and a wrong `multiColor` encoding only shows on the bulb. Lands before the ZHA A60 run.
- [ ] **ZHA A60 run** (13k step 3), on the lab: ZHA color suites, `set_attributes` hs and xy included. Attended for
  `sets_color_while_off`. Clears `experimental` on the ZHA adapters it proves.
- [ ] **9d** Rig coverage sweep for the non-color scope
  ([`2026-10-30-rig-coverage-sweep.md`](docs/plans/2026-10-30-rig-coverage-sweep.md)). 13k covers the color part.
- [ ] **12** v0.1.0: no adapter left `experimental` (`scripts/check_release.py --release`); README feature table
  current; release checklist adapted from hue_dimmer; `predicted_state` default reviewed against the rig runs and
  regression issues since #77.

## After v0.1.0

- **9b** Remote tester flow, once an adapter needs hardware the rig lacks.
