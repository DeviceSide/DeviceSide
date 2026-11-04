# Hue · lower_saturation

| | |
|---|---|
| Result | pass |
| Date | 2026-11-04 |
| Source | rig run (`scripts/rig.py`), commit `c3c83fe` |
| Profile | lab |
| Home Assistant | 2026.10.2 |
| Device | Hue Essential lamp (`LCA016`), firmware `1.164.2`; Zone, firmware `unknown` |

## Tests

| Test | Target | Result |
|---|---|---|
| `saturation_to_a_limit[light_color]` | `light` (light_color) | pass |
| `saturation_to_a_limit[group_color]` | `light` (group_color) | pass |
