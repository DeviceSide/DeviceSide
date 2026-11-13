# A60 jump at the stop: watched runs (2026-11-13)

Follows [2026-11-13-a60-color-fade-path.md](2026-11-13-a60-color-fade-path.md), which found that the bulb's own
reported state has no jump at `StopMoveStep`: the reads continue the fade's path and hold after the stop. Question:
what does a person at the light see, and where?

Devices: Philips Hue A60 color bulb (LCA016, firmware 1.164.2) as `light_color`; Philips Hue white ambiance E27
(9290024684, firmware 1.163.1) as `light_ct`. Home Assistant's ZHA and Zigbee2MQTT 2.14.3, lab rig, DeviceSide
`54278fc`. Answers are the watcher's own words.

## Bottom line

1. **The jump is real to the eye and is in the saturation, not the brightness.** Stopping a saturation fade alone
   shows it; with a brightness raise alongside, "the brightness is smooth. Saturation change lands as a jump at the
   stop." Same on ZHA and Zigbee2MQTT. Hue passes the same case.
2. **The bulb's reads show no jump** (the earlier probe), so the bulb renders the fade differently from the state it
   reports, and the stop snaps the rendered light to the reported point.
3. **A soft off on the white ambiance bulb looked unmoving while its reads fell.** CurrentLevel fell 254 → 166 over
   3 s of a 10 s fade, but the watcher saw "full brightness throughout".
4. **Unproven lead:** these bulbs render a `MoveTo…` transition on an ease-in curve while reporting it linearly, so
   2-3 s into a 9-10 s fade little has visibly changed and the stop lands as a jump. Against it: the brightness raise
   in the same A/B is also a `MoveToLevel` with a transition, and it looked smooth. The next probe is a rate-based
   `Move` (level `Move`, `MoveSaturation`) beside the `MoveTo…` with a transition, each stopped at 3 s, watched.

## Runs

| Run | Integration | Case | Watcher saw |
|---|---|---|---|
| `rig-run-2026-11-13-155739` | ZHA | `stop` `halts_brightness_and_saturation[light_color] observed` | "a jump at the stop. I can't tell whether it's a brightness or saturation jump, as both are leading to more white" |
| `rig-run-2026-11-13-155739` | Zigbee2MQTT | the same | "same jump as before" |
| `rig-run-2026-11-13-155739` | Zigbee2MQTT | `stop` `halts_a_lower_to_off[light_ct] observed` | "It stayed at full brightness throughout" |
| `rig-run-2026-11-13-163235` | ZHA | A/B: saturation fade alone, stopped | "Saturation jumped in << 2 seconds" |
| `rig-run-2026-11-13-163235` | ZHA | A/B: saturation fade with brightness raise, stopped | "The brightness is smooth. Saturation change lands as a jump at the stop." |
| `rig-run-2026-11-13-163235` | Zigbee2MQTT | soft-off probe, `light_ct`, read live | (not watched; reads below) |

Raise_hue's `hue_stop_raise[light_color] observed` (an `EnhancedMoveHue`, rate-based) passed on both integrations in
`155739`.

## A/B method

Throwaway step files, never committed, with the shipped case's setup and timing: the light at 20 % brightness,
`hs_color: [135, 90]`; after 1 s `lower_saturation` (sweep 10 s), stopped 2 s later. The second case also calls
`raise_brightness` (sweep 10 s) 1 s before the saturation fade, as the shipped case does. Both automated halves
passed on ZHA. The Zigbee2MQTT A/B did not run: its setup's 20 % set read back 255 within 3 s (a rig or roam
fault, not diagnosed).

## Soft-off reads (Zigbee2MQTT, `light_ct`)

`lower_brightness` (sweep 10 s) from full brightness, stopped after 2.8 s, CurrentLevel read live about every 0.7 s:
254 (before), 244, 227, 209, 191, 174, then 166 at the stop and unchanged over four more reads (3 s). The reads fall
steadily about 25 a second.
