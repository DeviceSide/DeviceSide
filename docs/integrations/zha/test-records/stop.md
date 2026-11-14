# ZHA · stop

| | |
|---|---|
| Result | pass |
| Ran | 7 passed, 3 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `7b50c5b` |
| Home Assistant | 2026.10.4 |
| Device | LTA009, firmware `0x01002a00`; ZBDongle-E, firmware `unknown`; LCA016, firmware `0x01001200` |

## Tests

| Test | Target | Result |
|---|---|---|
| `halts_a_raise[light_ct]` | `light` (light_ct) | pass |
| `halts_a_raise[group]` | `light` (group) | pass |
| `halts_a_lower_to_off[light_ct]` | `light` (light_ct) | pass |
| `halts_a_lower_to_off[group]` | `light` (group) | pass |
| `stop_when_idle[light_ct]` | `light` (light_ct) | pass |
| `halts_brightness_and_saturation[light_color]` | `light` (light_color) | pass |
| `halts_brightness_and_saturation[light_color] observed` | light_color | skipped |
| `halts_brightness_and_saturation[group_color]` | group_color: none in the profile | skipped |
| `halts_brightness_and_hue[light_color]` | `light` (light_color) | pass |
| `halts_brightness_and_hue[group_color]` | group_color: none in the profile | skipped |

Fact cases run only when asked (--facts), and their results go to [`_facts.md`](_facts.md), never here:

- `halts_brightness_and_saturation[light_color] observed`: none on file
