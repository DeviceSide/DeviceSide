# Shelly · clear_auto_off

| | |
|---|---|
| Result | pass |
| Date | 2026-11-11 |
| Source | rig run (`scripts/rig.py`), commit `3507e87` |
| Profile | shelly |
| Home Assistant | 2026.10.4 |
| Device | Shelly 1 Mini Gen3 (`S3SW-001X8EU`), firmware `20261026-122213/2.0.3-g4601943` |

## Tests

| Test | Target | Result |
|---|---|---|
| `clears[switch_plug]` | `switch` (switch_plug) | pass |
| `countdown_survives_a_clear[switch_plug]` | `switch` (switch_plug) | pass (firmware fact) |

A firmware fact proves the device's behavior, not the adapter's code: its pass stands at the firmware listed under Device, and may come from an earlier commit at that firmware.
