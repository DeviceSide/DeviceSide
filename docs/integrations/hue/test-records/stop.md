# Hue · stop

| | |
|---|---|
| Result | pass |
| Date | 2026-11-11 |
| Source | rig run (`scripts/rig.py`), commit `32dc547` |
| Home Assistant | 2026.10.4 |
| Device | Hue ambiance lamp (`LTA009`), firmware `1.163.1`; Zone, firmware `unknown`; Hue Essential lamp (`LCA016`), firmware `1.164.2` |

## Tests

| Test | Target | Result |
|---|---|---|
| `halts_a_raise[light_ct]` | `light` (light_ct) | pass |
| `halts_a_raise[group]` | `light` (group) | pass |
| `halts_a_lower_to_off[light_ct]` | `light` (light_ct) | pass |
| `halts_a_lower_to_off[group]` | `light` (group) | pass |
| `stop_when_idle[light_ct]` | `light` (light_ct) | pass |
| `halts_brightness_and_saturation[light_color]` | `light` (light_color) | pass |
| `halts_brightness_and_saturation[light_color] observed` | `light` (light_color) | not observed |
| `halts_brightness_and_saturation[group_color]` | `light` (group_color) | pass |

Tests marked `not observed` had nobody watching.
