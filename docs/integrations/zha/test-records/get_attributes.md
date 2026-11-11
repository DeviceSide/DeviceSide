# ZHA · get_attributes

| | |
|---|---|
| Result | pass |
| Date | 2026-11-08 |
| Source | rig run (`scripts/rig.py`), commit `8aae106` |
| Home Assistant | 2026.10.4 |
| Device | LTA009, firmware `0x01002a00`; ZBDongle-E, firmware `unknown`; LCA016, firmware `0x01001200`; LWA012, firmware `0x01002502` |

## Tests

| Test | Target | Result |
|---|---|---|
| `reads_while_off[light_ct]` | `light` (light_ct) | pass |
| `reads_while_off[group]` | `light` (group) | pass |
| `reads_color_while_off[light_color]` | `light` (light_color) | pass |
| `reads_a_running_timer[switch_plug]` | switch_plug: none in the profile | skipped |
| `reads_a_running_timer[light_onoff]` | light_onoff: none in the profile | skipped |
| `reads_a_running_timer[light_wrapped]` | light_wrapped: none in the profile | skipped |
| `reads_a_running_timer[light_dimmable]` | `light` (light_dimmable) | pass |
| `reads_no_timer_after_a_turn_off[switch_plug]` | switch_plug: none in the profile | skipped |
