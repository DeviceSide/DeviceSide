# Hardware the rig lacks

What v0.1.0 leaves out of scope because the maintainer's rig has nothing to prove it on. Each entry is refused with
the reason shown, or (where noted) not refused at all, until a passing test record covers it. Checked against the
adapter scopes on 4 Nov 2026. It is also the "testers needed" list for the release candidate that follows a release
leaving capabilities out.

A **tester** is someone with the hardware and a Home Assistant they can point the rig's step files at
(`tests/rig/steps/`, see [rig.md](rig.md)). A passing record clears the entry: widen the adapter's
`AdapterScope` and add the record under `docs/test-records/`. Proof follows the call, so one record covers every
entity domain the same call reaches.

## A tester can prove these

| Entry | Refused as | Adapters | A tester needs | Proves |
|---|---|---|---|---|
| Shelly `Light`, `CCT`, `RGB`, `RGBW` components | `capability_not_tested` | `turn_on_for`, `turn_off_for`, `get_attributes` | A Gen2+ dimmer, CCT, RGB or RGBW device (the rig has relays and one RGBCCT bulb) | Each component's `.Set` and `.GetStatus`, and the light fields it takes. One component per record |
| Matter lights | `domain_not_tested` | `turn_on_for`, `get_attributes` | A Matter light with the On/Off cluster's Lighting feature | `OnWithTimedOff` and the OnOff read on a `light` entity. On/off only: brightness and color fields stay out of scope until tested too |
| Zigbee plugs and switches on ZHA and Z2M | `domain_not_tested` | `turn_on_for`, `get_attributes` | A plug whose firmware honors the timed-on command. Not the Tuya TS011F, which stores the timer as a countdown and never switches on; many Sonoff and Tuya plugs run their own countdown instead | The OnTime timer on a `switch`. Zigbee2MQTT and ZHA each need their own record |
| Hue `set_scene` beyond the plain scene | none | `set_scene` | A second Hue bridge, a room of many lights, or scenes of other kinds. The rig proves one scene on one bridge | Nothing is refused, so this widens the claim in the test record, not the scope |

## A tester cannot clear these

| Entry | Why |
|---|---|
| Hue Bridge v1 (`bridge_v1`) | The Hue adapters use CLIP v2 only. Unsupported, not untested |
| Shelly Gen1 (`gen1_unsupported`) | No RPC. Unsupported, not untested |
| Hue smart (All-Day) scenes (`smart_scene`) | They have no fixed settings to write. Unsupported, not untested |
| Option `z2m_color_modes` off | Unit-tested only. The rig can't cleanly remove the override the option writes, so no record covers turning it off |
