# Tuya datapoint countdown, single-endpoint devices, on Zigbee2MQTT (Labs)

Copy this plan to `docs/plans/2026-11-24-tuya-datapoint-single-endpoint.md` as the first commit. Part of #437 (not
closing it: multi-gang stays open). It narrows [2026-11-15-tuya-datapoint-countdown.md](2026-11-15-tuya-datapoint-countdown.md)
to single-endpoint devices and amends its Design 2 (the call); add a one-line pointer there. It **supersedes Decision
67** of [2026-11-14-device-classes.md](2026-11-14-device-classes.md) (Decision 6 below): add a one-line note under
Decision 67 pointing here.

## Coordination

Intent: serve `turn_on_for` and `turn_off_for`, in Labs, on the single-endpoint Tuya datapoint devices Zigbee2MQTT
gives a countdown in seconds, by one publish `{"state": …, "countdown": N}`; the first `turn_off_for` on Zigbee.
Touches: `custom_components/deviceside/integrations/zigbee2mqtt/` (`families/tuya/`, `refusals.py`, a new
`turn_off_for.py`, `__init__.py`), `tests/integrations/zigbee2mqtt/`, `docs/integrations/zigbee2mqtt/`
(`index.md`, `internals.md`, `devices.yaml`, a new research file), `scripts/gen_features.py` (`NO_PATH`),
`docs/integrations.md`, `docs/plans/`, README and `docs/device-compatibility.md` (regenerated).
Depends-on: none.

## Context

#437: Tuya datapoint devices (TS0601 and kin) are refused on `turn_on_for` today (`tuya_mcu`, NotBuilt, harms: Z2M
sends a plain On and the device stays on). Z2M's own `countdown` key serves them. Multi-gang devices need per-endpoint
addressing (Z2M `internals.md`, future work), so this PR takes the single-endpoint ones only: about 18 definitions,
mostly dimmers (`TS0601_dimmer_1_gang_1` alone has 30 maker strings). The countdown toggles at zero, so it also gives
`turn_off_for`, which no Zigbee device has today.

## Decisions (Jason, 2026-11-24)

1. **Scope:** single-endpoint definitions only; both `turn_on_for` and `turn_off_for`; Labs, no hardware run to merge.
2. **Admitted:** every single-endpoint definition with a settable countdown in seconds, except Decision 67's
   exclusions and the three valves whose DP 11 may be a preset run time (a valve left open): FK-BV05, ZVL-PRO,
   ZG-308Z. FK_V02 (standard 0–43,200 "Countdown timer in seconds") and Nous D5Z (readback shows 0 while running,
   irrelevant as no read is served) are in.
3. **Limits per device:** each definition gets its own expose's `value_max`, as one class per limit sharing one call
   (core clamps by class through `OwnCall.limits`, so a per-device limit needs a class per limit).
4. **One publish, amending Decision 67's two-phase pattern.** Provenance, to record in the research file (step 1):
   Decision 67's pattern was Jason's design call on 2026-11-14, reasoned from the toggle, with no device evidence (no
   datapoint device has been in the lab). Its converter A twin was dropped on 2026-11-15 after the TS011F probe and the
   ZHC reading (`internals.md`, "The harm the order prevents"). Converter B gives the same guarantee: `tz.datapoints`
   (ZHC `src/lib/tuya.ts` 3299–3340 at `afdaa028`) loops the message's keys in payload order and awaits each
   `sendDataPoints` (`entity.command`, which rethrows a failed send), so a failed `state` throws before `countdown`
   goes out; and it returns the state optimistically, so Z2M's state publish is its own echo, which a "wait for the
   report" can't tell from the device's. Lab-plug probes can't test this (converter A, a different call: tenet 5).
6. **Decision 67 is superseded by this plan** (Jason, 2026-11-24), not amended: dated plans are history. What
   carries over, restated here as this plan's own: the exclusions (LYAI-14, ZBN-DJ-63, `TS0601_fan_switch`,
   `TS0601_smart_temperature_switch`, minute/hour/enum timers, the garage opener, Manhot MH03, Moes ZS-D) and D5Z's
   inclusion (harmless now because no read is served). What changes: the key is an allowlist of research-named
   definitions (The classes); limits are one class per `value_max` (Decision 3); FK-BV05 and ZVL-PRO are out
   (Decision 2); the safe call pattern is dropped (Decision 4).
5. **Toggle risk, launched with a caveat:** Tuya's general countdown spec says the countdown toggles at zero and is
   cleared when the on/off state changes (local button, app, timer)
   ([developer.tuya.com, General Countdown](https://developer.tuya.com/en/miniapp/solution-ai/ability/lamp-solution/lamp/module-set/common-countdown.md)).
   A light turned off by hand mid-timer shouldn't come back on; `index.md` says it is Tuya's spec, not measured here.
7. **An own-calls-only scope in core** (Jason, 2026-11-24, after step 3 found the gap): core had no shape for an
   adapter that serves only own calls (`execute` abstract; a None class passed `AdapterScope.refusal`, as `harms()`
   needs a refusal entry, and reached `execute`). `AdapterScope` gains a way to say it serves only its own calls: the
   dispatcher refuses every target whose class has none (None or Unplaced as `class_unknown`, any other class as
   `not_built`), and core gives such an adapter a default `execute`, so it holds no stub. `Z2MTurnOffFor` uses it.
   Chosen over making `harms()` entry-free (changes every harming adapter) and a Z2M NotBuilt entry (protection
   hanging on an unrelated entry). Core change: Opus implements, and its range gets an `/audit-code`.

## The classes

New module `families/tuya/datapoint.py` (the family's, beside `countdown.py`) holds:

- `DATAPOINT_DEFINITIONS: Mapping[str, int]`, Z2M definition model → the expose's `value_max` in seconds, from the
  research note ([2026-11-14-tuya-datapoint-countdown.md](../integrations/zigbee2mqtt/research/2026-11-14-tuya-datapoint-countdown.md)),
  each with its row number in a comment. Confirm each model string and max at ZHC's current release before coding;
  record any difference in the research file (step 1).
  - 43,200: ZDMS16-1, ZOT60, FK_V02, GL-SPI-206P, SFD02-Z, SFD02-Z_2, QADZ1LR, `TS0601_dimmer_1_gang_1`,
    `TS0601_dimmer_1_gang_2`, `TS0601_dimmer_5`, MG-ZG01W, `_TZE28C1000000_jlbsptkl`, ZMS-206US-1.
  - 86,400: TO-DM-W/B, `TS0601_multifunction_switch`, D1Z, D5Z.
  - 7,210: AVATTO ZBS16 (unit `seconds`, "Countdown to turn device off").
  - Left out, each with its reason in a comment: LYAI-14, ZBN-DJ-63, `TS0601_fan_switch`,
    `TS0601_smart_temperature_switch` (Decision 67); FK-BV05, ZVL-PRO, ZG-308Z (Decision 2); minute, hour, enum and
    read-only timers; `TS0601_power_monitoring_switch` (unit `m`, unclear); every multi-gang definition.
- One class per limit: `tuya_datapoint` (43,200 s), `tuya_datapoint_24h` (86,400 s), `tuya_datapoint_2h` (7,210 s),
  domains light and switch. An allowlist, not an expose rule: `docs/evidence.md` (In Labs) admits only the identities
  research names, so a definition ZHC adds later stays `tuya_mcu` until someone reads it.
- Rules in `ZIGBEE_RULES`, before `TUYA_TS011F` (ZOT60 is a TS011F) and `TUYA_MCU`: `definition_model` matching the
  class's models (escaped) and `exposes` containing `countdown`. `exposes` holds top-level, endpoint-less properties
  only (`rules.definition_fields`), so this doubles as the single-endpoint guard. Reuse the existing rule fields; no
  new field. The registry fallback can't see the definition's exposes, so such a device stays Unplaced until
  `bridge/devices` lists it (as converter A's do).

## The call

In `families/tuya/datapoint.py`, one `OwnCall` per limit, sharing one `send`:

- `turn_on_for`: `{"state": "ON", "countdown": int(duration_s)}` to the device's set topic via `bridge.publish_set`.
  With light fields on a dimmer, first run the existing `Z2MTurnOnFor._turn_on` (light.turn_on, waits for Z2M's state);
  the countdown publish still carries `state` first. Lift `_turn_on` to a module function if the own call can't reach
  it cleanly.
- `turn_off_for`: `{"state": "OFF", "countdown": int(duration_s)}`; the toggle at zero turns it back on.
- Result `sent`; `set_check` (via `Z2MAdapter.execute_own`) makes a logged failure `rejected`. No reads: no time left
  is served.
- `DurationLimits(min_s=1, max_s=<limit>, step_s=1)`; core rounds and clamps and reports `clamped_to`.

## turn_off_for on Zigbee2MQTT

New `integrations/zigbee2mqtt/turn_off_for.py`, `Z2MTurnOffFor(Z2MAdapter[TimedRequest])`, registered in
`__init__.py` `ADAPTERS`. Scope: `**class_scope("turn_off_for")` (the datapoint classes' own calls, `labs(...)`),
`native_groups=False` (a group falls back to members), `confirmable=False`, `supports` adds `not_addressable`. Every
other class is out of scope, so refused as not built. If core has no shape for an adapter that serves only own calls
(its `execute` never reached), stop and report it: that is a core change for an Opus review, not something to work
around.

## Scopes, refusals and docs

- `families/tuya/__init__.py`: add the classes to `CLASSES` and `_ALL` (card order); `scopes` gets
  `turn_on_for` (`labs(...)` plus own calls, merged with the existing) and a new `turn_off_for`.
- `refusals.py`: `TUYA_MCU` stays NotBuilt on `turn_on_for` (multi-gang and the rest), its comment updated.
  `get_attributes`: whatever `core/registry.py` `check_queries` needs for a class another action serves, as
  NotBuilt ("whether it reports time left is unprobed"), not NoKnownMethod.
- `scripts/gen_features.py` `NO_PATH`: `turn_off_for` impossible on Zigbee groups (and Matter) only.
  `docs/integrations.md`, What can't be done: non-Tuya Zigbee devices have no call for `turn_off_for`.
- `docs/integrations/zigbee2mqtt/index.md`: one `####` section for the three classes, under `### Tuya` as the page nests
  the Tuya classes, since they differ only by limit (step 4's plan review; the plan first said a `###` per class): what
  sets them apart, why admitted, the toggle caveat citing Tuya's spec, the source; `devices.yaml`: each class's card phrase and section; `internals.md`: a "Tuya's
  datapoint countdown" section with the call and the ZHC reading, linking the research file. Regenerate README and
  `docs/device-compatibility.md` (`scripts/gen_compat.py`).

## Steps

1. Branch `wt/tuya-datapoint-single` off `main` in its own worktree; `pr-draft` this plan. Copy the plan to
   `docs/plans/`, add the pointer in the 2026-11-15 plan and the superseded note under Decision 67, and write
   `docs/integrations/zigbee2mqtt/research/2026-11-24-tuya-datapoint-call.md`: Decision 4's provenance and ZHC reading
   (re-read `tz.datapoints` at the ZHC that Z2M 2.14.3 ships; quote the lines), Decision 5's Tuya spec quotes, and the
   model string check.
2. Classes and rules (`datapoint.py`, `__init__.py`), with classification tests.
3. The call and `turn_on_for` wiring; the `turn_off_for` adapter; call transcripts.
4. Refusals, `NO_PATH`, docs, regenerated output.

One implementer (opus: it admits devices whose failure harms, and may hit a core gap in step 3), then a `plan-reviewer`
(opus). Audit the PR's diff (`/audit-code`, then `owner-findings`) before `gh pr ready`.

## Verification

- `.venv/bin/pytest -n auto --transcripts=check`; transcripts for the new `turn_off_for` and the datapoint
  `turn_on_for` calls added on purpose (`docs/evidence.md`, Release gate).
- Classification tests (`tests/integrations/zigbee2mqtt/test_classification.py`, the family's `test_classes.py`), with
  a `bridge/devices` fixture per case:
  - one device per limit class;
  - ZOT60 placed in `tuya_datapoint`, not `tuya_ts011f`;
  - GL-SPI-206P placed in `tuya_datapoint`, not `gledopto`;
  - LYAI-14 staying `tuya_zcl` (a TS0049 switched over ZCL, with a ZCL manufacturer string), and ZBN-DJ-63, FK-BV05
    and a multi-gang ZMS-206EU-2 staying `tuya_mcu`;
  - a datapoint device before `bridge/devices` arrives staying Unplaced.
- Call tests (`tests/integrations/zigbee2mqtt/families/tuya/test_datapoint.py`, modeled on `test_countdown.py`):
  - the payloads for both actions;
  - the per-class clamp (86,400 s accepted on `_24h`, clamped on `tuya_datapoint`);
  - light fields running `_turn_on` first;
  - a logged failure answering `rejected`;
  - a group falling back to members;
  - every other class refused on `turn_off_for`.
- `scripts/gen_compat.py --check`, the gen_features check, `scripts/check_ha_literals.py`.
- No rig run gates the merge (Labs on research). **The Labs-lift decision** (tenet 8): one bought single-endpoint
  device (`TS0601_dimmer_1_gang_1` or ZMS-206US-1) on the rig, probing turn_on_for, turn_off_for, the cancel on a
  local toggle, and an unreachable device's set (the Decision 4 claim), recorded as a research file and test record.

## Handoff

2026-11-24, from the orchestrating session.

- **Done:** steps 1–4, each with its implementer and a `plan-reviewer`, findings fixed or answered in each step's `Plan review:` commit
  note. Decision 7 (own-calls-only scope in core) came from Jason mid-step 3; its core range `be230c8d..8c64fb74` had
  its own `/audit-code` (clean, 3 Lows; two fixed in `0937f1ea`, the `Request` vs `RequestT` signature Low left).
  Branch tip `422413c9`; full suite, `gen_compat --check`, `gen_features --check`, `check_ha_literals` pass there.
- **Next:**
  1. Merge `origin/main` into the branch (merge, never rebase): #581 (Z2M any base topic) landed as `46e8e5c6`.
     publish_set keeps its signature; addressing helpers take the base topic, `Address` is `(base, kind, z2m_id)`,
     `bridge_cache.get(hass, base)` needs the base, `restore_journal` keys are `Address`, and Z2M test devices need a
     bridge `via_device` (fixture helpers set it). Expect fixes in `families/tuya/datapoint.py`,
     `turn_off_for.py`, `light_turn_on.py`, `tests/integrations/zigbee2mqtt/families/tuya/test_datapoint.py` and
     the classification tests. Run the four checks; transcripts should not change from the merge.
  2. The PR audit (none recorded yet; one was briefed at the pre-merge diff and stopped): `audit-gate brief pr`,
     Opus auditor (binding-rule surface: AdapterScope). The gate guesses the plan as the 2026-11-14 one: correct the
     brief to this plan and add Decisions 7, D1Z/SFD02-Z_2 kept, LYAI-14 `tuya_zcl`, one `####` for the three classes.
     Then `audit-gate record`, `owner-findings`, `audit-gate status`.
  3. On CLEAN: write the PR summary, `gh pr ready 582`, then `merge-green 582 --squash --delete-branch` backgrounded.
- **Open decisions:** none. Owners: every changed path is @jasonmx's (`scripts/owners.py`); no owner-notice names
  another maintainer. PR has no comments or reviews as of 10:00.
- **Branch:** `wt/tuya-datapoint-single`. **Worktree:** `.claude/worktrees/tuya-datapoint-single`. **PR:** #582 (draft).
