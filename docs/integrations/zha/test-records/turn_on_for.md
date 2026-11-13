# ZHA · turn_on_for

| | |
|---|---|
| Result | pass |
| Ran | 5 passed, 2 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `7b50c5b` |
| Home Assistant | 2026.10.4 |
| Device | LWA012, firmware `0x01002a00`; LTA009, firmware `0x01002a00`; ZBDongle-E, firmware `unknown` |

## Tests

| Test | Target | Result |
|---|---|---|
| `on_then_off[switch_plug]` | switch_plug: none in the profile | skipped |
| `drops_brightness_on_a_wrapper[light_wrapped]` | light_wrapped: none in the profile | skipped |
| `bulb_on_then_off[light_dimmable]` | `light` (light_dimmable) | pass |
| `bulb_brightness_then_off[light_dimmable]` | `light` (light_dimmable) | pass |
| `bulb_color_temp_then_off[light_ct]` | `light` (light_ct) | pass |
| `group_on_then_off[group]` | `light` (group) | pass |
| `group_brightness_then_off[group]` | `light` (group) | pass |
