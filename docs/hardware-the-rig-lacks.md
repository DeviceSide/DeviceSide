# Hardware the rig lacks

What v0.1.0 leaves out of scope because the maintainer's rig has nothing to prove it on. Each entry is refused with
the reason shown until a passing test record covers it. Checked against the
adapter scopes on 4 Nov 2026. It is also the "testers needed" list for the release candidate that follows a release
leaving capabilities out.

A **tester** is someone with the hardware and a Home Assistant the rig's tests can run against; the rig is kept
outside this repo, so how a tester runs them is the remote tester flow still to come (TODO.md, 9b). A passing record
clears the entry: widen the adapter's
`AdapterScope` and add the record under `docs/test-records/`. Proof follows the call, so one record covers every
entity domain the same call reaches.

## Documented: ships, a record makes it Verified

These are in scope without a record, as Documented (conditions: [CLAUDE.md](../CLAUDE.md#release-flag)). A passing
record promotes them to Verified.

| Entry | Adapters | A tester needs | Proves |
|---|---|---|---|
| Shelly `Light`, `CCT`, `RGB`, `RGBW` components | `turn_on_for`, `turn_off_for`, the auto-off and auto-on actions, `get_attributes` | A Gen2+ dimmer, CCT, RGB or RGBW device (the rig has relays and one RGBCCT bulb) | Each component's `.Set`, `.SetConfig` and `.GetStatus`. One component per record. RGB and RGBW color stays dropped until core's color conversions are ported |
| Matter lights | `turn_on_for`, `get_attributes` | A Matter light with the On/Off cluster's Lighting feature | `OnWithTimedOff` and the OnTime and OnOff reads on a `light` entity. On/off only: brightness and color fields stay out of scope until tested too |

## A tester can prove these

| Entry | Refused as | Adapters | A tester needs | Proves |
|---|---|---|---|---|
| Zigbee plugs and switches on ZHA and Z2M | `domain_not_tested` | `turn_on_for`, `get_attributes` | A plug whose firmware honors the timed-on command. Not the Tuya TS011F, which stores the timer as a countdown and never switches on; many Sonoff and Tuya plugs run their own countdown instead | The OnTime timer on a `switch`. Zigbee2MQTT and ZHA each need their own record |

## A tester cannot clear these

| Entry | Why |
|---|---|
| Hue Bridge v1 (`bridge_v1`) | The Hue adapters use CLIP v2 only. Unsupported, not untested |
| Shelly Gen1 (`gen1_unsupported`) | No RPC. Unsupported, not untested |
| Hue smart (All-Day) scenes (`smart_scene`) | They have no fixed settings to write. Unsupported, not untested |
| Option `z2m_color_modes` off | Unit-tested only. The rig can't cleanly remove the override the option writes, so no record covers turning it off |
