# ZHA · facts

What the rig's fact cases found, dated. Rows are only ever added: each is a fact, which stands until evidence contradicts it.

| Date | Suite | Test | Kind | Devices | Result |
|---|---|---|---|---|---|
| 2026-11-13 | `set_attributes` | `sets_color_while_off[light_color] observed` | observed | LCA016, firmware `0x01001200` | pass |
| 2026-11-13 | `stop` | `halts_brightness_and_saturation[light_color] observed` | observed | LCA016, firmware `0x01001200` | fail |
| 2026-11-13 | `raise_hue` | `hue_stop_raise[light_color] observed` | observed | LCA016, firmware `0x01001200` | pass |
| 2026-11-13 | `stop` | `halts_brightness_and_saturation[light_color] observed` | observed | LCA016, firmware `0x01001200` | fail |
