# Hue · get_attributes

| | |
|---|---|
| Result | pass |
| Ran | 4 passed, 3 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `4c074d9` |
| Home Assistant | 2026.10.4 |
| Device | Hue ambiance lamp (`LTA009`), firmware `1.163.1`; Zone, firmware `unknown`; Hue Essential lamp (`LCA016`), firmware `1.164.2` |

## Tests

| Test | Target | Result |
|---|---|---|
| `reads_while_off[light_ct]` | `light` (light_ct) | pass |
| `predicts_mid_move[light_ct]` | `light` (light_ct) | pass |
| `predicts_mid_move[group]` | `light` (group) | pass |
| `reads_color_while_off[light_color]` | `light` (light_color) | pass |
| `reads_a_running_timer[switch_plug]` | switch_plug | skipped |
| `reads_a_running_timer[light_dimmable]` | light_dimmable | skipped |
| `reads_no_timer_after_a_turn_off[switch_plug]` | switch_plug | skipped |
