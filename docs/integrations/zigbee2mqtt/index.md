# Zigbee2MQTT

What DeviceSide's features do on Zigbee2MQTT, their limits, and what DeviceSide changes in your setup. What applies
to every integration is in [integrations.md](../../integrations.md); which devices each feature is proven on is
on the [device compatibility page](../../device-compatibility.md); how the calls work, and what was measured, is
in [internals.md](internals.md).

Lights that Zigbee2MQTT announced to Home Assistant through MQTT discovery.

## Device classes

Zigbee devices given the same command can answer it differently, by brand and firmware
([research](research/2026-11-14-timed-on-call-patterns.md)), so a test on one brand proves nothing about another.
DeviceSide tells them apart by the manufacturer and model Zigbee2MQTT registers in Home Assistant, and every feature
says how well it is proven for each ([levels of proof](../../device-compatibility.md#levels-of-proof)).

- **Hue bulbs** (manufacturer `Philips`) are tested: every feature on this page has passed on them.
- A **group** is proven as far as its weakest light. One with a light a feature refuses falls back to its lights, each
  on its own. Until Zigbee2MQTT has published its groups since it last connected, a group counts as Experimental.

### Other brands

Lights, plugs and switches of any brand DeviceSide doesn't tell apart yet, such as IKEA, Innr or Ledvance. Their
features are untested, so they run only with Experimental features on
([try it](../../device-compatibility.md#try-it-experimental-features)). Brands differ most on turn on with timer:
some turn on and never off, or ignore the timer. If you try one, please report it whether it works or not:
Integrations > [DeviceSide](https://my.home-assistant.io/redirect/integration/?domain=deviceside) > Configure >
Report a device test result or bug. A brand with a passing report gets its own entry here.

### Tuya devices

Tuya firmware runs its own countdown instead of the Zigbee timer: on the TS011F and TS000x plugs and switches and
their white labels (Tuya ZCL devices), and on TS0601 devices, which speak only Tuya's own datapoints (Tuya MCU
devices). Zigbee2MQTT turns DeviceSide's timer into a plain on that never ends, so turn on with timer refuses them as
not yet supported, rather than leave one on. Their other features are untested, as for other brands. DeviceSide
doesn't recognize Tuya devices yet: until a lab test confirms the strings Zigbee2MQTT registers for them, they count
as other brands.

### Sengled bulbs

DeviceSide doesn't recognize Sengled bulbs yet: until a lab test confirms the strings Zigbee2MQTT registers for them,
they count as other brands.

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
