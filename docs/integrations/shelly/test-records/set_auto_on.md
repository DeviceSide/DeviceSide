# Shelly · set_auto_on

| | |
|---|---|
| Result | pass |
| Ran | 1 passed, 1 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `308bd61` |
| Home Assistant | 2026.10.4 |
| Device | Shelly 1 Mini Gen3 (`S3SW-001X8EU`), firmware `20261026-122213/2.0.3-g4601943` |

## Tests

| Test | Target | Result |
|---|---|---|
| `applies_to_any_turn_off[switch_plug]` | `switch` (switch_plug) | pass |
| `takes_the_bounds[switch_plug]` | switch_plug | skipped |

Fact cases run only when asked (--facts), and their results go to [`_facts.md`](_facts.md), never here:

- `takes_the_bounds[switch_plug]`: last on file 2026-11-11, on Shelly 1 Mini Gen3 (`S3SW-001X8EU`), firmware `20261026-122213/2.0.3-g4601943`: pass
