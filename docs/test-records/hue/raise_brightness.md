# Hue · raise_brightness

| | |
|---|---|
| Result | pass |
| Date | 2026-11-02 |
| Source | rig run (`scripts/rig.py`), commit `f5db697` |
| Profile | lab |
| Home Assistant | 2026.10.2 |
| Device | Hue ambiance lamp (`LTA009`), firmware `1.163.1` |

## Tests

| Test | Target | Result |
|---|---|---|
| `raise[light_ct]` | `light` (light_ct) | pass |
| `raise[group]` | `light` (group) | pass |
| `raise_from_off[light_ct]` | `light` (light_ct) | pass |
| `raise_from_off[group]` | `light` (group) | pass |
| `raise_after_soft_off[light_ct]` | `light` (light_ct) | pass |
| `raise_after_soft_off[group]` | `light` (group) | pass |
| `raise_stop_raise[light_ct]` | `light` (light_ct) | pass |
| `raise_stop_raise[group]` | `light` (group) | pass |
| `ha_change_mid_raise[light_ct]` | `light` (light_ct) | pass |
| `ha_change_mid_raise[group]` | `light` (group) | pass |
| `late_stop_report[light_ct]` | `light` (light_ct) | pass |
| `late_stop_report[group]` | `light` (group) | pass |
