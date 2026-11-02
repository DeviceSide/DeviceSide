# Hue · lower_brightness-predicted_state

| | |
|---|---|
| Result | pass |
| Date | 2026-11-02 |
| Source | rig run (`scripts/rig.py`), commit `f5db697` |
| Profile | lab |
| Home Assistant | 2026.10.2 |
| Device | Hue ambiance lamp (`LTA009`), firmware `1.163.1` |

## Tests

| Test | Target | Result |
|---|---|---|
| `soft_off_stays_on_until_its_end[light_ct]` | `light` (light_ct) | pass |
| `soft_off_stays_on_until_its_end[group]` | `light` (group) | pass |
