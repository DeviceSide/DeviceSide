# Zigbee2MQTT · facts

What the rig's fact cases found, dated. Rows are only ever added: each is a fact, which stands until evidence contradicts it.

| Date | Suite | Test | Kind | Devices | Result |
|---|---|---|---|---|---|
| 2026-11-13 | `raise_hue` | `hue_stop_raise[light_color] observed` | observed | Hue Essential White and Color Ambiance A60 (`8720169392182`), firmware `1.164.2` | pass |
| 2026-11-13 | `set_attributes` | `sets_color_while_off[light_color] observed` | observed | Hue Essential White and Color Ambiance A60 (`8720169392182`), firmware `1.164.2` | pass |
| 2026-11-13 | `stop` | `halts_a_lower_to_off[light_ct] observed` | observed | Hue white ambiance E27 1100lm with Bluetooth (`9290024684`), firmware `1.163.1` | pass |
| 2026-11-13 | `stop` | `halts_brightness_and_saturation[light_color] observed` | observed | Hue Essential White and Color Ambiance A60 (`8720169392182`), firmware `1.164.2` | fail |
| 2026-11-13 | `raise_hue` | `hue_stop_raise[light_color] observed` | observed | Hue Essential White and Color Ambiance A60 (`8720169392182`), firmware `1.164.2` | pass |
| 2026-11-13 | `stop` | `halts_brightness_and_saturation[light_color] observed` | observed | Hue Essential White and Color Ambiance A60 (`8720169392182`), firmware `1.164.2` | fail |
| 2026-11-13 | `stop` | `halts_a_lower_to_off[light_ct] observed` | observed | Hue white ambiance E27 1100lm with Bluetooth (`9290024684`), firmware `1.163.1` | fail |
| 2026-11-13 | `stop` | `halts_a_lower_to_off[light_ct] observed` | observed | Hue white ambiance E27 1100lm with Bluetooth (`9290024684`), firmware `1.163.1` | pass |
