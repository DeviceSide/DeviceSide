# The Tuya `countdown` on Zigbee2MQTT: converters and upstream reports (2026-11-14)

Research date: 2026-11-14. Scope: which zigbee-herdsman-converters (ZHC) code a Z2M `countdown` or `on_time` publish
reaches on a switch or plug, and what upstream issues report for timed-on calls. Feeds the plan's part 3
([`docs/plans/2026-11-14-device-classes.md`](../../../plans/2026-11-14-device-classes.md), "Step 5 part 3: probe
spec").

Pinned sources, read only, no code run:

- ZHC `afdaa028a0972d801da762196ddfb2df631ea0cc` (2026-11-13). `ZHC/<path>#L<n>` below is
  `https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/<path>#L<n>`.
- Z2M `3c841fdfd66c92239921ef84fde8f039c64e1662`, for how a `/set` payload reaches the converters.

Counts come from grep and are approximate.

## 1. Three converters behind one name

| | Converter | Wire call | Units | Range check | Readback | Definitions |
|---|---|---|---|---|---|---|
| A | `tuya.tz.on_off_countdown` / `tuya.fz.on_off_countdown`, from `tuya.modernExtend.tuyaOnOff({onOffCountdown})` | genOnOff `onWithTimedOff` (0x42) `{ctrlbits: 0, ontime: N, offwaittime: N}` | whole seconds | integer 0..43200, else throws before sending | `/get` reads `onTime`; device reports `onTime` every 60 s while running | 49, about 250 `_TZ…` strings, plus the catch-all `TS011F_plug_1` |
| B | `tuya.tz.datapoints` with a `countdown` datapoint | Tuya `dataRequest` (cluster 0xEF00), DP id varies | as the device defines, mostly seconds | none; raw value | device DP reports only; no `convertGet` | 78, about 210 strings, mostly `TS0601`; one `TS011F` (AVATTO ZOT60) |
| C | `ewelinkExtend.countdown()` | 0x42 `{ontime: N×10, offwaittime: 0}`; 0 sends `off` | tenths on the wire, seconds in the expose | rounds, caps at 0xFFFE tenths | `/get` reads `onTime` ÷ 10 | 1 (eWeLink CK-BL702-MSW-01 and white labels) |

Sources: [`tz.on_off_countdown`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/lib/tuya.ts#L3351-L3407),
[`fz.on_off_countdown`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/lib/tuya.ts#L4057-L4071),
[`tuyaOnOff`, the `onOffCountdown` branch](https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/lib/tuya.ts#L5149-L5175),
[`tz.datapoints`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/lib/tuya.ts#L3299-L3340),
[`valueConverter.countdown`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/lib/tuya.ts#L1637),
[`ewelink_countdown`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/devices/ewelink.ts#L48-L106),
[`TS011F_plug_1`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/devices/tuya.ts#L13227-L13310),
[ZOT60](https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/devices/avatto.ts#L960-L1000).

The name `countdown` is also used for valve and irrigation durations (minutes, or up to 86400 s) and a window
pusher's motor timeout; those are not switch timers.

### Converter A in detail

One call handles both `state` and `countdown`, reading both from the message:

- `state` alone: plain On, Off or Toggle; publishes `countdown: 0` at once, as setting the state cancels a running
  countdown (source comment).
- `countdown` alone: sends only 0x42 `{0, N, N}` and publishes no state. Whether the plug turns on from off is up to
  the device.
- `{"state": "ON", "countdown": N}`: On, then 0x42 `{0, N, N}`, in that fixed order ("on/off/toggle cancels
  onWithTimedOff"); publishes `state: ON, countdown: N`.
- 0 passes the check and goes out as 0x42 `{0, 0, 0}`. The error text calls 0 a cancel; the source doesn't show what
  the device does.
- Above 43200, negative or not an integer: throws `countdown must be an integer between 1 and 43200 (12 hours) or 0
  to cancel`; nothing is sent.
- A second value while running sends another 0x42; replace or extend is not in the source.
- With `onOffCountdown` set, the definition gets `on_off_countdown` instead of `tz.on_off`, so `on_time` and
  `off_wait_time` have no converter: `{"state": "ON", "on_time": N}` sends a plain On, and Z2M logs no converter for
  `on_time`. The lab probe saw this (C6).

The expose depends on how `onOffCountdown` is given: `true` gives `countdown` (or one per endpoint) with access 7; a
function of the manufacturer name, used by 7 definitions including `TS011F_plug_1` and the generic `TS0001`, gives
one un-suffixed `countdown` with access 3 when it returns true, and none otherwise. Where it returns false the
converter is still installed and takes the key. Two function-form definitions have several endpoints
(`TS0002_basic`, `TS0726_4_gang_scene_switch`) yet get a single `countdown`; that looks like an upstream defect, not
checked on a device.

### Key order

Z2M calls each converter once per message. Converter A reads both keys itself, so payload key order doesn't change
its wire order. Converter B loops over the message in the payload's own key order, one DP per key: `countdown`
before `state` sends the countdown DP first, and the state DP that follows may reset it (Nous's `onOffWithZeros`
comment, [nous.ts#L469](https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/devices/nous.ts#L469)).
Z2M's sort reorders only how converters are found
([publish.ts](https://github.com/Koenkk/zigbee2mqtt/blob/3c841fdfd66c92239921ef84fde8f039c64e1662/lib/extension/publish.ts#L153-L290)).

### The expose doesn't tell A from B

A and B publish the same expose (`tuya.exposes.countdown()`: name `countdown`, unit `s`, 0..43200, same
description); only access differs, and access 3 occurs on both. Telling them apart needs the device identity: a
`TS0601` model or a `_TZE…` manufacturer means B, otherwise A, except ZOT60 (`TS011F`, `_TZ3218_…`), which is B. Z2M's
`definition.model` in `bridge/devices` (`ZOT60` vs `TS011F_plug_1`) separates that case.

## 2. Sonoff ZBMINIR2 and SWV

- **ZBMINIR2** uses `m.onOff()`, which installs `tz.on_off`: `on_time` goes out as 0x42 in tenths, with no guard.
  Z2M offers the Sonoff inching setting (`inchingControlSet`) as its timer
  ([ZBMINIR2](https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/devices/sonoff.ts#L11633-L11697),
  [`inchingControlSet`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/devices/sonoff.ts#L2676),
  [`m.onOff`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/lib/modernExtend.ts#L606-L630)).
- **SWV** (model `SWV`) gets `tzLocal.on_off_fixed_on_time`, which divides `on_time` by 10 before `tz.on_off`, so the
  wire carries whole seconds
  ([`on_off_fixed_on_time`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/devices/sonoff.ts#L1698-L1709),
  [SWV](https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/devices/sonoff.ts#L11506-L11511),
  [Z2M #27980](https://github.com/Koenkk/zigbee2mqtt/issues/27980)). The SWV-ZFE is a separate definition on
  `m.onOff()`, without that fix
  ([SWV-ZFE](https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/devices/sonoff.ts#L12279)).

## 3. Upstream issue triage

Method: GitHub issue search for issues created since 2023-11-14 in Koenkk/zigbee2mqtt,
Koenkk/zigbee-herdsman-converters, zigpy/zha-device-handlers, zigpy/zigpy and home-assistant/core gave 1,523 issues.
A regex shortlist (timer terms near failure words) cut them to 218, which a small model triaged from title and body
alone: comments were not read, and bodies were cut at 6,000 characters. 21 were relevant failures, all on Z2M. Outcomes
are as the reporter states them; none was reproduced here. Device names quoted in issues are left out.

### 0x42 countdown in seconds (Tuya `countdown`)

| Issue | Model | Manufacturer | Call | Outcome |
|---|---|---|---|---|
| [ZHC #9786](https://github.com/Koenkk/zigbee-herdsman-converters/issues/9786) | `TS011F` | `_TZ3000_okaz9tjs` | `countdown`, external converter | countdown "doesn't work"; no detail |
| [Z2M #25434](https://github.com/Koenkk/zigbee2mqtt/issues/25434) | `TS011F` | `_TZ3000_dg7fdg92` | `countdown` 3 with On; external converter on `onOff()` | stays on |
| [Z2M #30493](https://github.com/Koenkk/zigbee2mqtt/issues/30493) | `TS011F` | `_TZ3000_gjnozsaz` | `countdown` | time left jumps back below 254 s at random |

`_TZ3000_okaz9tjs` and `_TZ3000_gjnozsaz` are white labels of `TS011F_plug_1` at the pinned SHA, so converter A.
`_TZ3000_dg7fdg92` is not listed and would fall to the same catch-all.

### Standard `on_time`

| Issue | Model | Manufacturer | Call | Outcome |
|---|---|---|---|---|
| [Z2M #22182](https://github.com/Koenkk/zigbee2mqtt/issues/22182) | `TS011F` | `_TZ3000_cehuw1lw`, `_TZ3000_w0qqde0g` | `on_time` 15 (0x42, tenths) | toggles after 150 s, from on or off; a state set cancels the pending toggle |
| [Z2M #21797](https://github.com/Koenkk/zigbee2mqtt/issues/21797) | `TS0001` | `_TZ3000_skueekg3` | `on_time` 5, `off_wait_time` 2 | no timer |
| [Z2M #28914](https://github.com/Koenkk/zigbee2mqtt/issues/28914) | `TS0001` | `_TZ3000_mkmb4sms` | `on_time` 1 | must be on first; runs 10× long |
| [Z2M #26004](https://github.com/Koenkk/zigbee2mqtt/issues/26004) | `B1Z` (Nous) | not given | `on_time` 1 | turns on after 10 s, stays on |
| [Z2M #23845](https://github.com/Koenkk/zigbee2mqtt/issues/23845) | `R7060` (Woox) | not given | `on_time` 300 | ignored, no error |
| [Z2M #27265](https://github.com/Koenkk/zigbee2mqtt/issues/27265) | `S4SW-001X16EU` (Shelly) | not given | `on_time` 2 | refused, `{"cmdId":66,"statusCode":133}` |
| [Z2M #27913](https://github.com/Koenkk/zigbee2mqtt/issues/27913) | `ZBMINIR2` | not given | `on_time` | does nothing |
| [Z2M #32478](https://github.com/Koenkk/zigbee2mqtt/issues/32478) | `S60ZBTPF` | not given | `on_time` 300 | doesn't work, firmware 1.0.2, 2.0.2, 2.0.3 |
| [Z2M #27980](https://github.com/Koenkk/zigbee2mqtt/issues/27980) | `SWV` | not given | `on_time` 2 | open 20 s, 10× long; fixed upstream (§2) |
| [Z2M #32479](https://github.com/Koenkk/zigbee2mqtt/issues/32479) | `SWV-ZFE` | `SONOFF` | `on_time` 1, 5, 30 | valve doesn't start |
| [Z2M #29158](https://github.com/Koenkk/zigbee2mqtt/issues/29158) | `LED2005R5` / `LED2106R3` (IKEA) | not given | `on_time` 300, unicast | on, never off; by group it turns off |
| [Z2M #20912](https://github.com/Koenkk/zigbee2mqtt/issues/20912) | `SIN-4-FP-21_EQU` | not given | `on_time` 900 every 7 min | stops answering after hours, ends off |
| [Z2M #32889](https://github.com/Koenkk/zigbee2mqtt/issues/32889) | any | | `on_time` above 6553.5 | raw `RangeError` from the uint16 field |

\#22182 and #28914 show Tuya ZCL firmware reading 0x42 `on_time` as seconds, which converter A now sends. #22182 adds
that the timer is a toggle, not an off.

### Vendor timers

| Issue | Model | Manufacturer | Call | Outcome |
|---|---|---|---|---|
| [Z2M #20430](https://github.com/Koenkk/zigbee2mqtt/issues/20430) | `ZNCZ12LM` (Aqara) | not given | Auto OFF setting | can't be set |
| [Z2M #31804](https://github.com/Koenkk/zigbee2mqtt/issues/31804) | `TS0003` | `_TZ3000_gvoyoq2q` | inching, external converter | inching doesn't work |
| [Z2M #25303](https://github.com/Koenkk/zigbee2mqtt/issues/25303) | `ZBMINIR2` | not given | `inching_control_set` 1200 s | error; value doubled |
| [ZHC #13383](https://github.com/Koenkk/zigbee-herdsman-converters/issues/13383) | `MINI-ZBD` (ZBMINIR2 white label) | not given | `inching_control_set` | reported value outside the expose; relay latches on and turns back on after a manual off |
| [Z2M #31799](https://github.com/Koenkk/zigbee2mqtt/issues/31799) | `S60ZBTPF` | `SONOFF` | `inching_control_set` disable | no effect; still turns off after about 11 s |

### Reports of a countdown working: candidate evidence

Triaged out as not failures, these report a timer working. Each is one reporter's word, from the issue body:

| Issue | Model | Manufacturer | Converter | Report |
|---|---|---|---|---|
| [Z2M #32034](https://github.com/Koenkk/zigbee2mqtt/issues/32034) | `TS0002` | `_TZ3000_dershnvx` | A (external converter, `onOffCountdown: true`) | "Power off countdown" works |
| [ZHC #10325](https://github.com/Koenkk/zigbee-herdsman-converters/issues/10325) | `TS0601` | `_TZE284_7zazvlyn` | B | countdown writable in seconds |
| [Z2M #30347](https://github.com/Koenkk/zigbee2mqtt/issues/30347) | `TS0601` | `_TZE284_rcke0jsu` | B (DP 7, minutes) | light and fan timers work |
| [Z2M #31969](https://github.com/Koenkk/zigbee2mqtt/issues/31969) | `TS0601` | `_TZE204_hewlydpz` | B (DP 7–10) | "fully functional" |
| [Z2M #32120](https://github.com/Koenkk/zigbee2mqtt/issues/32120) | `TS0001` | `_TZE21C_i2ij4rb3` | B (DP 4) | listed as working; a thermostat |
| [Z2M #31534](https://github.com/Koenkk/zigbee2mqtt/issues/31534) | `CZV20` (eWeLink CK-BL702-MSW-01 white label) | not given | external converter, 0x42 | countdown added; a water valve |

Only #32034 is converter A on a switch.

## 4. The lab plug

The lab probe ran the TS011F on Z2M and ZHA, including the 0x42 from off that switched one plug on 106 s later:
[2026-11-14-lab-probe.md](2026-11-14-lab-probe.md), §2.

## 5. What it settled

Decisions in the plan ([`docs/plans/2026-11-14-device-classes.md`](../../../plans/2026-11-14-device-classes.md),
"Decisions (Jason, 2026-11-14, step 6 review)"):

- **34:** a class keys on what decides the outcome: the integration's routing where it picks the call, otherwise the
  device's identity. On Z2M the converter, set by the definition, picks the call (§1).
- **35:** the Tuya countdown on Z2M stays Experimental. A maker string is Verified only by its own record or manual
  row; a string reported failing (#30493, #9786 above) is a doesn't-work entry that harms.
