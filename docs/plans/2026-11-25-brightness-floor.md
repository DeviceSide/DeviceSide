# Brightness floor: 0.4 % is level 1, on Zigbee2MQTT's Hue bulbs too

2026-11-25. Branch `wt/brightness-floor`, worktree `deviceside-wt/brightness-floor`, PR #613.

## Coordination

Intent: Write down that 0.4 % is a light's lowest level (level 1) and every level is reachable; pin it on the rig; and
make Zigbee2MQTT's Hue fades reach level 1, where Z2M's converter sends 2 today.
Touches: docs/design.md, CLAUDE.md, docs/evidence.md, docs/integrations/zigbee2mqtt/internals.md, docs/integrations/zigbee2mqtt/index.md, custom_components/deviceside/integrations/zigbee2mqtt/fade.py, custom_components/deviceside/integrations/zigbee2mqtt/set_attributes.py, custom_components/deviceside/integrations/zigbee2mqtt/families/hue/**, custom_components/deviceside/integrations/zigbee2mqtt/families/aqara/**, docs/deferred.md, tests/integrations/zigbee2mqtt/**, tests/rig/steps/lower_brightness.yaml, tests/rig/steps/set_attributes.yaml, docs/integrations/*/test-records/**

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
  The flag on Philips definitions protects nothing DeviceSide needs. (Corrected by step 4's probe: the flag steps around the ZCL rule that a `...WithOnOff` command ending at the minimum turns the light off; plain `moveToLevel` holds level 1 lit. Decision 9.)

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

6. **(2026-11-25, after step 2) Other families' flagged lights keep Z2M's 2 too.** IKEA (15), Gledopto (3) and Aqara (3)
   definitions carry `turnsOffAtBrightness1` (ZHC `03b37655`, per PR #610's count). Like Decision 4: no bypass, and
   their lowest is 0.8 %, said in the Z2M `index.md` and `internals.md`. Reopens when a probe shows one holds level 1.

7. **(2026-11-25, after step 3) `set_attributes` skips the kept-level publish only for a level-1 write to a lit
   Hue-family light**, the one case the converter rewrites; every other write keeps it, so Z2M's stored level stays
   current.
8. **(2026-11-25, after step 3) Z2M's restore-after-soft-off memory is probed, not coded around.** Probed on the rig
   in step 4 ([research](../integrations/zigbee2mqtt/research/hue/2026-11-25-raw-bottom-probe.md)), with
   `hue_native_control` off: (a) a member soft-off at 40 %, a group raise from off to 100 %, then a plain on to that
   member: it went back to 40.2 %, and plain HA group commands with no DeviceSide call did the same, so the memory is
   Z2M's own; (b) a raw lower from 30 % to 0.4 %, then an off with a transition before the end read-back: the plain
   on came back at 29.9 %. With the option on, neither jumped. The probes also showed the raw lower's
   `moveToLevelWithOnOff` to level 1 leaves the bulb off. A failure reopens a fix in this PR: Decisions 9 and 10.
9. **(2026-11-25, after step 4's probe) The bottom of a lit lower is a raw `moveToLevel` to level 1**, not
   `moveToLevelWithOnOff` (which turns a light off at the minimum); the call ZHA's lower and Z2M's `set_attributes`
   already send. Raise from off goes back to the converter: it starts at level 2 before fading up, unseen. Supersedes
   Decision 3's call for the bottom. `lower_to_the_lowest_level` also asserts the light stays on.
10. **(2026-11-25) Probe (b)'s stale window is documented, not fixed:** after a raw lower, Z2M's state lags until the
    end read-back, so an off with a transition inside it makes the next plain on return to the pre-fade level. A known
    narrow case in Z2M `internals.md`. (a) is Z2M's own group behavior, recorded there.

11. **(2026-11-25, after step 4's Aqara run) The raw `moveToLevel` bottom goes by evidence: Hue and Aqara.** The
    Aqara bulb (unflagged, so the converter sends it `moveToLevelWithOnOff` to level 1) reported itself off at the end
    of `lower_to_the_lowest_level`, and held level 1 lit on `set_attributes`' raw `moveToLevel`: the with-On/Off
    rule, not a Hue trait. DeviceSide can't read `turnsOffAtBrightness1` (ZHC definition metadata, neither on the bulb
    nor in Z2M's API), so the rule goes by class. A lower's raw bottom serves every reached light of class `hue` or
    `aqara`, a mixed Hue and Aqara group included; each family says why its class is in it, and a class joins with its own
    probe. `set_attributes`' kept-level skip stays Hue's alone (Decision 7: the converter rewrites level 1 only there).
    `other` keeps the converter, a finding in Z2M `internals.md` (an unflagged light switches off at a lower to
    0.4 %) with a `docs/deferred.md` line. Caveat: ZHC flags 3 Aqara definitions; one in the `aqara` class would get a
    raw level 1 untested. Retest: Z2M `lower_brightness` on the Aqara bulb.
12. **(2026-11-25, after #615 merged) No flagged-model list: #615's table covers it.** The idea: generate the
    `turnsOffAtBrightness1` models from a pinned ZHC, so a lower to level 1 goes raw wherever no reached light is
    flagged. #615's `standard_light` class (Decision 24 of its plan) already sends its members a raw level 2, and a
    flagged light stays lit at 0.8 % through the converter. What a list would add is the unflagged lights off the
    table, about 80-95 definitions at ZHC v26.137.0 (226 `other` light definitions less about 132 flagged), most of
    them off it because their brightness path departs: 14 overridden converters (ORVIBO's sends `moveToLevel` alone,
    Control4's scales 0-100) and 11 `omitOptionalLevelAndColorParams` lights, which reject the option fields the raw
    call carries. A flag list can't tell those apart; the table's generator can. So nothing is built until a report
    asks for it (`docs/deferred.md`, The raw bottom for other lights on Zigbee2MQTT).

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


## Handoff

2026-11-25, from the second implementing session (Opus), at ~165k context.

**Done since the last handoff.** Rig recovered. The Z2M `lower_brightness.json` and `set_attributes.json` were deleted and
`lab_hue` rerun `--fresh` at `b6108499`: 6/6 and 13/13, committed (`8d2a57d7`). The group probe (an all-Hue group, one
member off, lowered to 0.4 %) passed: lit members held level 1, the off one stayed off at its own level; research note
`docs/integrations/zigbee2mqtt/research/hue/2026-11-25-move-to-level-bottom-rig.md`, cited from `internals.md` and
`index.md`. The restricted `lab_aqara` run (Jason's yes, `DEVICE_SIDE_RIG_RESTRICTED=1`): `set_attributes` 10/10, its
rows promoted and committed (`f2d972d0`); `lower_brightness` failed `lower_to_the_lowest_level` (the bulb switched off),
so Jason chose **Decision 11** (above). The finding is in Z2M `internals.md` (`fade`). Its run's logs:
`/var/folders/wk/kszxz30j6wd2vmmnd02c5bfc0000gn/T/deviceside-rig/rig-run-2026-11-25-134322.{ha,z2m}.log` (may be cleared).

**Update, 2026-11-25 (third session):** Next 1 and 2 are done: Decision 11 built (`50123dc7`, review fixes `eecace5d`),
the transcript regenerated (3 added segments), and `lower_brightness.json` rerun whole at it: `lab_aqara` (restricted)
and `lab_hue` `--fresh`, 9/9. Next is 3.

**Next:**
1. (Done) Build Decision 11 (one implementer, `sonnet`; then a `plan-reviewer`, `opus`, since it changes a wire call on a
   Verified class). `fade.py`'s raw bottom serves classes `hue` and `aqara`: each family says why its class is in it
   (`families/hue` and `families/aqara` each export their own set; `fade.py` unions them), and `set_attributes.py`
   keeps Hue's kept-level skip alone (Decision 7). Unit tests pin as literals the raw payload for an Aqara light, an
   Aqara + Hue group, and an Aqara + `other` group (converter kept). Update `fade.py`'s docstring, the families'
   comments, Z2M `internals.md` (`fade`: the bypass paragraph says Hue only), `index.md` (Aqara class, Lowest
   brightness: `other` unflagged lights switch off at a lower to 0.4 %), and a `docs/deferred.md` section (the raw
   bottom for `other`; reopens on a probe of an unflagged `other` light, or a report of one switching off). Also the
   open item: mixed groups through the converter light an off member (`moveToLevelWithOnOff`); put it in that section.
   Check: `.venv/bin/pytest -n auto --transcripts=check` (the transcript changes on purpose: `docs/evidence.md`,
   Release gate) and the generators' `--check`.
2. (Done) Retest on the rig (tenet 9): `lab_aqara`, restricted with Jason's yes for that run, `--integration zigbee2mqtt
   --action lower_brightness`. The Aqara bulb shares a fixture with the Hue A60: ask Jason to swap it in first, and
   tell him when it's done. Run from this worktree: `../../ha-rig/scripts/rig.py` (absolute
   `/Users/jason/projects/ha/ha-rig/scripts/rig.py`). Hue's records need no rerun if `check_release.py --signoffs
   --reruns` agrees. Until then pytest fails on `aqara is Verified but no record reaches it` (lower_brightness).
3. The PR audit via `audit-gate` (binding-rule text: Opus auditor), then `owner-findings`, `gh pr ready` and a
   backgrounded `merge-green 613 --squash --delete-branch`. The PR body names the user-visible failure each rule
   prevents (Decision 2, tenet 6), and Decision 11's finding.

**Rig permission (Jason):** the lab rig yes, the Z2M plugs never.

Branch `wt/brightness-floor`, worktree `/Users/jason/projects/ha/deviceside-wt/brightness-floor`, PR #613 (draft).
Overlaps: #611 (`docs/design.md`), #614 (merged into main since; merge main in before the audit).
