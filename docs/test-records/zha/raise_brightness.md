# ZHA · raise_brightness

| | |
|---|---|
| Result | pass |
| Date | 2026-11-08 |
| Source | rig run (`scripts/rig.py`), commit `8aae106` |
| Profile | lab |
| Home Assistant | 2026.10.4 |
| Device | LTA009, firmware `0x01002a00`; ZBDongle-E, firmware `unknown` |

## Tests

| Test | Target | Result |
|---|---|---|
| `raise[light_ct]` | `light` (light_ct) | pass |
| `raise[group]` | `light` (group) | pass |
| `raise_from_off[light_ct]` | `light` (light_ct) | pass |
| `raise_from_off[group]` | `light` (group) | pass |
| `raise_after_soft_off[light_ct]` | `light` (light_ct) | pass |
| `raise_after_soft_off[group]` | `light` (group) | pass |
| `raise_stop_raise[light_ct]` | `light` (light_ct) | pass |
| `raise_stop_raise[group]` | `light` (group) | pass |
