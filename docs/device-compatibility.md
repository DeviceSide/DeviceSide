# Device compatibility

Will DeviceSide work with your device? The [README's cards](../README.md#will-it-work-with-my-device) give the short
answer per integration. This page has the detail: what is known about each device and class of device, where that
comes from, and the evidence behind every claim.

## Levels of proof

Claims follow evidence, per class of device: devices that get the same command and run the same family of firmware,
such as Hue bulbs on Zigbee2MQTT. A test on one class says nothing about another, because makers' firmware answers the
same command differently. Each claim is at one of two levels of proof:

- **Verified:** a maintainer tested it on a real device, on the automated rig or by hand.
- **Documented:** no device of the class has been tested, but DeviceSide sends it the same call as a Verified device,
  differing only in addressing, and no known class of devices handles it differently.

New features ship as **Experimental** until a maintainer judges them ready for everyone: they stay off until you
turn on **Experimental features** in **Configure > Settings**, and so, for most features, does a device DeviceSide
can't place in a known class. Whether they work or not, please tell us with **Report a device test result or bug** in the same menu: your
reports help ship them to everyone. How we decide: [evidence rules](evidence.md).

## Maintainers

DeviceSide is run by volunteers. Each integration's maintainers look after it: they review changes
to it and fix bugs in it as they can. Please
[report a bug](https://github.com/DeviceSide/DeviceSide/issues/new?template=device_report.yml); the report goes to the
maintainers of the integration you choose. A report that a feature doesn't work is still useful: it goes to the
integration's maintainers, who decide whether to fix it, find it a maintainer, or turn it off; a fix may need someone
with the device.

**⚠️ Unmaintained** marks a feature no one is fixing. It still works as it did, but a bug in it stays unfixed until
someone fixes it or takes over the integration, so use it at your own risk. **🔧 Untested fix** marks a feature
changed in a release before anyone could test it on a device: please report how it works for you.

On the cards, ✔ marks what the automated rig verified; a model without it was verified by a maintainer by hand.

## Tested devices

A model works on the integrations and features its records and maintainers' hand tests (`_manual.json`) cover; the
[evidence](#evidence) lists them per action, with the firmware tested. Other models may work too, but makers implement
these features inconsistently: if yours isn't here, please try it and [report the
result](https://github.com/DeviceSide/DeviceSide/issues/new?template=device_report.yml), whether it works or not.

### Hue White Ambiance E27 1100lm

A color temperature bulb, rig-tested on Hue, ZHA and Zigbee2MQTT. Its Zigbee model ID is `LTA009`, which the records
name it by on every integration; Zigbee2MQTT shows it as `9290024684`, mapping one to the other
([zigbee-herdsman-converters](https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/devices/philips.ts)).
Smooth dimming is tested on all three, and turn on with timer on ZHA and Zigbee2MQTT (the Hue bridge has no usable
timer: see [integrations](integrations/hue/index.md)).

On a Hue bridge, a room fade can leave one of these bulbs last reported at a mid-fade brightness, with nothing after,
while the bulb reaches the end; and mid-fade, a bulb can report the color temperature it really holds, correcting the
bridge's earlier report (rig runs, 2026-11-11: Hue [Tested behavior](integrations/hue/internals.md#tested-behavior)).

### Hue Essential White and Color Ambiance A60

A color bulb, rig-tested on Hue, ZHA and Zigbee2MQTT: Zigbee model ID `LCA016`, which Zigbee2MQTT shows as
`8720169392182`
([zigbee-herdsman-converters](https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/devices/philips.ts)).
It carries the smooth saturation and hue tests, and Zigbee2MQTT's color mode override
([research](integrations/zigbee2mqtt/research/2026-10-28-color-modes.md)). Turning that option off is unit-tested only: the rig can't
cleanly remove the override the option writes.

### Hue White A60 B22

A white (dimmable) bulb, rig-tested with turn on with timer and get attributes on ZHA and Zigbee2MQTT: Zigbee model
ID `LWA012`, which Zigbee2MQTT shows as `9290018217`
([zigbee-herdsman-converters](https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/devices/philips.ts)).

### Native groups

A Hue room or zone, a ZHA group or a Zigbee2MQTT group, commanded as one, as the integration does it. The features a
group takes are in the README's feature table. A ZHA group command gives no delivery feedback, as is the way of a
Zigbee groupcast, and a Hue room write misses lights that are off, so DeviceSide writes a Hue room light by light when
it sets attributes ([integrations](integrations/hue/index.md)).

## Should work

Documented ([levels of proof](#levels-of-proof)).

## Try it: Experimental features

These are built and unit-tested, but not yet ready for everyone ([levels of proof](#levels-of-proof)); some may
have passed a maintainer's first tests. Turn on Experimental features to try them, then report the result, whether
they work or not: a working report helps ship them to everyone, and a "doesn't work" one goes to the integration's
maintainers, who decide whether to fix it, find it a maintainer, or turn it off.

### Zigbee plugs and switches

Turn on with timer on a ZHA `switch`, and get attributes on a ZHA or Zigbee2MQTT one. A plug works only if its firmware
honors the Zigbee timed-on command, and few do: Sonoff and Tuya plugs often run their own countdown instead. On
Zigbee2MQTT, turn on with timer is tested plug by plug: DeviceSide uses Tuya's countdown on the TS011F plugs Zigbee2MQTT
drives by it ([Tuya TS011F plugs](integrations/zigbee2mqtt/index.md#tuya-ts011f-plugs)), and every other plug, a Hue
one included, runs only with Experimental features on. On ZHA, and on Zigbee2MQTT's other Tuya
plugs, DeviceSide refuses it, as they would turn on and stay on, or on long after the time asked; the
[Tuya TS011F](#tuya-ts011f) runs only Tuya's own timer. Get attributes reads none of Tuya's plugs:
a Zigbee2MQTT countdown plug's time left can't be read, and it reads only plugs another feature runs on, which the
rest, and the Sonoff SWV on ZHA, are not. ZHA and Zigbee2MQTT each need their own report.

## Not built yet

A class of device that needs a command DeviceSide hasn't built yet. DeviceSide refuses it, rather than send a command
that would leave it doing something you didn't ask for. If you'd like one built,
[propose it](../CONTRIBUTING.md#how-to-help).

### Tuya TS011F

A Zigbee plug whose timer runs only Tuya's way, so DeviceSide's timer can leave it off, or turn it on long after the
time asked and leave it on. Tuya's own call would serve it. On ZHA it isn't built yet, so DeviceSide refuses turn on
with timer on it, even with Experimental features on. On Zigbee2MQTT DeviceSide sends it to the TS011F plugs
Zigbee2MQTT drives by Tuya's countdown ([Tuya TS011F plugs](integrations/zigbee2mqtt/index.md#tuya-ts011f-plugs)),
and refuses the rest. What was measured: [internals](internals.md#tested-behavior).

## Evidence

Per integration, a row per action and level of proof its entities, classes and fields hold, with the models and
records behind the action (a rig record, or a maintainer's test by hand); ⚠️ Unmaintained and 🔧 Untested fix mark an
action's caveat. A group is a native group of the integration (a Hue zone, a ZHA or Zigbee2MQTT group).

<!-- evidence:start -->
<!-- Generated by scripts/gen_compat.py from the bundles' records and devices.yaml, docs/models.yaml and the adapters' scopes. Do not edit; run the script. -->

### Zigbee2MQTT

| Action | Level | Items | Tested models | Records |
|---|---|---|---|---|
| `get_attributes` | Verified | light entities; hue classes | `LTA009` (`hue`), firmware `1.163.1`<br>`LCA016` (`hue`), firmware `1.164.2`<br>`LWA012` (`hue`), firmware `1.163.1`<br>group | [record](integrations/zigbee2mqtt/test-records/get_attributes.json) |
| `get_attributes` | Experimental | switch entities; other, tuya_zcl on light, sengled, gledopto classes | `TS011F` (`tuya_countdown_tz3000_0zfrhq4i`), firmware `0122052017`<br>`TS011F` (`tuya_countdown_tz3000_typdpbpg`), firmware `Zigbee2MQTT 2.14.3`<br>`TS011F` (`tuya_countdown_tz3000_gznh2xla`), firmware `Zigbee2MQTT 2.14.3`<br>`TS011F` (`tuya_countdown_tz3000_okaz9tjs`), firmware `500+TZSKT31BS102` | |
| `lower_brightness` | Verified | light entities; hue classes; brightness fields | `LTA009` (`hue`), firmware `1.163.1`<br>group | [record](integrations/zigbee2mqtt/test-records/lower_brightness.json) |
| `lower_brightness` | Documented | other classes | | |
| `lower_brightness` | Experimental | tuya_zcl, tuya_mcu, sengled, gledopto classes | | |
| `lower_hue` | Verified | light entities; hue classes; hue fields | `LCA016` (`hue`), firmware `1.164.2`<br>group | [record](integrations/zigbee2mqtt/test-records/lower_hue.json) |
| `lower_hue` | Experimental | other, tuya_zcl, tuya_mcu, sengled, gledopto classes | | |
| `lower_saturation` | Verified | light entities; hue classes; saturation fields | `LCA016` (`hue`), firmware `1.164.2`<br>group | [record](integrations/zigbee2mqtt/test-records/lower_saturation.json) |
| `lower_saturation` | Experimental | other, tuya_zcl, tuya_mcu, sengled, gledopto classes | | |
| `raise_brightness` | Verified | light entities; hue classes; brightness fields | `LTA009` (`hue`), firmware `1.163.1`<br>group | [record](integrations/zigbee2mqtt/test-records/raise_brightness.json) |
| `raise_brightness` | Documented | other classes | | |
| `raise_brightness` | Experimental | tuya_zcl, tuya_mcu, sengled, gledopto classes | | |
| `raise_hue` | Verified | light entities; hue classes; hue fields | `LCA016` (`hue`), firmware `1.164.2`<br>group | [record](integrations/zigbee2mqtt/test-records/raise_hue.json) |
| `raise_hue` | Experimental | other, tuya_zcl, tuya_mcu, sengled, gledopto classes | | |
| `raise_saturation` | Verified | light entities; hue classes; saturation fields | `LCA016` (`hue`), firmware `1.164.2`<br>group | [record](integrations/zigbee2mqtt/test-records/raise_saturation.json) |
| `raise_saturation` | Experimental | other, tuya_zcl, tuya_mcu, sengled, gledopto classes | | |
| `set_attributes` | Verified | light entities; hue classes; brightness, color_temp_kelvin, hs_color, rgb_color, xy_color, min_brightness, max_brightness fields | `LTA009` (`hue`), firmware `1.163.1`<br>`LCA016` (`hue`), firmware `1.164.2`<br>group | [record](integrations/zigbee2mqtt/test-records/set_attributes.json) |
| `set_attributes` | Experimental | other, tuya_zcl, sengled, gledopto classes | | |
| `stop` | Verified | light entities; hue classes | `LTA009` (`hue`), firmware `1.163.1`<br>`LCA016` (`hue`), firmware `1.164.2`<br>group | [record](integrations/zigbee2mqtt/test-records/stop.json) |
| `stop` | Documented | other classes | | |
| `stop` | Experimental | tuya_zcl, tuya_mcu, sengled, gledopto classes | | |
| `turn_on_for` | Verified | light, switch entities; hue on light, tuya_countdown_tz3000_0zfrhq4i on switch, tuya_countdown_tz3000_typdpbpg on switch, tuya_countdown_tz3000_gznh2xla on switch, tuya_countdown_tz3000_okaz9tjs on switch classes; brightness, color_temp_kelvin, hs_color, rgb_color, xy_color, transition fields | `TS011F` (`tuya_countdown_tz3000_0zfrhq4i`), firmware `0122052017`<br>`TS011F` (`tuya_countdown_tz3000_typdpbpg`), firmware `Zigbee2MQTT 2.14.3`<br>`TS011F` (`tuya_countdown_tz3000_gznh2xla`), firmware `Zigbee2MQTT 2.14.3`<br>`TS011F` (`tuya_countdown_tz3000_okaz9tjs`), firmware `500+TZSKT31BS102`<br>`LWA012` (`hue`), firmware `1.163.1`<br>`LTA009` (`hue`), firmware `1.163.1`<br>`LCA016` (`hue`), firmware `1.164.2`<br>group | [record](integrations/zigbee2mqtt/test-records/turn_on_for.json) |
| `turn_on_for` | Experimental | other, tuya_countdown, gledopto classes | | |

| No known method | Why | Source |
|---|---|---|
| Tuya TS011F plugs (`get_attributes`) | Its timer reads back the time it was set to, not the time left, so DeviceSide can't read it | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zigbee2mqtt/research/2026-11-15-tuya-countdown-probe.md) |

| Not built yet, harmed by today's call | Why | Source |
|---|---|---|
| Tuya TS011F plugs (no countdown setting) (`turn_on_for`) | Zigbee2MQTT would turn it on with no timer, so it would stay on | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zigbee2mqtt/research/2026-11-14-lab-probe.md) |
| other Tuya devices (`turn_on_for`) | Zigbee2MQTT would turn it on with no timer, so it would stay on | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md) |
| Tuya datapoint devices (`turn_on_for`) | Zigbee2MQTT would turn it on with no timer, so it would stay on | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md) |
| Tuya TS011F plugs (_TZ3000_gjnozsaz) (`turn_on_for`) | its maker string is reported to restart its timer at random, so it could stay on | [source](https://github.com/Koenkk/zigbee2mqtt/issues/30493) |

### ZHA

| Action | Level | Items | Tested models | Records |
|---|---|---|---|---|
| `get_attributes` | Verified | light entities; hue classes | `LTA009` (`hue`), firmware `0x01002a00`<br>`LCA016` (`hue`), firmware `0x01000d08`<br>`LWA012` (`hue`), firmware `0x01002a00` | [record](integrations/zha/test-records/get_attributes.json) |
| `get_attributes` | Experimental | switch entities; other, tuya_zcl on light, sengled classes | | |
| `lower_brightness` | Verified | light entities; hue classes; brightness fields | `LTA009` (`hue`), firmware `0x01002a00`<br>group | [record](integrations/zha/test-records/lower_brightness.json) |
| `lower_brightness` | Documented | other classes | | |
| `lower_brightness` | Experimental | tuya_zcl, sengled classes | | |
| `lower_hue` | Verified | light entities; hue classes; hue fields | `LCA016` (`hue`), firmware `0x01000d08` | [record](integrations/zha/test-records/lower_hue.json) |
| `lower_hue` | Experimental | other, tuya_zcl, sengled classes | | |
| `lower_saturation` | Verified | light entities; hue classes; saturation fields | `LCA016` (`hue`), firmware `0x01000d08` | [record](integrations/zha/test-records/lower_saturation.json) |
| `lower_saturation` | Experimental | other, tuya_zcl, sengled classes | | |
| `raise_brightness` | Verified | light entities; hue classes; brightness fields | `LTA009` (`hue`), firmware `0x01002a00`<br>group | [record](integrations/zha/test-records/raise_brightness.json) |
| `raise_brightness` | Experimental | other, tuya_zcl, sengled classes | | |
| `raise_hue` | Verified | light entities; hue classes; hue fields | `LCA016` (`hue`), firmware `0x01000d08` | [record](integrations/zha/test-records/raise_hue.json) |
| `raise_hue` | Experimental | other, tuya_zcl, sengled classes | | |
| `raise_saturation` | Verified | light entities; hue classes; saturation fields | `LCA016` (`hue`), firmware `0x01000d08` | [record](integrations/zha/test-records/raise_saturation.json) |
| `raise_saturation` | Experimental | other, tuya_zcl, sengled classes | | |
| `set_attributes` | Verified | light entities; hue classes; brightness, color_temp_kelvin, hs_color, rgb_color, xy_color, min_brightness, max_brightness fields | `LTA009` (`hue`), firmware `0x01002a00`<br>`LCA016` (`hue`), firmware `0x01000d08`<br>group | [record](integrations/zha/test-records/set_attributes.json) |
| `set_attributes` | Experimental | other, tuya_zcl, sengled classes | | |
| `stop` | Verified | light entities; hue classes | `LTA009` (`hue`), firmware `0x01002a00`<br>`LCA016` (`hue`), firmware `0x01000d08`<br>group | [record](integrations/zha/test-records/stop.json) |
| `stop` | Documented | other classes | | |
| `stop` | Experimental | tuya_zcl, sengled classes | | |
| `turn_on_for` | Verified | light entities; hue classes; brightness, color_temp_kelvin fields | `LWA012` (`hue`), firmware `0x01002a00`<br>`LTA009` (`hue`), firmware `0x01002a00`<br>group | [record](integrations/zha/test-records/turn_on_for.json) |
| `turn_on_for` | Experimental | switch entities; other classes | | |

| Not built yet, harmed by today's call | Why | Source |
|---|---|---|
| Tuya TS011F _TZ3000_gjnozsaz (`turn_on_for`) | Tuya's own timer is reported to jump back at random on it, so it may not turn off when asked, and the timer that would serve it isn't built | [source](https://github.com/Koenkk/zigbee2mqtt/issues/30493) |
| Tuya countdown plugs and switches (TS011F, TS0001–TS0004, TS0011, TS0726) (`turn_on_for`) | ZHA's timer can turn it on long after the time asked and leave it on | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zigbee2mqtt/research/2026-11-14-lab-probe.md) |
| other Tuya devices (`turn_on_for`) | ZHA's timer can turn it on or off long after the time asked | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md) |
| Tuya datapoint devices (`turn_on_for`) | ZHA refuses its timer, so with brightness or a color temperature it would turn on and stay on | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zha/internals.md#classes) |
| Sengled bulbs (`turn_on_for`) | It refuses the timer, so with brightness, a color temperature or in a group it would stay on | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zha/internals.md#tested-behavior) |
| Sonoff SWV (`turn_on_for`) | It reads ZHA's timer in seconds, so it would stay open about ten times longer than asked | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zigbee2mqtt/research/2026-11-14-tuya-countdown.md) |

### Shelly

| Action | Level | Items | Tested models | Records |
|---|---|---|---|---|
| `clear_auto_off` | Verified | light, switch entities; Switch, RGBCCT classes | `S3SW-001X8EU` (`Switch`), firmware `20261109-150253/2.2.0-g7968dca` | [record](integrations/shelly/test-records/clear_auto_off.json) |
| `clear_auto_off` | Documented | Light, CCT, RGB, RGBW classes | | |
| `clear_auto_on` | Verified | light, switch entities; Switch, RGBCCT classes | `S3SW-001X8EU` (`Switch`), firmware `20261109-150253/2.2.0-g7968dca` | [record](integrations/shelly/test-records/clear_auto_on.json) |
| `clear_auto_on` | Documented | Light, CCT, RGB, RGBW classes | | |
| `get_attributes` | Verified | light, switch entities; Switch, RGBCCT classes | `S3BL-C010007AEU` (`RGBCCT`), firmware `20261026-122229/2.0.3-g4601943`<br>`S3SW-001X8EU` (`Switch`), firmware `20261109-150253/2.2.0-g7968dca` | [record](integrations/shelly/test-records/get_attributes.json) |
| `get_attributes` | Documented | Light, CCT, RGB, RGBW classes | | |
| `lower_brightness` | Verified | light entities; RGBCCT classes; brightness fields | `S3BL-C010007AEU` (`RGBCCT`), firmware `20261026-122229/2.0.3-g4601943` | [record](integrations/shelly/test-records/lower_brightness.json) |
| `lower_brightness` | Experimental | Light, CCT, RGB, RGBW classes | | |
| `raise_brightness` | Verified | light entities; RGBCCT classes; brightness fields | `S3BL-C010007AEU` (`RGBCCT`), firmware `20261026-122229/2.0.3-g4601943` | [record](integrations/shelly/test-records/raise_brightness.json) |
| `raise_brightness` | Experimental | Light, CCT, RGB, RGBW classes | | |
| `set_attributes` | Verified | light entities; RGBCCT classes; brightness, color_temp_kelvin, hs_color, rgb_color, xy_color, min_brightness, max_brightness fields | `S3BL-C010007AEU` (`RGBCCT`), firmware `20261026-122229/2.0.3-g4601943` | [record](integrations/shelly/test-records/set_attributes.json) |
| `set_attributes` | Experimental | Light, CCT, RGB, RGBW classes | | |
| `set_auto_off` | Verified | light, switch entities; Switch, RGBCCT classes | `S3SW-001X8EU` (`Switch`), firmware `20261109-150253/2.2.0-g7968dca` | [record](integrations/shelly/test-records/set_auto_off.json) |
| `set_auto_off` | Documented | Light, CCT, RGB, RGBW classes | | |
| `set_auto_on` | Verified | light, switch entities; Switch, RGBCCT classes | `S3SW-001X8EU` (`Switch`), firmware `20261109-150253/2.2.0-g7968dca` | [record](integrations/shelly/test-records/set_auto_on.json) |
| `set_auto_on` | Documented | Light, CCT, RGB, RGBW classes | | |
| `stop` | Verified | light entities; RGBCCT classes | `S3BL-C010007AEU` (`RGBCCT`), firmware `20261026-122229/2.0.3-g4601943` | [record](integrations/shelly/test-records/stop.json) |
| `stop` | Experimental | Light, CCT, RGB, RGBW classes | | |
| `turn_off_for` | Verified | light, switch entities; Switch, RGBCCT classes | `S3SW-001X8EU` (`Switch`), firmware `20261109-150253/2.2.0-g7968dca`<br>`S3BL-C010007AEU` (`RGBCCT`), firmware `20261026-122229/2.0.3-g4601943` | [record](integrations/shelly/test-records/turn_off_for.json) |
| `turn_off_for` | Documented | Light, CCT, RGB, RGBW classes | | |
| `turn_on_for` | Verified | light, switch entities; Switch, RGBCCT classes; brightness, color_temp_kelvin, hs_color, rgb_color, transition, xy_color fields | `S3SW-001X8EU` (`Switch`), firmware `20261109-150253/2.2.0-g7968dca`<br>`S4SW-001X8EU` (`Switch`), firmware `20261109-150253/2.2.0-g7968dca`<br>`S3SW-001X8EU` (`Switch`), firmware `20261026-122213/2.0.3-g4601943`<br>`S3BL-C010007AEU` (`RGBCCT`), firmware `20261026-122229/2.0.3-g4601943` | [record](integrations/shelly/test-records/turn_on_for.json) |
| `turn_on_for` | Documented | Light, CCT, RGB, RGBW classes | | |

### Hue

| Action | Level | Items | Tested models | Records |
|---|---|---|---|---|
| `get_attributes` | Verified | light entities; hue classes | `LTA009` (`hue`), firmware `1.163.1`<br>`LCA016` (`hue`), firmware `1.164.2`<br>group | [record](integrations/hue/test-records/get_attributes.json) |
| `get_attributes` | Experimental | other classes | | |
| `lower_brightness` | Verified | light entities; hue classes; brightness fields | `LTA009` (`hue`), firmware `1.163.1`<br>group | [predicted state](integrations/hue/test-records/lower_brightness-predicted_state.json), [record](integrations/hue/test-records/lower_brightness.json) |
| `lower_brightness` | Experimental | other classes | | |
| `lower_saturation` | Verified | light entities; hue classes; saturation fields | `LCA016` (`hue`), firmware `1.164.2`<br>group | [record](integrations/hue/test-records/lower_saturation.json) |
| `lower_saturation` | Experimental | other classes | | |
| `raise_brightness` | Verified | light entities; hue classes; brightness fields | `LTA009` (`hue`), firmware `1.163.1`<br>group | [predicted state](integrations/hue/test-records/raise_brightness-predicted_state.json), [record](integrations/hue/test-records/raise_brightness.json) |
| `raise_brightness` | Experimental | other classes | | |
| `raise_saturation` | Verified | light entities; hue classes; saturation fields | `LCA016` (`hue`), firmware `1.164.2`<br>group | [record](integrations/hue/test-records/raise_saturation.json) |
| `raise_saturation` | Experimental | other classes | | |
| `set_attributes` | Verified | light entities; hue classes; brightness, color_temp_kelvin, hs_color, rgb_color, xy_color, min_brightness, max_brightness fields | `LTA009` (`hue`), firmware `1.163.1`<br>`LCA016` (`hue`), firmware `1.164.2`<br>group | [record](integrations/hue/test-records/set_attributes.json) |
| `set_attributes` | Experimental | other classes | | |
| `set_scene` | Verified | scene entities; hue classes | group | [record](integrations/hue/test-records/set_scene.json) |
| `set_scene` | Experimental | other classes | | |
| `stop` | Verified | light entities; hue classes | `LTA009` (`hue`), firmware `1.163.1`<br>`LCA016` (`hue`), firmware `1.164.2`<br>group | [predicted state](integrations/hue/test-records/stop-predicted_state.json), [record](integrations/hue/test-records/stop.json) |
| `stop` | Experimental | other classes | | |

| No known method | Why | Source |
|---|---|---|
| Hue smart scenes (`set_scene`) | A smart (All-Day) scene changes with the time of day, so it has no fixed settings to write | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/hue/index.md#hue-smart-scenes) |

### Matter

| Action | Level | Items | Tested models | Records |
|---|---|---|---|---|
| `get_attributes` | Verified | switch entities; wiz_plug classes | `8979` (`wiz_plug`), firmware `v1.4` | [record](integrations/matter/test-records/get_attributes.json) |
| `get_attributes` | Documented | light entities; other classes | | |
| `get_attributes` | Experimental | multi_endpoint, bridged, uncertified classes | | |
| `turn_on_for` | Verified | switch entities; wiz_plug classes | `8979` (`wiz_plug`), firmware `v1.4` | [record](integrations/matter/test-records/turn_on_for.json) |
| `turn_on_for` | Documented | light entities | | |
| `turn_on_for` | Experimental | other, multi_endpoint, bridged, uncertified classes | | |

### Control4

| Action | Level | Items | Tested models | Records |
|---|---|---|---|---|
| `get_attributes` | Experimental | light entities; no_stop, other classes | `LTD010` (`other`), by hand<br>group, by hand | [by hand](integrations/control4/test-records/_manual.json) |
| `lower_brightness` | Experimental | light entities; other classes; brightness fields | `LTD010` (`other`), by hand<br>group, by hand | [by hand](integrations/control4/test-records/_manual.json) |
| `raise_brightness` | Experimental | light entities; other classes; brightness fields | `LTD010` (`other`), by hand<br>group, by hand | [by hand](integrations/control4/test-records/_manual.json) |
| `set_attributes` | Experimental | light entities; no_stop, other classes; color_temp_kelvin fields | `LTD010` (`other`), by hand<br>group, by hand | [by hand](integrations/control4/test-records/_manual.json) |
| `stop` | Experimental | light entities; other classes | `LTD010` (`other`), by hand<br>group, by hand | [by hand](integrations/control4/test-records/_manual.json) |

| No known method | Why | Source |
|---|---|---|
| lights whose driver can't stop a ramp (`lower_brightness`, `raise_brightness`) | The light's driver says it can't stop a ramp, so a raise or lower couldn't be halted | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/control4/index.md#lights-whose-driver-cant-stop-a-ramp) |
| lights whose driver can't stop a ramp (`stop`) | The light's driver says it can't stop a ramp, and it ignores the stop | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/control4/index.md#lights-whose-driver-cant-stop-a-ramp) |

<!-- evidence:end -->
