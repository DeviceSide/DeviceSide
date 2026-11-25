# Brightness floor: 0.4 % is level 1, on Zigbee2MQTT's Hue bulbs too

2026-11-25. Branch `wt/brightness-floor`, worktree `deviceside-wt/brightness-floor`, PR #613.

## Coordination

Intent: Write down that 0.4 % is a light's lowest level (level 1) and every level is reachable; pin it on the rig; and
make Zigbee2MQTT's Hue fades reach level 1, where Z2M's converter sends 2 today.
Touches: docs/design.md, CLAUDE.md, docs/evidence.md, docs/integrations/zigbee2mqtt/internals.md, docs/integrations/zigbee2mqtt/index.md, custom_components/deviceside/integrations/zigbee2mqtt/fade.py, custom_components/deviceside/integrations/zigbee2mqtt/set_attributes.py, custom_components/deviceside/integrations/zigbee2mqtt/families/hue/**, tests/integrations/zigbee2mqtt/**, tests/rig/steps/lower_brightness.yaml, tests/rig/steps/raise_brightness.yaml, tests/rig/steps/set_attributes.yaml, docs/integrations/*/test-records/**

## Why

Jason's intent: DeviceSide exercises a light's full brightness range, and 0.4 % is the lowest level. DeviceSide's own
conversions hold to it (`core/zcl_write.level`: `max(1, round(percent * 254 / 100))`; `tests/core/test_zcl_write.py`
pins brightness 0 to `MoveToLevel(1)`). The gap is under it, on Zigbee2MQTT, read from the converter source and not
yet measured:

- zigbee-herdsman-converters' `light_onoff_brightness` sends a brightness of 1 as level 2 on a definition with
  `turnsOffAtBrightness1`
  ([toZigbee.ts L1378](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L1378)),
  which `philips.m.light` sets by default
  ([philips.ts L315](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/lib/philips.ts#L315)),
  as do 92 Innr and 28 ADEO definitions (survey: `docs/research/2026-11-25-z2m-converter-survey.md`, on
  `wt/v0.2.0-backlog`, PR #610).
- `raise_brightness` and `lower_brightness` hold `hue_native_control` off (`families/hue` `NEED`), so their publishes
  ride that converter: `AT_THE_BOTTOM` (`fade.py`) and a fade to a limit that rounds to level 1 reach a Hue bulb as
  level 2, 0.8 %.
- `set_attributes` writes level 1 raw, then publishes `_kept_level(1)`, which the same converter would send as a
  `moveToLevel` to 2: on a lit flagged bulb the read-back, which expects 1, may answer `not_stored`. Unverified.
- A Hue bulb holds level 1: ZHA sends it raw ([ZHA internals](../integrations/zha/internals.md), `lower_brightness`).
  The flag on Philips definitions protects nothing DeviceSide needs.

It went unseen because the intent was written nowhere as a rule, unit tests pin the payload handed to Z2M and not the
wire, and no rig case touches the bottom (lowest limit 30 %; the raise-from-off check takes any HA brightness to 8).

## Decisions (Jason, 2026-11-25)

1. **The rule, in `docs/design.md` beside the percent rule:** 0.4 % is level 1, the lowest a light takes, and every
   level 1–254 is reachable. No shared conversion raises the floor. A device or a layer below that can't reach level 1
   is a device fact in its `internals.md` and a class limit in its `index.md`.
2. **One line in CLAUDE.md's Evidence section** (and its long form in `docs/evidence.md`): a layer between DeviceSide
   and the device that changes what we send (a converter's rewrite, a quirk) is a finding for a maintainer, recorded in
   `internals.md`, never "by design". Fold it into tenet 4 (Surprises reopen facts) unless it reads worse there; no
   tenth tenet without need. The PR body names the user-visible failure each rule prevents (tenet 6): a light that
   stops at 0.8 % when asked for its lowest level, unseen for four weeks.
3. **Hue on Zigbee2MQTT: the bottom bypasses the converter.** Where a brightness publish would carry level 1 to a Hue
   light, DeviceSide sends the raw `genLevelCtrl` command through Z2M's `command` payload instead, as
   `set_attributes` already does, so the wire carries level 1. The same call as the converter's otherwise
   (`moveToLevelWithOnOff`, the same `transtime`, `optionsMask`/`optionsOverride` 0).
4. **Other flagged lights keep Z2M's 2** (Innr, ADEO: they turn off at 1, by ZHC's reports). Their lowest is 0.8 %,
   said in the Z2M `index.md` and `internals.md`. No bypass for `other`.
5. **A rig case at the bottom, per Zigbee integration** (ZHA and Zigbee2MQTT, Hue bulbs): lower to a 0.4 % limit, and
   set brightness 0.4 %, lit; each asserts level 1 exactly. What it catches that nothing else does: the wire level
   under Z2M's converter and the bulb's own answer, which unit tests can't see.

The 2026-11-24 research note's aside ("DeviceSide should treat minimum staged level as 2, or skip") is superseded by
Decision 1; research files aren't edited.

## Settled, don't redesign

- The rule's owner is the Hue family (`families/hue` says a Hue light's bottom goes raw, with why); the mechanism is
  the integration's (`fade.py`), as `NEED` and `native_control` split today.
- A group gets the raw bottom only when every member is a Hue-family light; a mixed group keeps the converter
  (ZHC applies the flag to a group only when all members agree, `allEqual`). Say so in `internals.md`.
- `brightness_move: stop` halts a raw fade as it does the converter's: both are ZCL transitions.

## For the implementer to check, and report

- A raw command draws no state from Z2M and doesn't update the level Z2M keeps for the next plain on. The fade's end
  read-back covers the state; check the kept level after a raw lower to 0.4 % then a plain off and on.
- `set_attributes` and `_kept_level`: if step 2 shows the rejection, the recommended fix is to skip the kept-level
  publish on a lit light (it exists for a light off after a transition). If that isn't right, bring Jason the options.
- `turn_on_for` with a 0.4 % brightness goes through `light.turn_on` with native control on, where Philips' converter
  clamps to 1–254 and appears not to rewrite (philips.ts L420). Probe it in step 2; no change planned.

## Steps

1. **Rules and facts.** Decisions 1 and 2 in `docs/design.md`, `CLAUDE.md`, `docs/evidence.md`; the converter's
   rewrite and Decision 4 in the Z2M `internals.md` (`fade`) and `index.md`. Docs only. Check:
   `.venv/bin/pytest -n auto --transcripts=check` and the generators' `--check`.
2. **Rig cases and the probe.** Add Decision 5's cases to `tests/rig/steps/`. Run them on the rig against the code as
   it stands, on Hue bulbs over ZHA and Zigbee2MQTT (rig rules: `../ha-rig`'s `CLAUDE.local.md`). The run decides
   (tenet 8): whether the converter sends 2 as read (expected: ZHA passes, Z2M fails at level 2), and whether
   `set_attributes` at 0.4 % on a lit Hue bulb is rejected. Record what it shows in the Z2M `internals.md`. If Z2M
   passes at level 1, stop and tell Jason: step 3 has nothing to fix.
3. **The bypass** (Decision 3), and the `set_attributes` fix if step 2 showed the need. Unit tests pin the raw payload
   as literals for a Hue light, an all-Hue group, a mixed group and a non-Hue light, for raise from off and for a
   lower to 0.4 %. Risky step (a wire call changes on a Verified class): it gets its own `/audit-code`.
4. **Retest and records.** Rerun the cases whose call changed (tenet 9: Z2M raise, lower, and set_attributes if
   changed), commit the records, then the PR audit (binding-rule text: Opus auditor), `owner-findings`, ready and
   `merge-green 613 --squash --delete-branch`.
