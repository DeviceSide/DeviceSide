# ZHA

What DeviceSide's features do on ZHA, their limits, and what DeviceSide changes in your setup. What applies
to every integration is in [integrations.md](../../integrations.md); which devices each feature is proven on is
on the [device compatibility page](../../device-compatibility.md); how the calls work, and what was measured, is
in [internals.md](internals.md).

Lights on the core `zha` integration.

**Admin only.** DeviceSide uses ZHA's admin-only actions, so a call made by a non-admin user fails
(`admin_required`). Automations run without a user and pass.

## Device classes

Zigbee devices given the same command can answer it differently, by brand and firmware
([research](../zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md)), so a test on one brand proves nothing
about another. DeviceSide tells them apart by the manufacturer and model the device reports when it pairs, and by
how ZHA's device handler for it sends commands. Every feature says how well it is
proven for each ([levels of proof](../../device-compatibility.md#levels-of-proof)).

- **Hue bulbs** (manufacturer `Signify Netherlands B.V.` or `Philips`) are tested: every feature on this page has
  passed on them.
- A **group** is proven as far as its weakest light. One with a light a feature refuses, or, with Labs off, one in
  Labs, falls back to its lights, each on its own; with Labs on, it runs as one group.
  Turn on with timer sends a group one command only when its lights are every device in it, so a plug in the group
  with no light (a plug ZHA shows as a switch, say), or a light it refused, never gets the group's timer: the lights
  get one command each instead, a fraction of a second apart.
  A ZHA group command gives no delivery feedback, as is the way of a Zigbee groupcast
  ([internals](internals.md#upstream-defects)).
- A device whose manufacturer or model ZHA couldn't read when it paired (ZHA shows `unk_manufacturer` or
  `unk_model`) can't be placed, so turn on with timer refuses it (`class_unknown`), even with Labs
  on, as it could be a Tuya datapoint device. Reconfigure it from its ZHA device page, or pair it again.

### Tuya

Tuya plugs, switches and lights, including those sold under other brands (Lidl, Moes, BlitzWolf and more). No feature
is built for them yet, and DeviceSide refuses them, even with Labs on: none has passed on one, and
nothing predicts Tuya's firmware takes the standard commands. Their timer isn't the standard Zigbee one, so turn on
with timer would leave them on or turn them on late; why, for each kind, is below.

#### Tuya plugs and switches

Tuya's plugs, switches and relays on the standard Zigbee on/off commands (models `TS011F`, `TS0001` to `TS0004`,
`TS0011` and `TS0726`), including the Tuya TS011F: the Zigbee timer
can turn them on long after the time asked and leave them on.

#### Reported Tuya plugs

A TS011F reported to fail Tuya's own timer call: `_TZ3000_gjnozsaz`, whose time left jumps back at random, so it may
not turn off when asked ([Z2M #30493](https://github.com/Koenkk/zigbee2mqtt/issues/30493)). Another of Tuya's calls
may serve it.

#### Other Tuya devices

Tuya's other devices on the standard Zigbee commands: bulbs (such as `TS0505B`), dimmers and other white labels. Their
timer is unprobed: it may be read in seconds, as the plugs read it.

#### Tuya datapoint devices

Tuya devices that speak only Tuya's own protocol (model `TS0601`, and others ZHA handles the same way). ZHA turns
DeviceSide's commands into Tuya's own: it refuses the timer, so with a brightness or color temperature the light
would turn on and stay on, and it drops a fade's timing and reads from memory rather than the device.

### Sengled

Sengled bulbs refuse the Zigbee timer command, and miss it silently when it is sent to a group (tested on the
E11-G13; Sengled's other bulbs don't list the command either,
[research](../zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md)). So turn on with timer isn't built for
them yet: with a brightness or color temperature, or in a group, the bulb would turn on and stay on. Their other
features aren't built either, as the E11-G13 departs from the standard commands (written while off, it jumps to full
brightness: [Flash-free turn-on](#flash-free-turn-on)) and nothing predicts which it takes. DeviceSide refuses them,
even with Labs on.

### Sonoff SWV

Sonoff's SWV water valve reads the Zigbee timer in seconds rather than tenths, so it would stay open about ten times
longer than asked ([research](../zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md)). Turn on with timer isn't
built for it yet, and DeviceSide refuses it, even with Labs on. The light features
don't apply to a valve.

### IKEA

IKEA's TRÅDFRI lights (manufacturer `IKEA of Sweden`). Most run the Zigbee timer, by what they report when paired and
by users' reports ([research](../zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md), §3), so turn on with
timer is in Labs on them: it runs with Labs on
([Labs](../../device-compatibility.md#levels-of-proof)). Two GU10 white spectrum bulbs, LED2005R5 and
LED2106R3, are reported to turn on with it and never turn off
([Z2M #29158](https://github.com/Koenkk/zigbee2mqtt/issues/29158)), so DeviceSide refuses them there, even with
Labs on. IKEA's outlets get no turn on with timer, as no plug has passed
([Zigbee plugs and switches](../../integrations.md#zigbee-plugs-and-switches)). Smooth dimming and stop are in
Labs, as for other brands (below); the other features aren't built yet.

On IKEA lights, lower brightness to off may stop at the lowest level instead of turning the light off
([evidence](../hue/internals.md#device-classes)).

### Other brands

Lights of every other brand, such as Innr, Ledvance or Sonoff, and their plugs and switches. A Zigbee 3.0 certified
dimmable light must take the standard dimming and stop commands ([internals](../../internals.md#shared)), which they
get exactly as a Hue bulb does, so smooth dimming and stop are in Labs on them: they run with Labs on
([Labs](../../device-compatibility.md#levels-of-proof)). Raising brightness from off sets them to
their lowest level first, where a Hue bulb gets Hue's own command. Their other features aren't built yet: nothing
predicts how other brands take color moves, reads and writes, and on turn on with timer some lights turn on and never
off, and most plugs ignore the timer. If you try dimming, please report it whether it works or not: Integrations >
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
