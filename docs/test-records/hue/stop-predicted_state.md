# Hue · stop-predicted_state

| | |
|---|---|
| Result | pass |
| Date | 2026-11-10 |
| Source | rig run (`scripts/rig.py`), commit `c2916f1` |
| Profile | lab |
| Home Assistant | 2026.10.4 |
| Device | Hue ambiance lamp (`LTA009`), firmware `1.163.1`; Zone, firmware `unknown` |
| Options | predicted_state |

## Tests

| Test | Target | Result |
|---|---|---|
| `shows_the_halt[light_ct]` | `light` (light_ct) | pass |
| `shows_the_halt[group]` | `light` (group) | pass |
| `shows_the_halt_of_a_lower_to_off[light_ct]` | `light` (light_ct) | pass |
| `shows_the_halt_of_a_lower_to_off[group]` | `light` (group) | pass |
