# ZHA · lower_hue

| | |
|---|---|
| Result | pass |
| Ran | 1 passed, 1 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `7b50c5b` |
| Home Assistant | 2026.10.4 |
| Device | LCA016, firmware `0x01001200` |

## Tests

| Test | Target | Result |
|---|---|---|
| `cycles_down_the_wheel[light_color]` | `light` (light_color) | pass |
| `cycles_down_the_wheel[group_color]` | group_color: none in the profile | skipped |
