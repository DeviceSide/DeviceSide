# ZHA · lower_brightness

| | |
|---|---|
| Result | pass |
| Date | 2026-11-04 |
| Source | rig run (`scripts/rig.py`), commit `4f709eb` |
| Profile | lab |
| Home Assistant | 2026.10.2 |
| Device | LTA009, firmware `0x01002a00`; ZBDongle-E, firmware `unknown` |

## Tests

| Test | Target | Result |
|---|---|---|
| `lower_to_off[light_ct]` | `light` (light_ct) | pass |
| `lower_to_off[group]` | `light` (group) | pass |
| `soft_off_keeps_level[light_ct]` | `light` (light_ct) | pass |
| `soft_off_keeps_level[group]` | `light` (group) | pass |
| `lower_to_a_limit[light_ct]` | `light` (light_ct) | pass |
| `lower_to_a_limit[group]` | `light` (group) | pass |
| `lower_stop_lower[light_ct]` | `light` (light_ct) | pass |
| `lower_stop_lower[group]` | `light` (group) | pass |
| `light_raised_mid_room_lower[group]` | `light` (group) | pass |
