# Hue · raise_brightness

| | |
|---|---|
| Result | pass |
| Ran | 6 passed, 2 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `4c074d9` |
| Home Assistant | 2026.10.4 |
| Device | Hue ambiance lamp (`LTA009`), firmware `1.163.1`; Zone, firmware `unknown` |

## Tests

| Test | Target | Result |
|---|---|---|
| `raise[light_ct]` | `light` (light_ct) | pass |
| `raise[group]` | `light` (group) | pass |
| `raise_after_soft_off[light_ct]` | `light` (light_ct) | pass |
| `raise_after_soft_off[group]` | `light` (group) | pass |
| `ha_change_mid_raise[light_ct]` | `light` (light_ct) | pass |
| `ha_change_mid_raise[group]` | `light` (group) | pass |
| `late_stop_report[light_ct]` | light_ct | skipped |
| `late_stop_report[group]` | group | skipped |

Fact cases run only when asked (--facts), and their results go to [`_facts.md`](_facts.md), never here:

- `late_stop_report[light_ct]`: none on file
- `late_stop_report[group]`: none on file
