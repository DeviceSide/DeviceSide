# ZHA · turn_on_for

| | |
|---|---|
| Result | pass |
| Date | 2026-11-02 |
| Source | rig run (`scripts/rig.py`), commit `f5db697` |
| Profile | lab |
| Home Assistant | 2026.10.2 |
| Device | Hue white lamp (`LWA012`), firmware `1.104.2`; Hue ambiance lamp (`LTA009`), firmware `1.163.1` |

## Tests

| Test | Target | Result |
|---|---|---|
| `on_then_off[switch_plug]` | switch_plug: none in the profile | skipped |
| `on_then_off[light_onoff]` | light_onoff: none in the profile | skipped |
| `on_then_off[light_wrapped]` | light_wrapped: none in the profile | skipped |
| `drops_brightness_on_a_wrapper[light_wrapped]` | light_wrapped: none in the profile | skipped |
| `bulb_on_then_off[light_dimmable]` | `light` (light_dimmable) | pass |
| `bulb_brightness_then_off[light_dimmable]` | `light` (light_dimmable) | pass |
| `bulb_color_temp_then_off[light_ct]` | `light` (light_ct) | pass |
| `group_on_then_off[group]` | `light` (group) | pass |
| `group_brightness_then_off[group]` | `light` (group) | pass |
