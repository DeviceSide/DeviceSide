# ZHA · lower_brightness

| | |
|---|---|
| Result | pass |
| Date | 2026-11-03 |
| Source | rig run (`scripts/rig.py`), commit `7d5836f` |
| Profile | lab |
| Home Assistant | 2026.10.2 |
| Device | Hue ambiance lamp (`LTA009`), firmware `1.163.1` |

## Tests

| Test | Target | Result |
|---|---|---|
| `lower_to_off[light_ct]` | `light` (light_ct) | pass |
| `lower_to_off[group]` | `light` (group) | pass |
| `soft_off_keeps_level[light_ct]` | `light` (light_ct) | pass |
| `soft_off_keeps_level[light_ct] observed` | `light` (light_ct) | not observed |
| `soft_off_keeps_level[group]` | `light` (group) | pass |
| `soft_off_keeps_level[group] observed` | `light` (group) | not observed |
| `lower_to_a_limit[light_ct]` | `light` (light_ct) | pass |
| `lower_to_a_limit[group]` | `light` (group) | pass |
| `lower_stop_lower[light_ct]` | `light` (light_ct) | pass |
| `lower_stop_lower[group]` | `light` (group) | pass |
| `light_raised_mid_room_lower[group]` | `light` (group) | pass |

Tests marked `not observed` had nobody watching.
