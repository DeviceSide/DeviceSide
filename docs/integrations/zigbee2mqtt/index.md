# Zigbee2MQTT

What DeviceSide's features do on Zigbee2MQTT, their limits, and what DeviceSide changes in your setup. What applies
to every integration is in [integrations.md](../../integrations.md); which devices each feature is proven on is
on the [device compatibility page](../../device-compatibility.md); how the calls work, and what was measured, is
in [internals.md](internals.md).

Lights that Zigbee2MQTT announced to Home Assistant through MQTT discovery.

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

## Turn on with timer

With light fields, DeviceSide calls `light.turn_on` first, then starts the timer once Zigbee2MQTT reports the
light's new state, usually within a fraction of a second. If that takes over 5 s, the light stays on up to 5 s
longer than asked.

The result is always `sent`: Zigbee2MQTT doesn't confirm a timer, or report the light's state after one. Device
Side reads the state back after the light turns on and when the timer ends, so Home Assistant stays right. A
restart during a timer loses those reads, and the state can stay stale until the light next reports.

Color bulbs of other brands have no equivalent of Hue native control, so one given a color from off may show its
last color for a moment. With native control on, a Hue bulb may report its old color for the first seconds of a
timer.

**Cancelling.** `turn_off` cancels the timer.

## Smooth color changes

- **Hue moves** cycle the color wheel until `stop`, with a `sweep_time` of 1 to 254 s. Saturation and hue need a
  light that is on and supports hue and saturation, or a group whose lights all do.
- **Saturation on a group** publishes one color to the group, at the group's hue in Home Assistant, and every light
  that is on moves to it. A group whose lights sit at different hues ends at one hue.

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
- **Large groups.** A call has 30 s for all its targets. Reading a large group on a slow mesh can run out, failing
  every target with `timeout`. Target the lights by area or label instead, which reads four at a time.
