# A60 color fade path and its stop: live probe (2026-11-13)

Question: the watched `stop` case `halts_brightness_and_saturation[light_color]` failed on ZHA ("saturation jumped
paler after the brightness stop") and on Zigbee2MQTT ("slight jump at the stop"); it passed on Hue. The halted xy
read off the bulb sits far from the straight CIE xy line between the fade's ends, which suggested the bulb renders
one path and stores another, snapping to the stored point on `StopMoveStep`. Does the reported xy follow the
straight line and jump at the stop, or run off it from the start?

Device: Philips Hue A60 color bulb (LCA016, firmware 1.164.2), Home Assistant's ZHA and Zigbee2MQTT 2.14.3, lab rig,
DeviceSide `e385562`.

## Bottom line

1. **The bulb fades MoveToColor along a curve, not a straight line in xy.** It reports ColorMode xy throughout, but its
   own CurrentHue and CurrentSaturation fall at a steady rate per read, which fits a fade that is linear in the bulb's
   hue and saturation, with xy worked out from them. A fade toward white therefore swings the hue: green 136° on the
   bulb's wheel reached 100° (yellow-green) 2.5 s into a 9 s fade.
2. **The stop halts on that curve, with no jump in any attribute.** The halt continues the path, and every read for
   4 s (ZHA) or 5 s (Z2M) after it is identical. The same holds with a brightness raise running alongside, so the
   level `Stop` changes nothing in the color attributes.
3. **The earlier "off its path" reading was a wrong baseline**: the halt was compared with the straight line, not the
   bulb's curve. Halting with `MoveToColor` to the straight-line xy, transition 0 (as Hue's halt writes its
   predicted xy) would make the jump, not remove it.
4. Whatever the watched runs saw is not in the bulb's reported state. Only a watched A/B can say more: the
   saturation fade stopped alone, and with the brightness raise.

## Method

A throwaway step file, run on `light_color` with `--debug-logs` and never committed (`rig-run-2026-11-13-152029` on
ZHA, `rig-run-2026-11-13-152355` on Zigbee2MQTT). The `sample` steps poll `deviceside.get_attributes`, a live read of
the bulb, as fast as the round trip allows (about every 0.65 s); the values below are the attribute reads in the HA
(ZHA) and Zigbee2MQTT logs.

```yaml
action: stop
tests:
  - name: probe_saturation_path_alone
    roles: [light_color]
    setup:
      - set: {state: on, brightness_pct: 20, hs_color: [135, 90]}
      - wait: 1.5
    steps:
      - call: {action: lower_saturation, sweep_time: 10}
      - sample: {attribute: xy_color.0, for: 2, every: 0.25, expect: rising, source: deviceside}
      - call: {}
      - sample: {attribute: xy_color.0, for: 4, every: 0.25, expect: steady, source: deviceside}
  # probe_saturation_path_with_brightness: the same, with raise_brightness (sweep_time 10) called 1 s before
  # lower_saturation, as in the watched case
```

## ZHA

`MoveToColor` (11337, 43908) → (21168, 21561), that is (0.173, 0.670) → (0.323, 0.329), transition 9.0 s, sent at
15:20:57.331; `StopMoveStep` at 59.877 (2.55 s in), level `Stop` 0.10 s later.

| t (s) | CurrentX, CurrentY | x, y of the way | CurrentHue (°) | CurrentSaturation |
|---|---|---|---|---|
| 0.42 | 12902, 43889 | 16 %, 0 % | 96 (136°) | 223 |
| 1.10 | 17044, 40205 | 58 %, 17 % | 88 (125°) | 206 |
| 1.79 | 18800, 38192 | 76 %, 26 % | 81 (115°) | 189 |
| 2.43 | 20270, 36301 | 91 %, 34 % | 74 (105°) | 173 |
| stop 2.55 | | | | |
| 3.12 to 7.48 (8 reads) | 20888, 35483 | 97 %, 38 % | 71 (101°) | 167 |

Saturation falls 24 to 25 steps a second and hue about 11, each steady. The halt (0.319, 0.541) is where the curve
was heading; the straight line at 2.55 s is (0.215, 0.573). With the brightness raise alongside, the reads were
within 100 units of these, halting at (20864, 35515) and holding for 4 s.

## Zigbee2MQTT

The fade is Z2M's `color: {hue: 135, saturation: 0}`, `transition: 8.9`, with `hue_native_control` on; the bulb
reports ColorMode xy. Reads: (14956, 42108), (17616, 39536), (19269, 37530), (20718, 35634) at 0.58 to 2.57 s, hue 93
→ 72, saturation 216 → 167; `stopMoveStep` at 2.59 s, then (21119, 35118), hue 70, saturation 163, unchanged over 7
reads to 7.5 s. The run with brightness halted at (20934, 35346) and held. Same curve, same halt, no jump.
