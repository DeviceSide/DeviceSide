# Zigbee2MQTT

What DeviceSide's features do on Zigbee2MQTT, their limits, and what DeviceSide changes in your setup. What applies
to every integration is in [integrations.md](../../integrations.md); which devices each feature is proven on is
on the [device compatibility page](../../device-compatibility.md); how the calls work, and what was measured, is
in [internals.md](internals.md).

Lights that Zigbee2MQTT announced to Home Assistant through MQTT discovery.

## Device classes

Zigbee devices given the same command can answer it differently, by brand and firmware
([research](research/2026-11-14-timed-on-call-patterns.md)), so a test on one brand proves nothing about another.
DeviceSide tells them apart by the manufacturer and model Zigbee2MQTT registers in Home Assistant and, for IKEA's
devices and Tuya devices sold under other brands, by the device's own Zigbee manufacturer and model, which Zigbee2MQTT
publishes as it connects.

- A **group** gets only what all its devices get. Zigbee2MQTT shows a group as one entity per kind of member: a group of
  lights is a light, a group of switches is a switch, and a group holding both gets two entities, a light and a switch,
  each reaching only its own domain's members on a fallback. So target `switch.<group>` for auto-off, and `light.<group>`
  for the lights. One with a light a feature refuses, or, with Labs
  off, one in Labs, falls back to its lights, each on its own; with Labs on, it runs as one group. A member
  Home Assistant has no light for (a plug Zigbee2MQTT shows as a switch, say) counts by its device, so a Tuya plug in a
  group makes it fall back too. A TS011F plug makes it fall back on smooth dimming, smooth color changes and set without
  turning on even with Labs on, as those serve lights alone, and a TS011F is a plug even where
  Zigbee2MQTT shows it as a light. So does a TS011F plug on Tuya's countdown for turn on with timer, as the group's
  timer isn't the plug's: each light gets its own, and so does a plug Zigbee2MQTT shows as a light. One it shows as a
  switch is skipped (`not_addressable`), with a warning, as no light reaches it: target its switch beside the group (or the group's switch), and
  it gets its countdown, with no warning. Set auto-off and clear auto-off work the same way: a group of switches, or the
  group's switch entity, falls back to its members. A Tuya datapoint device with one countdown makes a group fall back on turn on
  with timer the same way, and turn off with timer, set auto-off and clear auto-off always run a group as its devices, each on its own: a Zigbee group
  has no call for it ([integrations](../../integrations.md#what-cant-be-done-and-why)). Right after Home Assistant connects to MQTT, until Zigbee2MQTT republishes its
  groups, which it does as the connection comes up, DeviceSide can't tell a group's members: the group is in
  Labs, and turn on with timer refuses it (`class_unknown`), as a Tuya plug in it would stay on. If DeviceSide
  can't subscribe to Zigbee2MQTT's bridge at all, it logs a warning, groups run only with Labs on, and,
  until the integration reloads, turn on with timer refuses every group and every light, plug or switch but Hue's
  (IKEA's included), as it can't tell which is a rebadged Tuya device.

### Hue

Signify's Hue devices (manufacturer `Philips`). A Hue smart plug gets no turn on with timer
([Zigbee plugs and switches](../../integrations.md#zigbee-plugs-and-switches)).

### Tuya

Tuya plugs, switches and lights, including those sold under other brands (Lidl, Moes, BlitzWolf and more). Most run
Tuya's own countdown instead of the Zigbee timer, and Zigbee2MQTT turns the Zigbee timer into a plain on. So turn on
with timer uses Tuya's countdown on the TS011F plugs and the datapoint devices with one countdown below, which take
turn off with timer too, and isn't built yet on the rest: the Zigbee timer would turn the device on and leave it on ([research](research/2026-11-14-timed-on-call-patterns.md)).
Their other features aren't built yet either, as none has passed on a Tuya device and nothing predicts Tuya's
firmware takes the standard commands. DeviceSide refuses them, even with Labs on.

#### Tuya TS011F plugs

Tuya's TS011F smart plugs, and their white labels, that Zigbee2MQTT drives by Tuya's countdown (it shows a `countdown`
setting for the plug). Turn on with timer uses that countdown:

- **One maker string at a time** (the Zigbee manufacturer Zigbee2MQTT shows for the plug): plugs of the same model
  answer the countdown differently by maker, so a run on one string proves nothing about another's. A string a run
  has passed on is a class of its own.
- **Every other maker string:** about 200 maker strings share the plugs' Zigbee2MQTT definitions, each a different
  maker's build, and some are reported to ignore the countdown ([research](research/2026-11-15-converter-seed-list.md)).
  If you try one, please report whether it works: a string gets a class of its own with a passing run
  ([evidence](../../evidence.md#no-known-method-not-built-yet-in-labs)).
- **Shown as a light:** a plug of a string with its own class that Zigbee2MQTT shows as a light is still a plug to
  DeviceSide, but no run has tried one shown as a light.
- **Not built yet on `_TZ3000_gjnozsaz`,** even with Labs on: its countdown is reported to restart
  at random, so it could stay on ([Zigbee2MQTT #30493](https://github.com/Koenkk/zigbee2mqtt/issues/30493)).

The timer runs in whole seconds, up to 12 hours: a duration is rounded to the nearest second, at least 1, and one
rounded or longer than 12 hours reports `clamped_to`, the value sent. Turning the plug off, its button or a new timer
cancels it. The plug's time left can't be read, so get attributes refuses it, with no known method. A TS011F that
Zigbee2MQTT shows no `countdown` for, or a multi-socket one, isn't built yet: the Zigbee timer was tested on the
Tuya TS011F and left it on ([internals](../../internals.md#tested-behavior)). A TS011F is a plug even where Zigbee2MQTT
shows it as a light, so the actions for lights alone, such as stop, refuse it there as not built yet; turn on with
timer still takes it.

#### Tuya datapoint devices with one countdown

Tuya datapoint devices (they speak only Tuya's own protocol) whose Zigbee2MQTT definition, the Model on the device's
Zigbee2MQTT page, gives one `countdown` setting, in seconds, for the whole device: dimmers, wall switches, relays, a
plug and a valve. Turn on with timer and turn off with timer send the on or the off with that countdown, and the device
toggles back when it ends. They are admitted by Model, on a reading of each one's Zigbee2MQTT definition, not on a test
of the device ([research](research/2026-11-14-tuya-datapoint-countdown.md),
[the call](research/2026-11-24-tuya-datapoint-call.md)). A Model not listed here is one of the
[other Tuya datapoint devices](#other-tuya-datapoint-devices), even with a countdown setting, until its definition is
read. If you try one, please report whether it works.

- **Up to 12 hours:** ZDMS16-1, ZOT60 (a TS011F plug on Tuya's protocol), FK_V02, GL-SPI-206P, SFD02-Z, SFD02-Z_2,
  QADZ1LR, `TS0601_dimmer_1_gang_1`, `TS0601_dimmer_1_gang_2`, `TS0601_dimmer_5`, MG-ZG01W, `_TZE28C1000000_jlbsptkl`,
  ZMS-206US-1.
- **Up to 24 hours:** TO-DM-W/B, `TS0601_multifunction_switch`, D1Z, D5Z.
- **Up to 7,210 s (2 h 10 s):** AVATTO ZBS16.

D1Z and SFD02-Z_2 need a Zigbee2MQTT release after 2.14.3, which doesn't have their definitions yet.

The timer runs in whole seconds, from 1 s to the device's limit: a duration is rounded to the nearest second, and one
rounded or over the limit reports `clamped_to`, the value sent. Nothing is read back, so the result is `sent`; get
attributes isn't built for these devices. On a GL-SPI-206P, which gets the on or off twice, a call can report failed
while its timer runs ([internals](internals.md#turn_off_for)).

**The toggle and its cancelling are Tuya's general spec, not measured here.** Tuya's countdown spec says the device
turns off when the countdown ends if it is on, and on if it is off, and that the countdown is cleared when the device's
on/off state changes (its button, the Tuya app, a schedule) or it loses power
([Tuya, General Countdown](https://developer.tuya.com/en/miniapp/solution-ai/ability/lamp-solution/lamp/module-set/common-countdown.md)). That page is Tuya's guide for its Wi-Fi and Bluetooth lamp panels, not for
Zigbee; that these devices follow it is an inference, which Zigbee2MQTT's own description of the setting, "Toggle the
device after a set duration", agrees with ([research](research/2026-11-24-tuya-datapoint-call.md), §2). So a light
turned off by hand during a timer shouldn't come back on, but no device here has been tried.

Left with the other Tuya datapoint devices, though their definitions have a countdown: devices with several switches,
and any whose countdown Zigbee2MQTT names per switch (`countdown_l1`), as DeviceSide's command would reach only the
first ([Sharp edges](#sharp-edges)); timers in minutes, hours or a list of steps; three irrigation valves (FK-BV05,
ZVL-PRO, ZG-308Z), whose countdown may be a preset run time rather than a timer, so a valve could be left open; and a
few whose setting may not be a plain timer, such as a circuit
breaker's ([research](research/2026-11-14-tuya-datapoint-countdown.md)).

#### Tuya inching switches

The Tuya WHD02 (maker string `_TZ3000_skueekg3`, Zigbee model `TS0001`) and the Mowe MW781Z (`_TZ300A_rncj86af`, model
`TS0726`) keep a persistent auto-off, "inching", which set auto-off and clear auto-off write
([research](research/tuya/2026-11-24-inching.md)). Both are single-switch devices with a time measured on the device
(5 s and 63 s on the WHD02, 5 s on the MW781Z). They are admitted by maker string, so a string not named here is not.

- **Time:** whole seconds, from 1 s to 65,535 s.
- **Sent, not confirmed:** the setting can't be read back, so the result is `sent`, and get attributes reports no
  auto-off setting for these devices.
- **No auto-on,** and turn on with timer is refused, as on the other Tuya plugs and switches below.
- **Not these:** the WHD02's `TS000F` variant, the Moes ZM4LT3 (`_TZ3000_mzcp0of6`, reported having no effect) and every
  other Tuya switch whose Zigbee2MQTT definition has an inching setting stay with the other Tuya plugs and switches
  below. The datapoint devices (`TS0601`) time themselves by a countdown, a different mechanism
  ([above](#tuya-datapoint-devices-with-one-countdown)).

#### Tuya plugs and switches

Tuya devices on the standard Zigbee on/off commands: plugs, switches and relays (models `TS0001` to `TS0004`, and white
labels), and lights, such as bulbs and dimmers. No feature is built for them yet, as above.

The LYAI-14 irrigation valve (model `TS0049`) is one of them, as it switches on the standard commands. Zigbee2MQTT
shows a countdown setting for it, but its definition's source says the valve ignores the countdown and runs its own
default 10 minutes, so it doesn't get Tuya's datapoint countdown ([research](research/2026-11-14-tuya-datapoint-countdown.md), §5).

#### Other Tuya datapoint devices

Tuya devices that speak only Tuya's own protocol (model `TS0601`), but for the
[ones with one countdown](#tuya-datapoint-devices-with-one-countdown). No feature is built for them yet, as above; they
take no standard Zigbee reads or writes, and their timer is Tuya's own countdown, which isn't built for them: on a
device with several switches it needs a command per switch.

Until Zigbee2MQTT publishes its devices after Home Assistant connects to MQTT, or while it is still pairing one,
DeviceSide knows a rebadged Tuya device only by what Home Assistant shows: the vendor `Tuya`, or a model starting
`TS`. One shown under another brand, as another brand's device (Lidl's, or Gledopto's GL-SPI-206P, which runs Tuya's
own protocol), can't be told apart from that brand's own devices for those first moments. So turn on with timer
refuses every light, plug or switch but a Hue one (`class_unknown`), even with Labs on, and so do turn off with timer
(`class_unknown`; a Hue light, known from the start, it refuses as not built yet), set auto-off and clear auto-off
(`class_unknown`), until
Zigbee2MQTT lists it as fully paired (interviewed), with its own Zigbee manufacturer and model. A group with such a
light in it runs its other lights, each on its own, one command per light. A device whose pairing never completes stays
refused until you pair it again in Zigbee2MQTT, and until then its groups run their other lights one by one.

### Sengled

Sengled bulbs ignore the Zigbee timer command, so turn on with timer is not built yet on them: the bulb would stay
off ([probe](research/2026-11-14-lab-probe.md)). Their other features aren't built either: a Sengled E11-G13 departs
from the standard commands on ZHA (written while off, it jumps to full brightness:
[ZHA internals](../zha/internals.md)), and nothing predicts which it takes. DeviceSide refuses them, even with
Labs on.

### Sonoff

Sonoff's relays and dimmers keep a persistent auto-off, "inching", which set auto-off and clear auto-off write
([research](research/sonoff/2026-11-24-inching.md)). The MINI-ZBDIM dimmer also takes smooth dimming and stop,
which rest on the standard commands every Zigbee 3.0 certified dimmable light must take, as for
[other brands](#other-brands). Sonoff's other features aren't built yet: nothing predicts how its devices take color
moves, reads and writes, or the Zigbee timer. A two-gang MINI-ZB2GS waits on [per-endpoint addressing](../../deferred.md#per-endpoint-addressing-on-zigbee2mqtt).

#### Sonoff inching relays

The single-channel models ZBMINIR2 (and its white label MINI-ZBD), ZBMicro, MINI-ZB1GS, MINI-ZB1GSP, BASIC-ZB1GSP,
S61SZBTPB and the MINI-ZBDIM dimmer, admitted by model on Zigbee2MQTT's definition, not on a test of the device.

- **Time:** half seconds, from 0.5 s to 3,599.5 s (just under an hour), on every model, the ones that take longer
  included.
- **Sent, not confirmed:** the setting can't be read back, so the result is `sent`, and get attributes reports no
  auto-off setting for these devices.
- **No auto-on:** DeviceSide sets the relay to turn off after the time, never to turn on again.

#### Sonoff S60 plugs

The S60ZBTPF and S60ZBTPG are not built, even with Labs on: users report Zigbee2MQTT's disable has no effect on them
([Zigbee2MQTT #31799](https://github.com/Koenkk/zigbee2mqtt/issues/31799)), so clear auto-off would leave the plug
pulsing.

### Gledopto

Gledopto's LED controllers and bulbs. Zigbee2MQTT sends some of them a plain on, a pause, then the brightness, rather
than the standard command a Hue bulb gets, and some turn on when their color is set while off
([research](research/2026-11-14-timed-on-call-patterns.md)). So no feature is built for them yet, and DeviceSide
refuses them, even with Labs on. The GL-SPI-206P, which runs Tuya's own protocol, is one of the
[Tuya datapoint devices with one countdown](#tuya-datapoint-devices-with-one-countdown).

### IKEA

IKEA's TRÅDFRI lights (Zigbee manufacturer `IKEA of Sweden`, which Zigbee2MQTT publishes as it connects; until then
an IKEA light counts as another brand's). Most run the Zigbee timer, by what they report when paired and by users'
reports ([research](research/2026-11-14-timed-on-call-patterns.md), §3), so they take the Zigbee timer. Two GU10
white spectrum bulbs, LED2005R5 and LED2106R3, are reported to turn on with it and never turn off
([Zigbee2MQTT #29158](https://github.com/Koenkk/zigbee2mqtt/issues/29158)), so DeviceSide refuses them there, even
with Labs on. IKEA's outlets get no turn on with timer, as no plug has passed
([Zigbee plugs and switches](../../integrations.md#zigbee-plugs-and-switches)). Smooth dimming and stop rest on
the standard commands every Zigbee 3.0 certified dimmable light must take, as for [other brands](#other-brands); the
other features aren't built yet.

On IKEA lights, lower brightness to off may stop at the lowest level instead of turning the light off
([evidence](../hue/internals.md#device-classes)).

### Other brands

Lights of every other brand, such as Innr or Ledvance, and their plugs and switches. A Zigbee 3.0 certified dimmable
light must take the standard dimming and stop commands ([internals](../../internals.md#shared)), which they get
exactly as a Hue bulb does, so they take smooth dimming and stop. Their other features aren't built yet: nothing
predicts how other brands take color moves, reads and writes, and on turn on with timer some lights turn on and never
off, and most plugs ignore the timer. If you try dimming, please report it whether it works or not: Integrations >
[DeviceSide](https://my.home-assistant.io/redirect/integration/?domain=deviceside) > Configure > Report a device test
result or bug.

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
- **`hue_native_control`**, on a Hue bulb, or a group with one, for one command at a time, then put back as you had
  it. A `turn_on_for` with a color goes out with it on: without it, a Hue bulb that is off drops
  the color and lights at its last one first. A brightness move goes out with it off: with it, a Hue bulb runs a
  long fade faster than asked, and reports off at once during a fade to off. DeviceSide sets the option, sends the
  command, and puts your setting back once Zigbee2MQTT answers, within a second. Every other command, DeviceSide's
  or not, goes out as you set it. With the option on, a plain `light.turn_on` is the bulb's own short fade (about
  0.4 s), and a `stop` sent during it halts it there, as it halts any fade the bulb runs.
- **`filtered_cache`**, before the first read of a device, so a read's answer isn't resent in every later state
  message. Your own entries are kept. Removing DeviceSide's is harmless: it comes back at the next read.

## Failed sends

When Zigbee2MQTT logs that it couldn't send a command (a busy coordinator refusing a group command, say), raise,
lower, stop, turn on with timer, turn off with timer and set attributes report that light or group failed, with the reason Zigbee2MQTT
gave (`busy`). These actions answer up to 2 s later than before while DeviceSide listens for that line; a command
Zigbee2MQTT answers with the light's state ends the wait at once.

## Turn on with timer

With light fields, DeviceSide calls `light.turn_on` first, then starts the timer once Zigbee2MQTT reports the
light's new state, usually within a fraction of a second. If that takes over 5 s, the light stays on up to 5 s
longer than asked.

A Tuya TS011F plug gets Tuya's countdown instead, with its own limits ([Tuya TS011F plugs](#tuya-ts011f-plugs)); it
reports its state when the timer ends, so DeviceSide reads nothing back. So does a Tuya datapoint device with one
countdown ([its section](#tuya-datapoint-devices-with-one-countdown)), with its own limits too.

The result is `sent`: Zigbee2MQTT doesn't confirm a timer, or report the light's state after one. Device
Side reads the state back after the light turns on and when the timer ends, so Home Assistant stays right. A
restart during a timer loses those reads, and the state can stay stale until the light next reports.

Color bulbs of other brands have no equivalent of Hue native control, so one given a color from off may show its
last color for a moment. With native control on, a Hue bulb may report its old color for the first seconds of a
timer.

**Cancelling.** `turn_off` cancels the timer. A new timer replaces the old one, longer or shorter, as on ZHA: Zigbee2MQTT
sends the same `OnWithTimedOff` (untested on Zigbee2MQTT).

## Turn off with timer

Only the [Tuya datapoint devices with one countdown](#tuya-datapoint-devices-with-one-countdown) take it: DeviceSide
turns the device off with its countdown set, and the device turns itself back on when the countdown ends. No other
Zigbee device has a call for it ([integrations](../../integrations.md#what-cant-be-done-and-why)), so DeviceSide
refuses every other light, plug or switch as not built yet, and runs a group as its devices. The result is `sent`:
nothing is read back.

**Cancelling.** By Tuya's spec, turning the device on cancels the timer, as any change of its on/off state does, and a
new timer replaces the old one. Turning off a device already off changes nothing on it, so Tuya's spec doesn't say it
cancels the timer (untested).

## Smooth color changes

- **Hue moves** cycle the color wheel until `stop`, with a `sweep_time` of 1 to 254 s. Saturation and hue need a
  light that is on and supports hue and saturation, or a group whose lights all do.

## Flash-free turn-on

`set_attributes` reads each light back, so the result is `confirmed`. A light that ignored the write fails the call
(`not_stored`).

## Get attributes

`get_attributes` reads each bulb live, since Hue bulbs on Zigbee2MQTT don't report and its cached state can be stale.
A group returns one entry, averaged over the lights that are on, as Hue averages a room. It reads only Hue's lights
yet: other brands' reads aren't built, Tuya's datapoint devices' included. Tuya's countdown plugs, which Turn on with timer runs on, are refused: their
time left can't be read ([Tuya TS011F plugs](#tuya-ts011f-plugs)).

## Sharp edges

- **A renamed base topic** leaves the old one's bridge entities in Home Assistant, and until you remove them
  DeviceSide can't tell which base is live, so that Zigbee2MQTT's lights are refused (`not_addressable`). Remove the
  old base topic's Zigbee2MQTT Bridge entities ([internals](internals.md#addressing)).
- **A device named with a bare number** that matches a group's ID gets that group's commands.
- **Devices with several lights or switches** (a two-gang switch, a dual-channel Gledopto, a two-gang relay) are
  refused (`not_addressable`) by every action, each of their lights or switches, the first too (a plug's own child
  lock or LED switch is refused the same way, and the plug beside it works): DeviceSide's
  command would reach only the device's default endpoint, maybe a gang the user didn't target
  ([internals](internals.md#addressing)). Named, the call raises; by area, label or an HA group, the light is
  skipped. A Zigbee2MQTT group holding one of its lights still runs as one group; when it falls back to its lights,
  the device is skipped (`not_addressable`). Raise, lower, stop and set attributes refuse such a group
  (`not_addressable`), as they plan from each light's state and can't see that one; get attributes reads the
  group's other lights, and refuses a group with none.
- **Large groups.** A call has 30 s for all its targets. Reading a large group on a slow mesh can run out, failing
  every target with `timeout`. Target the lights by area or label instead, which reads four at a time.
