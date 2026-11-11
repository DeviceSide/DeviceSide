# ZHA · set_attributes

| | |
|---|---|
| Result | pass |
| Date | 2026-11-06 |
| Source | rig run (`scripts/rig.py`), commit `1de5a51` |
| Profile | a60_roam |
| Home Assistant | 2026.10.2 |
| Device | LCA016, firmware `0x01001200` |

## Tests

| Test | Target | Result |
|---|---|---|
| `sets_while_off[light_ct]` | light_ct: none in the profile | skipped |
| `sets_while_off[group]` | group: none in the profile | skipped |
| `sets_after_a_soft_off[light_ct]` | light_ct: none in the profile | skipped |
| `sets_after_a_soft_off[group]` | group: none in the profile | skipped |
| `sets_color_while_off[light_color]` | `light` (light_color) | pass |
| `sets_color_while_off[light_color] observed` | `light` (light_color) | not observed |
| `sets_hs_while_off[light_color]` | `light` (light_color) | pass |
| `sets_hs_while_off[group_color]` | group_color: none in the profile | skipped |
| `sets_xy_while_off[light_color]` | `light` (light_color) | pass |
| `sets_xy_while_off[group_color]` | group_color: none in the profile | skipped |
| `min_brightness_raises[light_ct]` | light_ct: none in the profile | skipped |
| `min_brightness_raises[group]` | group: none in the profile | skipped |
| `min_brightness_leaves_brighter[light_ct]` | light_ct: none in the profile | skipped |
| `min_brightness_leaves_brighter[group]` | group: none in the profile | skipped |
| `max_brightness_lowers[light_ct]` | light_ct: none in the profile | skipped |
| `max_brightness_lowers[group]` | group: none in the profile | skipped |

Tests marked `not observed` had nobody watching.
