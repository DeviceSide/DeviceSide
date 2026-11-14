# Hue · lower_saturation

| | |
|---|---|
| Result | pass |
| Ran | 2 passed, 0 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `4c074d9` |
| Home Assistant | 2026.10.4 |
| Device | Hue Essential lamp (`LCA016`), firmware `1.164.2`; Zone, firmware `unknown` |

## Tests

| Test | Target | Result |
|---|---|---|
| `saturation_to_a_limit[light_color]` | `light` (light_color) | pass |
| `saturation_to_a_limit[group_color]` | `light` (group_color) | pass |
