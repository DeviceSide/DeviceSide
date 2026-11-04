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
| 13k | Flag-clearing follow-up: composed group proof (CLAUDE.md), `sets_color_while_off` reads its color back, `predicted_state` out of the Hue saturation scopes, `saturation_stop_raise` and `hue_stop_raise`; clears Hue `raise_saturation` and `lower_saturation` (Z2M `lower_hue`'s group case failed twice on the lab's Z2M mesh) | #NNN |
| 13k | Flag audits clear 18 adapters on the lab records: Hue, ZHA, Z2M ([hue](docs/plans/2026-11-04-flag-audit-hue.md), [zha](docs/plans/2026-11-04-flag-audit-zha.md), [z2m](docs/plans/2026-11-04-flag-audit-z2m.md)) | #201, #202, #203 |
| 13j | Z2M `set_attributes` and `stop` on the lab: read after the write fade, soft-off cut, rig settles and reads a joined bulb | #192, #196 |
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
| 15 (follow-up) | Lab run failures, fixes before the rerun: the rig checks what each group member can take and shows it absent (A1), skips a case with no adapter (A3); Hue and ZHA `set_attributes` replace the level HA keeps after a soft off (B); Hue `predicted_state` starts a raise from off at the lowest step, not `min_dim_level` (F) | #160, #161, #162, #163 |
| 15 (follow-up) | Rig checks every phase's devices before the gate, so an unpowered one stops a roaming run before any move; `--check` runs that check alone | #165 |
| 13f | ZHA raise, lower and `stop`: the six actions on ZHA (experimental until the ZHA A60 run), a Hue bulb raised from off turned on at the bottom by Hue's own command, the fit's deadband; lab records for each | #167 |
| 15 (follow-up) | Rig: a failed Z2M interview is asked again, Z2M logs joins at `info`, and a run stopped by a move keeps the phases before it | #169 |
| 15 (follow-up) | Rig runs each integration's fixed-bulb cases in parallel lanes, then the rest in turn; `--serial` keeps the old order | #171 |
| — | ZHA `set_attributes` waits out zha's transition flag before its refresh, so HA shows a setting made right after an off (bucket C) | #172 |
| 15 (follow-up) | Rig shared between sessions: a lock per integration and HA shared or exclusive (deploys, option suites), a journal per run, `--hold` for probes; the pause ledger and roam `networks`/`home` follow | #175 |
| 15 (follow-up) | Rig: runs side by side share their pauses through a ledger (last one out resumes), `pause:` by integration, and roaming bulbs visit only the networks a profile declares, from each bulb's `home` | #177, #178 |
| 15 (follow-up) | Rig step fixes from the lab rerun: hue moves wait for the setup color; `halts_brightness_and_saturation` starts inside gamut C | #191, #193 |
| 15 (follow-up) | Rig: a test record names the devices seen when its suite ended, not after the bulbs moved home | #194 |
| — | ZHA `set_attributes` reads back once the write's 0.4 s fade has ended, then once more, so HA shows the color temperature written after a soft off | #197 |
| 15 (follow-up) | Rig: Z2M joins open on the coordinator only; a bulb that missed the Hue bridge's Leave is searched back, released alone and given one more window | #174 |
| 7c2 | Hue `raise_saturation` and `lower_saturation`, and `stop` halting them (experimental until the Hue A60 run) | #179 |
| 13f (follow-up) | One core watch for light calls from HA drops the predictions of the lights a call names; Hue and ZHA move onto it, Z2M gains one | #181 |
| 15 (follow-up) | Rig clear gate: with `RIG_BLOCKER_ENTITY` set, env-approved runs and `--hold` probes go only while the household's blocker sensor is off, and abort, putting devices back, once it reads on twice | #180 |
| 15 (follow-up) | Rig captures Z2M's and HA's logs for every run (kept after a failure), and `--debug-logs` raises both to debug | #183 |
| 15 (follow-up) | Tests no longer color the cmux workspace running them green (a locks test's `monkeypatch.undo()` reached the real cmux) | #184 |
| 15 (follow-up) | Rig clear gate per profile: `pre_authorized: true` profiles (the lab's) skip `RIG_BLOCKER_ENTITY`; others stay gated | #187 |

## To go, in order

Slice 13 detail lives in [`2026-10-27-zigbee-parity-timer-state.md`](docs/plans/2026-10-27-zigbee-parity-timer-state.md).
The A60 (the rig's only color bulb) moves into the lab (15), whose runs move it Hue → ZHA → Z2M and home, so the
A60 runs are lab runs (`--profile lab`). Each integration's code freezes before its A60 run.

Three lanes run in parallel, each in order: Z2M (`Transition` PR, 13i, 13j, 14, its A60 run), ZHA (13f),
and Hue (7c2, its A60 run). The lab lands before the first A60 run. Lanes on different integrations run the rig side by side (#175); a deploy waits for them all.

- [x] **`Transition` to core**: refactor PR moving `hue/transition_cache.py` into `core/`. Unblocks 13i and 13f.
- [x] **13i** Z2M `move`/`stop`, with the hue/saturation stop probe on the A60.
- [x] **Raise and lower**: six actions, one per attribute and direction, replace `move`
  ([`2026-10-30-raise-lower.md`](docs/plans/2026-10-30-raise-lower.md)). Lands before 13j's freeze and the Z2M A60
  run.
- [ ] **Raise/lower rig run**: unattended, the six actions and `stop` on Hue and Z2M. Its records replace
  `docs/test-records/{hue,zigbee2mqtt}/move*.md` and rewrite `stop*.md`; it measures the new hue, saturation and two-call
  stop ranges for the first time.
- [x] **13j** Z2M `set_attributes` while off. Z2M code freezes.
  Code, tests and docs merged in #130, experimental. Lab record `docs/test-records/zigbee2mqtt/set_attributes.md`
  (3 Nov, all 15 unattended cases pass, and again on two later full runs; `sets_color_while_off` observed is still to watch before the adapter leaves
  `experimental`). Two causes cleared on the way: the read-back compared mid-fade (the adapter now waits out the
  0.4 s write fade once, #192), and Z2M, which publishes the read-backs of a restore's commands about 0.5 s later and
  republishes a group's state onto every member (Z2M's `extension/groups.ts`: a member's `ON` always goes to its groups, a group's state is written onto every member, and an `OFF` reaches the group only when every member is off), overwrote a light's `off` in the next case with a late `on` (the rig
  now settles 1.5 s after a restore). A/B on the lab (settle 0 vs 1.5 s, same tree): with 0, both cases failed again in two
  of the next three runs (with a setup failure and a bulb dropping off the network in the third); with 1.5, 15/15 in
  the one run that got through. A real group's members still show Z2M's aggregate state, which the adapter can't
  correct.
  One settle-0 run also failed `sets_while_off[light_ct]` with `not_stored`: a color temperature read 0.7 s after
  the write returned 317 (written 370) and the next read 370, a slow bulb fade past the 0.6 s wait. `_stored` now
  reads again (twice, 0.5 s apart) before it calls a write ignored.
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
  `docs/plans/2026-11-02-lab-run-failures.md`). Fixes merged (#160–#163, #172); left: the lab rerun, which also
  retries Z2M `not_stored` with `hue_native_control` on (D) and the single readings (E), then fixes for what repeats.
- [ ] **Watched lab session** (13k), `--profile lab`, the A60 visiting each network: Hue `saturation_down_stop`,
  `halts_brightness_and_saturation`, `sets_color_while_off`; ZHA `hue_cycle_stop`, `saturation_down_stop`,
  `sets_color_while_off`; Z2M `halts_a_lower_to_off`, `hue_cycle_stop`, `saturation_down_stop`,
  `sets_color_while_off`. Unattended alongside: Z2M `lower_hue` `cycles_down_the_wheel[group_color]` (failed twice
  on 4 Nov: the sideboard missed the group stop, then a read errored) and ZHA `lower_brightness`. Then the PR
  clearing the last flags: every `set_attributes` and `stop`, Z2M `lower_hue` and ZHA `lower_brightness`.
- [x] **7c2** Hue `raise_saturation`/`lower_saturation`, built against the A60
  ([`2026-10-27-hue-move-color.md`](docs/plans/2026-10-27-hue-move-color.md)). Experimental until the Hue A60 run.
- [x] **13f** ZHA raise, lower and `stop`, after the `Transition` PR. ZHA code freezes. Built on `wt/zha-move-stop`
  over the six raise and lower actions; lab runs and records in its
  [handoff note](docs/plans/2026-10-28-zha-move-stop.md#status-and-handoff-2026-11-02).
- [x] **13f follow-up** One core watch for light calls from HA, which drop the predictions of the lights a call names:
  a listener in `core/` with a resolver per integration (call entities to cache entries, plus a hook after the
  forget). Hue's (`hue/report_filter.py`, which also hands back its `predicted_state` ends) and ZHA's
  (`watch_ha_changes` in `zha/fade.py`) move onto it, and Z2M, which has none, gets one: a fix for a prediction left
  stale by a change from HA mid-fade, as 13f's lab probe found on ZHA. Rig run on Hue's predicted-state cases and Z2M's
  raise, lower and `stop` before it lands. `opus`: it changes released Hue behavior.
- [x] **ZHA `set_attributes` right after an off** (bucket C of
  [`2026-11-02-lab-run-failures.md`](docs/plans/2026-11-02-lab-run-failures.md)): `sets_while_off[light_ct]`,
  `[group]`, `sets_hs_while_off` and `sets_xy_while_off` failed on two lab runs. Probed 3 Nov: the bulbs store every
  write. zha skips `update_entity` for 1.5 s after an HA `turn_off`, and ZHA applies no color reports, so HA showed the
  old color after the next on. Fixed (#172): the refresh waits out zha's transition flag. Rig proof rides the
  pre-release run.
- [x] **Z2M lab: stop on the lab bulbs since 3 Nov's resets.** All unattended cases pass (3 Nov, and again on two later full runs; record
  `docs/test-records/zigbee2mqtt/stop.md`). Causes: with Hue native control on, Z2M sends a soft off as Philips'
  own command, which `brightness_move: stop` doesn't end, so `stop` now also cuts a soft off of ours with
  `state: ON` at its predicted brightness (as on Hue); the cases' setup `set` fade was still running when a raise
  started, so they wait 1.5 s; and a bulb newly joined to Z2M has no `color_mode` in its state (HA's MQTT light
  then shows no `brightness`, which failed every group setup and, through it, two group color checks), so the
  rig reads each bulb once after it joins. A lost read on the sideboard's radio path was seen once (one color read
  unanswered for Z2M's 10 s timeout); the lab join-parent plan covers it. A 180 s probe of live reads on it (3 Nov, 19:5x) failed on its first sample with
  a read error, and the bulb then left the network on the move home (the fourth move that has dropped a lab
  bulb): the sideboard's link is the weak point, not the adapters. Repeated after it was re-added (3 Nov, 20:28):
  Z2M's log shows the coordinator's source route to it failing (`ZIGBEE_SOURCE_ROUTE_FAILURE`, all 7 in the run target
  it) after its relay hop flipped from the corner bulb to other routers (one a household device, LQI 108 to 120),
  then `ZIGBEE_DELIVERY_FAILED` on the read. The cause is the mesh path, not the adapter; fixing it needs the
  join-route plan or a better-placed relay. Source-route failures hit many nodes in nearly every lab run (a household
  device most), so the mesh drops routed messages in general. A one-retry on `Delivery failed` was tried and dropped: when
  it first fired (3 Nov, 22:48) the second read got no reply for over 20 s, so the bulb was unreachable for longer than a
  route rebuild takes, and the adapter's error was right. The other lab failure seen, a newly joined bulb's first read
  unanswered (no `color_mode`, no brightness in the case's setup), the rig now tries up to three times.
  A 20-minute probe at one read every 4 s (3 Nov, 23:04) still lost one: the bulb was on a direct link (no relay, LQI
  148 to 156), the coordinator's frame was acknowledged (`status=OK`), and the bulb never answered the `genOnOff` read
  (Z2M's own 10 s timeout fired), yet it answered another command five seconds later. So at least some drops are the
  Hue Essential not answering a read over a healthy link, not the mesh. Open: whether a second read a moment later is
  answered (it was not in the 22:48 case, which waited over 20 s).
  Across all 33 kept Z2M logs of 3 Nov, all 7 failed reads are the sideboard's (about 5,600 commands to it); the corner
  (about 1,200) and desk (about 400) bulbs, on the same mesh, had none. Too few to be conclusive for those two, but it points at
  the bulb, the Hue Essential.
  The sideboard is also the only different model on the mesh: the Hue Essential (firmware 1.164.2); the corner and desk
  bulbs are the full-range white ambiance (1.163.1) and white A60 (1.104.2) lines. A bulb swap with the corner would settle it.
- [ ] **9d** Rig coverage sweep for the non-color scope
  ([`2026-10-30-rig-coverage-sweep.md`](docs/plans/2026-10-30-rig-coverage-sweep.md)). 13k covers the color part.
- [ ] **12** v0.1.0: no adapter left `experimental` (`scripts/check_release.py --release`); README feature table
  current; release checklist adapted from hue_dimmer; `predicted_state` default reviewed against the rig runs and
  regression issues since #77.

## After v0.1.0

- **9b** Remote tester flow, once an adapter needs hardware the rig lacks.
