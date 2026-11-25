# Hue on Zigbee2MQTT: the `moveToLevel` bottom, a lamp and a group with a member off (2026-11-25)

Rig runs of 2026-11-25, 13:23 to 13:30 local, for step 4 of
[the plan](../../../../plans/2026-11-25-brightness-floor.md) (Decisions 9 and 5): whether the lit lower's raw
`moveToLevel` to level 1 keeps Hue bulbs lit at 0.4 %, and what it does to a group member that is off. DeviceSide
commit `b6108499`, integration tree `ab5c1246f351`, as HA loaded it. Home Assistant 2026.10.4, Zigbee2MQTT 2.14.3.

## Setup

- Devices: the lab's three Hue bulbs, roamed from the Hue bridge to Zigbee2MQTT by the rig, DeviceSide class `hue`:
  a Hue White (LWA012, firmware 1.163.1, role `light_dimmable`), a white ambiance E27 (LTA009, 1.163.1, `light_ct`)
  and a color A60 (LCA016, 1.164.2, `light_color`). The rig's Z2M group holds all three, so it goes raw
  (`RAW_BOTTOM`). `lower_brightness` holds `hue_native_control` off for its call.
- Run 1, the record run: `lower_brightness` and `set_attributes` whole, `--fresh`
  (`../../test-records/lower_brightness.json`, `set_attributes.json`). Its logs weren't kept, so it gives results,
  not wire timings.
- Run 2, a probe: one case from a step file run uncommitted and then deleted, no record, with `--debug-logs` (HA's
  `deviceside` and `mqtt` at DEBUG, which carry every `/set` publish and Z2M's state publishes). Brightness is read
  live (`deviceside.get_attributes`: `currentLevel`, and `onOff`), in percent.

## Run 1: the lamp

`lower_to_the_lowest_level[light_ct]`, the LTA009 lowered from 30 % to a 0.4 % limit: pass. The live level held 0.4 %
(level 1) for a second's sampling after the fade and Z2M's end read-back, and Home Assistant showed the light on.
`sets_the_lowest_level_while_lit[light_ct]` passed too, and every other case of both suites (6/6 and 13/13).

## Run 2: a group lowered to 0.4 %, one member off

| Time | What |
|---|---|
| 13:28:56.761 | HA sets the group `{"state":"ON","brightness":76}` (30 %) |
| 13:28:57.339 | HA turns the LTA009 off, plain `{"state":"OFF"}`; Z2M publishes it OFF, brightness 76, at 13:28:57.383 |
| 13:28:59.413 | DeviceSide's lower: one raw groupcast, `moveToLevel` level 1, `transtime` 15, `optionsMask`/`optionsOverride` 0 |
| 13:29:01.936 | the LTA009's Hue report: OFF, level 76 (`philips_raw` `0700004c…`) |
| 13:29:02.117 | the end read-back: Z2M publishes the LWA012 and the LCA016 ON, brightness 1; the group ON, brightness 1 |
| 13:29:05 to 08 | live reads: the LWA012 and the LCA016 `onOff` 1, `currentLevel` 1, 0.4 % |

The off member stayed off through the case's last check, 3 s after the read-back, and kept its level of 30 %: the
bulb's own report said so. The two lit members held level 1, lit.

## Reading

- The lit lower's `moveToLevel` to level 1 keeps Hue bulbs lit at 0.4 %: the LTA009 alone, and the LWA012 and the
  LCA016 in a group. It supersedes the `moveToLevelWithOnOff` result of
  [the earlier probe](2026-11-25-raw-bottom-probe.md), which left the bulb off.
- A `moveToLevel`, the command without On/Off, left the off member off at its own level: the call the unit test of
  `0655d7af` pins.
- Z2M published no state for the raw command until the end read-back, 2.7 s after it, as the earlier probe found.
