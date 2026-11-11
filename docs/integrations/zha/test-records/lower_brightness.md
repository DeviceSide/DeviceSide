# ZHA · lower_brightness

| | |
|---|---|
| Result | pass |
| Date | 2026-11-11 |
| Source | rig run (`scripts/rig.py`), commit `32dc547` |
| Home Assistant | 2026.10.4 |
| Device | LTA009, firmware `0x01002a00`; ZBDongle-E, firmware `unknown` |

## Tests

| Test | Target | Result |
|---|---|---|
| `lower_to_off[light_ct]` | `light` (light_ct) | pass |
| `lower_to_off[group]` | `light` (group) | pass |
| `soft_off_keeps_level[light_ct]` | `light` (light_ct) | pass (firmware fact) |
| `soft_off_keeps_level[group]` | `light` (group) | pass (firmware fact) |
| `lower_to_a_limit[light_ct]` | `light` (light_ct) | pass |
| `lower_to_a_limit[group]` | `light` (group) | pass |
| `light_raised_mid_room_lower[group]` | `light` (group) | pass |

A firmware fact proves the device's behavior, not the adapter's code: its pass stands at the firmware listed under Device, and may come from an earlier commit at that firmware.
