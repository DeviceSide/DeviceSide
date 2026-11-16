# Device facts across integrations: call signatures and lofted levels

**When:** after v0.1.0 ships (Jason, 2026-11-14). Tracked in the issue named in the PR that lands this plan.

## Coordination

Intent: A firmware fact proven on one integration counts on every integration that sends the device the same call. A
device Verified on Zigbee2MQTT becomes Documented on ZHA when ZHA sends it the identical frames. A harmful failure
banned on one integration is refused wherever that call goes to that device.
Touches: custom_components/deviceside/core/{scope.py, adapter.py} (call signatures, a class's signature),
docs/models.yaml (device facts), docs/evidence.md (Documented, Contrary evidence), CLAUDE.md (Where facts go),
scripts/gen_compat.py and scripts/check_release.py (lofting, coverage), the integration packages that send a shared
call (Zigbee2MQTT and ZHA first), and their tests.
Tests-with: none expected. The rig writes records as it does now, and lofting is computed from them.
Depends-on: the device-classes plan (`2026-11-14-device-classes.md`) through step 7 and its Decisions 34, 35, 66 and 68.

## Why

- **Firmware facts belong to the device and the call, not the integration.** "This plug reads 0x42 `on_time` as
  seconds" is true whether Zigbee2MQTT or ZHA sends the frame. Today a device Verified on Zigbee2MQTT stays
  Experimental on ZHA until a ZHA run. That leaves Documented coverage, which the evidence rules already allow,
  unclaimed.
- **Bans have the same gap.** A doesn't-work entry with `harms` on one integration doesn't protect users of another
  that sends the same call.
- **"Same call" must be explicit.** ZHA's spec call to `_TZ3000_typdpbpg` (0x42 in tenths) and Zigbee2MQTT's Tuya
  recipe (On, then 0x42 in whole seconds) are different calls. The device was fine and the call was wrong (step 7).
  A fact can carry across only with the call it was proven on attached.
- **Tenet 5 already covers this:** "proof follows the call and the class". Documented already means a call that
  differs from a Verified class's call only in addressing. What's missing is a way to name a call independently of
  the integration that sends it, so that the comparison is mechanical, not argued afresh in every PR.

## Design

### Call signatures

- A **call signature** is a named constant in core for one wire-level call shape. Examples:
  `zcl.on_off.timed_off.tenths` (spec), `zcl.on_off.timed_off.tuya_seconds` (On, then 0x42 with N whole seconds in
  both fields), `tuya.dp.countdown` (state, wait for the report, then the countdown datapoint), and
  `zcl.on_off.timed_off.ewelink_tenths`.
- Each class names the signature its integration sends for each action, beside its level. Two integrations share a
  signature only when their frames match: command IDs, fields, units, order, and any preceding command. A unit test
  in each package pins the frames against the signature's reference payload, so a drift fails CI.
- Bridges that hide the wire (Hue, Matter, Shelly's RPC) get their own signatures and share them with no one.
- Integration-side behavior is part of the call. Zigbee2MQTT's datapoint countdown toggles at zero, retries differ,
  and a groupcast is not a unicast. Where it differs, the signature differs.

### Device facts

- **One shared home**, `docs/models.yaml`, already "models across integrations", gains a `facts` list per model. Each
  fact is keyed on (model ID, manufacturer string, firmware where it decides) and a signature. It holds the outcome
  (works, with the unit where one applies; doesn't work; harms) and its source, either a record path or a credible
  report link.
- A fact is written where its evidence lands: a record's PR adds or confirms it, and a harmful report adds it under
  Decision 68's rule.

### Lofting

- `gen_compat` and `check_release` read the facts. When a class on integration B sends signature S to a device that
  has a Verified fact for S, that device is Documented on B, and the card cites A's record.
- A harm fact for S adds a doesn't-work entry with `harms` on every integration whose class sends S to that device.
  It is generated, not hand-copied, so the refusal and the card agree everywhere.
- Lofting never raises past Documented, and never crosses signatures.
- What the maintainer judges shrinks to one question: does B's call really match S? The frame-pinning test answers
  it, and the PR that adds B's signature argues it.

## Steps

1. **Signatures in core.** Define the constants and a class's per-action signature. Fill them in for Zigbee2MQTT and
   ZHA, with frame-pinning tests. No level changes yet.
2. **Facts in `docs/models.yaml`.** Add the schema and a validator, and seed facts from existing records and
   Decision 35's bans.
3. **Lofting.** gen_compat and check_release compute Documented and doesn't-work from the facts. Update evidence.md's
   Documented and Contrary evidence sections and CLAUDE.md's Where facts go. Opus audit, as this is the binding-rule
   surface.
4. **Spread.** Hue, Matter and Shelly declare their own signatures, so that each class states its call even where
   nothing is shared.

## Open questions

- Should a fact carry firmware ranges, or only exact firmware with a "holds across firmware until contradicted" rule
  (tenet 3)?
- Does the Tuya cloud integration, if ever added, share any signature? Likely not: it is a different call entirely.
- Until this lands, step 7's ZHA Tuya branch argues Documented in its PR body under tenet 5, by hand.
