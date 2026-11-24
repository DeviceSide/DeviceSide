# The Tuya datapoint countdown call on Zigbee2MQTT: one publish, the spec and the model check (2026-11-24)

Research date: 2026-11-24. Scope: the evidence the single-endpoint datapoint plan
([`docs/plans/2026-11-24-tuya-datapoint-single-endpoint.md`](../../../plans/2026-11-24-tuya-datapoint-single-endpoint.md))
rests on: where its Decision 4 (one publish) comes from and the ZHC reading behind it, Tuya's spec for Decision 5
(the toggle), and a check of each admitted definition's model string and countdown limit. Read only, no code run, no
device probed.

Pinned sources:

- Zigbee2MQTT 2.14.3, tag commit `3c841fdfd66c92239921ef84fde8f039c64e1662` (2026-11-01), the release the rig runs and
  the latest Z2M release today. Its [`package.json`](https://github.com/Koenkk/zigbee2mqtt/blob/3c841fdfd66c92239921ef84fde8f039c64e1662/package.json) pins `zigbee-herdsman-converters`
  `26.125.0` and `zigbee-herdsman` `11.2.0`, as does its `pnpm-lock.yaml`. `Z2M/<path>#L<n>` below is
  `https://github.com/Koenkk/zigbee2mqtt/blob/3c841fdfd66c92239921ef84fde8f039c64e1662/<path>#L<n>`.
- ZHC `v26.125.0`, commit `c18c32d94c77f683fa768618d1fd32b348fdd7b9` (2026-10-27), the ZHC that Z2M 2.14.3 ships.
  `ZHC/<path>#L<n>` below is `https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/<path>#L<n>`.
- ZHC `v26.136.0` (2026-11-22), the latest ZHC release, for the model check only.
- zigbee-herdsman `v11.2.0`, commit `c1a54e3d52858fa0055aeaf1cf74c3dac65e9811`.
- Tuya, [General Countdown](https://developer.tuya.com/en/miniapp/solution-ai/ability/lamp-solution/lamp/module-set/common-countdown.md),
  fetched 2026-11-24.

**The SHA the earlier notes cite is newer than what Z2M 2.14.3 ships.** The datapoint note
([2026-11-14-tuya-datapoint-countdown.md](2026-11-14-tuya-datapoint-countdown.md)) and the converter note
([2026-11-14-tuya-countdown.md](2026-11-14-tuya-countdown.md)) read ZHC `afdaa028` (2026-11-13), which is 155 commits
ahead of `v26.125.0`. `tz.datapoints` is the same at both, and at `v26.136.0` (compared line for line); only its line
numbers differ (3299–3340 at `afdaa028`, 3237–3278 here). Two admitted definitions differ: see 3.

## 1. Decision 4: one publish

### Provenance

Decision 67 of the device-classes plan ([2026-11-14-device-classes.md](../../../plans/2026-11-14-device-classes.md))
set a two-phase "safe call pattern" for every datapoint countdown: send the state, wait for the device to report it,
only then send the countdown, and arm nothing if the report doesn't come. That was Jason's design call on 2026-11-14,
reasoned from the toggle (a countdown armed on a device that is off turns it on at zero), with no device evidence: no
datapoint device has been in the lab. Its twin for converter A (0x42) was dropped on 2026-11-15, after the TS011F probe
([2026-11-15-tuya-countdown-probe.md](2026-11-15-tuya-countdown-probe.md)) and the ZHC reading showed that the On's
`await` already stops a lost On from being followed by the timer ([`internals.md`](../internals.md), "The harm the
order prevents"). The reading below shows converter B gives the same guarantee, so the plan drops the pattern here too
(Jason, 2026-11-24). The lab plugs can't test it: they take converter A, a different call (evidence tenet 5).

### The ZHC reading

`tz.datapoints` ([ZHC/src/lib/tuya.ts#L3237-L3278](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/lib/tuya.ts#L3237-L3278)):

```ts
    datapoints: {
        convertSet: async (entity, key, value, meta) => {
            // A set converter is only called once; therefore we need to loop
            const state: KeyValue = {};
            if (Array.isArray(meta.mapped)) throw new Error("Not supported for groups");
            const datapoints = meta.mapped.meta?.tuyaDatapoints;
            if (!datapoints) throw new Error("No datapoints map defined");
            for (const [attr, value] of Object.entries(meta.message)) {
                const convertedKey: string =
                    meta.mapped.meta.multiEndpoint && meta.endpoint_name && !attr.startsWith(`${key}_`) ? `${attr}_${meta.endpoint_name}` : attr;
                const dpEntry = datapoints.find((d) => d[1] === convertedKey);
                if (!dpEntry?.[1] || !dpEntry?.[2].to) {
                    throw new Error(`No datapoint defined for '${attr}'`);
                }
                if (dpEntry[3]?.skip?.(meta)) continue;
                const dpId = dpEntry[0];
                const convertedValue = await dpEntry[2].to(value, meta);
                const sendCommand = utils.getMetaValue(entity, meta.mapped, "tuyaSendCommand", undefined, "dataRequest");
                if (convertedValue === undefined) {
                    // conversion done inside converter, ignore.
                } else if (typeof convertedValue === "boolean") {
                    await sendDataPointBool(entity, dpId, convertedValue, sendCommand, 1);
                } else if (typeof convertedValue === "number") {
                    await sendDataPointValue(entity, dpId, convertedValue, sendCommand, 1);
                } else if (typeof convertedValue === "string") {
                    await sendDataPointStringBuffer(entity, dpId, convertedValue, sendCommand, 1);
                } else if (Array.isArray(convertedValue)) {
                    await sendDataPointRaw(entity, dpId, Buffer.from(convertedValue), sendCommand, 1);
                } else if (convertedValue instanceof Enum) {
                    await sendDataPointEnum(entity, dpId, convertedValue.valueOf(), sendCommand, 1);
                } else if (convertedValue instanceof Bitmap) {
                    await sendDataPointBitmap(entity, dpId, convertedValue.valueOf(), sendCommand, 1);
                } else {
                    throw new Error(`Don't know how to send type '${typeof convertedValue}'`);
                }

                if (dpEntry[3] && dpEntry[3].optimistic === false) continue;

                state[attr] = value;
            }
            return {state};
        },
```

What it does with `{"state": "ON", "countdown": N}` on a single-endpoint device's base topic:

- **One converter call for the whole payload.** `tuyaBase({dp: true})` adds `tz.datapoints` with no `key`
  ([ZHC/src/lib/tuya.ts#L4728-L4731](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/lib/tuya.ts#L4728-L4731)), so Z2M matches it on the payload's first key,
  `state`, and skips it for `countdown`: "Use a converter for set only once"
  ([Z2M/lib/extension/publish.ts#L194-L205](https://github.com/Koenkk/zigbee2mqtt/blob/3c841fdfd66c92239921ef84fde8f039c64e1662/lib/extension/publish.ts#L194-L205)). `meta.message` is the whole
  payload ([#L219-L234](https://github.com/Koenkk/zigbee2mqtt/blob/3c841fdfd66c92239921ef84fde8f039c64e1662/lib/extension/publish.ts#L219-L234)).
- **Payload order.** It loops `Object.entries(meta.message)` (3244), which for these string keys is the order they
  arrived in, so the `state` datapoint goes out before `countdown`. On a base topic `meta.endpoint_name` is unset, so
  each key is looked up as written (3245–3247). A key with no datapoint throws (3248–3250).
- **Each send is awaited, and a failed one throws.** Every branch awaits a `sendDataPoint*` (3257–3268), each of which
  awaits `sendDataPoints` ([ZHC/src/lib/tuya.ts#L618-L626](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/lib/tuya.ts#L618-L626),
  [#L652-L674](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/lib/tuya.ts#L652-L674)):

  ```ts
  export async function sendDataPoints(entity: Zh.Endpoint | Zh.Group, dpValues: Tuya.DpValue[], cmd = "dataRequest", seq?: number) {
      if (seq === undefined) {
          seq = globalStore.getValue(entity, "sequence", 0);
          globalStore.putValue(entity, "sequence", (seq + 1) % 0xffff);
      }

      await entity.command("manuSpecificTuya", cmd as "dataRequest", {seq, dpValues}, {disableDefaultResponse: true});
      return seq;
  }
  ```

  `Endpoint.command` awaits `zclCommand` ([endpoint.ts#L950-L960](https://github.com/Koenkk/zigbee-herdsman/blob/c1a54e3d52858fa0055aeaf1cf74c3dac65e9811/src/controller/model/endpoint.ts#L950-L960)),
  which rethrows a failed send ([#L1196-L1212](https://github.com/Koenkk/zigbee-herdsman/blob/c1a54e3d52858fa0055aeaf1cf74c3dac65e9811/src/controller/model/endpoint.ts#L1196-L1212)). So a `state`
  that herdsman can't deliver throws before `countdown` is built, and no countdown goes out. `disableDefaultResponse:
  true` means "failed" is herdsman's delivery failing; a datapoint the device receives and ignores is not detected.
- **The state it returns is optimistic.** It returns every key it sent as `state` (3273–3277), and Z2M publishes that
  as the device's state when `optimistic` is on, its default
  ([Z2M/lib/extension/publish.ts#L250-L267](https://github.com/Koenkk/zigbee2mqtt/blob/3c841fdfd66c92239921ef84fde8f039c64e1662/lib/extension/publish.ts#L250-L267)). Z2M's state publish after a
  set is therefore its own echo, which a "wait for the report" can't tell from the device's own report: the wait
  Decision 67 asked for has no signal to wait on, short of turning `optimistic` off per device.
- **A throw is logged, not published.** Z2M catches it and logs `Publish 'set' 'state' to '<device>' failed: …`
  ([#L282-L287](https://github.com/Koenkk/zigbee2mqtt/blob/3c841fdfd66c92239921ef84fde8f039c64e1662/lib/extension/publish.ts#L282-L287)), with no optimistic state; the converter still counts as
  used (289), so `countdown` isn't retried. That log line is what `set_check` reads.

What stays, as on converter A: a `state` delivered but whose delivery herdsman reports as failed, or a `countdown`
that fails after the `state` went out, leaves the device switched with no timer; Z2M logs the set as failed. A local
toggle in the milliseconds between the two frames would put the timer on the other state.

Per-definition notes on the same path:

- **Dimmers' `state` skip.** On the dimmers, DP 1 carries `{skip: tuya.skip.stateOnAndBrightnessPresent}`, so a
  payload holding `brightness` would skip the state datapoint (3251). The countdown publish carries no light fields.
- **ZMS-206US-1** maps `state` to DP 1 and DP 13 ([ZHC/src/devices/zemismart.ts#L624-L627](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/zemismart.ts#L624-L627));
  `datapoints.find` takes the first, DP 1.
- **FK_V02** sets `multiEndpoint: true` with an endpoint map naming every key on endpoint 1
  ([ZHC/src/devices/frankever.ts#L22-L29](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/frankever.ts#L22-L29)). Z2M's endpoint names are that map's
  keys ([Z2M/lib/model/device.ts#L135-L147](https://github.com/Koenkk/zigbee2mqtt/blob/3c841fdfd66c92239921ef84fde8f039c64e1662/lib/model/device.ts#L135-L147)), so its suffix match
  (`^(.*?)_(state|…|countdown)$`, [publish.ts#L172-L192](https://github.com/Koenkk/zigbee2mqtt/blob/3c841fdfd66c92239921ef84fde8f039c64e1662/lib/extension/publish.ts#L172-L192)) matches neither
  `state` nor `countdown`; `endpoint_name` stays unset and the keys pass unchanged. Its exposes carry no endpoint.
- **GL-SPI-206P** lists its own `glspi206p_light` converter for `state`
  ([ZHC/src/devices/gledopto.ts#L291-L305](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/gledopto.ts#L291-L305)). It awaits its own
  `sendDataPoints`, and `tz.datapoints` then sends DP 1 again before the countdown (datapoint note, §5). If the first
  send fails, Z2M logs the set as failed, and the second pass still sends DP 1 before the countdown, so the same
  guarantee holds.
- **D5Z**'s state converter publishes `countdown: 0` whenever the reported state changes, with the comment "setting/
  changing the state resets the countdown, but device doesn't report it"
  ([ZHC/src/lib/tuya.ts#L1831-L1841](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/lib/tuya.ts#L1831-L1841)). The publish sends the state before the
  countdown, so the reset comes first. Its readback shows 0 while the timer runs; no read is served.

## 2. Decision 5: Tuya's General Countdown spec

From [developer.tuya.com, General Countdown](https://developer.tuya.com/en/miniapp/solution-ai/ability/lamp-solution/lamp/module-set/common-countdown.md)
(fetched 2026-11-24):

> The countdown can set the time after which the current light turns off or on.
> - If it is currently on, it will turn off after the set duration.
> - If it is currently off, it will turn on after the set duration.

> In what cases will the countdown function be canceled (cleared)?
> 1. The countdown DP sent by the panel is 0 (that is, the countdown is canceled through the clear button in the
>    control panel or the countdown time is reset to 0 hours and 0 minutes);
> 2. During the countdown execution period, the device on/off status changes, including local device button control,
>    App panel remote control, timed control execution, etc.;
> 3. The device is powered off and then powered on again or the module is restarted.

Limits of the source: the page is Tuya's lamp panel (mini-app) guide, not a Zigbee MCU spec. Its DP table gives
`countdown` as a value of "0 - 1440" with no unit, unlike Z2M's seconds (0–43,200 or 0–86,400), and its reporting
note names Wi-Fi+BLE only. That a Zigbee datapoint device follows the same toggle and clearing rules is an inference
from Tuya's shared DP model, not measured here; ZHC's standard expose text, "Toggle the device after a set duration
(one time action)" ([ZHC/src/lib/tuya.ts#L702-L709](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/lib/tuya.ts#L702-L709)), and D5Z's comment above agree
with it. Case 3 adds one the plan doesn't name: a power cycle clears the timer.

## 3. Model string check

Each definition in the plan's "The classes", at ZHC `v26.125.0` (what Z2M 2.14.3 ships) and `v26.136.0` (latest).
"std" is `tuya.exposes.countdown()`: unit `s`, 0–43,200, step 1, `STATE_SET`
([ZHC/src/lib/tuya.ts#L702-L709](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/lib/tuya.ts#L702-L709)). Lines are `v26.125.0`'s: the `model` line, the
countdown expose, the countdown datapoint. Every one exposes `countdown` with no `withEndpoint`.

| Plan limit | Model | v26.125.0 source | Expose: unit, max | v26.136.0 |
|---|---|---|---|---|
| 43,200 | ZDMS16-1 | [avatto.ts#L434](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/avatto.ts#L434), 441, DP 6 452 | std | same |
| 43,200 | ZOT60 | [avatto.ts#L969](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/avatto.ts#L969), 976, DP 9 993 | std | same |
| 43,200 | FK_V02 | [frankever.ts#L12](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/frankever.ts#L12), 20, DP 9 32 | `s`, 43,200, "Countdown timer in seconds" | same |
| 43,200 | GL-SPI-206P | [gledopto.ts#L1259](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/gledopto.ts#L1259), 1302, DP 7 1357 | std | same |
| 43,200 | SFD02-Z | [moes.ts#L945](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/moes.ts#L945), 952, DP 6 966 | std | same |
| 43,200 | SFD02-Z_2 | **absent** | | [moes.ts#L986](https://github.com/Koenkk/zigbee-herdsman-converters/blob/v26.136.0/src/devices/moes.ts#L986): std, DP 6 |
| 43,200 | QADZ1LR | [qa.ts#L346](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/qa.ts#L346), 352, DP 6 369 | std | same |
| 43,200 | `TS0601_dimmer_1_gang_1` | [tuya.ts#L6144](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/tuya.ts#L6144), 6177, DP 6 6199 | std | same |
| 43,200 | `TS0601_dimmer_1_gang_2` | [tuya.ts#L6227](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/tuya.ts#L6227), 6233, DP 6 6244 | std | same |
| 43,200 | `TS0601_dimmer_5` | [tuya.ts#L6474](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/tuya.ts#L6474), 6481, DP 6 6501 | std | same |
| 43,200 | MG-ZG01W | [tuya.ts#L7718](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/tuya.ts#L7718), 7723, DP 7 7734 | std | same |
| 43,200 | `_TZE28C1000000_jlbsptkl` | [tuya.ts#L10247](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/tuya.ts#L10247), 10254–10260, DP 7 10277 | `s`, 43,200, "Switch 1 Countdown" | same |
| 43,200 | ZMS-206US-1 | [zemismart.ts#L587](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/zemismart.ts#L587), 615–621, DP 7 626 | `s`, 43,200, "Countdown for switch 1" | same |
| 86,400 | TO-DM-W/B | [tuya.ts#L7621](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/tuya.ts#L7621), 7655–7661, DP 6 7683 | `s`, 86,400, "Countdown timer" | same |
| 86,400 | `TS0601_multifunction_switch` | [tuya.ts#L29486](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/tuya.ts#L29486), 29493, DP 7 29505 | `s`, 86,400, "Countdown to turn off" | same |
| 86,400 | D1Z | **absent** | | [nous.ts#L494](https://github.com/Koenkk/zigbee-herdsman-converters/blob/v26.136.0/src/devices/nous.ts#L494): std with max 86,400, DP 105 |
| 86,400 | D5Z | [nous.ts#L408](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/nous.ts#L408), 418, DP 105 475 | std with max 86,400 | same |
| 7,210 | ZBS16 | [avatto.ts#L518](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/avatto.ts#L518), 532–538, DP 103 573 | `seconds`, 7,210, "Countdown to turn device off after a certain time" | same |

"same" means the same model string, unit and max at `v26.136.0` (line numbers shift). The plan's three valves left out
by Decision 2 read as the datapoint note has them, at `v26.125.0`: FK-BV05 ([frankever.ts#L48](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/frankever.ts#L48),
`s`, 86,400, "Irrigation Duration (countdown in seconds)"), ZVL-PRO ([tuya.ts#L28032](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/tuya.ts#L28032),
`s`, 86,400, "Countdown time in seconds"), ZG-308Z ([hobeian.ts#L253](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/devices/hobeian.ts#L253), `s`, 86,400,
"Valve countdown in seconds", on a `switch` key).

Differences from the plan:

- **D1Z and SFD02-Z_2 are not in the ZHC that Z2M 2.14.3 ships.** D1Z was added in ZHC `v26.126.0`
  ([#13665](https://github.com/Koenkk/zigbee-herdsman-converters/pull/13665)), SFD02-Z_2 in `v26.127.0`
  ([#13666](https://github.com/Koenkk/zigbee-herdsman-converters/pull/13666)); no Z2M release carries either yet. On
  2.14.3 no device reports those definition models, so their allowlist entries match nothing until Z2M's next release.
  At `v26.136.0` both read as the plan has them (model string, unit `s`, max).
- **ZBS16's expose text** is "Countdown to turn device off after a certain time"; the plan quotes it cut short. Unit
  `seconds` and max 7,210 match.
- Every other model string and `value_max` matches the plan at both releases.
