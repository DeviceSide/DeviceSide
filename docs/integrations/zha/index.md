# ZHA

What DeviceSide's features do on ZHA, their limits, and what DeviceSide changes in your setup. What applies
to every integration is in [integrations.md](../../integrations.md), and what holds for a brand on both Zigbee
integrations in [zigbee.md](../zigbee.md); which devices each feature is proven on is on the
[device compatibility page](../../device-compatibility.md); how the calls work, and what was measured, is in
[internals.md](internals.md).

Lights on the core `zha` integration.

**Admin only.** DeviceSide uses ZHA's admin-only actions, so a call made by a non-admin user fails
(`admin_required`). Automations run without a user and pass.

## Device classes

DeviceSide tells brands apart ([why](../zigbee.md#why-brands-have-classes)) by the manufacturer and model the device
reports when it pairs, and by how ZHA's device handler for it sends commands ([internals](internals.md#classes)).

- A **group** gets only what all its lights get, and otherwise falls back to its lights, each on its own
  ([the rules](../../integrations.md#all-integrations)). Turn on with timer sends a group one command only when its
  lights are every device in it; otherwise each light gets its own, so a plug or a refused light in the group never
  gets the timer ([internals](internals.md#turn_on_for)). A ZHA group command gives no delivery feedback, so each
  light is read back.
- A device whose manufacturer or model ZHA couldn't read when it paired (ZHA shows `unk_manufacturer` or
  `unk_model`) can't be placed, so turn on with timer refuses it (`class_unknown`), even with Labs
  on, as it could be a Tuya datapoint device. Reconfigure it from its ZHA device page, or pair it again.

### Hue

Signify's Hue devices (manufacturer `Signify Netherlands B.V.` or `Philips`). Raising brightness from off sends a Hue
bulb Hue's own command.

### Tuya

Tuya's devices, under any brand ([Tuya](../zigbee.md#tuya)). DeviceSide refuses them, even with Labs on. Their timer
isn't the standard Zigbee one, so turn on with timer would leave them on or turn them on late; why, for each kind, is
below.

#### Tuya plugs and switches

Tuya's plugs, switches and relays on the standard Zigbee on/off commands (models `TS011F`, `TS0001` to `TS0004`,
`TS0011` and `TS0726`), including the Tuya TS011F: the Zigbee timer can turn them on long after the time asked and
leave them on ([the Zigbee timer](../zigbee.md#the-zigbee-timer)). The TS011F `_TZ3000_gjnozsaz` is also reported to
fail Tuya's own timer call, so it may not turn off when asked; another of Tuya's calls may serve it.

#### Other Tuya devices

Tuya's other devices on the standard Zigbee commands: bulbs (such as `TS0505B`), dimmers and other white labels. Their
timer is unprobed: it may be read in seconds, as the plugs read it.

#### Tuya datapoint devices

Tuya devices that speak only Tuya's own protocol (model `TS0601`, and others ZHA handles the same way). ZHA turns
DeviceSide's commands into Tuya's own: it refuses the timer, so with a brightness or color temperature the light
would turn on and stay on, and it drops a fade's timing and reads from memory rather than the device.

### Sengled

Sengled's bulbs ([Sengled](../zigbee.md#sengled)). They refuse the Zigbee timer, and miss it silently when it is sent
to a group ([the Zigbee timer](../zigbee.md#the-zigbee-timer)), so with a brightness or color temperature, or in a
group, turn on with timer would turn a bulb on and leave it on. DeviceSide refuses them, even with Labs on.

### Sonoff SWV

Sonoff's SWV water valve reads the Zigbee timer in seconds rather than tenths, so it would stay open about ten times
longer than asked ([research](../zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md)), so DeviceSide refuses
it, even with Labs on. The light features don't apply to a valve.

### IKEA

IKEA's TRÅDFRI lights (manufacturer `IKEA of Sweden`). They take the Zigbee timer but for two GU10 bulbs, LED2005R5
and LED2106R3, refused even with Labs on, and a lower to off may stop at the lowest level ([IKEA](../zigbee.md#ikea),
[the Zigbee timer](../zigbee.md#the-zigbee-timer)). Smooth dimming and stop rest on the standard commands
([why](../zigbee.md#smooth-dimming-and-stop)).

### Other brands

Lights of every other brand, such as Innr, Ledvance or Sonoff, and their plugs and switches. Their lights take smooth
dimming and stop ([why](../zigbee.md#smooth-dimming-and-stop)); raising brightness from off sets them to their lowest
level first, where a Hue bulb gets Hue's own command. If you try dimming, please report it whether it works or not: Integrations >
[DeviceSide](https://my.home-assistant.io/redirect/integration/?domain=deviceside) > Configure > Report a device test
result or bug.

## Turn on with timer

DeviceSide reads the timer back from the bulb, so the result is `confirmed`, or `sent` if the read-back didn't
show it.

**Cancelling.** Only `turn_off` or a new `turn_on_for` cancels the timer. A plain `turn_on`, or a brightness change,
leaves it running, and the light still turns off when it ends. Nothing stops a timer and keeps the light on: turn
it off, then on, which blinks.

**Why the timer belongs on the device.** For 1.5 s after `light.turn_off`, ZHA ignores the light's "on" report, so
a timer sent in that window lights the bulb while Home Assistant shows it off. The bulb still turns itself
off on time; an automation waiting for the light to be on would never fire.

## Smooth dimming

A soft off restores the light's level just after the fade ends. A restart during the fade loses that, and the light
comes back at its lowest level.

## Smooth color changes

- **Hue moves** cycle the color wheel until `stop`, with a `sweep_time` of 1 to 65535 s.

## Flash-free turn-on

- **`set_attributes`** reads nothing back, so a bulb that ignores the write still reports `sent`. The Sengled
  E11-G13 is refused (`execute_if_off_unsupported`): written while off, it jumps to full brightness.
- **`min_brightness` and `max_brightness`** read the light's level live. Within about 0.5 s of a brightness change
  the light is still fading, and the limit can replace the fade's end.

## Get attributes

`get_attributes` reads each light live, not from ZHA's cache, which goes stale after a remote or a command Home
Assistant didn't send. A ZHA group returns one entry per light. It reads only devices another DeviceSide feature runs
on, and only Hue's yet: other brands' reads aren't built.
