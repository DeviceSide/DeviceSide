# Hue · lower_brightness-predicted_state

| | |
|---|---|
| Result | pass |
| Date | 2026-11-08 |
| Source | rig run (`scripts/rig.py`), commit `8aae106` |
| Profile | lab |
| Home Assistant | 2026.10.4 |
| Device | Hue ambiance lamp (`LTA009`), firmware `1.163.1`; Zone, firmware `unknown` |
| Options | predicted_state |

## Tests

| Test | Target | Result |
|---|---|---|
| `soft_off_stays_on_until_its_end[light_ct]` | `light` (light_ct) | pass |
| `soft_off_stays_on_until_its_end[group]` | `light` (group) | pass |
