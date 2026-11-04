# Shelly · turn_on_with_auto_off

| | |
|---|---|
| Result | pass |
| Date | 2026-11-04 |
| Source | rig run (`scripts/rig.py`), commit `baf4f56` |
| Profile | shelly |
| Home Assistant | 2026.10.2 |
| Device | Shelly 1 Mini Gen3 (`S3SW-001X8EU`), firmware `20261026-122213/2.0.3-g4601943`; Shelly 1 Mini Gen4 (`S4SW-001X8EU`), firmware `20261026-122156/2.0.3-g4601943`; Shelly Multicolor Bulb Gen3 (`S3BL-C010007AEU`), firmware `20261026-122229/2.0.3-g4601943` |

## Tests

| Test | Target | Result |
|---|---|---|
| `on_then_off[switch_plug]` | `switch` (switch_plug) | pass |
| `on_then_off[light_onoff]` | light_onoff: none in the profile | skipped |
| `on_then_off[light_wrapped]` | `light` (light_wrapped) | pass |
| `drops_brightness_on_a_wrapper[light_wrapped]` | `light` (light_wrapped) | pass |
| `drops_brightness_on_a_relay_light[light_onoff]` | light_onoff: none in the profile | skipped |
| `bulb_on_then_off[light_dimmable]` | `light` (light_dimmable) | pass |
| `bulb_brightness_then_off[light_dimmable]` | `light` (light_dimmable) | pass |
| `bulb_color_temp_then_off[light_ct]` | `light` (light_ct) | pass |
| `bulb_transition_then_off[light_dimmable]` | `light` (light_dimmable) | pass |
| `rgbcct_bulb_rgb_then_off[light_color]` | `light` (light_color) | pass |
| `rgbcct_bulb_hs_then_off[light_color]` | `light` (light_color) | pass |
| `rgbcct_bulb_xy_then_off[light_color]` | `light` (light_color) | pass |
