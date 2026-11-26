# Zigbee2MQTT

What DeviceSide's features do on Zigbee2MQTT, their limits, and what DeviceSide changes in your setup. What applies
to every integration is in [integrations.md](../../integrations.md), and what holds for a brand on both Zigbee
integrations in [zigbee.md](../zigbee.md); which devices each feature is proven on is on the
[device compatibility page](../../device-compatibility.md); how the calls work, and what was measured, is in
[internals.md](internals.md).

Lights that Zigbee2MQTT announced to Home Assistant through MQTT discovery.

## Device classes

DeviceSide tells brands apart ([why](../zigbee.md#why-brands-have-classes)) by the manufacturer and model Zigbee2MQTT
registers in Home Assistant and, for IKEA's, Aqara's and Tuya's devices, by the device's own Zigbee manufacturer and
model, which Zigbee2MQTT publishes as it connects ([Right after startup](#right-after-startup)). Groups:
[Groups](#groups).

### Hue

Signify's Hue devices (manufacturer `Philips`).

### Tuya

Tuya's devices, under any brand ([Tuya](../zigbee.md#tuya)). Most run Tuya's own countdown in place of the Zigbee
timer, and Zigbee2MQTT turns the Zigbee timer into a plain on, which would leave the device on
([research](research/2026-11-14-timed-on-call-patterns.md)). So turn on with timer uses Tuya's countdown where a class
below says so.

#### Tuya TS011F plugs

Tuya's TS011F smart plugs, and their white labels, that Zigbee2MQTT drives by Tuya's countdown (it shows a
`countdown` setting for the plug). Turn on with timer uses that countdown. Plugs of one model answer it differently by
maker string (the Zigbee manufacturer Zigbee2MQTT shows for the plug), so each string is placed on its own:

| Plug | Class |
|---|---|
| A maker string a run has passed on | A class of its own |
| Any other maker string | One class for about 200 strings, each a different maker's build; some are reported to ignore the countdown ([research](research/2026-11-15-converter-seed-list.md)). If you try one, please report whether it works: a passing run gives its string a class of its own ([evidence](../../evidence.md#no-known-method-not-built-yet-in-labs)) |
| `_TZ3000_gjnozsaz` | Refused, even with Labs on: its countdown is reported to restart at random ([the Zigbee timer](../zigbee.md#the-zigbee-timer)) |
| No `countdown` setting, or several sockets | Refused: the Zigbee timer left the TS011F on ([internals](../../internals.md#tested-behavior)) |

- **Timer:** whole seconds, up to 12 hours. A duration is rounded to the nearest second, at least 1, and one rounded or
  longer than 12 hours reports `clamped_to`, the value sent. Turning the plug off, its button or a new timer cancels
  it.
- **No time left:** it can't be read, so get attributes refuses the plug, with no known method.
- **Shown as a light:** a TS011F is still a plug to DeviceSide, so the actions for lights alone, such as stop, refuse
  it; turn on with timer takes it, though no run has tried one shown as a light.
- **In a group:** a group with a TS011F plug, shown as a light or a switch, falls back to its devices on smooth dimming,
  smooth color changes and set without turning on, even with Labs on, as those serve lights alone. On turn on with
  timer it falls back too, as the group's timer isn't the plug's: each light gets its own timer, and so does a plug
  shown as a light. A plug shown as a switch is skipped (`not_addressable`), with a warning, as no light reaches it:
  target its switch beside the group (or the group's switch), and it gets its countdown, with no warning.

#### Tuya datapoint devices with one countdown

Tuya datapoint devices whose Zigbee2MQTT definition, the Model on the device's Zigbee2MQTT page, gives one `countdown`
setting, in seconds, for the whole device: dimmers, wall switches, relays, a plug and a valve. Turn on with timer and
turn off with timer send the on or the off with that countdown, and the device toggles back when it ends. They are
admitted by Model, on a reading of each one's definition, not on a test of the device
([research](research/2026-11-14-tuya-datapoint-countdown.md), [the call](research/2026-11-24-tuya-datapoint-call.md)).
A Model not listed here is one of the [other Tuya datapoint devices](#other-tuya-datapoint-devices), even with a
countdown setting, until its definition is read. If you try one, please report whether it works.

| Limit | Models |
|---|---|
| 12 hours | ZDMS16-1, ZOT60 (a TS011F plug on Tuya's protocol), FK_V02, GL-SPI-206P, SFD02-Z, SFD02-Z_2, QADZ1LR, `TS0601_dimmer_1_gang_1`, `TS0601_dimmer_1_gang_2`, `TS0601_dimmer_5`, MG-ZG01W, `_TZE28C1000000_jlbsptkl`, ZMS-206US-1 |
| 24 hours | TO-DM-W/B, `TS0601_multifunction_switch`, D1Z, D5Z |
| 7,210 s (2 h 10 s) | AVATTO ZBS16 |

D1Z and SFD02-Z_2 need a Zigbee2MQTT release after 2.14.3, which doesn't have their definitions yet.

- **Timer:** whole seconds, from 1 s to the device's limit. A duration is rounded to the nearest second, and one
  rounded or over the limit reports `clamped_to`, the value sent. Nothing is read back, so the result is `sent`;
  get attributes isn't built for these devices.
- **GL-SPI-206P:** it gets the on or off twice, so a call can report failed while its timer runs
  ([internals](internals.md#turn_off_for)).
- **Cancelling** is Tuya's general spec, not measured: [Turn off with timer](#turn-off-with-timer).
- **In a group:** a group with one falls back to its devices on turn on with timer, each light getting its own timer.

#### Tuya inching switches

The Tuya WHD02 (maker string `_TZ3000_skueekg3`, Zigbee model `TS0001`) and the Mowe MW781Z (`_TZ300A_rncj86af`,
model `TS0726`) keep a persistent auto-off, "inching", which set auto-off and clear auto-off write
([research](research/tuya/2026-11-24-inching.md)). Both are single-switch devices with a time measured on the device
(5 s and 63 s on the WHD02, 5 s on the MW781Z). They are admitted by maker string, so a string not named here is not.

- **Time:** whole seconds, from 1 s to 65,535 s.
- **Sent, not confirmed:** the setting can't be read back, so the result is `sent`, and get attributes reports no
  auto-off setting for these devices.
- **No auto-on.**
- **Not these:** the WHD02's `TS000F` variant, the Moes ZM4LT3 (`_TZ3000_mzcp0of6`, reported having no effect) and
  every other Tuya switch whose Zigbee2MQTT definition has an inching setting are
  [Tuya plugs and switches](#tuya-plugs-and-switches). The datapoint devices (`TS0601`) time themselves by a
  countdown, a different mechanism ([above](#tuya-datapoint-devices-with-one-countdown)).

#### Tuya plugs and switches

Tuya devices on the standard Zigbee on/off commands: plugs, switches and relays (models `TS0001` to `TS0004`, and
white labels), and lights, such as bulbs and dimmers. The LYAI-14 irrigation valve (model `TS0049`) is one of them:
Zigbee2MQTT shows a countdown setting for it, but its definition's source says the valve ignores the countdown and runs
its own default 10 minutes ([research](research/2026-11-14-tuya-datapoint-countdown.md), §5).

#### Other Tuya datapoint devices

Tuya devices that speak only Tuya's own protocol (model `TS0601`), but for the
[ones with one countdown](#tuya-datapoint-devices-with-one-countdown). Their timer is Tuya's own countdown, which on a
device with several switches needs a command per switch.

### Sengled

Sengled's bulbs ([Sengled](../zigbee.md#sengled)). Zigbee2MQTT sends the Zigbee timer, which they ignore, so with turn
on with timer a bulb would stay off ([probe](research/2026-11-14-lab-probe.md)). DeviceSide refuses them, even with
Labs on.

### Sonoff

Sonoff's relays and dimmers keep a persistent auto-off, "inching", which set auto-off and clear auto-off write
([research](research/sonoff/2026-11-24-inching.md)). The MINI-ZBDIM dimmer also takes smooth dimming and stop
([why](../zigbee.md#smooth-dimming-and-stop)). A two-gang MINI-ZB2GS waits on
[per-endpoint addressing](../../deferred.md#per-endpoint-addressing-on-zigbee2mqtt).

#### Sonoff inching relays

The single-channel models ZBMINIR2 (and its white label MINI-ZBD), ZBMicro, MINI-ZB1GS, MINI-ZB1GSP, BASIC-ZB1GSP,
S61SZBTPB and the MINI-ZBDIM dimmer, admitted by model on Zigbee2MQTT's definition, not on a test of the device.

- **Time:** half seconds, from 0.5 s to 3,599.5 s (just under an hour), on every model, the ones that take longer
  included.
- **Sent, not confirmed:** the setting can't be read back, so the result is `sent`, and get attributes reports no
  auto-off setting for these devices.
- **No auto-on:** DeviceSide sets the relay to turn off after the time, never to turn on again.

#### Sonoff S60 plugs

The S60ZBTPF and S60ZBTPG are refused, even with Labs on: users report Zigbee2MQTT's disable has no effect on them
([Zigbee2MQTT #31799](https://github.com/Koenkk/zigbee2mqtt/issues/31799)), so clear auto-off would leave the plug
pulsing.

### Gledopto

Gledopto's LED controllers and bulbs. Zigbee2MQTT sends some of them a plain on, a pause, then the brightness, rather
than the standard command a Hue bulb gets, and some turn on when their color is set while off
([research](research/2026-11-14-timed-on-call-patterns.md)), so DeviceSide refuses them, even with Labs on. The
GL-SPI-206P, which runs Tuya's own protocol, is one of the
[Tuya datapoint devices with one countdown](#tuya-datapoint-devices-with-one-countdown).

### IKEA

IKEA's TRÅDFRI lights (Zigbee manufacturer `IKEA of Sweden`, which Zigbee2MQTT publishes as it connects; until then an
IKEA light counts as another brand's). They take the Zigbee timer but for two GU10 bulbs, LED2005R5 and LED2106R3,
refused even with Labs on, and a lower to off may stop at the lowest level ([IKEA](../zigbee.md#ikea),
[the Zigbee timer](../zigbee.md#the-zigbee-timer)). Smooth dimming and stop rest on the standard commands
([why](../zigbee.md#smooth-dimming-and-stop)).

### Aqara

Aqara's lights, placed by the Zigbee manufacturer string `Aqara`, which Zigbee2MQTT publishes as it connects (until
then an Aqara light counts as another brand's). Lights that report `LUMI` are [standard lights](#standard-lights)
when their model is on that list, and otherwise [other brands](#other-brands). The class starts from one bulb, the T2
E27 color bulb (Zigbee model `lumi.light.agl003`), which passed smooth dimming, stop, and get and set attributes on the
rig ([records](test-records/)). Smooth dimming and stop rest on the standard commands
([why](../zigbee.md#smooth-dimming-and-stop)). What sets it apart ([probe](research/aqara/2026-11-25-agl003-probe.md)):

- **No hue or saturation:** the bulb reports xy and color temperature only, and the hue and saturation moves leave its
  color unchanged, so raise and lower hue and saturation are refused. An emulation from the host in xy is plausible,
  but nothing builds it yet (sections 1 and 2).
- **No timer:** the bulb ignored a timed on from off and stayed off, so turn on with timer is refused (section 3).
- **Set attributes can time out:** sent at once after a turn off, it timed out in 1 of 10 runs (no reply from
  Zigbee2MQTT, and the values didn't land); sent after Home Assistant showed the bulb off, about 0.1 s later, in 0 of
  10. The cause is unexplained (section 4).

### Standard lights

Other brands' lights whose Zigbee2MQTT device definition sends DeviceSide's commands through the converters
Zigbee2MQTT uses for most lights, with no change for that model: [the list](standard-lights.md), built from a
zigbee-herdsman-converters release (the library that holds Zigbee2MQTT's device support). A light of a brand with a
section of its own here, such as Hue, IKEA or Tuya, stays there. Zigbee2MQTT's own users send the same dimming, stop
and color moves through the same converters, and no Zigbee2MQTT or zigbee-herdsman-converters report names one of
these lights failing them, so that usage is their evidence, in place of a DeviceSide test run
([survey](../../research/2026-11-25-z2m-converter-survey.md)). Get and set attributes, and a lower to the lowest
brightness, are DeviceSide's own commands, not Zigbee2MQTT's: they qualify as every failure reported for them shows as
an error, never as a light quietly doing something else. Smooth hue and saturation changes need a light that exposes
Zigbee2MQTT's `color_hs`; one without is left unchanged (`fields_dropped`), and the list's column says which do.

To check a light, open its device page in Zigbee2MQTT and look for its **Model** in [the list](standard-lights.md). A
light a report shows failing one of these commands is listed apart, with the report, and is one of
[other brands](#other-brands).

### Other brands

Lights of every other brand, such as Innr, and their plugs and switches. Their lights take smooth dimming and stop
([why](../zigbee.md#smooth-dimming-and-stop)), and get and set attributes in Labs: no other brand's light is reported to
come on when written while off, an older bulb that rejects the write fails it with an error, and a light that can't
read one of its color attributes fails the read
([research](research/2026-11-24-other-brands-execute-if-off-and-reads.md)). If you try them, please report it whether it
works or not: Integrations > [DeviceSide](https://my.home-assistant.io/redirect/integration/?domain=deviceside) >
Configure > Report a device test result or bug.

## Groups

Zigbee2MQTT shows a group as one entity per kind of member: a group of lights is a light, a group of switches is a
switch, and a group holding both gets two entities, a light and a switch, each reaching only its own domain's members
on a fallback. So target `switch.<group>` for auto-off, and `light.<group>` for the lights.

A group gets only what all its devices get. A member Home Assistant has no light for (a plug Zigbee2MQTT shows as a
switch, say) counts by its device. Falling back, the group runs its devices each on its own:

| A group | Falls back on |
|---|---|
| With a device the action refuses, or, with Labs off, one in Labs | that action (with Labs on, a Labs device doesn't make it fall back) |
| Any | turn off with timer, set auto-off and clear auto-off, always: a Zigbee group has no call for them ([integrations](../../integrations.md#what-cant-be-done-and-why)); a group of switches, or the group's switch entity, too |

Groups holding a Tuya TS011F plug or datapoint device fall back on more: [TS011F](#tuya-ts011f-plugs),
[datapoint](#tuya-datapoint-devices-with-one-countdown).

## Right after startup

Until Zigbee2MQTT lists a device as fully paired (interviewed) in the devices it publishes, which it does as Home
Assistant connects to MQTT and once it finishes pairing one, DeviceSide knows the device only by what Home Assistant
shows: the vendor `Tuya`, or a model starting `TS`, for a rebadged Tuya device. One shown under another brand (Lidl's,
or Gledopto's GL-SPI-206P) can't be told apart from that brand's own devices ([Tuya](../zigbee.md#tuya)).

- **Every device but Hue's, until the bridge lists it:** turn on with timer, turn off with timer, set auto-off and clear
  auto-off refuse it (`class_unknown`), even with Labs on, as it could be a Tuya device that stays on. Hue's are known
  from the start (turn off with timer refuses them as not built). A group with such a device runs its other lights,
  each on its own. A device whose pairing never completes stays refused until you pair it again in Zigbee2MQTT.
- **A group, until Zigbee2MQTT republishes its groups:** DeviceSide can't tell its members, so the group is in Labs, and
  turn on with timer refuses it (`class_unknown`), as a Tuya plug in it would stay on.
- **If DeviceSide can't subscribe to Zigbee2MQTT's bridge at all,** it logs a warning, groups run only with Labs on,
  and, until the integration reloads, turn on with timer refuses every group and every light, plug or switch but Hue's
  (IKEA's included).

## What DeviceSide changes in Zigbee2MQTT

DeviceSide sets three Zigbee2MQTT options:

- **Fix colors of full-color Zigbee2MQTT lights** (on by default). Home Assistant ignores Zigbee2MQTT's color
  updates for full-color bulbs in hue-saturation (HS) mode: Zigbee2MQTT announces only one of the light's two color
  modes, usually XY, so Home Assistant keeps showing the old color after a hue or saturation change, a Hue gradient
  scene, a remote, or a power cut ([Koenkk/zigbee2mqtt#28757](https://github.com/Koenkk/zigbee2mqtt/issues/28757)).
  DeviceSide sets the Home Assistant override of every full-color light and group to announce both XY and HS, plus
  color temperature where the light has it. The bulb itself is untouched. Lights with one color model, lights on an
  endpoint (`light_l1`), and lights with an override of your own are left alone. Turning the option off in
  DeviceSide's options puts back the modes Zigbee2MQTT announced itself.
- **`hue_native_control`**, on a Hue bulb, or a group with one, for one command at a time, then put back as you had it
  within a second; every other command, DeviceSide's or not, goes out as you set it ([why](internals.md#native_control)).
  With it on, a plain `light.turn_on` is the bulb's own short fade (about 0.4 s), and a `stop` sent during it halts it.
- **`filtered_cache`**, before the first read of a device, so a read's answer isn't resent in every later state
  message. Your own entries are kept. Removing DeviceSide's is harmless: it comes back at the next read.

## Failed sends

When Zigbee2MQTT logs that it couldn't send a command (a busy coordinator refusing a group command, say), raise,
lower, stop, turn on with timer, turn off with timer, set attributes, `set_auto_off` and `clear_auto_off` report that
light or group failed, with the reason Zigbee2MQTT gave (`busy`). These actions answer up to 2 s later than before
while DeviceSide listens for that line; a command Zigbee2MQTT answers with the light's state ends the wait at once.

## Turn on with timer

With light fields, DeviceSide calls `light.turn_on` first, then starts the timer once Zigbee2MQTT reports the
light's new state, usually within a fraction of a second. If that takes over 5 s, the light stays on up to 5 s
longer than asked.

The result is `sent`: Zigbee2MQTT doesn't confirm a timer, or report the light's state after one. DeviceSide reads
the state back after the light turns on and when the timer ends, so Home Assistant stays right. A restart during a
timer loses those reads, and the state can stay stale until the light next reports. A Tuya countdown device
([TS011F](#tuya-ts011f-plugs), [datapoint](#tuya-datapoint-devices-with-one-countdown)) reports its state when the
timer ends, so nothing is read back.

Color bulbs of other brands have no equivalent of Hue native control, so one given a color from off may show its
last color for a moment. With native control on, a Hue bulb may report its old color for the first seconds of a
timer.

**Cancelling.** `turn_off` cancels the timer. A new timer replaces the old one, longer or shorter, as on ZHA:
Zigbee2MQTT sends the same `OnWithTimedOff` (untested on Zigbee2MQTT).

## Turn off with timer

Only the [Tuya datapoint devices with one countdown](#tuya-datapoint-devices-with-one-countdown) take it: DeviceSide
turns the device off with its countdown set, and the device turns itself back on when the countdown ends. No other
Zigbee device has a call for it ([integrations](../../integrations.md#what-cant-be-done-and-why)), so DeviceSide
refuses every other light, plug or switch as not built yet, and runs a group as its devices. The result is `sent`:
nothing is read back.

**Cancelling, by Tuya's general spec, not measured here.** The device toggles when the countdown ends, and a change of
its on/off state (turning it on, its button, the Tuya app, a schedule) or a power loss clears it; a new timer replaces
the old one ([Tuya, General Countdown](https://developer.tuya.com/en/miniapp/solution-ai/ability/lamp-solution/lamp/module-set/common-countdown.md)).
That is Tuya's guide for its Wi-Fi and Bluetooth lamp panels; that these Zigbee devices follow it is an inference, which
Zigbee2MQTT's own description of the setting, "Toggle the device after a set duration", agrees with
([research](research/2026-11-24-tuya-datapoint-call.md), §2). So a light turned off by hand during a timer shouldn't
come back on, though no device has been tried. Turning off a device already off changes nothing on it, so the spec
doesn't say it cancels the timer.

## Lowest brightness

A light's lowest brightness is 0.4 %. Zigbee2MQTT sends 0.8 % in its place to a light whose definition says it turns
off at 0.4 %, which every Hue bulb's does, and to a group only when every member's does. DeviceSide sends the level
directly, with the command Flash-free turn-on uses, to the lights below that hold it lit ([internals](internals.md#fade)):

| Lights | A lower to the lowest brightness |
|---|---|
| Hue and Aqara bulbs, and groups of them alone | 0.4 %, held lit, sent directly; a group's off bulbs stay off |
| Standard lights, and groups of them with Hue and Aqara bulbs alone | 0.8 %, held lit, sent directly, as the Zigbee standard holds a light at its own minimum; until a test shows one holds 0.4 % lit |
| Other lights flagged in their definition: some Innr, ADEO, IKEA, Gledopto and Aqara lights | 0.8 %, Zigbee2MQTT's own (Innr's are reported to turn off at 0.4 %) |
| Other lights not so flagged | Off: Zigbee2MQTT sends the lowest level with its on/off command |
| A group that mixes any of these with other lights | Zigbee2MQTT's: 0.8 % when every member's definition is flagged; otherwise its lit lights switch off and its off members light |

## Smooth color changes

- **Hue moves** cycle the color wheel until `stop`, with a `sweep_time` of 1 to 254 s. Saturation and hue need a
  light that is on and supports hue and saturation, or a group whose lights all do.

## Flash-free turn-on

`set_attributes` reads each light back, so the result is `confirmed`. A light that ignored the write fails the call
(`not_stored`).

## Get attributes

`get_attributes` reads each bulb live, since Hue bulbs on Zigbee2MQTT don't report and its cached state can be stale.
A group returns one entry, averaged over the lights that are on, as Hue averages a room. Other brands' lights are read
in Labs, without a timer ([other brands](#other-brands)); Tuya's datapoint devices' reads aren't built, and Tuya's
countdown plugs are refused ([why](#tuya-ts011f-plugs)).

## Sharp edges

- **A renamed base topic** leaves the old one's bridge entities in Home Assistant, and until you remove them
  DeviceSide can't tell which base is live, so that Zigbee2MQTT's lights are refused (`not_addressable`). Remove the
  old base topic's Zigbee2MQTT Bridge entities ([internals](internals.md#addressing)).
- **A device named with a bare number** that matches a group's ID gets that group's commands.
- **Devices with several lights or switches** (a two-gang switch, a dual-channel Gledopto, a two-gang relay, a Tuya
  datapoint device with a countdown per switch) are refused (`not_addressable`) by every action, each of their lights
  or switches, the first too, as DeviceSide's command would reach only the device's default endpoint; a plug's own
  child lock or LED switch is refused the same way, and the plug beside it works. Named, the call raises; by area,
  label or an HA group, the light is skipped. A Zigbee2MQTT group holding one of its lights still runs as one group,
  but raise, lower, stop and set attributes refuse it, and get attributes reads its other lights
  ([internals](internals.md#addressing)).
- **Large groups.** A call has 30 s for all its targets. Reading a large group on a slow mesh can run out, failing
  every target with `timeout`. Target the lights by area or label instead, which reads four at a time.
