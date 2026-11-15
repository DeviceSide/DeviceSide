# A60 saturation fade: three ways to halt it, watched (2026-11-15)

Follows [2026-11-13-a60-stop-jump-watched.md](2026-11-13-a60-stop-jump-watched.md), which saw the stop of a saturation
fade jump on ZHA and Zigbee2MQTT, though the bulb's reads had none. For #411. Question: which fade and halt shows no
jump?

Device: Philips Hue A60 color bulb (LCA016, firmware 1.164.2) as `light_color`, on Home Assistant's ZHA, lab rig,
DeviceSide `1a7ca835`, run `rig-run-2026-11-15-215921`. Answers are the watcher's own words.

## Bottom line

1. **`MoveToSaturation` halted by `StopMoveStep` is the closest to smooth.** The watcher: "That was the closest to
   perfect of all 3 runs, but it looked like there was a small step back in saturation at the finish." The light
   stayed green as it paled. ZHA's saturation fades now send it (#411).
2. **`MoveToColor` halted by `StopMoveStep`, the call ZHA sent until now, jumps.** "It jumped in one step, not
   smoothly over 3 s."
3. **Halting the `MoveToColor` fade as Hue does, with `MoveToColor` to the straight-line xy and no transition, is
   smooth until a small step at the halt.** That halt point came from the 2026-11-13 reads timed at 3.05 s; the rig
   sends the halt after a 3 s wait plus Zigbee latency, which can account for the step.
4. **This replaces bottom line 3 of [2026-11-13-a60-color-fade-path.md](2026-11-13-a60-color-fade-path.md)** (an
   xy fade runs in the bulb's own hue and saturation) as the account of what the eye sees: the bulb reports a
   `MoveToColor` fade along its hue and saturation, and the watched jump at `StopMoveStep` says it doesn't render it
   there. Bottom line 4 of the watched file (an ease-in rendering) has no support: `MoveToSaturation`, also an end
   point with a transition, looked smooth.
5. **The small step at the halt in (c) is left as is** unless users report it as visually annoying. No `--debug-logs`
   on this run, so no reads measure it.

## Runs

Each case: the light at 20 % brightness, `hs_color: [135, 90]`, settled 1.5 s; the fade started; halted 3 s later;
then `xy_color` sampled for 4 s. Throwaway step file, never committed.

| Probe | Fade | Halt | Automated (xy steady after the halt) | Watcher saw |
|---|---|---|---|---|
| (a) | `lower_saturation`, sweep 10 s (`MoveToColor`) | DeviceSide `stop` (`StopMoveStep`) | pass | "It jumped in one step, not smoothly over 3 s" |
| (b) | the same | `MoveToColor` to (14670, 36330), transition 0 | pass | "Saturation lowered smoothly but then had a small step at the finish." |
| (c) | `MoveToSaturation` to 0, transition 9.0 s | `StopMoveStep` | pass | "That was the closest to perfect of all 3 runs, but it looked like there was a small step back in saturation at the finish." |

(b)'s halt point is 3.05 s along the straight xy line from the start (11337, 43908) to the end (21168, 21561) over
9.0 s, the reads in the 2026-11-13 fade-path probe. (c)'s 9.0 s is DeviceSide's duration for 90 % at sweep 10 s.

## Not tested

- A bulb in color temperature mode, whose stored hue may be stale for `MoveToSaturation`: DeviceSide sends it
  `MoveToColor` at Home Assistant's hue, as before.
- Zigbee2MQTT's equivalent, which shares the jump: not probed here.
