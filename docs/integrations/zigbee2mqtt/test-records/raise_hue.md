# Zigbee2MQTT · raise_hue

| | |
|---|---|
| Result | pass |
| Ran | 2 passed, 1 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `e385562` |
| Home Assistant | 2026.10.4 |
| Device | Hue Essential White and Color Ambiance A60 (`8720169392182`), firmware `1.164.2`; Group, firmware `Zigbee2MQTT 2.14.3` |

## Tests

| Test | Target | Result |
|---|---|---|
| `hue_stop_raise[light_color]` | `light` (light_color) | pass |
| `hue_stop_raise[light_color] observed` | light_color | skipped |
| `hue_stop_raise[group_color]` | `light` (group_color) | pass |

Fact cases run only when asked (--facts), and their results go to [`_facts.md`](_facts.md), never here:

- `hue_stop_raise[light_color] observed`: none on file
