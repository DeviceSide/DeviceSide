# The lab TS011F's Tuya `countdown` on Zigbee2MQTT: probe (2026-11-15)

Probe date: 2026-11-15. Runs the plan's "Step 5 part 3: probe spec"
([`docs/plans/2026-11-14-device-classes.md`](../../../plans/2026-11-14-device-classes.md)), cases P1, P1b and P2–P7, on
the lab TS011F. What Z2M sends for each publish is the converter reading in
[2026-11-14-tuya-countdown.md](2026-11-14-tuya-countdown.md), §1 (converter A, `tuya.tz.on_off_countdown`); the earlier
probe of the same plug is [2026-11-14-lab-probe.md](2026-11-14-lab-probe.md). This file adds the plug's answers.

## Setup

- Device: TS011F, manufacturer `_TZ3000_0zfrhq4i`, Z2M definition `TS011F_plug_1`, `software_build_id` `0122052017`.
  Its definition exposes `countdown`.
- Home Assistant 2026.10.4, Zigbee2MQTT 2.14.3, zigbee-herdsman-converters 26.125.0.
- A script published to `zigbee2mqtt/<plug>/set` (and `/get`) through HA's `mqtt.publish`, inside the rig's Z2M lock
  (`rig.py --hold zigbee2mqtt`). It logged each publish, each state payload on `zigbee2mqtt/<plug>` and each line on
  `zigbee2mqtt/bridge/logging`, timed from the case's first publish. State and time-left come from those payloads.
- Before each case: a `/get` of `countdown` read 0, then the plug was set to the case's pre-state and left 3 s.
- Two full runs, 17:15 and 17:32 local time. The table is the second; the first agreed on every case to within 0.1 s
  except P5 (no button press landed) and P6 (noted below).
- **What Z2M sent is not logged here.** Z2M's log level was `debug`, with `log_debug_to_mqtt_frontend` on for the
  second run, but neither the MQTT log feed nor Z2M's frontend log showed any `zh:` debug line for these commands, only
  `info` state publishes. Z2M likely needs a restart for the setting. The wire calls are therefore the converter
  reading's, and every state payload below matches it.

## Results

Times are seconds from the case's first publish. "Report" is Z2M's state payload for the plug.

| Case | Pre | Publishes (t s) | Reports (t s: state, countdown) | State at end | Answer |
|---|---|---|---|---|---|
| P1 | on | 0: `{"countdown": 10}` | 0.15: ON, 10 · 10.16: OFF, 10 · 10.39: OFF, 0 | off (25 s) | a countdown starts without `state`: off at 10.2 s |
| P1b | off | 0: `{"countdown": 10}` | 0.16: OFF, 10 · 10.21: ON, 10 · 10.30: ON, 0 | on (140 s) | 0x42 alone doesn't turn it on; at 10.2 s it toggles on and stays on |
| P2 | off | 0: `{"state": "ON", "countdown": 30}` · 5: `{"countdown": 10}` | 0.09: ON, 30 · 5.16: ON, 10 · 15.15: OFF, 10 · 15.38: OFF, 0 | off (50 s) | replace: off at 15.2 s (5 + 10), not ~35 s |
| P3 | off | 0: `{"state": "ON", "countdown": 30}` · 5: `{"state": "OFF"}` · 6: `{"state": "ON"}` | 0.10: ON, 30 · 5.07: OFF, 0 · 6.07: ON, 0 | on (45 s) | off cancels it: still on at 45 s |
| P4 | off | 0: `{"state": "ON", "countdown": 30}` · 5: `{"countdown": 0}` | 0.10: ON, 30 · 5.15: ON, 0 | on (45 s) | 0 cancels it: still on at 45 s |
| P5 | off | 0: `{"state": "ON", "countdown": 30}` · 5: button pressed twice | 0.11: ON, 30 · 8.74: OFF, 30 · 8.93: OFF, 0 · 9.55: ON, 0 | on (45 s) | a local toggle cancels it: still on at 45 s |
| P6 | off | 0: `{"state": "ON", "countdown": 150}` · 5: `/get` `{"countdown": ""}` | 0.10: ON, 150 · 5.08: ON, 150 · 150.22: OFF, 150 · 150.42: OFF, 0 | off (165 s) | time left can't be read: the `/get` at 5 s reads 150, the value set; off at 150.2 s |
| P7, 1 | off | 0: `{"state": "ON", "countdown": 1}` | 0.09: ON, 1 · 1.19: OFF, 1 · 1.39: OFF, 0 | off (15 s) | 1 reaches the plug: off at 1.2 s |
| P7, 43200 | off | 0: `{"state": "ON", "countdown": 43200}` · 5: `/get` · 8: `{"countdown": 0}` · 15: `/get` | 0.14: ON, 43200 · 5.07: ON, 43200 · 8.16: ON, 0 · 15.05: ON, 0 | on, cleared (15 s) | 43200 reaches the plug (`/get` reads it back); 0 clears it |
| P7, 43201 | off | 0: `{"state": "ON", "countdown": 43201}` | none | off (10 s) | Z2M refuses it before sending, `state` included (log below) |

Case start times (second run, local): P1 17:32:55.0, P1b 17:33:23.2, P2 17:35:46.7, P3 17:36:39.9, P4 17:37:28.3,
P5 17:38:26.7, P6 17:39:15.2, P7 17:42:03.4 (1), 17:42:21.6 (43200), 17:42:40.3 (43201).

P6, unprompted reports: the first run's plug sent one at 88.6 s, reading `countdown` 150; the second sent none between
5 s and the off. So a report while running carries the value set, not the time left, and doesn't come every 60 s here.

P5, first run: no button press landed (no report between 0.1 s and 30 s), and the plug went off at 30.2 s. Not a
result; the second run's presses are.

Z2M's only log line for a probe publish, P7 at 43201 (`error`, t 0.01 s):

```
z2m: Publish 'set' 'state' to '<plug>' failed: 'Error: countdown must be an integer between 1 and 43200 (12 hours) or 0 to cancel'
```

## What it shows

- The timer is a toggle at expiry, not an off: from on it ends off (P1), from off it ends on (P1b), as #22182 reports
  (research §3).
- A new value replaces the running one (P2). An off, a `countdown: 0` and a local button toggle each cancel it (P3–P5).
- Time left can't be read: `/get` and reports carry the value last set (P6).
- The bounds are 1 to 43200 s, both reaching the plug; Z2M refuses 43201 before anything is sent (P7).
