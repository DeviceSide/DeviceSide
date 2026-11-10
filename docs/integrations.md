# Integrations

What the [README](../README.md) features do on each integration, their limits, and what DeviceSide changes in your
setup. Which devices each feature is proven on is on the [device compatibility page](device-compatibility.md). How the
commands work on the wire, and what was measured on real bulbs, is in
[integration-internals.md](integration-internals.md).

## All integrations

- **Refused targets.** A target that can't take an action fails the call if you named it, and is skipped if it
  came through an area, device, label or group ([action-behavior.md](action-behavior.md)). The error names the
  reason, such as `capability_not_tested`.
- **Groups.** For timers and smooth moves, Zigbee2MQTT and ZHA groups and Hue rooms and zones get one
  command, so their lights move together. `set_attributes` writes a ZHA group's or Hue room's lights one by one.
  Any other group, such as a light group helper, is expanded and each light gets its own command.
- **Switches shown as lights.** A light made from a supported switch with Home Assistant's "Change device type of a
  switch" helper is treated as that switch: light fields are dropped and the timer still runs. An inverted one is
  refused (`inverted_wrapper`).
- **No color temperature moves.** Every stop of a color temperature fade on a Hue bulb, the Hue bridge's own
  included, makes a visible jump, so there is no raise or lower for it.
- **Fades pick up where the last one stopped.** DeviceSide remembers each raise, lower and `stop` for a few
  seconds after it ends (2 s on Zigbee, 15 s on Hue), so releasing and pressing again doesn't jump. A light
  command from Home Assistant clears it at once; a change from a remote or app in that window may be missed.
- **Dimming to 0 % is a soft off.** The light fades out and keeps its level, so a plain turn on brings it back
  there. Raising brightness on a light that is off fades in from the bottom.

## Shelly

Gen2 and later (Plus, Pro, Gen3, Gen4): relays, whether Home Assistant shows them as a switch or a light, RGBCCT
bulbs, and the other Shelly lights (dimmers, CCT, RGB and RGBW devices: the Light, CCT, RGB and RGBW components),
which take the same calls. CCT, RGB and RGBW devices take brightness but not color or color temperature yet: either
is left out of the call, which reports `fields_dropped`. Gen1 isn't built: it has Shelly's older
[HTTP API](https://shelly-api-docs.shelly.cloud/gen1/), not the [Gen2+ RPC calls](https://shelly-api-docs.shelly.cloud/gen2/)
the adapters send, so it is refused (`gen1_unsupported`).

### Turn on with timer

The device runs the timer and confirms it. A transition is at least 0.5 s. A color temperature outside the bulb's
range is clamped. `hs_color` and `xy_color` are sent as the RGB color Home Assistant would send for them, whatever
mode the bulb is in.

### Turn off with timer

The device runs the timer and confirms it, as for turn on.

**Cancelling either timer.** Any on or off cancels the timer, whoever sends it: Home Assistant, the Shelly app or
another integration. A wall switch wired to the device's input is untested and may depend on the input mode.

### Auto-off/on

`set_auto_off` stores a delay on the device: from then on, every turn-on from any source (a button, the Shelly app, a
schedule, Home Assistant) turns off again after it, as a garage-door relay needs. `set_auto_on` is the reverse.
`clear_auto_off` and `clear_auto_on` remove the setting; the output stays as it is. `get_attributes` reports each as
`{"duration": <seconds>}` when set and `null` when not. Lights take the same calls as relays, and each is confirmed by
reading the stored setting back.

- **It reloads the Shelly entry.** Changing the setting makes the core Shelly integration reload the device's
  config entry about 60 s later, so its entities go unavailable briefly. The output doesn't change. A call that
  matches what the device already holds sends nothing and returns `unchanged`, with no reload.
- **It writes the device's flash.** Set it once, not from a frequent automation.
- **With `turn_on_for`.** A `turn_on_for` overrides the stored auto-off for that one turn-on, whether its duration
  is shorter or longer: the output turns off when `turn_on_for` says. Clearing auto-off doesn't stop a
  `turn_on_for` countdown that is already running.

### Smooth dimming

On a Multicolor Bulb (RGBCCT), `raise_brightness` and `lower_brightness` read the bulb's own level, mid-fade included,
then send one fade the bulb runs itself; `stop` halts it and reads back where it halted. A fade is at least 0.5 s.
Lowering to 0 % is the bulb's own soft off: it fades out, turns off, and comes back on at its old level; a `stop`
during it leaves the bulb on. Raising a bulb that is off fades it in from the bottom. Other Shelly lights take the same
calls on their own component.

### Flash-free turn-on

On a Multicolor Bulb (RGBCCT) `set_attributes` sends one `RGBCCT.Set` without `on`, so a bulb that is off stores the
values and stays off, and the next plain on comes up with them. The device answers a `Set` with nothing, so DeviceSide
reads the status back: brightness, color temperature and mode must read as written, or the call fails (`not_stored`).
A color is not compared, only the mode it switches to. `min_brightness` and `max_brightness` clamp the brightness the
bulb has stored, read first, so they work while it is off; a bulb already within them is `unchanged`. Other Shelly
lights don't take `set_attributes` yet.

### Get attributes

On lights other than the Multicolor Bulb, `get_attributes` reports the timer and auto-off/on but not brightness or
color.

## Zigbee2MQTT

Lights that Zigbee2MQTT announced to Home Assistant through MQTT discovery.

### What DeviceSide changes in Zigbee2MQTT

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

### Turn on with timer

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

### Smooth color changes

- **Hue moves** cycle the color wheel until `stop`, with a `sweep_time` of 1 to 254 s. Saturation and hue need a
  light that is on and supports hue and saturation, or a group whose lights all do.
- **Saturation on a group** publishes one color to the group, at the group's hue in Home Assistant, and every light
  that is on moves to it. A group whose lights sit at different hues ends at one hue.

### Flash-free turn-on

`set_attributes` reads each light back, so the result is `confirmed`. A light that ignored the write fails the call
(`not_stored`).

### Get attributes

`get_attributes` reads each bulb live, since Hue bulbs on Zigbee2MQTT don't report and its cached state can be stale.
A group returns one entry, averaged over the lights that are on, as Hue averages a room.

### Sharp edges

- **Custom base topic.** Groups on a base topic other than `zigbee2mqtt` are refused (`not_addressable`). Devices
  aren't, but their commands reach nothing while the result still says `sent`.
- **A device named with a bare number** that matches a group's ID gets that group's commands.
- **Large groups.** A call has 30 s for all its targets. Reading a large group on a slow mesh can run out, failing
  every target with `timeout`. Target the lights by area or label instead, which reads four at a time.

## ZHA

Lights on the core `zha` integration.

**Admin only.** DeviceSide uses ZHA's admin-only actions, so a call made by a non-admin user fails
(`admin_required`). Automations run without a user and pass.

### Turn on with timer

DeviceSide reads the timer back from the bulb, so the result is `confirmed`, or `sent` if the read-back didn't
show it.

**Cancelling.** Only `turn_off` or a new `turn_on_for` cancels the timer. A plain `turn_on`, or a brightness change,
leaves it running, and the light still turns off when it ends. Nothing stops a timer and keeps the light on: turn
it off, then on, which blinks.

**Why the timer belongs on the device.** For 1.5 s after `light.turn_off`, ZHA ignores the light's "on" report, so
a timer sent in that window lights the bulb while Home Assistant shows it off. The bulb still turns itself
off on time; an automation waiting for the light to be on would never fire.

### Smooth dimming

A soft off restores the light's level just after the fade ends. A restart during the fade loses that, and the light
comes back at its lowest level.

### Smooth color changes

- **Hue moves** cycle the color wheel until `stop`, with a `sweep_time` of 1 to 65535 s.
- **Saturation on a group** sends every light that is on one color, at the hue of the first of them. A group whose
  lights sit at different hues ends at one hue.

### Flash-free turn-on

- **`set_attributes`** reads nothing back, so a bulb that ignores the write still reports `sent`. The Sengled
  E11-G13 is refused (`execute_if_off_unsupported`): written while off, it jumps to full brightness. For the same
  reason it doesn't fade in from the bottom when raised from off, and comes back at its lowest level after a soft
  off.
- **`min_brightness` and `max_brightness`** read the light's level live. Within about 0.5 s of a brightness change
  the light is still fading, and the limit can replace the fade's end.

### Get attributes

`get_attributes` reads each light live, not from ZHA's cache, which goes stale after a remote or a command Home
Assistant didn't send. A ZHA group returns one entry per light.

## Matter

Plugs and lights on the core `matter` integration whose endpoint has the On/Off cluster's Lighting feature, which
Matter's timer needs; one without it is refused (`no_lt_feature`). On/off only: brightness and color fields are
refused on a Matter light.

### Turn on with timer

The timer is read back from the device, so the result is `confirmed` only when it reports both a running timer
(`OnTime`) and that it is on, otherwise `sent`. `turn_off` cancels the timer; a plain `turn_on` doesn't.

### Get attributes

`get_attributes` reports a timer only when the device reports both a running timer and that it is on.

## Hue

A Hue Bridge v2 or Bridge Pro on the core `hue` integration. The v1 bridge isn't built: it lacks the v2 API and
event stream DeviceSide uses, and Signify no longer supports it
([Home Assistant](https://www.home-assistant.io/integrations/hue/#support-for-legacy-v1-hue-bridges)), so it is
refused (`bridge_v1`). Rooms and zones are targets in their own right.

**No `turn_on_for` or `turn_off_for`.** The bridge's own timers keep running through a plain on or off, from Home
Assistant, the Hue app or a dimmer switch, and the Hue app doesn't show them. To time Hue bulbs, pair them with ZHA,
Zigbee2MQTT or Matter.

**No auto-off or auto-on.** Neither a light nor a room stores one in the CLIP v2 API, and v2 has no rule engine to
build one from. The v1 rule engine could, but Signify advises against it as "it will not be available long term"
([Hue API V2](https://developers.meethue.com/develop/hue-api-v2/)). A timer kept by Home Assistant wouldn't survive
it going offline, which is the point of auto-off.

### Smooth dimming

The bridge runs the fade. A room fades as one, and its lights converge on the end point.

**Fix Hue Bridge brightness reports while dimming** (on by default). When a fade starts, the bridge reports 0 % or
100 % brightness, and only snaps back to the light's actual level about 10 s later. With this option on, Home
Assistant shows the brightness the fade started at while it runs, where a `stop` halted it, and the end once the fade
has run, so a dashboard slider holds still, then jumps. Color is always shown as the bridge reports it. A change from
the Hue app, a dimmer switch or a bridge scene shows at once, except a brightness change or a turn on within 15 s of a
fade. A restart or bridge reconnect mid-fade shows what the bridge reports. Turn the option off in DeviceSide's
options to see the bridge's own reports.

### Smooth color changes

There are no hue moves, as a trip around the color wheel isn't a straight line the bridge can fade along. Saturation
keeps each light's current hue, so a white deepens toward its own tint (a warm white toward amber). 100 % saturation
is the edge of Home Assistant's color space, a little short of the deepest colors the Hue app can reach.

### Flash-free turn-on

- **`set_attributes`** writes a room light by light, as a room write misses lights that are off.
- **`set_scene`** reads the scene live, so edits in the Hue app apply. A light the scene turns off is turned off.
  Dynamic scenes set their first frame; gradients and effects are skipped. Smart (All-Day) scenes are refused
  (`smart_scene`). Lights are written one after another: an 8-light scene takes under a second.

### Get attributes

`get_attributes` reads the bridge's live event stream, so it sends nothing to the bridge. During a fade it returns
DeviceSide's estimate of where the fade has reached. A room averages the lights that are on, or all of them
when every light is off, as the Hue integration shows it.

### Sharp edges

- **A room turned off with a transition keeps its level.** Turning the room on without a brightness brings every
  light back at that level, overriding one set on its own while off. Set the room instead.
- **Lights without an entity in Home Assistant** are skipped by `set_attributes` and `get_attributes` on their
  room, though `set_scene` writes them. A disabled entity still counts.

## Zigbee plugs and switches

`turn_on_for` and `get_attributes` on Zigbee2MQTT and ZHA plugs and switches are untested
([device compatibility](device-compatibility.md#zigbee-plugs-and-switches)). Few honor the Zigbee timer command:
IKEA's are moving to Thread, and Sonoff and Tuya run their own countdowns (the Tuya TS011F tested never switches on).
If you try one, please report it whether it works or not: Integrations >
[DeviceSide](https://my.home-assistant.io/redirect/integration/?domain=deviceside) > Configure > Report a device test
result or bug, which prefills the device's details.
