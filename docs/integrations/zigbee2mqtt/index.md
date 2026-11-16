# Zigbee2MQTT

What DeviceSide's features do on Zigbee2MQTT, their limits, and what DeviceSide changes in your setup. What applies
to every integration is in [integrations.md](../../integrations.md); which devices each feature is proven on is
on the [device compatibility page](../../device-compatibility.md); how the calls work, and what was measured, is
in [internals.md](internals.md).

Lights that Zigbee2MQTT announced to Home Assistant through MQTT discovery.

## Device classes

Zigbee devices given the same command can answer it differently, by brand and firmware
([research](research/2026-11-14-timed-on-call-patterns.md)), so a test on one brand proves nothing about another.
DeviceSide tells them apart by the manufacturer and model Zigbee2MQTT registers in Home Assistant and, for Tuya
devices sold under other brands, by the device's own Zigbee manufacturer and model, which Zigbee2MQTT publishes as
it connects. Every feature says how well it is proven for each
([levels of proof](../../device-compatibility.md#levels-of-proof)).

- **Hue bulbs** (manufacturer `Philips`) are tested: every feature on this page has passed on them. A Hue smart plug
  hasn't: turn on with timer runs on it only with Experimental features on.
- A **group** is proven as far as its weakest light. One with a light a feature refuses, or, with Experimental features
  off, one of another brand, falls back to its lights, each on its own; with them on, it runs as one group. A member
  Home Assistant has no light for (a plug Zigbee2MQTT shows as a switch, say) counts by its device, so a Tuya plug in a
  group makes it fall back too. So does a TS011F plug on Tuya's countdown for turn on with timer, as the group's timer
  isn't the plug's: each light gets its own, and so does a plug Zigbee2MQTT shows as a light. One it shows as a switch
  is skipped (`not_addressable`), with a warning, as no light reaches it: target its switch beside the group, and it
  gets its countdown, with no warning. Right after Home Assistant connects to MQTT, until Zigbee2MQTT republishes its
  groups, which it does as the connection comes up, DeviceSide can't tell a group's members: the group counts as
  Experimental, and turn on with timer refuses it (`class_unknown`), as a Tuya plug in it would stay on. If DeviceSide
  can't subscribe to Zigbee2MQTT's bridge at all, it logs a warning, groups run only with Experimental features on, and,
  until the integration reloads, turn on with timer refuses every group and every light, plug or switch but Hue's
  (IKEA's included), as it can't tell which is a rebadged Tuya device.

### Tuya

Tuya plugs, switches and lights, including those sold under other brands (Lidl, Moes, BlitzWolf and more). Most run
Tuya's own countdown instead of the Zigbee timer, and Zigbee2MQTT turns the Zigbee timer into a plain on. So turn on
with timer uses Tuya's countdown on the TS011F plugs below, and isn't supported yet on the rest: the Zigbee timer would
turn the device on and leave it on ([research](research/2026-11-14-timed-on-call-patterns.md)). DeviceSide refuses it
there, even with Experimental features on. Their other features are untested, so they run only with Experimental
features on.

#### Tuya TS011F plugs

Tuya's TS011F smart plugs, and their white labels, that Zigbee2MQTT drives by Tuya's countdown (it shows a `countdown`
setting for the plug). Turn on with timer uses that countdown:

- **Verified one maker string at a time** (the Zigbee manufacturer Zigbee2MQTT shows for the plug), each by its own
  test record: `_TZ3000_0zfrhq4i`, `_TZ3000_typdpbpg`, `_TZ3000_gznh2xla` and `_TZ3000_okaz9tjs`. Plugs of the same
  model answer the countdown differently by maker, so one string's test proves nothing about another's.
- **Untested** on every other maker string, and on any of them Zigbee2MQTT shows as a light: it runs only with
  Experimental features on. If you try one, please report
  it, whether it works or not.
- **Not supported yet on `_TZ3000_gjnozsaz`,** even with Experimental features on: its countdown is reported to restart
  at random, so it could stay on ([Zigbee2MQTT #30493](https://github.com/Koenkk/zigbee2mqtt/issues/30493)).

The timer runs in whole seconds, up to 12 hours: a duration is rounded to the nearest second, at least 1, and one
rounded or longer than 12 hours reports `clamped_to`, the value sent. Turning the plug off, its button or a new timer
cancels it. The plug's time left can't be read, so get attributes shows no `timer` for it. A TS011F that Zigbee2MQTT
shows no `countdown` for, or a multi-socket one, isn't supported yet: the Zigbee timer was tested on the
[Tuya TS011F](../../device-compatibility.md#tuya-ts011f) and left it on.

#### Tuya plugs and switches

Tuya devices on the standard Zigbee on/off commands: plugs, switches and relays (models `TS0001` to `TS0004`, and white
labels). Turn on with timer isn't supported yet, as above.

#### Tuya datapoint devices

Tuya devices that speak only Tuya's own protocol (model `TS0601`). Turn on with timer isn't supported yet, as above,
and they take no standard Zigbee reads or writes, so get attributes and set attributes aren't supported on them
either.

Until Zigbee2MQTT publishes its devices after Home Assistant connects to MQTT, or while it is still pairing one,
DeviceSide knows a rebadged Tuya device only by what Home Assistant shows: the vendor `Tuya`, or a model starting
`TS`. One shown under another brand, as another brand's device (Lidl's, or Gledopto's GL-SPI-206P, which runs Tuya's
own protocol), can't be told apart from that brand's own devices for those first moments. So turn on with timer
refuses every light, plug or switch but a Hue one (`class_unknown`), even with Experimental features on, until
Zigbee2MQTT lists it as fully paired (interviewed), with its own Zigbee manufacturer and model. A group with such a
light in it runs its other lights, each on its own, one command per light. A device whose pairing never completes stays
refused until you pair it again in Zigbee2MQTT, and until then its groups run their other lights one by one.

### Sengled

Sengled bulbs ignore the Zigbee timer command, so turn on with timer is not yet supported on them: the bulb would stay
off ([probe](research/2026-11-14-lab-probe.md)). Their other features are untested, so they run only with
Experimental features on. A Sengled E11-G13 written while off jumps to full brightness on ZHA
([ZHA internals](../zha/internals.md)); set attributes on Zigbee2MQTT waits for a test on one.

### Gledopto

Gledopto's LED controllers and bulbs. Zigbee2MQTT sends some of them a plain on, a pause, then the brightness, rather
than the standard command a Hue bulb gets ([research](research/2026-11-14-timed-on-call-patterns.md)), so every
feature on them is untested and runs only with Experimental features on.

### Other brands

Lights, plugs and switches of every other brand, such as IKEA, Innr or Ledvance. Dimming smoothly (raise and lower
brightness) and stop send them exactly the standard Zigbee commands a Hue bulb gets, which no known brand handles
differently, so they should work. Their other features are untested, so they run only with Experimental features on
([try it](../../device-compatibility.md#try-it-experimental-features)). Brands differ most on turn on with timer:
some turn on and never off, or ignore the timer. If you try one, please report it whether it works or not:
Integrations > [DeviceSide](https://my.home-assistant.io/redirect/integration/?domain=deviceside) > Configure > Report
a device test result or bug. A brand with a passing report gets its own entry here.

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

**Cancelling.** `turn_off` cancels the timer.

## Smooth color changes

- **Hue moves** cycle the color wheel until `stop`, with a `sweep_time` of 1 to 254 s. Saturation and hue need a
  light that is on and supports hue and saturation, or a group whose lights all do.

## Flash-free turn-on

`set_attributes` reads each light back, so the result is `confirmed`. A light that ignored the write fails the call
(`not_stored`).

## Get attributes

`get_attributes` reads each bulb live, since Hue bulbs on Zigbee2MQTT don't report and its cached state can be stale.
A group returns one entry, averaged over the lights that are on, as Hue averages a room.

## Sharp edges

- **Custom base topic.** Groups on a base topic other than `zigbee2mqtt` are refused (`not_addressable`). Devices
  aren't, but their commands reach nothing while the result still says `sent`.
- **A device named with a bare number** that matches a group's ID gets that group's commands.
- **Devices with several lights or switches** (a two-gang switch, a dual-channel Gledopto, a two-gang relay) are
  refused (`not_addressable`) by every action, each of their lights or switches, the first too: DeviceSide's
  command would reach only the device's default endpoint, maybe a gang the user didn't target
  ([internals](internals.md#addressing)). Named, the call raises; by area, label or an HA group, the light is
  skipped. A Zigbee2MQTT group holding one of its lights still runs as one group; when it falls back to its lights,
  the device is skipped (`not_addressable`). Raise, lower, stop and set attributes refuse such a group
  (`not_addressable`), as they plan from each light's state and can't see that one; get attributes reads the
  group's other lights, and refuses a group with none.
- **Large groups.** A call has 30 s for all its targets. Reading a large group on a slow mesh can run out, failing
  every target with `timeout`. Target the lights by area or label instead, which reads four at a time.
