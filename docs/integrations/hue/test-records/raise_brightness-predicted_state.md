# Hue · raise_brightness-predicted_state

| | |
|---|---|
| Result | pass |
| Ran | 6 passed, 1 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `4c074d9` |
| Home Assistant | 2026.10.4 |
| Device | Hue ambiance lamp (`LTA009`), firmware `1.163.1`; Zone, firmware `unknown` |
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
| `bridge_scene_recall_mid_fade_shows_at_once[group]` | group | skipped |

Fact cases run only when asked (--facts), and their results go to [`_facts.md`](_facts.md), never here:

- `bridge_scene_recall_mid_fade_shows_at_once[group]`: none on file
