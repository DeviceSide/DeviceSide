# ZHA · set_attributes

| | |
|---|---|
| Result | pass |
| Ran | 10 passed, 3 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `7b50c5b` |
| Home Assistant | 2026.10.4 |
| Device | LTA009, firmware `0x01002a00`; ZBDongle-E, firmware `unknown`; LCA016, firmware `0x01001200` |

## Tests

| Test | Target | Result |
|---|---|---|
| `sets_while_off[light_ct]` | `light` (light_ct) | pass |
| `sets_while_off[group]` | `light` (group) | pass |
| `sets_after_a_soft_off[light_ct]` | `light` (light_ct) | pass |
| `sets_after_a_soft_off[group]` | `light` (group) | pass |
| `sets_color_while_off[light_color]` | `light` (light_color) | pass |
| `sets_color_while_off[light_color] observed` | light_color | skipped |
| `sets_hs_while_off[light_color]` | `light` (light_color) | pass |
| `sets_hs_while_off[group_color]` | group_color: none in the profile | skipped |
| `sets_xy_while_off[light_color]` | `light` (light_color) | pass |
| `sets_xy_while_off[group_color]` | group_color: none in the profile | skipped |
| `min_brightness_raises[light_ct]` | `light` (light_ct) | pass |
| `min_brightness_leaves_brighter[light_ct]` | `light` (light_ct) | pass |
| `max_brightness_lowers[light_ct]` | `light` (light_ct) | pass |

Fact cases run only when asked (--facts), and their results go to [`_facts.md`](_facts.md), never here:

- `sets_color_while_off[light_color] observed`: none on file
