# Hue · lower_brightness-predicted_state

| | |
|---|---|
| Result | pass |
| Date | 2026-11-11 |
| Source | rig run (`scripts/rig.py`), commit `32dc547` |
| Home Assistant | 2026.10.4 |
| Device | Hue ambiance lamp (`LTA009`), firmware `1.163.1`; Zone, firmware `unknown` |
| Options | predicted_state |

## Tests

| Test | Target | Result |
|---|---|---|
| `soft_off_stays_on_until_its_end[light_ct]` | `light` (light_ct) | pass |
| `soft_off_stays_on_until_its_end[group]` | `light` (group) | pass |
| `lower_to_a_limit[light_ct]` | `light` (light_ct) | pass |
| `lower_to_a_limit[group]` | `light` (group) | pass |
