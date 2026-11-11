# Device compatibility

Will DeviceSide work with your device? The [README's cards](../README.md#will-it-work-with-my-device) give the short
answer per integration. This page has the detail: what is known about each device and class of device, where that
comes from, and the evidence behind every claim.

## Levels of proof

Aligned to our core tenet that claims follow evidence, we classify feature claims into four levels of proof:

- **Verified:** proven via automated tests on real hardware.
- **Reported:** reported as working by a user.
- **Documented:** uses the same call pattern as a Verified or Reported device.
- **Experimental:** untested call pattern.

Experimental features stay off until you turn on **Experimental features** in **Configure > Settings**. Whether they
work or not, please tell us with **Report a device test result or bug** in the same menu: a working report makes a
feature Reported, for everyone.

## Support

Who fixes a bug depends on how the feature was proven on your device:

- **Maintainer-supported:** Verified, or Documented on a Verified device. The maintainer fixes it and retests it on the
  rig. Please [report it](https://github.com/jasonmx/DeviceSide/issues/new?template=device_report.yml).
- **Community-supported:** Reported, or Documented on a Reported device. Bugs are welcome, and labelled `community`:
  the maintainer has no such device to test a fix on, so fixes come from users who do, as pull requests the
  maintainer reviews. A feature that keeps breaking with nobody to fix it may be dropped.
- **Experimental:** unsupported until it is proven. A report that it doesn't work is still useful: it is how features
  get fixed or left out.

On the cards, ✔ marks what the automated rig verified, so it is maintainer-supported. A model with a report link and
no ✔ was reported by users and is community-supported.

## Tested devices

A model works on the integrations and features its records cover; the [evidence](#evidence) lists them per action,
with the firmware tested. Other models may work too, but makers implement these features inconsistently: if yours isn't here, please try it and
[report the result](https://github.com/jasonmx/DeviceSide/issues/new?template=device_report.yml), whether it works or
not.

### Hue White Ambiance E27 1100lm

A color temperature bulb, rig-tested on Hue, ZHA and Zigbee2MQTT. It is `LTA009` on Hue and ZHA, and `9290024684` on
Zigbee2MQTT, which maps one to the other
([zigbee-herdsman-converters](https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/devices/philips.ts)).
Smooth dimming is tested on all three, and turn on with timer on ZHA and Zigbee2MQTT (the Hue bridge has no usable
timer: see [integrations](integrations/hue/index.md)).

On a Hue bridge, a room fade can leave one of these bulbs last reported at a mid-fade brightness, with nothing after,
while the bulb reaches the end; and mid-fade, a bulb can report the color temperature it really holds, correcting the
bridge's earlier report (rig runs, 2026-11-11: Hue [Tested behavior](integrations/hue/internals.md#tested-behavior)).

### Hue Essential White and Color Ambiance A60

A color bulb, rig-tested on Hue, ZHA and Zigbee2MQTT: `LCA016` on Hue and ZHA, `8720169392182` on Zigbee2MQTT
([zigbee-herdsman-converters](https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/devices/philips.ts)).
It carries the smooth saturation and hue tests, and Zigbee2MQTT's color mode override
([record](integrations/zigbee2mqtt/records/color_modes.md)). Turning that option off is unit-tested only: the rig can't
cleanly remove the override the option writes.

### Hue White A60 B22

A white (dimmable) bulb, rig-tested with turn on with timer and get attributes on ZHA and Zigbee2MQTT: `LWA012` on
ZHA, `9290018217` on Zigbee2MQTT
([zigbee-herdsman-converters](https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/devices/philips.ts)).

### Native groups

A Hue room or zone, a ZHA group or a Zigbee2MQTT group, commanded as one, as the integration does it. The features a
group takes are in the README's feature table. A ZHA group command gives no delivery feedback, as is the way of a
Zigbee groupcast, and a Hue room write misses lights that are off, so DeviceSide writes a Hue room light by light when
it sets attributes ([integrations](integrations/hue/index.md)).

## Should work

Documented: no device of the class has been tested, but DeviceSide sends it the call a tested device takes, and the
maker documents that call identically for both.

## Help us test

These are built and unit-tested, and wait only for someone with the hardware. Turn on Experimental features to try
them, then report the result, whether they work or not: a working report ships them to everyone.

### Zigbee plugs and switches

Turn on with timer and get attributes on a ZHA or Zigbee2MQTT `switch`. A plug works only if its firmware honors the
Zigbee timed-on command, and few do: Sonoff and Tuya plugs often run their own countdown instead, and the
[Tuya TS011F](#tuya-ts011f) never switches on. ZHA and Zigbee2MQTT each need their own report.

## Doesn't work

### Tuya TS011F

A Zigbee plug that stores the timed-on command's timer as a countdown, which it counts down while off, and never
switches on. Found on the rig ([integrations](integrations.md#zigbee-plugs-and-switches)).

## Evidence

Per integration, every action's level, who supports it, the models its passing records tested, and the reports on
it. A group is a
native group of the integration (a Hue zone, a ZHA or Zigbee2MQTT group).

<!-- evidence:start -->
<!-- Generated by scripts/gen_compat.py from docs/test-records/, the adapters' scopes and docs/devices.yaml. Do not edit; run the script. -->

### ZHA

| Action | Level | Support | Tested models | Records | Reports |
|---|---|---|---|---|---|
| `get_attributes` | Unproven: record older than its code |  | `LTA009`, firmware `0x01002a00`<br>`LCA016`, firmware `0x01001200`<br>`LWA012`, firmware `0x01002502`<br>group | [record](test-records/zha/get_attributes.md) | |
| `get_attributes` | Experimental | experimental (opt-in) | none (untested, behind Experimental features: switch entities) | | |
| `lower_brightness` | Unproven: record older than its code |  | `LTA009`, firmware `0x01002a00`<br>group | [record](test-records/zha/lower_brightness.md) | |
| `lower_hue` | Unproven: record older than its code |  | `LCA016`, firmware `0x01001200` | [record](test-records/zha/lower_hue.md) | |
| `lower_saturation` | Unproven: record older than its code |  | `LCA016`, firmware `0x01001200` | [record](test-records/zha/lower_saturation.md) | |
| `raise_brightness` | Unproven: record older than its code |  | `LTA009`, firmware `0x01002a00`<br>group | [record](test-records/zha/raise_brightness.md) | |
| `raise_hue` | Unproven: record older than its code |  | `LCA016`, firmware `0x01001200` | [record](test-records/zha/raise_hue.md) | |
| `raise_saturation` | Unproven: record older than its code |  | `LCA016`, firmware `0x01001200` | [record](test-records/zha/raise_saturation.md) | |
| `set_attributes` | Experimental (in RCs only) |  | `LCA016`, firmware `0x01001200` | [record](test-records/zha/set_attributes.md) | |
| `stop` | Experimental (in RCs only) |  | `LTA009`, firmware `0x01002a00`<br>`LCA016`, firmware `0x01001200`<br>group | [record](test-records/zha/stop.md) | |
| `turn_on_for` | Unproven: record older than its code |  | `LWA012`, firmware `0x01002502`<br>`LTA009`, firmware `0x01002a00`<br>group | [record](test-records/zha/turn_on_for.md) | |
| `turn_on_for` | Experimental | experimental (opt-in) | none (untested, behind Experimental features: switch entities) | | |

| Doesn't work | Why | Source |
|---|---|---|
| Tuya TS011F | It stores the Zigbee timer as a countdown and never switches on | [source](https://github.com/jasonmx/DeviceSide/blob/main/docs/integrations.md#zigbee-plugs-and-switches) |

### Zigbee2MQTT

| Action | Level | Support | Tested models | Records | Reports |
|---|---|---|---|---|---|
| `get_attributes` | Unproven: record older than its code |  | `9290024684`, firmware `1.163.1`<br>`8720169392182`, firmware `1.164.2`<br>`9290018217`, firmware `1.122.2`<br>group | [record](test-records/zigbee2mqtt/get_attributes.md) | |
| `get_attributes` | Experimental | experimental (opt-in) | none (untested, behind Experimental features: switch entities) | | |
| `lower_brightness` | Unproven: record older than its code |  | `9290024684`, firmware `1.163.1`<br>group | [record](test-records/zigbee2mqtt/lower_brightness.md) | |
| `lower_hue` | Experimental (in RCs only) |  | `8720169392182`, firmware `1.164.2`<br>group | [record](test-records/zigbee2mqtt/lower_hue.md) | |
| `lower_saturation` | Unproven: record older than its code |  | `8720169392182`, firmware `1.164.2`<br>group | [record](test-records/zigbee2mqtt/lower_saturation.md) | |
| `raise_brightness` | Unproven: record older than its code |  | `9290024684`, firmware `1.163.1`<br>group | [record](test-records/zigbee2mqtt/raise_brightness.md) | |
| `raise_hue` | Unproven: record older than its code |  | `8720169392182`, firmware `1.164.2`<br>group | [record](test-records/zigbee2mqtt/raise_hue.md) | |
| `raise_saturation` | Unproven: record older than its code |  | `8720169392182`, firmware `1.164.2`<br>group | [record](test-records/zigbee2mqtt/raise_saturation.md) | |
| `set_attributes` | Experimental (in RCs only) |  | `9290024684`, firmware `1.163.1`<br>`8720169392182`, firmware `1.164.2`<br>group | [record](test-records/zigbee2mqtt/set_attributes.md) | |
| `stop` | Experimental (in RCs only) |  | `9290024684`, firmware `1.163.1`<br>`8720169392182`, firmware `1.164.2`<br>group | [record](test-records/zigbee2mqtt/stop.md) | |
| `turn_on_for` | Unproven: record older than its code |  | `LWA012`, firmware `1.104.2`<br>`LTA009`, firmware `1.163.1`<br>`LCA016`, firmware `1.164.2` | [record](test-records/zigbee2mqtt/turn_on_for.md) | |
| `turn_on_for` | Experimental | experimental (opt-in) | none (untested, behind Experimental features: switch entities) | | |

| Doesn't work | Why | Source |
|---|---|---|
| Tuya TS011F | It stores the Zigbee timer as a countdown and never switches on | [source](https://github.com/jasonmx/DeviceSide/blob/main/docs/integrations.md#zigbee-plugs-and-switches) |

### Shelly

| Action | Level | Support | Tested models | Records | Reports |
|---|---|---|---|---|---|
| `clear_auto_off` | Verified | maintainer | `S3SW-001X8EU`, firmware `20261026-122213/2.0.3-g4601943` | [record](test-records/shelly/clear_auto_off.md) | |
| `clear_auto_off` | Documented | maintainer | none (untested: Light, CCT, RGB, RGBW, RGBCCT components) | | |
| `clear_auto_on` | Verified | maintainer | `S3SW-001X8EU`, firmware `20261026-122213/2.0.3-g4601943` | [record](test-records/shelly/clear_auto_on.md) | |
| `clear_auto_on` | Documented | maintainer | none (untested: Light, CCT, RGB, RGBW, RGBCCT components) | | |
| `get_attributes` | Verified | maintainer | `S3BL-C010007AEU`, firmware `20261026-122229/2.0.3-g4601943`<br>`S3SW-001X8EU`, firmware `20261026-122213/2.0.3-g4601943` | [record](test-records/shelly/get_attributes.md) | |
| `get_attributes` | Documented | maintainer | none (untested: Light, CCT, RGB, RGBW components) | | |
| `lower_brightness` | Verified | maintainer | `S3BL-C010007AEU`, firmware `20261026-122229/2.0.3-g4601943` | [record](test-records/shelly/lower_brightness.md) | |
| `lower_brightness` | Experimental | experimental (opt-in) | none (untested, behind Experimental features: Light, CCT, RGB, RGBW components) | | |
| `raise_brightness` | Verified | maintainer | `S3BL-C010007AEU`, firmware `20261026-122229/2.0.3-g4601943` | [record](test-records/shelly/raise_brightness.md) | |
| `raise_brightness` | Experimental | experimental (opt-in) | none (untested, behind Experimental features: Light, CCT, RGB, RGBW components) | | |
| `set_attributes` | Verified | maintainer | `S3BL-C010007AEU`, firmware `20261026-122229/2.0.3-g4601943` | [record](test-records/shelly/set_attributes.md) | |
| `set_auto_off` | Verified | maintainer | `S3SW-001X8EU`, firmware `20261026-122213/2.0.3-g4601943` | [record](test-records/shelly/set_auto_off.md) | |
| `set_auto_off` | Documented | maintainer | none (untested: Light, CCT, RGB, RGBW, RGBCCT components) | | |
| `set_auto_on` | Verified | maintainer | `S3SW-001X8EU`, firmware `20261026-122213/2.0.3-g4601943` | [record](test-records/shelly/set_auto_on.md) | |
| `set_auto_on` | Documented | maintainer | none (untested: Light, CCT, RGB, RGBW, RGBCCT components) | | |
| `stop` | Verified | maintainer | `S3BL-C010007AEU`, firmware `20261026-122229/2.0.3-g4601943` | [record](test-records/shelly/stop.md) | |
| `stop` | Experimental | experimental (opt-in) | none (untested, behind Experimental features: Light, CCT, RGB, RGBW components) | | |
| `turn_off_for` | Verified | maintainer | `S3SW-001X8EU`, firmware `20261026-122213/2.0.3-g4601943`<br>`S3BL-C010007AEU`, firmware `20261026-122229/2.0.3-g4601943` | [record](test-records/shelly/turn_off_for.md) | |
| `turn_off_for` | Documented | maintainer | none (untested: Light, CCT, RGB, RGBW components) | | |
| `turn_on_for` | Verified | maintainer | `S3SW-001X8EU`, firmware `20261026-122213/2.0.3-g4601943`<br>`S4SW-001X8EU`, firmware `20261026-122156/2.0.3-g4601943`<br>`S3BL-C010007AEU`, firmware `20261026-122229/2.0.3-g4601943` | [record](test-records/shelly/turn_on_for.md) | |
| `turn_on_for` | Documented | maintainer | none (untested: Light, CCT, RGB, RGBW components) | | |

### Hue

| Action | Level | Support | Tested models | Records | Reports |
|---|---|---|---|---|---|
| `get_attributes` | Unproven: record older than its code |  | `LTA009`, firmware `1.163.1`<br>`LCA016`, firmware `1.164.2`<br>group | [record](test-records/hue/get_attributes.md) | |
| `lower_brightness` | Unproven: record older than its code |  | `LTA009`, firmware `1.163.1`<br>group | [predicted state](test-records/hue/lower_brightness-predicted_state.md), [record](test-records/hue/lower_brightness.md) | |
| `lower_saturation` | Unproven: record older than its code |  | `LCA016`, firmware `1.164.2`<br>group | [record](test-records/hue/lower_saturation.md) | |
| `raise_brightness` | Unproven: record older than its code |  | `LTA009`, firmware `1.163.1`<br>group | [predicted state](test-records/hue/raise_brightness-predicted_state.md), [record](test-records/hue/raise_brightness.md) | |
| `raise_saturation` | Unproven: record older than its code |  | `LCA016`, firmware `1.164.2`<br>group | [record](test-records/hue/raise_saturation.md) | |
| `set_attributes` | Experimental (in RCs only) |  | `LTA009`, firmware `1.163.1`<br>`LCA016`, firmware `1.164.2`<br>group | [record](test-records/hue/set_attributes.md) | |
| `set_scene` | Unproven: record older than its code |  | group | [record](test-records/hue/set_scene.md) | |
| `stop` | Experimental (in RCs only) |  | `LTA009`, firmware `1.163.1`<br>`LCA016`, firmware `1.164.2`<br>group | [predicted state](test-records/hue/stop-predicted_state.md), [record](test-records/hue/stop.md) | |

| Doesn't work | Why | Source |
|---|---|---|
| Hue smart scenes | A smart (All-Day) scene changes with the time of day, so it has no fixed settings to write | [source](https://github.com/jasonmx/DeviceSide/blob/main/docs/integrations.md#hue) |

### Matter

| Action | Level | Support | Tested models | Records | Reports |
|---|---|---|---|---|---|
| `get_attributes` | Verified | maintainer | `8979`, firmware `v1.4` | [record](test-records/matter/get_attributes.md) | |
| `get_attributes` | Documented | maintainer | none (untested: light entities) | | |
| `turn_on_for` | Verified | maintainer | `8979`, firmware `v1.4` | [record](test-records/matter/turn_on_for.md) | |
| `turn_on_for` | Documented | maintainer | none (untested: light entities) | | |

<!-- evidence:end -->
