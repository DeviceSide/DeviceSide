# Hue's lowest level on Zigbee2MQTT and ZHA: rig run and probes (2026-11-25)

Rig runs of 2026-11-25, 11:00 to 11:06 local, for step 2 of
[the plan](../../../../plans/2026-11-25-brightness-floor.md) (Decision 5): whether a Hue bulb reaches level 1, 0.4 %,
through DeviceSide on each Zigbee integration. DeviceSide's integration tree `9dbaea7c2ea4`, as HA loaded it. Every value below is from the run's captured logs (HA's at DEBUG for
`deviceside`, `mqtt` and `zha`, which carry Z2M's `bridge/logging` info lines) and its run report.

## Setup

- Device: a Hue white ambiance E27 (LTA009, Z2M model `9290024684`), firmware 1.163.1, roamed from the Hue bridge
  to each network by the rig, DeviceSide class `hue` on both.
- Zigbee2MQTT 2.14.3, zigbee-herdsman-converters 26.125.0, zigbee-herdsman 11.2.0. The bulb's
  `hue_native_control` was on in its profile; `lower_brightness` holds it off for its publish (`native_control`),
  and the set_attributes cases set it as each says. HA's version is not in the captured logs.
- Z2M's `advanced.log_debug_to_mqtt_frontend` is off, so only Z2M's info lines (its invoked raw commands, read
  results and state publishes) reached the log; the ZCL frame the converter sent isn't logged. The level is read
  live: Z2M's generic `read` of `genLevelCtrl` `currentLevel`, and on ZHA zigpy's attribute reads and reports.
- Cases: `lower_to_the_lowest_level` and `sets_the_lowest_level_while_lit` (`tests/rig/steps/`). Probes, from
  step files run uncommitted and then deleted: `set_attributes` with the option off and on, and `turn_on_for`.
  No test record was written.

## Zigbee2MQTT

**`lower_brightness` to a 0.4 % limit, from 30 %.** Fail: level 2.

| Time | What |
|---|---|
| 11:01:13.247 | HA sets the start, `{"state":"ON","brightness":76}` |
| 11:01:13.468 | DeviceSide publishes `{"brightness": 1, "transition": 1.5}`, `hue_native_control` off |
| 11:01:13.620 | Z2M's state publish: `brightness` 2 |
| 11:01:16.005 | Z2M's state publish: `brightness` 2, `philips_raw` `07000102fb00` (was `070001fefb00` at 254) |
| 11:01:19.492, 11:01:20.416 | the rig's two live reads: `currentLevel` 2, DeviceSide's 0.8 % |

**`set_attributes` brightness 0.4 % on the lit bulb, option off** (the case, then the probe). Rejected `not_stored`
both times.

| Time | What |
|---|---|
| 11:01:25.655 | raw `{"command": {"cluster": "genLevelCtrl", "command": "moveToLevel", "payload": {"level": 1, "transtime": 4, "optionsMask": 1, "optionsOverride": 1}}}`; Z2M logs it invoked |
| 11:01:25.658 | the kept-level publish, `{"state": null, "brightness": 1, "transition": 0.4}` |
| 11:01:26.307, 26.859, 27.414 | the read-backs: `currentLevel` 2, 2, 2 |
| 11:01:27.422 | `not_stored` |
| 11:01:31.850, 31.854 | the probe: the same two publishes |
| 11:01:32.506, 33.062, 33.620 | `currentLevel` 2, 2, 2; `not_stored` at 11:01:33.628 |

**`set_attributes` 0.4 %, lit, option on** (probe). Confirmed: the same two publishes at 11:01:37.310 and
11:01:37.313; read-back `currentLevel` 1 at 11:01:37.966, and the rig's reads 1 at 11:01:38.239 and 11:01:39.045.

**`turn_on_for` brightness 0.4 %, from off, 8 s** (probe). Pass: level 1. At 11:01:41.405 DeviceSide sent HA's
`light.turn_on` `{'brightness': 1}` with `hue_native_control` on, which reached Z2M as `{"state":"ON","brightness":1}`,
then `{"state": "ON", "on_time": 8.0}`. Reads during the timer: `currentLevel` 1 at 11:01:43.791 and 11:01:44.586.
Philips' native-control converter clamps a brightness to 1–254
([philips.ts L420](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/lib/philips.ts#L420)) and the bulb took 1; this is one call from off, not every path
with the option on.

## ZHA

**`lower_brightness` to a 0.4 % limit, from 30 %.** Pass: level 1. At 11:04:42.564 zigpy sent
`move_to_level(level=1, transition_time=15)`; reports fell 63, 13, 1 (11:04:42.925 to 44.942), and reads at
11:04:45.343, 48.393 and 49.357 gave 1.

**`set_attributes` 0.4 %, lit.** Pass: level 1. At 11:04:52.582 `move_to_level(level=1, transition_time=4)` with
ExecuteIfOff; reads at 11:04:53.485, 53.868, 54.949 and 55.063 gave 1.

## Reading

Z2M's converter sends a brightness of 1 as level 2 on this Hue bulb with `hue_native_control` off, as
`light_onoff_brightness` reads for a definition with `turnsOffAtBrightness1`
([toZigbee.ts L1378](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L1378)): the fade's publish ended at 2, and in
`set_attributes` the kept-level publish moved the bulb from the raw write's 1 to 2 before the read-back. The bulb
holds level 1 when it is sent raw (ZHA, and Z2M's raw command with the option on).
