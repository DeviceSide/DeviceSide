# Hue · raise_brightness

| | |
|---|---|
| Result | pass |
| Date | 2026-11-10 |
| Source | rig run (`scripts/rig.py`), commit `c2916f1` |
| Profile | lab |
| Home Assistant | 2026.10.4 |
| Device | Hue ambiance lamp (`LTA009`), firmware `1.163.1`; Zone, firmware `unknown` |

## Tests

| Test | Target | Result |
|---|---|---|
| `raise[light_ct]` | `light` (light_ct) | pass |
| `raise[group]` | `light` (group) | pass |
| `raise_after_soft_off[light_ct]` | `light` (light_ct) | pass |
| `raise_after_soft_off[group]` | `light` (group) | pass |
| `ha_change_mid_raise[light_ct]` | `light` (light_ct) | pass |
| `ha_change_mid_raise[group]` | `light` (group) | pass |
| `late_stop_report[light_ct]` | `light` (light_ct) | pass (firmware fact) |
| `late_stop_report[group]` | `light` (group) | pass (firmware fact) |

A firmware fact proves the device's behavior, not the adapter's code: its pass stands at the firmware listed under Device, and may come from an earlier commit at that firmware.
