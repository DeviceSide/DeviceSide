# Hue · raise_brightness-predicted_state

| | |
|---|---|
| Result | pass |
| Date | 2026-11-11 |
| Source | rig run (`scripts/rig.py`), commit `32dc547` |
| Home Assistant | 2026.10.4 |
| Device | Zone, firmware `unknown`; Hue ambiance lamp (`LTA009`), firmware `1.163.1` |
| Options | predicted_state |

## Tests

| Test | Target | Result |
|---|---|---|
| `holds_the_start_then_shows_the_end[light_ct]` | `light` (light_ct) | pass |
| `holds_the_start_then_shows_the_end[group]` | `light` (group) | pass |
| `up_from_off_shows_the_dimmest[light_ct]` | `light` (light_ct) | pass |
| `up_from_off_shows_the_dimmest[group]` | `light` (group) | pass |
| `ha_change_mid_fade_shows_at_once[light_ct]` | `light` (light_ct) | pass |
| `ha_change_mid_fade_shows_at_once[group]` | `light` (group) | pass |
| `bridge_scene_recall_mid_fade_shows_at_once[group]` | `light` (group) | pass (firmware fact) |

A firmware fact proves the device's behavior, not the adapter's code: its pass stands at the firmware listed under Device, and may come from an earlier commit at that firmware.
