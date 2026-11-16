# Tuya datapoint `countdown` on Zigbee2MQTT: which definitions suit `turn_on_for` (2026-11-14)

Research date: 2026-11-14. Scope: every zigbee-herdsman-converters (ZHC) definition whose `countdown` is a Tuya
datapoint (converter B in [2026-11-14-tuya-countdown.md](2026-11-14-tuya-countdown.md), §1), and which of them a
"state on, countdown N" call suits. Feeds the plan's Decision 67
([`docs/plans/2026-11-14-device-classes.md`](../../../plans/2026-11-14-device-classes.md)).

Pinned sources, read only, no code run:

- ZHC `afdaa028a0972d801da762196ddfb2df631ea0cc`. `src/devices/<file>:<n>` below is
  `https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/devices/<file>#L<n>`;
  "lib" is `src/lib/tuya.ts` at the same SHA.
- Z2M `3c841fdfd66c92239921ef84fde8f039c64e1662`: `lib/extension/publish.ts` and `lib/extension/homeassistant.ts`,
  `https://github.com/Koenkk/zigbee2mqtt/blob/3c841fdfd66c92239921ef84fde8f039c64e1662/<path>#L<n>`.

Line numbers are at those SHAs.

**Scope.** These are the 81 definitions that map a Tuya datapoint (`meta.tuyaDatapoints`, or `dpNumeric`) to a key named
`countdown` or `countdown_<x>`. The 78 in the converter note, plus four it missed: `TS0601_dimmer_2` and
`TS0601_garage_door_opener` (via `dpNumeric`), Ronco RM28-LE (an enum over several lines), and `_TZE284_z5jz7wpo`
(`countdown_hours`). GX03 is counted though its `countdown_N` is read-only. Left out: Third Reality, Namron and eWeLink
(not datapoints), and a `countdown` melody enum value (tuya.ts 31025). "Maker strings" counts the manufacturer names in
each definition's fingerprint. White labels are not counted, and a string can appear in more than one definition.

**Candidate rule** (the rule this reading tests). The device has a numeric expose whose property is `countdown` (or `countdown_<ep>`),
with unit `s`, `value_max` 43200 and SET in its access. The same endpoint also has an on/off `state` (`state` or
`state_<ep>`) from a switch or light expose. Pair the two by **property**, not by `name` plus `endpoint`. Six
definitions that match the rule (SA-WK 4X4, `TS0601_switch_6_gang`, TO-6, TO-WK-1, TO-WK-2, ZMZ609-2) build
`e.numeric("countdown_l1")`. That gives `name` `countdown_l1` with no `endpoint` field, so a name-plus-endpoint match
would miss them.

## Summary

### 1. Device kinds

| Kind | Definitions | Maker strings | Candidate rule matches, LYAI-14 left out (defs / strings) |
|---|---|---|---|
| wall switch | 37 | 99 | 24 / 59 |
| plug / socket | 4 | 6 | 3 / 4 |
| relay module | 4 | 5 | 2 / 3 |
| light or dimmer | 18 | 74 | 14 / 69 |
| valve or irrigation | 10 | 24 | 1 / 3 |
| thermostat | 1 | 1 | 0 / 0 |
| fan | 2 | 4 | 1 / 3 |
| curtain | 2 | 2 | 0 / 0 |
| other | 3 | 6 | 1 / 1 |
| **total** | **81** | **221** | **46 / 142** |

Light or dimmer has 18 definitions: 15 expose a light, and Moes ZS-D1/D2/D3 expose `e.switch()` plus a numeric
brightness, so HA gets a `switch`. Fan has two: `TS0601_fan_switch` exposes a switch, and only `_TZE284_z5jz7wpo`
exposes a fan.

### 2. Standard countdown expose plus a same-endpoint state: the candidate rule

47 definitions match (46 once LYAI-14 is left out, about 142 maker strings). In each one a `state` DP and a `countdown`
DP sit on the same endpoint, and the expose reads as s, 0–43200, access 3 (LYAI-14: 7):

- **The standard expose `tuya.exposes.countdown()`, 32 definitions:** CH8Z, ZDMS16-US-W2, ZDMS16-1, ZDMS16-2, ZOT60,
  GL-SPI-206P, VM-Zigbee-S02-0-10V, MG-GPO02Z, MG-AU03, MG-AU01ZLMV01-XX, SFD02-Z, SFD02-Z_2, SFL02-Z-1…4 (4), QADZ1LR,
  `TS0601_dimmer_1_gang_1`, `_1_gang_2`, `_2`, `_3`, `_4`, `_5`, OXT-4CH-RELAY-AC, MG-ZG01W, `TS0601_fan_switch`,
  `TS0601_switch_8_2`, ZS-TYG3-SM-21Z/31Z/41Z/61Z, and LYAI-14 (a false positive, see 5).
- **A custom expose with the same numbers, 15 definitions:** FK_V02 (valve), ZBN-DJ-63 (circuit breaker), SA-WK 4X4,
  `TS0601_switch_6_gang` (only `_TZE204_gxbdnfrh` gets the expose, tuya.ts 7535–7547; the other 13 strings have the DPs
  and no expose), TO-6 W/B, TO-WK-1W/B, TO-WK-2W/B, `_TZE28C1000000_jlbsptkl`, ZMS-206US-1, ZMS-206EU-2, ZMS-206EU-3,
  ZMS-206US-4, ZMS-208US-2, ZMS-208US-3, ZMZ609-2.

The expose JSON can't tell the helper from a custom expose. Only the description differs, so the rule needn't try.

**How the payload reaches the device (all 46):**

- Single-endpoint devices take `{"state":"ON","countdown":N}` on the base topic. `tz.datapoints` loops over
  `meta.message` in payload order (lib 3299–3340), so the state DP goes out first, then the countdown DP.
- Multi-gang devices take `{"state_l1":"ON","countdown_l1":N}` on the base topic, or `{"state":"ON","countdown":N}` on
  `<device>/l1/set`. Z2M strips the endpoint suffix from every key ending in it (publish.ts 173–191, 236–245), and
  `tz.datapoints` adds it back (lib 3307–3309). Without an endpoint map, the keys pass through unchanged and still match
  the datapoints.
- Don't send unsuffixed `{"state":"ON","countdown":N}` to a multi-gang device's base topic. Where `state` has its own DP
  (DP 13 "all switches" on ZS-TYG3, ZMS-206/208, ZN2S), every gang turns on. Then `countdown` throws
  `No datapoint defined`.
- `TS0601_dimmer_2` uses one `dpNumeric`/`dpBinary` converter per key (lib 4380–4445). Each sends its own DP, in payload
  order. Same result.
- The candidate rule's 46 definitions include no `countdown_N` naming, so none of them hits the `countdown_N` failure in
  5.

### 3. Countdowns not in seconds, or not "turn off after N"

**Excluded, and rightly:**

| Definition | What the countdown is | Why the rule drops it |
|---|---|---|
| NEO NAS-WV03B, NAS-WV03B2 | off after N **minutes**, 1–240 (`countdown_min`, lib 716–723); `on_with_countdown` (min) opens and starts the timer in one key | unit `min` |
| TS0601_water_switch | valve countdown in **minutes**, 0–1440, per l1/l2 | unit `min` |
| TS0049 | "Max on time in **minutes**", 0–255 | unit `minutes` |
| GX03 (GIEX) | `countdown_N` is a read-only remaining time in minutes; the run time is `timer_N` (min, SET only) | not settable |
| TS0601_power_monitoring_switch | "Countdown to turn off", unit `m`, 0–120 (minutes or a mislabel; not in the source) | unit `m` |
| `_TZE284_z5jz7wpo` (fan) | `countdown_hours`, h 0.25–12, ×3600 on the wire | name, unit |
| Ronco RM28-LE (cover) | enum cancel/1h–4h, "trigger open/close" | enum |
| Nova EPJ-ZB (window pusher) | motor timeout, 10–90 s | range; the state is a cover |
| TS0601_garage_door_opener | "trigger door movement after a certain time, will pulse output" | no `state` |

No thermostat here has a boost-time `countdown`. The only thermostat-like device, `TS0601_smart_temperature_switch`, is
excluded by its max of 86400.

**Excluded, though they look like real "off after N seconds" timers (the `value_max` = 43200 test is too strict):**

- Max 86400, `state` on the same endpoint, payload works: ZN2S-RS02E, TS0601_3gang_rkbxtclc, TS0601_4gang_7ytnacie,
  TO-DM-W/B, DS-1450WN, TS0601_multifunction_switch ("Countdown to turn off"), Nous D1Z, Nous D5Z,
  TS0601_smart_temperature_switch (access 7, "turn device on/off after"; its `autowork` mode also drives the output),
  FK-BV05 and ZVL-PRO (valves).
- AVATTO ZBS16: unit `seconds` (not `s`), max 7210, "Countdown to turn device off".
- Moes ZS-D1/D2/D3 (max 86400) and Manhot MH03-*: the key is `countdown_N`, which fails in one payload (5).

**Suggestion:** test unit `s` and `N <= value_max` instead of `value_max == 43200`. That adds 11 definitions, the list
above minus ZBS16, ZS-D and Manhot. Two need care. D5Z's state converter publishes `countdown: 0` whenever the state
changes (lib 1877–1878), so its readback shows 0 while the timer runs. The smart temperature switch's auto mode may
override the timer.

### 4. Valves

Z2M at this SHA has no HA `valve` mapping. `homeassistant.ts` has cases for light, switch, cover, fan and binary (lines
634, 705, 967, 1074, 1170), and the string `"valve"` appears nowhere in the file as an entity type. Every valve's on/off
is therefore an HA **`switch`**: `e.switch()` gives a switch, and a settable binary gives a switch through the binary
case (1170–1200).

**Countdown in seconds on a switchable state** (likely "open for N s, then close"; no definition says so outright):

| Valve | State key | Countdown | HA domain | `{"state":"ON","countdown":N}` |
|---|---|---|---|---|
| FrankEver FK_V02 (frankever.ts 12) | `state` DP 1 | DP 9, s 0–43200, "Countdown timer in seconds" | switch | works; **matches the candidate rule** |
| FrankEver FK-BV05 (frankever.ts 48) | `state` DP 1 | DP 11, s 0–86400, "Irrigation Duration (countdown in seconds)" | switch | works; excluded by max |
| Nova Digital ZVL-PRO (tuya.ts 29222) | `state` DP 1 | DP 11, s 0–86400, "Countdown time in seconds" | switch | works; excluded by max |
| HOBEIAN ZG-308Z (hobeian.ts 254) | **`switch`** DP 1 (binary) | DP 11, s 0–86400, "Valve countdown in seconds" | switch (property `switch`) | needs **`{"switch":"ON","countdown":N}`** |

The source doesn't say whether DP 11 on FK-BV05, ZVL-PRO and ZG-308Z is a live timer or a preset run time kept for the
next opening. A probe should settle that before these are trusted.

**Minute-based valves** (different units or keys, not this payload): NEO NAS-WV03B/B2 (`countdown` min, or
`on_with_countdown` min, which opens and times in one key), TS0601_water_switch (`state_lN` + `countdown_lN` in min),
TS0049 (`state` + `countdown` in min, a "max on time"), GX03 (`valve_N` + `timer_N` in min, written before opening).

**LYAI-14** is excluded: see 5.

### 5. False positives and payload traps

- **LYAI-14 (TS0049, tuya.ts 17921) matches the rule but should be excluded.** Its comment says "Countdown is not
  working properly yet - device ignores it and uses the default (10 minutes)" (17925–17926). Its `state` goes over ZCL
  `tz.on_off` (17924, 17928), not the datapoint.
- **ZBN-DJ-63 is a circuit breaker.** It matches and the call would work, but "on for N, then off" on a breaker is the
  maintainers' call.
- **TS0601_fan_switch** matches, with the text "Max ON time in seconds". DP 2 on the sibling module `_TZE284_z5jz7wpo`
  is "Fan ON time", written in seconds (26969–26976), so it is most likely a one-shot timer. HA sees a `switch`, not a
  `fan`.
- **GL-SPI-206P** matches and works. Its local light converter sends DP 1, then `tz.datapoints` sends DP 1 again before
  the countdown. That is harmless, unless bursts hang the MCU (its own comment, gledopto.ts 292–293).
- **The `countdown_N` naming fails in one payload when the device has an endpoint map.** This hits Manhot MH03-1Z…8Z
  and Moes ZS-D1/D2/D3. The rule doesn't pair them, which is the right outcome. For `{"state_l1":"ON","countdown_1":N}`,
  Z2M takes the endpoint from `state_l1` and strips only keys ending in `l1` (publish.ts 236–245). `tz.datapoints` then
  turns `countdown_1` into `countdown_1_l1`, sends the state DP, and throws `No datapoint defined for 'countdown_1'`
  (lib 3307–3311). The converter has now run once for that endpoint, so the second key is skipped (publish.ts 202). The
  light turns on and stays on. `countdown_1` sent alone works. The `_TZE28C1000000_jaunkx9g`/`usmqzgdm` presence
  switches have no endpoint map, so one payload works there, but the rule doesn't pair them either.
- **General caveat for every Tuya datapoint countdown:** the standard text is "Toggle the device after a set duration".
  If the ON is lost, or the device is off when the timer expires, a toggle-type countdown could turn it **on** at the end.
  Nous notes that a state change resets the countdown (lib 1877). Other devices aren't stated.

## Table

Line numbers in brackets are in the row's file unless marked "lib". "std" is `tuya.exposes.countdown()`: s, 0–43200,
step 1, access 3, "Toggle the device after a set duration (one time action)" (lib 708–715). The converter `countdown` is
`raw` (lib 1637). No row scales the value except `_TZE284_z5jz7wpo` (hours to seconds). The minute-unit rows send the
number unchanged, as minutes.

| # | Model (vendor) | Def. | Fingerprint, maker strings | Kind | Countdown key: DP, converter [lines] | Expose: unit, range, access [lines] | Same-endpoint on/off state [lines] | HA domain of the state | Semantics in code | `state` + `countdown` in one payload | Candidate rule |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | CH8Z (AutomatOn) | `automaton.ts:38` | TS0601, 1 | relay module | `countdown_l1`–`_l8`: DP 9–16, `countdown` (raw) [65–72] | std ×8, `withEndpoint(l1…l8)` [47] | `state_l1`–`_l8`: DP 1–8 [54–64] | switch | std text (toggle) | OK, suffixed keys | match |
| 2 | ZDMS16-US-W2 (AVATTO) | `avatto.ts:387` | TS0601, 1 | light or dimmer | `countdown_l1` DP 6, `_l2` DP 12, `countdown` [408, 414] | std l1, l2 [393, 396] | `state_l1` DP 1, `_l2` DP 7 [403, 409] | light | std | OK | match |
| 3 | ZDMS16-1 (AVATTO) | `avatto.ts:434` | TS0601, 9 | light or dimmer | `countdown` DP 6, `countdown` [452] | std [441] | `state` DP 1 [447] | light | std | OK | match |
| 4 | ZDMS16-2 (AVATTO) | `avatto.ts:466` | TS0601, 6 | light or dimmer | `countdown_l1` DP 6, `_l2` DP 12 [487, 493] | std l1, l2 [472, 475] | `state_l1` DP 1, `_l2` DP 7 [482, 488] | light | std | OK | match |
| 5 | ZBS16 (AVATTO) | `avatto.ts:518` | TS0601, 1 | relay module | `countdown` DP 103, `raw` [573] | custom: unit `seconds`, 0–7210, 3 [532–538] | `state` DP 1 [543] | switch | "Countdown to turn device off" [538] | OK | no: unit `seconds`, max 7210 |
| 6 | ZOT60 (AVATTO) | `avatto.ts:969` | TS011F, 2 | plug / socket | `countdown` DP 9, `countdown` [993] | std [976] | `state` DP 1 [992] | switch | std | OK | match (TS011F, yet converter B) |
| 7 | FK_V02 (FrankEver) | `frankever.ts:12` | TS0601, 3 | valve or irrigation | `countdown` DP 9, `countdown` [32] | custom: s, 0–43200, 3, "Countdown timer in seconds" [20] | `state` DP 1 [31] | switch | not stated | OK | match (valve) |
| 8 | FK-BV05 (FrankEver) | `frankever.ts:48` | TS0601, 1 | valve or irrigation | `countdown` DP 11, `raw` [150] | custom: s, 0–86400, 3, "Irrigation Duration" [65–70] | `state` DP 1 [132] | switch | irrigation duration | OK | no: max 86400 |
| 9 | GL-SPI-206P (Gledopto) | `gledopto.ts:1259` | TS0601, 3 | light or dimmer | `countdown` DP 7, `countdown` [1357] | std [1302] | `state` DP 1 via local `glspi206p_light` [1262, 291–303] | light | std | OK; DP 1 may be sent twice (local converter, then the `tz.datapoints` loop) | match |
| 10 | ZG-308Z (HOBEIAN) | `hobeian.ts:254` | TS0601 (+zigbeeModel), 1 | valve or irrigation | `countdown` DP 11, `raw` [283] | custom: s, 0–86400, 3, "Valve countdown in seconds" [261] | **`switch`** (binary, not `state`) DP 1 [259, 281] | switch (property `switch`) | valve countdown | needs `{"switch":"ON","countdown":N}` | no: no `state`; max 86400 |
| 11 | VM-Zigbee-S02-0-10V (Lonsonho) | `lonsonho.ts:332` | TS0603, 1 | light or dimmer | `countdown_l1` DP 6, `_l2` DP 12, `raw` [356, 362] | std l1, l2 [339–340] | `state_l1` DP 1, `_l2` DP 7 [351, 357] | light | std | OK | match |
| 12 | MG-GPO02Z (MakeGood) | `makegood.ts:288` | TS0601, 1 | plug / socket | `countdown_l1` DP 7, `_l2` DP 8, local `countdownConverter` (`Number`, `false`→0) [321–322; 21–24] | std l1, l2 [299–300] | `state_l1` DP 1, `_l2` DP 2 [317–318] | switch | std | OK | match |
| 13 | MG-AU03 (MakeGood) | `makegood.ts:347` | TS0601, 1 | plug / socket | `countdown_l1`–`_l3` DP 7–9, local [385–387] | std ×3 [360–362] | `state_l1`–`_l3` DP 1–3 [380–382] | switch | std | OK | match |
| 14 | MG-AU01ZLMV01-XX (MakeGood) | `makegood.ts:413` | TS0601, 1 | wall switch | `countdown_l1` DP 7, local [440] | std l1 [421] | `state_l1` DP 1 [437] | switch | std | OK | match |
| 15 | MH03-1Z-OLED (Manhot) | `manhot.ts:36` | TS0601, 2 | wall switch | `countdown_1` DP 7, `raw` [63] | custom `countdown_1`: s, 0–43200, 3, no endpoint [42] | `state_l1` DP 1 [62] | switch | "Timer for switch 1" | **fails** (see summary 5) | no: `countdown_1` doesn't pair with `state_l1` |
| 16 | MH03-2Z-OLED (Manhot) | `manhot.ts:108` | TS0601, 2 | wall switch | `countdown_1`, `_2` DP 7–8 [141–142] | custom, as above [115–116] | `state_l1`, `_l2` DP 1–2 [139–140] | switch | as above | **fails** | no: as above |
| 17 | MH03-3Z-OLED (Manhot) | `manhot.ts:206` | TS0601, 2 | wall switch | `countdown_1`–`_3` DP 7–9 [249–251] | custom [215–217] | `state_l1`–`_l3` DP 1–3 [245–247] | switch | as above | **fails** | no: as above |
| 18 | MH03-4Z-OLED (Manhot) | `manhot.ts:318` | TS0601, 2 | wall switch | `countdown_1`–`_4` DP 7–10 [365–368] | custom [328–331] | `state_l1`–`_l4` DP 1–4 [360–363] | switch | as above | **fails** | no: as above |
| 19 | MH03-6Z-OLED (Manhot) | `manhot.ts:438` | TS0601, 4 | wall switch | `countdown_1`–`_6` DP 7–12 [509–514] | custom [450–455] | `state_l1`–`_l6` DP 1–6 [502–507] | switch | as above | **fails** | no: as above |
| 20 | MH03-8Z-OLED (Manhot) | `manhot.ts:590` | TS0601, 4 | wall switch | `countdown_1`–`_8` DP 7–12, 116, 117 [673–680] | custom [604–611] | `state_l1`–`_l8` DP 1–6, 114, 115 [664–671] | switch | as above | **fails** | no: as above |
| 21 | ZS-D1 (Moes) | `moes.ts:594` | TS0601, 2 | light or dimmer | `countdown_1` DP 6, `raw` [633] | custom: s, 0–86400, 3 [615–620] | `state_l1` DP 1 [629] | **switch** (`e.switch()` plus numeric `brightness_1`, no light expose) [600–601] | "Channel 1 countdown" | **fails** (endpoint map [655]) | no: name pairing; max 86400 |
| 22 | ZS-D2 (Moes) | `moes.ts:663` | TS0601, 1 | light or dimmer | `countdown_1` DP 6, `_2` DP 12 [723, 728] | custom: s, 0–86400 [684–710] | `state_l1` DP 1, `_l2` DP 7 [719, 724] | switch | as above | **fails** | no: as above |
| 23 | ZS-D3 (Moes) | `moes.ts:759` | TS0601, 1 | light or dimmer | `countdown_1`–`_3` DP 6, 12, 20 [840, 845, 859] | custom: s, 0–86400 [782–828] | `state_l1`–`_l3` DP 1, 7, 15 [836, 841, 855] | switch | as above | **fails** | no: as above |
| 24 | SFD02-Z (Moes) | `moes.ts:945` | TS0601, 1 | light or dimmer | `countdown` DP 6, `countdown` [966] | std [952] | `state` DP 1 [961] | light | std | OK | match |
| 25 | SFD02-Z_2 (Moes) | `moes.ts:986` | TS0601, 1 | light or dimmer | `countdown` DP 6 [1009] | std [993] | `state` DP 1 [1004] | light | std | OK | match |
| 26 | SFL02-Z-1 (Moes) | `moes.ts:1024` | TS0601, 4 | wall switch | `countdown_l1` DP 30, `countdown` [1061] | std l1 [1032] | `state_l1` DP 24 [1060] | switch | std; separate `momentary_1` DP 105 is inching [1071] | OK | match |
| 27 | SFL02-Z-2 (Moes) | `moes.ts:1077` | TS0601, 4 | wall switch | `countdown_l1`, `_l2` DP 30–31 [1122–1123] | std ×2 [1085–1086] | `state_l1`, `_l2` DP 24–25 [1120–1121] | switch | std | OK | match |
| 28 | SFL02-Z-3 (Moes) | `moes.ts:1140` | TS0601, 3 | wall switch | `countdown_l1`–`_l3` DP 30–32 [1206–1208] | std ×3 [1149–1151] | `state_l1`–`_l3` DP 24–26 [1203–1205] | switch | std | OK | match |
| 29 | SFL02-Z-4 (Moes) | `moes.ts:1226` | TS0601, 3 | wall switch | `countdown_l1`–`_l4` DP 30–33 [1305–1308] | std ×4 [1236–1239] | `state_l1`–`_l4` DP 24–27 [1301–1304] | switch | std | OK | match |
| 30 | NAS-WV03B (NEO) | `neo.ts:179` | TS0601, 10 | valve or irrigation | `countdown` DP 5, `raw` [244]; `countdown_left` DP 6, read-only [245] | `countdown_min()`: **min**, 1–240, 3, "Turn off the sprinkler after set duration" [200; lib 716–723]; `on_with_countdown` DP 109, min [201, 271] | `state` DP 1 [232] | switch | off after N **minutes** | N would be read as minutes | no: unit min |
| 31 | NAS-WV03B2 (NEO) | `neo.ts:278` | TS0601, 2 | valve or irrigation | `countdown` DP 5 [313]; `countdown_left` DP 6 [314] | `countdown_min()` [286]; `on_with_countdown` DP 101 [287, 330] | `state` DP 1 [301] | switch | as above | as above | no: unit min |
| 32 | D5Z (Nous) | `nous.ts:409` | TS0601, 1 | other | `countdown` DP 105, `raw` [476] | std with max 86400 [419] | `state` DP 16, `onOffWithZeros` [469] | switch | "timer"; a state change publishes `countdown: 0` [lib 1877–1878] | OK on the wire; readback may show 0 while running | no: max 86400 |
| 33 | D1Z (Nous) | `nous.ts:494` | TS0601, 1 | relay module | `countdown` DP 105, `raw` [537] | std with max 86400 [500] | `state` DP 16 [530] | switch | not stated | OK | no: max 86400 |
| 34 | SA-WK 4X4 (Nova Digital) | `nova_digital.ts:287` | TS0601, 1 | wall switch | `countdown_l1`–`_l6` DP 7–12, `raw` [336–341] | custom `countdown_lN` (in the name, no endpoint field): s, 0–43200, 3 [300–305] | `state_l1`–`_l6` DP 1–6; `state_master` DP 101 [320–326] | switch | not stated | OK | match (by property) |
| 35 | QADZ1LR (QA) | `qa.ts:346` | TS0601, 1 | light or dimmer | `countdown` DP 6, `countdown` [369] | std [352] | `state` DP 1 [365] | light | std | OK | match |
| 36 | ZBN-DJ-63 (Tuya) | `tuya.ts:3046` | TS0601, 1 | other | `countdown` DP 105, `countdown` [3186] | custom: s, 0–43200, 3, "Countdown Timer" [3102] | `state` DP 16 [3170] | switch | not stated | OK | match (circuit breaker) |
| 37 | ZN2S-RS02E (Tuya) | `tuya.ts:4026` | TS0601, 2 | wall switch | `countdown_l1`, `_l2` DP 7–8, `countdown` [4054–4055] | custom `countdown_lN`: s, 0–86400 [4045–4046] | `state_l1`, `_l2` DP 1–2; all-gang `state` DP 13 [4051–4053] | switch | not stated | OK | no: max 86400 |
| 38 | TS0601_3gang_rkbxtclc (Tuya) | `tuya.ts:4105` | TS0601, 1 | wall switch | `countdown_l1`–`_l3` DP 7–9 [4137–4139] | custom: s, 0–86400 [4126–4128] | `state_l1`–`_l3` DP 1–3; `state` DP 13 [4133–4136] | switch | not stated | OK | no: max 86400 |
| 39 | TS0601_4gang_7ytnacie (Tuya) | `tuya.ts:4188` | TS0601, 2 | wall switch | `countdown_l1`–`_l4` DP 7–10 [4222–4225] | custom: s, 0–86400 [4209–4212] | `state_l1`–`_l4` DP 1–4; `state` DP 13 [4217–4221] | switch | not stated | OK | no: max 86400 |
| 40 | TS0601_dimmer_1_gang_1 (Tuya) | `tuya.ts:6564` | TS0601, 30 | light or dimmer | `countdown` DP 6, `countdown` [6619] | std [6597] | `state` DP 1 [6614] | light | std | OK | match |
| 41 | TS0601_dimmer_1_gang_2 (Tuya) | `tuya.ts:6647` | TS0601, 1 | light or dimmer | `countdown` DP 6 [6664] | std [6653] | `state` DP 1 [6660] | light | std | OK | match |
| 42 | TS0601_dimmer_2 (Tuya) | `tuya.ts:6695` | TS0601, 4 | light or dimmer | `countdown` l1 DP 6, l2 DP 12, via `dpNumeric` (raw) [6723–6729, 6747–6753] | std, endpoint l1, l2 [6727, 6751] | `state` l1 DP 1, l2 DP 7 via `dpLight` [6706–6722, 6730–6746] | light | std | OK (one converter per key; sent in payload order) | match |
| 43 | TS0601_dimmer_3 (Tuya) | `tuya.ts:6766` | TS0601, 5 | light or dimmer | `countdown_l1`–`_l3` DP 6, 12, 20 [6799, 6805, 6812] | std ×3 [6774–6776] | `state_l1`–`_l3` DP 1, 7, 15 [6794, 6800, 6807] | light | std | OK | match |
| 44 | TS0601_dimmer_4 (Tuya) | `tuya.ts:6829` | TS0601, 3 | light or dimmer | `countdown_l1`, `_l2` DP 6, 12 [6858, 6872] | std ×2 [6836–6837] | `state_l1`, `_l2` DP 1, 7 [6845, 6859] | light | std | OK | match |
| 45 | TS0601_dimmer_5 (Tuya) | `tuya.ts:6894` | TS0601, 3 | light or dimmer | `countdown` DP 6 [6921] | std [6901] | `state` DP 1 [6907] | light | std | OK | match |
| 46 | OXT-4CH-RELAY-AC (Tuya) | `tuya.ts:7434` | TS0601, 2 | relay module | `countdown_l1`–`_l4` DP 7–10, `countdown` [7453–7456] | std ×4 [7440] | `state_l1`–`_l4` DP 1–4 [7449–7452] | switch | std | OK | match |
| 47 | TS0601_switch_6_gang (Tuya) | `tuya.ts:7509` | TS0601, 14 | wall switch | `countdown_l1`–`_l6` DP 7–12, `raw` [7562–7567] | custom `countdown_lN`: s, 0–43200, 3, "Toggle lN after…", **only for `_TZE204_gxbdnfrh`** [7535–7547] | `state_l1`–`_l6` DP 1–6 [7556–7561] | switch | toggle | OK | match for 1 string (by property); the other 13 have the DPs but no expose |
| 48 | TO-6 W/B (Nova Digital) | `tuya.ts:7650` | TS0601, 1 | wall switch | `countdown_l1`–`_l6` DP 30–35, `raw` [7794–7799] | custom `countdown_lN`: s, 0–43200, 3 [7681–7722] | `state_l1`–`_l6` DP 24–29 [7787–7792] | switch | "Countdown timer"; separate inching 0–3600 [7724–7765] | OK | match (by property) |
| 49 | TO-WK-1W/B (Nova Digital) | `tuya.ts:7840` | TS0601, 1 | wall switch | `countdown_l1`, `_l2` DP 7–8 [7902–7903] | custom `countdown_lN`: s, 0–43200 [7867–7880] | `state_l1`, `_l2` DP 1–2 [7899–7900] | switch | as above | OK | match (by property) |
| 50 | TO-WK-2W/B (Nova Digital) | `tuya.ts:7943` | TS0601, 1 | wall switch | `countdown_l1`–`_l3` DP 7–9 [8020–8022] | custom `countdown_lN`: s, 0–43200 [7953–7972] | `state_l1`–`_l3` DP 1–3 [8016–8018] | switch | as above | OK | match (by property) |
| 51 | TO-DM-W/B (Nova Digital) | `tuya.ts:8063` | TS0601, 1 | light or dimmer | `countdown` DP 6, `raw` [8125] | custom: s, 0–86400 [8098–8103] | `state` DP 1 [8107] | light | not stated | OK | no: max 86400 |
| 52 | MG-ZG01W (Tuya) | `tuya.ts:8160` | TS0601, 2 | wall switch | `countdown` DP 7, `countdown` [8176] | std [8165] | `state` DP 1 [8175] | switch | std | OK | match |
| 53 | _TZE28C1000000_jlbsptkl (Tuya) | `tuya.ts:10785` | TS0601, 1 | wall switch | `countdown` DP 7, `raw` [10815] | custom: s, 0–43200, 3 [10793–10798] | `state` DP 1 [10814] | switch | "Switch 1 Countdown" | OK | match |
| 54 | _TZE28C1000000_jaunkx9g (Tuya) | `tuya.ts:10865` | TS0601, 1 | wall switch | `countdown_1`, `_2` DP 7–8 [10908–10909] | custom `countdown_N`: s, 0–43200 [10874–10886] | `state_l1`, `_l2` DP 1–2 [10906–10907] | switch | as above | OK (no endpoint map, keys pass through) | no: `countdown_N` doesn't pair |
| 55 | _TZE28C1000000_usmqzgdm (Tuya) | `tuya.ts:10963` | TS0601, 1 | wall switch | `countdown_1`–`_3` DP 7–9 [11024–11026] | custom `countdown_N` [10973–10992] | `state_l1`–`_l3` DP 1–3 [11021–11023] | switch | as above | OK | no: as above |
| 56 | TS0601_garage_door_opener (Tuya) | `tuya.ts:16140` | TS0601, 4 | other | `countdown` DP 2, `dpNumeric` (raw) [16158–16166] | custom: s, 0–43200, 3 [16159–16165] | none: `trigger` binary DP 1 [16149–16157] | switch (`trigger`) | "trigger door movement after a certain time, will pulse output" [16162] | n/a | no: no `state` |
| 57 | TS0049 (Tuya) | `tuya.ts:17899` | zigbeeModel TS0049, 0 | valve or irrigation | `countdown` DP 111, `raw` [17914] | std, changed to unit `minutes`, 0–255, "Max on time in minutes" [17907] | `state` DP 101 [17913] | switch | max on time, **minutes** | N read as minutes | no: unit |
| 58 | LYAI-14 (Tuya) | `tuya.ts:17921` | TS0049, 1 | valve or irrigation | `countdown` DP 11, `countdown` [17944] | std, access 7 [17930] | `state` via ZCL `tz.on_off` (`m.onOff`) [17924, 17928]; DP 1 also mapped [17942] | switch | comment: "device ignores it and uses the default (10 minutes)" [17925–17926] | state goes by ZCL; countdown DP ignored | **match: false positive** |
| 59 | TS0601_water_switch (Tuya) | `tuya.ts:17953` | TS0601, 2 | valve or irrigation | `countdown_l1` DP 13, `_l2` DP 14, `raw` [17985–17986] | custom, endpoint l1, l2: **min**, 0–1440, 3 [17963–17976] | `state_l1`, `_l2` DP 1–2 [17983–17984] | switch | "Valve N countdown in minutes" | N read as minutes | no: unit min |
| 60 | TS0601_fan_switch (Tuya) | `tuya.ts:18004` | TS0601, 3 | fan | `countdown` DP 2, `countdown` [18017] | std, text "Max ON time in seconds" [18011] | `state` DP 1 [18016] | **switch** (not fan) | DP 2 is "Fan ON time" on the sibling module [26969–26976] | OK | match |
| 61 | TS0601_switch_8_2 (Tuya) | `tuya.ts:19895` | TS0601, 2 | wall switch | `countdown_l1`–`_l8` DP 9–16 [19932–19939] | std ×8 [19908–19915] | `state_l1`–`_l8` DP 1–8 [19924–19931] | switch | std | OK | match |
| 62 | ZS-TYG3-SM-61Z (Tuya) | `tuya.ts:20215` | TS0601, 2 | wall switch | `countdown_l1`–`_l6` DP 7–12 [20257–20262] | std ×6 [20228–20233] | `state_l1`–`_l6` DP 1–6; `state` DP 13 [20251–20263] | switch | std | OK | match |
| 63 | ZS-TYG3-SM-21Z (Tuya) | `tuya.ts:20271` | TS0601, 1 | wall switch | `countdown_l1`, `_l2` DP 7–8 [20292–20293] | std ×2 [20280–20281] | `state_l1`, `_l2` DP 1–2; `state` DP 13 [20290–20294] | switch | std | OK | match |
| 64 | ZS-TYG3-SM-31Z (Tuya) | `tuya.ts:20302` | TS0601, 1 | wall switch | `countdown_l1`–`_l3` DP 7–9 [20326–20328] | std ×3 [20311–20313] | `state_l1`–`_l3` DP 1–3; `state` DP 13 [20323–20329] | switch | std | OK | match |
| 65 | ZS-TYG3-SM-41Z (Tuya) | `tuya.ts:20337` | TS0601, 2 | wall switch | `countdown_l1`–`_l4` DP 7–10 [20364–20367] | std ×4 [20348–20351] | `state_l1`–`_l4` DP 1–4; `state` DP 13 [20360–20368] | switch | std | OK | match |
| 66 | GX03 (GIEX) | `tuya.ts:24785` | TS0601, 3 | valve or irrigation | `countdown_1` DP 13, `_2` DP 14, `countdown` [24818, 24823] (same DPs also map `timer_1`, `timer_2`) | custom: **read-only** (1), min, "Time remaining" [24799, 24810] | `valve_1` DP 1, `valve_2` DP 2 (binary) [24790, 24801] | switch (`valve_1`, `valve_2`) | remaining time; run time is `timer_N`: min, 1–1440, SET only [24792–24809] | n/a | no: read-only, min |
| 67 | EPJ-ZB (Nova Digital) | `tuya.ts:26160` | TS0601 (+zigbeeModel), 1 | curtain | `countdown` DP 108, `raw` [26185] | custom: s, 10–90, "Motor timeout" [26170] | `state` DP 102: OPEN/CLOSE/STOP [26180] | cover | motor timeout | n/a | no: no on/off switch; range |
| 68 | _TZE284_z5jz7wpo (Tuya) | `tuya.ts:26950` | TS0601, 1 | fan | `countdown_hours` DP 2: h × 3600 to seconds, capped 43200 [26969–26976] | custom: **h**, 0.25–12 [26957–26963] | `state` DP 1 [26968] | fan | "Fan ON time in hours" | needs `countdown_hours` (N/3600) | no: name, unit |
| 69 | DS-1450WN (Tuya) | `tuya.ts:28061` | TS0601, 2 | plug / socket | `countdown_usb_a`, `_usb_c`, `_plug_1`, `_plug_2` DP 7–10, `countdown` [28128–28131] | custom, endpoint in the name: s, 0–86400 [28071–28102] | `state_usb_a` … `_plug_2` DP 1–4 [28124–28127] | switch | not stated | OK | no: max 86400 |
| 70 | RM28-LE (Ronco) | `tuya.ts:28339` | TS0601, 1 | curtain | `countdown` DP 8, enum lookup [28371–28380]; `countdown_left` DP 9 [28382] | enum cancel/1h–4h [28350] | `state` DP 1, cover action [28364] | cover | timer to trigger open/close | n/a | no: enum |
| 71 | ZVL-PRO (Nova Digital) | `tuya.ts:29222` | TS0601, 1 | valve or irrigation | `countdown` DP 11, `raw` [29237] | custom: s, 0–86400 [29229] | `state` DP 1 [29235] | switch | not stated | OK | no: max 86400 |
| 72 | TS0601_smart_temperature_switch (Tuya) | `tuya.ts:29339` | TS0601, 1 | thermostat | `countdown` DP 4, `countdown` [29456] | std, changed: access 7, max 86400, category config, "turn device on/off after" [29410–29415] | `state` DP 2, `onOffNotStrict` [29455] | switch | toggle; `autowork` mode also drives the output [29359] | OK | no: max 86400 |
| 73 | TS0601_multifunction_switch (Tuya) | `tuya.ts:30756` | TS0601, 2 | wall switch | `countdown` DP 7, `countdown` [30775] | custom: s, 0–86400, "Countdown to turn off" [30763] | `state` DP 1 [30774] | switch | off after N | OK | no: max 86400 |
| 74 | TS0601_power_monitoring_switch (Tuya) | `tuya.ts:30821` | TS0601, 2 | wall switch | `countdown` DP 7, `countdown` [30836] | custom: unit **`m`**, 0–120, "Countdown to turn off" [30827] | `state` DP 1 [30835] | switch | off after N; unit unclear | unit unclear | no: unit |
| 75 | ZMS-206US-1 (Zemismart) | `zemismart.ts:619` | TS0601, 3 | wall switch | `countdown` DP 7, `raw` [658] | custom: s, 0–43200, 3 [647–653] | `state` DP 1 (DP 13 also maps to `state`) [657, 659] | switch | "Countdown for switch 1" | OK | match |
| 76 | ZMS-206EU-2 (Zemismart) | `zemismart.ts:678` | TS0601, 4 | wall switch | `countdown_l1`, `_l2` DP 7–8 [741–742] | custom, endpoint l1, l2: s, 0–43200 [716–731] | `state_l1`, `_l2` DP 1–2; `state` DP 13 [739–743] | switch | as above | OK | match |
| 77 | ZMS-206EU-3 (Zemismart) | `zemismart.ts:770` | TS0601, 5 | wall switch | `countdown_l1`–`_l3` DP 7–9 [848–850] | custom ×3 [814–837] | `state_l1`–`_l3` DP 1–3; `state` DP 13 [845–851] | switch | as above | OK | match |
| 78 | ZMS-206US-4 (Zemismart) | `zemismart.ts:885` | TS0601, 10 | wall switch | `countdown_l1`–`_l4` DP 7–10 [1001–1004] | custom ×4 [958–989] | `state_l1`–`_l4` DP 1–4; `state` DP 13 [997–1005] | switch | as above | OK | match |
| 79 | ZMS-208US-2 (Zemismart) | `zemismart.ts:1030` | TS0601, 2 | wall switch | `countdown_l1`, `_l2` DP 7–8 [1066–1067] | custom ×2 [1041–1056] | `state_l1`, `_l2` DP 1–2; `state` DP 13 [1064–1068] | switch | as above | OK | match |
| 80 | ZMS-208US-3 (Zemismart) | `zemismart.ts:1078` | TS0601, 2 | wall switch | `countdown_l1`–`_l3` DP 7–9 [1125–1127] | custom ×3 [1091–1114] | `state_l1`–`_l3` DP 1–3; `state` DP 13 [1122–1128] | switch | as above | OK | match |
| 81 | ZMZ609-2 (Zemismart) | `zemismart.ts:1257` | TS0601, 2 | wall switch | `countdown_l1`, `_l2` DP 7–8, `countdown` [1317–1318] | custom `countdown_lN`: s, 0–43200 [1277–1290] | `state_l1`, `_l2` DP 1–2 [1315–1316] | switch | "Countdown for gang N" | OK | match (by property) |
