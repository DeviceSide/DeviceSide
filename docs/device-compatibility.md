# Device compatibility

Will DeviceSide work with your device? The [README's cards](../README.md#will-it-work-with-my-device) give the short
answer per integration. This page has the detail: what is known about each device and class of device, where that
comes from, and the evidence behind every claim.

## Levels of proof

Claims follow evidence, per class of device: devices that get the same command and run the same family of firmware,
such as Hue bulbs on Zigbee2MQTT. A test on one class says nothing about another, because makers' firmware answers the
same command differently. Each claim is at one of two levels of proof:

- **Verified:** a maintainer tested it on a real device, on the automated rig or by hand.
- **Documented:** no device of the class has been tested, and no known class of devices handles the call differently.
  Either DeviceSide sends it the same call as a Verified device of the same maker's firmware, differing only in
  addressing, or certification tests the same read on every device of the class. A class holding many makers' devices
  is never Documented by another maker's test.

**Labs** is not a promise. What's in Labs may be withdrawn: a class that fails and isn't fixed is taken
off until someone builds it better. Labs features stay off until you turn on **Labs** in
**Configure > Settings**. Labs admits only what its evidence names, so a device DeviceSide can't place in a known
class gets a feature only where its integration's page says so. Whether they work or not, please tell us
with **Report a device test result or bug** in the same menu: your reports help ship them to everyone. How we decide:
[evidence rules](evidence.md#no-known-method-not-built-yet-in-labs).

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
these features inconsistently: if yours isn't here and its class is in Labs, please try it and [report the
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

## Try it: Labs

These classes are in Labs ([levels of proof](#levels-of-proof)): built and unit-tested, and some may have passed a maintainer's first tests. Turn on
Labs to try them, then report the result, whether they work or not: a working report helps ship them
to everyone, and a "doesn't work" one goes to the integration's maintainers, who decide whether to fix it, find it a maintainer, or
turn it off ([in Labs](evidence.md#no-known-method-not-built-yet-in-labs)).

## Not built yet

A class of device that needs a command DeviceSide hasn't built yet. DeviceSide refuses it, rather than send a command
that would leave it doing something you didn't ask for. A class returns when a contributor's pull request builds it
with a passing run on their own device ([how to help](../CONTRIBUTING.md#how-to-help)).

### Zigbee plugs and switches

Turn on with timer runs on a Zigbee plug or switch only where Tuya's countdown serves it: the Zigbee2MQTT Tuya TS011F
plugs with a countdown setting, Verified on the maker strings with a passing run and in Labs on the rest
([Tuya TS011F plugs](integrations/zigbee2mqtt/index.md#tuya-ts011f-plugs)). Research predicts most other plugs fail
the Zigbee timed-on command: plugs needn't implement it, and many run a countdown of their own instead. So on ZHA, and
on every other Zigbee2MQTT plug, a Hue or IKEA one included, it isn't built yet, even with Labs on: it
waits for DeviceSide's own timer or a plug's auto-off. Get attributes reads no Zigbee plug, as it reads only what
another feature runs on, and a Zigbee2MQTT countdown plug's time left can't be read. A contributor with a plug that
passes can add it ([evidence](evidence.md#levels)).

### Tuya TS011F

A Zigbee plug whose timer runs only Tuya's way, so DeviceSide's timer can leave it off, or turn it on long after the
time asked and leave it on. Tuya's own call would serve it. On ZHA it isn't built yet, so DeviceSide refuses turn on
with timer on it, even with Labs on. On Zigbee2MQTT DeviceSide sends it only to the
TS011F plugs Zigbee2MQTT drives by Tuya's countdown, Verified on the maker strings that have passed and in Labs on
the rest ([Tuya TS011F plugs](integrations/zigbee2mqtt/index.md#tuya-ts011f-plugs)), and refuses the others. What was measured: [internals](internals.md#tested-behavior).

## Evidence

Per integration, a row per action and level of proof its entities, classes and fields hold, with the models and
records behind the action (a rig record, or a maintainer's test by hand); ⚠️ Unmaintained and 🔧 Untested fix mark an
action's caveat. A group is a native group of the integration (a Hue zone, a ZHA or Zigbee2MQTT group).

<!-- evidence:start -->
<!-- Generated by scripts/gen_compat.py from the bundles' records and devices.yaml, docs/models.yaml and the adapters' scopes. Do not edit; run the script. -->

## Tested devices

### Hue White Ambiance E27 1100lm

Bulb. Model IDs: `LTA009`, `9290024684`.

| Integration | Features tested | Firmware | How |
|---|---|---|---|
| [Zigbee2MQTT](#zigbee2mqtt) | [turn on with timer](integrations/zigbee2mqtt/test-records/turn_on_for.json)<br>smooth dimming: [up](integrations/zigbee2mqtt/test-records/raise_brightness.json) [down](integrations/zigbee2mqtt/test-records/lower_brightness.json)<br>[set without turning on](integrations/zigbee2mqtt/test-records/set_attributes.json)<br>[get attributes](integrations/zigbee2mqtt/test-records/get_attributes.json)<br>[stop](integrations/zigbee2mqtt/test-records/stop.json) | `1.163.1` | ✔ rig |
| [ZHA](#zha) | [turn on with timer](integrations/zha/test-records/turn_on_for.json)<br>smooth dimming: [up](integrations/zha/test-records/raise_brightness.json) [down](integrations/zha/test-records/lower_brightness.json)<br>[set without turning on](integrations/zha/test-records/set_attributes.json)<br>[get attributes](integrations/zha/test-records/get_attributes.json)<br>[stop](integrations/zha/test-records/stop.json) | `0x01002a00` | ✔ rig |
| [Hue Bridge](#hue-bridge) | smooth dimming: [up predicted state](integrations/hue/test-records/raise_brightness-predicted_state.json) [up](integrations/hue/test-records/raise_brightness.json) [down predicted state](integrations/hue/test-records/lower_brightness-predicted_state.json) [down](integrations/hue/test-records/lower_brightness.json)<br>[set without turning on](integrations/hue/test-records/set_attributes.json)<br>[get attributes](integrations/hue/test-records/get_attributes.json)<br>stop: [predicted state](integrations/hue/test-records/stop-predicted_state.json) [record](integrations/hue/test-records/stop.json) | `1.163.1` | ✔ rig |

### Hue Essential White and Color Ambiance A60

Bulb. Model IDs: `LCA016`, `8720169392182`.

| Integration | Features tested | Firmware | How |
|---|---|---|---|
| [Zigbee2MQTT](#zigbee2mqtt) | [turn on with timer](integrations/zigbee2mqtt/test-records/turn_on_for.json)<br>smooth saturation: [up](integrations/zigbee2mqtt/test-records/raise_saturation.json) [down](integrations/zigbee2mqtt/test-records/lower_saturation.json)<br>smooth hue: [up](integrations/zigbee2mqtt/test-records/raise_hue.json) [down](integrations/zigbee2mqtt/test-records/lower_hue.json)<br>[set without turning on](integrations/zigbee2mqtt/test-records/set_attributes.json)<br>[get attributes](integrations/zigbee2mqtt/test-records/get_attributes.json)<br>[stop](integrations/zigbee2mqtt/test-records/stop.json) | `1.164.2` | ✔ rig |
| [ZHA](#zha) | smooth saturation: [up](integrations/zha/test-records/raise_saturation.json) [down](integrations/zha/test-records/lower_saturation.json)<br>smooth hue: [up](integrations/zha/test-records/raise_hue.json) [down](integrations/zha/test-records/lower_hue.json)<br>[set without turning on](integrations/zha/test-records/set_attributes.json)<br>[get attributes](integrations/zha/test-records/get_attributes.json)<br>[stop](integrations/zha/test-records/stop.json) | `0x01000d08` | ✔ rig |
| [Hue Bridge](#hue-bridge) | smooth saturation: [up](integrations/hue/test-records/raise_saturation.json) [down](integrations/hue/test-records/lower_saturation.json)<br>[set without turning on](integrations/hue/test-records/set_attributes.json)<br>[get attributes](integrations/hue/test-records/get_attributes.json)<br>[stop](integrations/hue/test-records/stop.json) | `1.164.2` | ✔ rig |

### Hue White A60 B22

Bulb. Model IDs: `LWA012`, `9290018217`.

| Integration | Features tested | Firmware | How |
|---|---|---|---|
| [Zigbee2MQTT](#zigbee2mqtt) | [turn on with timer](integrations/zigbee2mqtt/test-records/turn_on_for.json)<br>[get attributes](integrations/zigbee2mqtt/test-records/get_attributes.json) | `1.163.1` | ✔ rig |
| [ZHA](#zha) | [turn on with timer](integrations/zha/test-records/turn_on_for.json)<br>[get attributes](integrations/zha/test-records/get_attributes.json) | `0x01002a00` | ✔ rig |

### Shelly Multicolor Bulb Gen3

Bulb. Model IDs: `S3BL-C010007AEU`.

| Integration | Features tested | Firmware | How |
|---|---|---|---|
| [Shelly](#shelly) | [turn on with timer](integrations/shelly/test-records/turn_on_for.json)<br>[turn off with timer](integrations/shelly/test-records/turn_off_for.json)<br>auto-off/on: [set auto off](integrations/shelly/test-records/set_auto_off.json) [set auto on](integrations/shelly/test-records/set_auto_on.json) [clear auto off](integrations/shelly/test-records/clear_auto_off.json) [clear auto on](integrations/shelly/test-records/clear_auto_on.json)<br>smooth dimming: [up](integrations/shelly/test-records/raise_brightness.json) [down](integrations/shelly/test-records/lower_brightness.json)<br>[set without turning on](integrations/shelly/test-records/set_attributes.json)<br>[get attributes](integrations/shelly/test-records/get_attributes.json)<br>[stop](integrations/shelly/test-records/stop.json) | `20261113-111623/2.2.1-gffa2ea1`<br>`20261026-122229/2.0.3-g4601943` | ✔ rig |

### Hue White Ambiance 5/6" Retrofit Downlight

Bulb. Model IDs: `LTD010`, `5996411U5`.

| Integration | Features tested | Firmware | How |
|---|---|---|---|
| [Control4](#control4) | [smooth dimming](integrations/control4/test-records/_manual.json)<br>[set without turning on](integrations/control4/test-records/_manual.json)<br>[get attributes](integrations/control4/test-records/_manual.json)<br>[stop](integrations/control4/test-records/_manual.json) | | by hand |

### Shelly 1 Mini Gen3

Relay. Model IDs: `S3SW-001X8EU`.

| Integration | Features tested | Firmware | How |
|---|---|---|---|
| [Shelly](#shelly) | [turn on with timer](integrations/shelly/test-records/turn_on_for.json)<br>[turn off with timer](integrations/shelly/test-records/turn_off_for.json)<br>auto-off/on: [set auto off](integrations/shelly/test-records/set_auto_off.json) [set auto on](integrations/shelly/test-records/set_auto_on.json) [clear auto off](integrations/shelly/test-records/clear_auto_off.json) [clear auto on](integrations/shelly/test-records/clear_auto_on.json)<br>[get attributes](integrations/shelly/test-records/get_attributes.json) | `20261109-150253/2.2.0-g7968dca`<br>`20261026-122213/2.0.3-g4601943` | ✔ rig |

### Shelly 1 Mini Gen4

Relay. Model IDs: `S4SW-001X8EU`.

| Integration | Features tested | Firmware | How |
|---|---|---|---|
| [Shelly](#shelly) | [turn on with timer](integrations/shelly/test-records/turn_on_for.json) | `20261109-150253/2.2.0-g7968dca` | ✔ rig |

### Tuya TS011F

Plug. Model IDs: `TS011F`, `TS011F_plug_1`.

| Integration | Features tested | Firmware | How |
|---|---|---|---|
| [Zigbee2MQTT](#zigbee2mqtt) | [turn on with timer](integrations/zigbee2mqtt/test-records/turn_on_for.json)<br>[get attributes](integrations/zigbee2mqtt/test-records/get_attributes.json) | `0122052017`<br>`Zigbee2MQTT 2.14.3`<br>`500+TZSKT31BS102` | ✔ rig |

### WiZ Smart Plug

Plug. Model IDs: `8979`.

| Integration | Features tested | Firmware | How |
|---|---|---|---|
| [Matter](#matter) | [turn on with timer](integrations/matter/test-records/turn_on_for.json)<br>[get attributes](integrations/matter/test-records/get_attributes.json) | `v1.4` | ✔ rig |

### Native groups

| Integration | Features tested | How |
|---|---|---|
| [Zigbee2MQTT](#zigbee2mqtt) | [turn on with timer](integrations/zigbee2mqtt/test-records/turn_on_for.json)<br>smooth dimming: [up](integrations/zigbee2mqtt/test-records/raise_brightness.json) [down](integrations/zigbee2mqtt/test-records/lower_brightness.json)<br>smooth saturation: [up](integrations/zigbee2mqtt/test-records/raise_saturation.json) [down](integrations/zigbee2mqtt/test-records/lower_saturation.json)<br>smooth hue: [up](integrations/zigbee2mqtt/test-records/raise_hue.json) [down](integrations/zigbee2mqtt/test-records/lower_hue.json)<br>[set without turning on](integrations/zigbee2mqtt/test-records/set_attributes.json)<br>[get attributes](integrations/zigbee2mqtt/test-records/get_attributes.json)<br>[stop](integrations/zigbee2mqtt/test-records/stop.json) | ✔ rig |
| [ZHA](#zha) | [turn on with timer](integrations/zha/test-records/turn_on_for.json)<br>smooth dimming: [up](integrations/zha/test-records/raise_brightness.json) [down](integrations/zha/test-records/lower_brightness.json)<br>[set without turning on](integrations/zha/test-records/set_attributes.json)<br>[stop](integrations/zha/test-records/stop.json) | ✔ rig |
| [Hue Bridge](#hue-bridge) | smooth dimming: [up predicted state](integrations/hue/test-records/raise_brightness-predicted_state.json) [up](integrations/hue/test-records/raise_brightness.json) [down predicted state](integrations/hue/test-records/lower_brightness-predicted_state.json) [down](integrations/hue/test-records/lower_brightness.json)<br>smooth saturation: [up](integrations/hue/test-records/raise_saturation.json) [down](integrations/hue/test-records/lower_saturation.json)<br>[set without turning on](integrations/hue/test-records/set_attributes.json)<br>[set scene](integrations/hue/test-records/set_scene.json)<br>[get attributes](integrations/hue/test-records/get_attributes.json)<br>stop: [predicted state](integrations/hue/test-records/stop-predicted_state.json) [record](integrations/hue/test-records/stop.json) | ✔ rig |
| [Control4](#control4) | [smooth dimming](integrations/control4/test-records/_manual.json)<br>[set without turning on](integrations/control4/test-records/_manual.json)<br>[get attributes](integrations/control4/test-records/_manual.json)<br>[stop](integrations/control4/test-records/_manual.json) | by hand |

## By integration

Each mark links its proof: 🟢 its records, 🟡 and ⚪ the class's section on its integration's page, 🔴 its row under [Not supported](#not-supported).

### Zigbee2MQTT

| Class | turn on with timer | smooth dimming | smooth saturation | smooth hue | set without turning on | get attributes | stop |
|---|---|---|---|---|---|---|---|
| [native groups](#native-groups) ✔ | 🟢 [record](integrations/zigbee2mqtt/test-records/turn_on_for.json) | 🟢 [up](integrations/zigbee2mqtt/test-records/raise_brightness.json) [down](integrations/zigbee2mqtt/test-records/lower_brightness.json) | 🟢 [up](integrations/zigbee2mqtt/test-records/raise_saturation.json) [down](integrations/zigbee2mqtt/test-records/lower_saturation.json) | 🟢 [up](integrations/zigbee2mqtt/test-records/raise_hue.json) [down](integrations/zigbee2mqtt/test-records/lower_hue.json) | 🟢 [record](integrations/zigbee2mqtt/test-records/set_attributes.json) | 🟢 [record](integrations/zigbee2mqtt/test-records/get_attributes.json) | 🟢 [record](integrations/zigbee2mqtt/test-records/stop.json) |
| [Hue lights](integrations/zigbee2mqtt/index.md#device-classes) ([Hue White Ambiance E27 1100lm](#hue-white-ambiance-e27-1100lm) ✔, [Hue Essential White and Color Ambiance A60](#hue-essential-white-and-color-ambiance-a60) ✔, [Hue White A60 B22](#hue-white-a60-b22) ✔) | 🟢 [record](integrations/zigbee2mqtt/test-records/turn_on_for.json) | 🟢 [up](integrations/zigbee2mqtt/test-records/raise_brightness.json) [down](integrations/zigbee2mqtt/test-records/lower_brightness.json) | 🟢 [up](integrations/zigbee2mqtt/test-records/raise_saturation.json) [down](integrations/zigbee2mqtt/test-records/lower_saturation.json) | 🟢 [up](integrations/zigbee2mqtt/test-records/raise_hue.json) [down](integrations/zigbee2mqtt/test-records/lower_hue.json) | 🟢 [record](integrations/zigbee2mqtt/test-records/set_attributes.json) | 🟢 [record](integrations/zigbee2mqtt/test-records/get_attributes.json) | 🟢 [record](integrations/zigbee2mqtt/test-records/stop.json) |
| [IKEA LED2005R5 and LED2106R3 (TRÅDFRI GU10 white spectrum)](integrations/zigbee2mqtt/index.md#ikea) | | ⚪ [why](integrations/zigbee2mqtt/index.md#ikea) | | | | | ⚪ [why](integrations/zigbee2mqtt/index.md#ikea) |
| [IKEA lights](integrations/zigbee2mqtt/index.md#ikea) | ⚪ [why](integrations/zigbee2mqtt/index.md#ikea) | ⚪ [why](integrations/zigbee2mqtt/index.md#ikea) | | | | | ⚪ [why](integrations/zigbee2mqtt/index.md#ikea) |
| [Tuya TS011F plugs](integrations/zigbee2mqtt/index.md#tuya-ts011f-plugs): check Manufacturer and the countdown setting on the plug's Zigbee2MQTT page | | | | | | | |
| &emsp;[_TZ3000_0zfrhq4i, _TZ3000_gznh2xla, _TZ3000_okaz9tjs, or _TZ3000_typdpbpg](integrations/zigbee2mqtt/index.md#tuya-ts011f-plugs) ✔ | 🟢 [record](integrations/zigbee2mqtt/test-records/turn_on_for.json) | | | | | 🔴 [why](#tuya-ts011f-plugs) | |
| &emsp;[other makers with a countdown setting](integrations/zigbee2mqtt/index.md#tuya-ts011f-plugs) | ⚪ [why](integrations/zigbee2mqtt/index.md#tuya-ts011f-plugs) | | | | | 🔴 [why](#tuya-ts011f-plugs) | |
| [other brands' lights](integrations/zigbee2mqtt/index.md#other-brands) | | ⚪ [why](integrations/zigbee2mqtt/index.md#other-brands) | | | | | ⚪ [why](integrations/zigbee2mqtt/index.md#other-brands) |

### ZHA

| Class | turn on with timer | smooth dimming | smooth saturation | smooth hue | set without turning on | get attributes | stop |
|---|---|---|---|---|---|---|---|
| [native groups](#native-groups) ✔ | 🟢 [record](integrations/zha/test-records/turn_on_for.json) | 🟢 [up](integrations/zha/test-records/raise_brightness.json) [down](integrations/zha/test-records/lower_brightness.json) | | | 🟢 [record](integrations/zha/test-records/set_attributes.json) | | 🟢 [record](integrations/zha/test-records/stop.json) |
| [Hue lights](integrations/zha/index.md#device-classes) ([Hue White Ambiance E27 1100lm](#hue-white-ambiance-e27-1100lm) ✔, [Hue Essential White and Color Ambiance A60](#hue-essential-white-and-color-ambiance-a60) ✔, [Hue White A60 B22](#hue-white-a60-b22) ✔) | 🟢 [record](integrations/zha/test-records/turn_on_for.json) | 🟢 [up](integrations/zha/test-records/raise_brightness.json) [down](integrations/zha/test-records/lower_brightness.json) | 🟢 [up](integrations/zha/test-records/raise_saturation.json) [down](integrations/zha/test-records/lower_saturation.json) | 🟢 [up](integrations/zha/test-records/raise_hue.json) [down](integrations/zha/test-records/lower_hue.json) | 🟢 [record](integrations/zha/test-records/set_attributes.json) | 🟢 [record](integrations/zha/test-records/get_attributes.json) | 🟢 [record](integrations/zha/test-records/stop.json) |
| [IKEA LED2005R5 and LED2106R3 (TRÅDFRI GU10 white spectrum)](integrations/zha/index.md#ikea) | | ⚪ [why](integrations/zha/index.md#ikea) | | | | | ⚪ [why](integrations/zha/index.md#ikea) |
| [IKEA lights](integrations/zha/index.md#ikea) | ⚪ [why](integrations/zha/index.md#ikea) | ⚪ [why](integrations/zha/index.md#ikea) | | | | | ⚪ [why](integrations/zha/index.md#ikea) |
| [other brands' lights](integrations/zha/index.md#other-brands) | | ⚪ [why](integrations/zha/index.md#other-brands) | | | | | ⚪ [why](integrations/zha/index.md#other-brands) |

### Shelly

| Class | turn on with timer | turn off with timer | auto-off/on | smooth dimming | set without turning on | get attributes | stop |
|---|---|---|---|---|---|---|---|
| [multicolor bulbs](integrations/shelly/index.md#tested-devices) ([Multicolor Bulb Gen3](#shelly-multicolor-bulb-gen3) ✔) | 🟢 [record](integrations/shelly/test-records/turn_on_for.json) | 🟢 [record](integrations/shelly/test-records/turn_off_for.json) | 🟢 [set auto off](integrations/shelly/test-records/set_auto_off.json) [set auto on](integrations/shelly/test-records/set_auto_on.json) [clear auto off](integrations/shelly/test-records/clear_auto_off.json) [clear auto on](integrations/shelly/test-records/clear_auto_on.json) | 🟢 [up](integrations/shelly/test-records/raise_brightness.json) [down](integrations/shelly/test-records/lower_brightness.json) | 🟢 [record](integrations/shelly/test-records/set_attributes.json) | 🟢 [record](integrations/shelly/test-records/get_attributes.json) | 🟢 [record](integrations/shelly/test-records/stop.json) |
| [relays and plugs](integrations/shelly/index.md#tested-devices) ([1 Mini Gen3](#shelly-1-mini-gen3) ✔, [1 Mini Gen4](#shelly-1-mini-gen4) ✔) | 🟢 [record](integrations/shelly/test-records/turn_on_for.json) | 🟢 [record](integrations/shelly/test-records/turn_off_for.json) | 🟢 [set auto off](integrations/shelly/test-records/set_auto_off.json) [set auto on](integrations/shelly/test-records/set_auto_on.json) [clear auto off](integrations/shelly/test-records/clear_auto_off.json) [clear auto on](integrations/shelly/test-records/clear_auto_on.json) | | | 🟢 [record](integrations/shelly/test-records/get_attributes.json) | |
| [dimmers](integrations/shelly/index.md#shelly-dimmers), [LED controllers (CCT, RGB, RGBW)](integrations/shelly/index.md#shelly-led-controllers) | 🟡 [why](integrations/shelly/index.md#shelly-dimmers) | 🟡 [why](integrations/shelly/index.md#shelly-dimmers) | 🟡 [why](integrations/shelly/index.md#shelly-dimmers) | ⚪ [why](integrations/shelly/index.md#shelly-dimmers) | 🟡 [why](integrations/shelly/index.md#shelly-dimmers) | 🟡 [why](integrations/shelly/index.md#shelly-dimmers) | ⚪ [why](integrations/shelly/index.md#shelly-dimmers) |

### Hue Bridge

| Class | smooth dimming | smooth saturation | set without turning on | set scene | get attributes | stop |
|---|---|---|---|---|---|---|
| [native groups](#native-groups) ✔ | 🟢 [up predicted state](integrations/hue/test-records/raise_brightness-predicted_state.json) [up](integrations/hue/test-records/raise_brightness.json) [down predicted state](integrations/hue/test-records/lower_brightness-predicted_state.json) [down](integrations/hue/test-records/lower_brightness.json) | 🟢 [up](integrations/hue/test-records/raise_saturation.json) [down](integrations/hue/test-records/lower_saturation.json) | 🟢 [record](integrations/hue/test-records/set_attributes.json) | 🟢 [record](integrations/hue/test-records/set_scene.json) | 🟢 [record](integrations/hue/test-records/get_attributes.json) | 🟢 [predicted state](integrations/hue/test-records/stop-predicted_state.json) [record](integrations/hue/test-records/stop.json) |
| [Hue lights](integrations/hue/index.md#device-classes) ([Hue White Ambiance E27 1100lm](#hue-white-ambiance-e27-1100lm) ✔, [Hue Essential White and Color Ambiance A60](#hue-essential-white-and-color-ambiance-a60) ✔) | 🟢 [up predicted state](integrations/hue/test-records/raise_brightness-predicted_state.json) [up](integrations/hue/test-records/raise_brightness.json) [down predicted state](integrations/hue/test-records/lower_brightness-predicted_state.json) [down](integrations/hue/test-records/lower_brightness.json) | 🟢 [up](integrations/hue/test-records/raise_saturation.json) [down](integrations/hue/test-records/lower_saturation.json) | 🟢 [record](integrations/hue/test-records/set_attributes.json) | 🟢 [record](integrations/hue/test-records/set_scene.json) | 🟢 [record](integrations/hue/test-records/get_attributes.json) | 🟢 [predicted state](integrations/hue/test-records/stop-predicted_state.json) [record](integrations/hue/test-records/stop.json) |
| [Hue smart scenes](integrations/hue/index.md#hue-smart-scenes) | | | | 🔴 [why](#hue-smart-scenes) | | |

### Matter

| Class | turn on with timer | get attributes |
|---|---|---|
| [WiZ Smart Plug](integrations/matter/index.md#wiz-smart-plug) ✔ | 🟢 [record](integrations/matter/test-records/turn_on_for.json) | 🟢 [record](integrations/matter/test-records/get_attributes.json) |
| [certified Matter devices](integrations/matter/index.md#certified-devices) | ⚪ [why](integrations/matter/index.md#certified-devices) | 🟡 [why](integrations/matter/index.md#certified-devices) |

### Control4

| Class | smooth dimming | set without turning on | get attributes | stop |
|---|---|---|---|---|
| [lights](integrations/control4/index.md#control4-lights) | ⚪ [why](integrations/control4/index.md#control4-lights) | ⚪ [why](integrations/control4/index.md#control4-lights) | ⚪ [why](integrations/control4/index.md#control4-lights) | ⚪ [why](integrations/control4/index.md#control4-lights) |
| [lights whose driver can't stop a ramp](integrations/control4/index.md#lights-whose-driver-cant-stop-a-ramp) | 🔴 [why](#lights-whose-driver-cant-stop-a-ramp) | ⚪ [why](integrations/control4/index.md#lights-whose-driver-cant-stop-a-ramp) | ⚪ [why](integrations/control4/index.md#lights-whose-driver-cant-stop-a-ramp) | 🔴 [why](#lights-whose-driver-cant-stop-a-ramp-1) |

## Not supported

| Devices | Integrations | Features | Why | Source |
|---|---|---|---|---|
| devices behind a Matter bridge | Matter | turn on with timer | A bridge's software answers the timer for its devices, which nothing found says it runs, so it could stay on, and DeviceSide's own off isn't built | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/matter/internals.md#what-decides-the-call) |
| Hue smart plugs | Zigbee2MQTT, ZHA | turn on with timer | Most plugs and switches ignore the timer or read it as a delayed toggle, so it could stay on, and the calls that would serve them, DeviceSide's own off or the plug's auto-off, aren't built | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md) |
| <a id="hue-smart-scenes"></a>Hue smart scenes | Hue Bridge | set scene | A smart (All-Day) scene changes with the time of day, so it has no fixed settings to write | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/hue/index.md#hue-smart-scenes) |
| IKEA LED2005R5 and LED2106R3 (TRÅDFRI GU10 white spectrum) | Zigbee2MQTT, ZHA | turn on with timer | It is reported to turn on with the timer and never turn off, and DeviceSide's own off, which would serve it, isn't built | [source](https://github.com/Koenkk/zigbee2mqtt/issues/29158) |
| IKEA outlets | Zigbee2MQTT, ZHA | turn on with timer | Most plugs and switches ignore the timer or read it as a delayed toggle, so it could stay on, and the calls that would serve them, DeviceSide's own off or the plug's auto-off, aren't built | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md) |
| <a id="lights-whose-driver-cant-stop-a-ramp"></a>lights whose driver can't stop a ramp | Control4 | smooth dimming | The light's driver says it can't stop a ramp, so a raise or lower couldn't be halted | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/control4/index.md#lights-whose-driver-cant-stop-a-ramp) |
| <a id="lights-whose-driver-cant-stop-a-ramp-1"></a>lights whose driver can't stop a ramp | Control4 | stop | The light's driver says it can't stop a ramp, and it ignores the stop | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/control4/index.md#lights-whose-driver-cant-stop-a-ramp) |
| multi-outlet Matter devices | Matter | turn on with timer | Certification tests the timer on one endpoint, and nothing found says it tests the others, so one could stay on, and DeviceSide's own off isn't built | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/matter/internals.md#what-decides-the-call) |
| other brands | Zigbee2MQTT, ZHA | turn on with timer | Too few reports say its brand runs the timer, and some lights and most plugs turn on and never off, so it could stay on; DeviceSide's own off, which would serve it, isn't built | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md) |
| other Tuya devices | Zigbee2MQTT | turn on with timer | Zigbee2MQTT would turn it on with no timer, so it would stay on | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md) |
| other Tuya devices | ZHA | turn on with timer | ZHA's timer can turn it on or off long after the time asked | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md) |
| Sengled bulbs | ZHA | turn on with timer | It refuses the timer, so with brightness, a color temperature or in a group it would stay on | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zha/internals.md#tested-behavior) |
| Sonoff SWV | ZHA | turn on with timer | It reads ZHA's timer in seconds, so it would stay open about ten times longer than asked | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zigbee2mqtt/research/2026-11-14-tuya-countdown.md) |
| Tuya countdown plugs and switches (TS011F, TS0001–TS0004, TS0011, TS0726) | ZHA | turn on with timer | ZHA's timer can turn it on long after the time asked and leave it on | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zigbee2mqtt/research/2026-11-14-lab-probe.md) |
| Tuya datapoint devices | Zigbee2MQTT | turn on with timer | Zigbee2MQTT would turn it on with no timer, so it would stay on | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md) |
| Tuya datapoint devices | ZHA | turn on with timer | ZHA refuses its timer, so with brightness or a color temperature it would turn on and stay on | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zha/internals.md#classes) |
| <a id="tuya-ts011f-plugs"></a>Tuya TS011F plugs | Zigbee2MQTT | get attributes | Its timer reads back the time it was set to, not the time left, so DeviceSide can't read it | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zigbee2mqtt/research/2026-11-15-tuya-countdown-probe.md) |
| Tuya TS011F plugs (_TZ3000_gjnozsaz) | Zigbee2MQTT, ZHA | turn on with timer | Tuya's own timer is reported to restart at random on its maker string, so it may not turn off when asked, and the timer that would serve it isn't built | [source](https://github.com/Koenkk/zigbee2mqtt/issues/30493) |
| Tuya TS011F plugs (no countdown setting) | Zigbee2MQTT | turn on with timer | Zigbee2MQTT would turn it on with no timer, so it would stay on | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zigbee2mqtt/research/2026-11-14-lab-probe.md) |
| uncertified Matter devices | Matter | turn on with timer | Nothing has tested its timer, so it could stay on, and DeviceSide's own off isn't built | [source](https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/matter/internals.md#what-decides-the-call) |

<!-- evidence:end -->
