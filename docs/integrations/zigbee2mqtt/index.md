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

- A **group** gets only what all its lights get. One with a light a feature refuses, or, with Labs
  off, one in Labs, falls back to its lights, each on its own; with Labs on, it runs as one group. A member
  Home Assistant has no light for (a plug Zigbee2MQTT shows as a switch, say) counts by its device, so a Tuya plug in a
  group makes it fall back too. A TS011F plug makes it fall back on smooth dimming, smooth color changes and set without
  turning on even with Labs on, as those serve lights alone, and a TS011F is a plug even where
  Zigbee2MQTT shows it as a light. So does a TS011F plug on Tuya's countdown for turn on with timer, as the group's
  timer isn't the plug's: each light gets its own, and so does a plug Zigbee2MQTT shows as a light. One it shows as a
  switch is skipped (`not_addressable`), with a warning, as no light reaches it: target its switch beside the group, and
  it gets its countdown, with no warning. Right after Home Assistant connects to MQTT, until Zigbee2MQTT republishes its
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
with timer uses Tuya's countdown on the TS011F plugs below, and isn't built yet on the rest: the
Zigbee timer would turn the device on and leave it on ([research](research/2026-11-14-timed-on-call-patterns.md)).
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

#### Tuya plugs and switches

Tuya devices on the standard Zigbee on/off commands: plugs, switches and relays (models `TS0001` to `TS0004`, and white
labels), and lights, such as bulbs and dimmers. No feature is built for them yet, as above.

#### Tuya datapoint devices

Tuya devices that speak only Tuya's own protocol (model `TS0601`). No feature is built for them yet, as above; they
take no standard Zigbee reads or writes, and their timer is Tuya's own countdown, which isn't built for them.

Until Zigbee2MQTT publishes its devices after Home Assistant connects to MQTT, or while it is still pairing one,
DeviceSide knows a rebadged Tuya device only by what Home Assistant shows: the vendor `Tuya`, or a model starting
`TS`. One shown under another brand, as another brand's device (Lidl's, or Gledopto's GL-SPI-206P, which runs Tuya's
own protocol), can't be told apart from that brand's own devices for those first moments. So turn on with timer
refuses every light, plug or switch but a Hue one (`class_unknown`), even with Labs on, until
Zigbee2MQTT lists it as fully paired (interviewed), with its own Zigbee manufacturer and model. A group with such a
light in it runs its other lights, each on its own, one command per light. A device whose pairing never completes stays
refused until you pair it again in Zigbee2MQTT, and until then its groups run their other lights one by one.

### Sengled

Sengled bulbs ignore the Zigbee timer command, so turn on with timer is not built yet on them: the bulb would stay
off ([probe](research/2026-11-14-lab-probe.md)). Their other features aren't built either: a Sengled E11-G13 departs
from the standard commands on ZHA (written while off, it jumps to full brightness:
[ZHA internals](../zha/internals.md)), and nothing predicts which it takes. DeviceSide refuses them, even with
Labs on.

### Gledopto

Gledopto's LED controllers and bulbs. Zigbee2MQTT sends some of them a plain on, a pause, then the brightness, rather
than the standard command a Hue bulb gets, and some turn on when their color is set while off
([research](research/2026-11-14-timed-on-call-patterns.md)). So no feature is built for them yet, and DeviceSide
refuses them, even with Labs on.

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
lower, stop, turn on with timer and set attributes report that light or group failed, with the reason Zigbee2MQTT
gave (`busy`). These actions answer up to 2 s later than before while DeviceSide listens for that line; a command
Zigbee2MQTT answers with the light's state ends the wait at once.

## Turn on with timer

With light fields, DeviceSide calls `light.turn_on` first, then starts the timer once Zigbee2MQTT reports the
light's new state, usually within a fraction of a second. If that takes over 5 s, the light stays on up to 5 s
longer than asked.

A Tuya TS011F plug gets Tuya's countdown instead, with its own limits ([Tuya TS011F plugs](#tuya-ts011f-plugs)); it
reports its state when the timer ends, so DeviceSide reads nothing back.

The result is `sent`: Zigbee2MQTT doesn't confirm a timer, or report the light's state after one. Device
Side reads the state back after the light turns on and when the timer ends, so Home Assistant stays right. A
restart during a timer loses those reads, and the state can stay stale until the light next reports.

Color bulbs of other brands have no equivalent of Hue native control, so one given a color from off may show its
last color for a moment. With native control on, a Hue bulb may report its old color for the first seconds of a
timer.

**Cancelling.** `turn_off` cancels the timer. A new timer replaces the old one, longer or shorter, as on ZHA: Zigbee2MQTT
sends the same `OnWithTimedOff` (untested on Zigbee2MQTT).

## Smooth color changes

- **Hue moves** cycle the color wheel until `stop`, with a `sweep_time` of 1 to 254 s. Saturation and hue need a
  light that is on and supports hue and saturation, or a group whose lights all do.

## Flash-free turn-on

`set_attributes` reads each light back, so the result is `confirmed`. A light that ignored the write fails the call
(`not_stored`).

## Get attributes

`get_attributes` reads each bulb live, since Hue bulbs on Zigbee2MQTT don't report and its cached state can be stale.
A group returns one entry, averaged over the lights that are on, as Hue averages a room. It reads only Hue's lights
yet: other brands' reads aren't built. Tuya's countdown plugs, which Turn on with timer runs on, are refused: their
time left can't be read ([Tuya TS011F plugs](#tuya-ts011f-plugs)).

## Sharp edges

- **Custom base topic.** Groups and devices on a base topic other than `zigbee2mqtt` are refused
  (`not_addressable`).
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
