# Shelly · set_attributes

| | |
|---|---|
| Result | pass |
| Date | 2026-11-09 |
| Source | rig run (`scripts/rig.py`), commit `63b2d95` |
| Profile | shelly |
| Home Assistant | 2026.10.4 |
| Device | Shelly Multicolor Bulb Gen3 (`S3BL-C010007AEU`), firmware `20261026-122229/2.0.3-g4601943` |

## Tests

| Test | Target | Result |
|---|---|---|
| `sets_while_off[light_ct]` | `light` (light_ct) | pass |
| `sets_while_off[group]` | group: none in the profile | skipped |
| `sets_after_a_soft_off[light_ct]` | `light` (light_ct) | pass |
| `sets_after_a_soft_off[group]` | group: none in the profile | skipped |
| `sets_color_while_off[light_color]` | `light` (light_color) | pass |
| `sets_color_while_off[light_color] observed` | `light` (light_color) | not observed |
| `sets_hs_while_off[light_color]` | `light` (light_color) | pass |
| `sets_hs_while_off[group_color]` | group_color: none in the profile | skipped |
| `sets_xy_while_off[light_color]` | `light` (light_color) | pass |
| `sets_xy_while_off[group_color]` | group_color: none in the profile | skipped |
| `min_brightness_raises[light_ct]` | `light` (light_ct) | pass |
| `min_brightness_leaves_brighter[light_ct]` | `light` (light_ct) | pass |
| `max_brightness_lowers[light_ct]` | `light` (light_ct) | pass |

Tests marked `not observed` had nobody watching.
