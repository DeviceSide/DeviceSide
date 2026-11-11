# Hue · get_attributes

| | |
|---|---|
| Result | pass |
| Date | 2026-11-08 |
| Source | rig run (`scripts/rig.py`), commit `8aae106` |
| Home Assistant | 2026.10.4 |
| Device | Hue ambiance lamp (`LTA009`), firmware `1.163.1`; Zone, firmware `unknown`; Hue Essential lamp (`LCA016`), firmware `1.164.2` |

## Tests

| Test | Target | Result |
|---|---|---|
| `reads_while_off[light_ct]` | `light` (light_ct) | pass |
| `reads_while_off[group]` | `light` (group) | pass |
| `predicts_mid_move[light_ct]` | `light` (light_ct) | pass |
| `predicts_mid_move[group]` | `light` (group) | pass |
| `reads_color_while_off[light_color]` | `light` (light_color) | pass |
| `reads_a_running_timer[switch_plug]` | switch_plug: none in the profile | skipped |
| `reads_a_running_timer[light_onoff]` | light_onoff: none in the profile | skipped |
| `reads_a_running_timer[light_wrapped]` | light_wrapped: none in the profile | skipped |
| `reads_a_running_timer[light_dimmable]` | light_dimmable: none in the profile | skipped |
| `reads_no_timer_after_a_turn_off[switch_plug]` | switch_plug: none in the profile | skipped |
