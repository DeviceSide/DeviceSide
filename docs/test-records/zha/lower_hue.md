# ZHA · lower_hue

| | |
|---|---|
| Result | pass |
| Date | 2026-11-03 |
| Source | rig run (`scripts/rig.py`), commit `2d70127` |
| Profile | lab |
| Home Assistant | 2026.10.2 |
| Device | Hue Essential lamp (`LCA016`), firmware `1.164.2` |

## Tests

| Test | Target | Result |
|---|---|---|
| `cycles_down_the_wheel[light_color]` | `light` (light_color) | pass |
| `cycles_down_the_wheel[group_color]` | group_color: none in the profile | skipped |
