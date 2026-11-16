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
- A **group** is proven as far as its weakest light. One with a light a feature refuses, or, with Experimental
  features off, one of another brand, falls back to its lights, each on its own; with them on, it runs as one group.
  Turn on with timer sends a group one command only when its lights are every device in it, so a plug in the group
  with no light (a plug ZHA shows as a switch, say), or a light it refused, never gets the group's timer: the lights
  get one command each instead, a fraction of a second apart.
- A device whose manufacturer or model ZHA couldn't read when it paired (ZHA shows `unk_manufacturer` or
  `unk_model`) can't be placed, so turn on with timer refuses it (`class_unknown`), even with Experimental features
  on, as it could be a Tuya datapoint device. Reconfigure it from its ZHA device page, or pair it again.

### Tuya

Tuya plugs, switches and lights, including those sold under other brands (Lidl, Moes, BlitzWolf and more). Their
timer isn't the standard Zigbee one, so DeviceSide refuses turn on with timer on every Tuya device, even with
Experimental features on; why, and what else runs, is in each kind's section below.

#### Tuya plugs and switches

Tuya's plugs, switches and relays on the standard Zigbee on/off commands (models `TS011F`, `TS0001` to `TS0004`,
`TS0011` and `TS0726`), including the [Tuya TS011F](../../device-compatibility.md#tuya-ts011f). Turn on with timer
isn't built yet, as above.

#### Reported Tuya plugs

A TS011F reported to fail Tuya's own timer call: `_TZ3000_gjnozsaz`, whose time left jumps back at random, so it may
not turn off when asked ([Z2M #30493](https://github.com/Koenkk/zigbee2mqtt/issues/30493)). Turn on with timer isn't
built for it yet, as another of Tuya's calls may serve it, and DeviceSide refuses it, even with Experimental
features on.

#### Other Tuya devices

Tuya's other devices on the standard Zigbee commands: bulbs (such as `TS0505B`), dimmers and other white labels.
Turn on with timer isn't built yet, as above.

#### Tuya datapoint devices

Tuya devices that speak only Tuya's own protocol (model `TS0601`, and others ZHA handles the same way). ZHA turns
DeviceSide's commands into Tuya's own: it refuses the timer, so with a brightness or color temperature the light
would turn on and stay on, and it drops a fade's timing and reads from memory rather than the device. So none of
DeviceSide's features are built for them yet, and turn on with timer is refused even with Experimental features
on.

### Sengled

Sengled bulbs refuse the Zigbee timer command, and miss it silently when it is sent to a group (tested on the
E11-G13; Sengled's other bulbs don't list the command either,
[research](../zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md)). So turn on with timer isn't built for
them yet: with a brightness or color temperature, or in a group, the bulb would turn on and stay on, and DeviceSide
refuses it, even with Experimental features on. A Sengled E11-G13 written while off jumps to full brightness, so set
attributes refuses it ([Flash-free turn-on](#flash-free-turn-on)). Their other features are untested, so they run
only with Experimental features on.

### Sonoff SWV

Sonoff's SWV water valve reads the Zigbee timer in seconds rather than tenths, so it would stay open about ten times
longer than asked ([research](../zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md)). Turn on with timer isn't
built for it yet, and DeviceSide refuses it, even with Experimental features on. Get attributes is untested, so it
runs only with Experimental features on; the light features don't apply to a valve.

### Other brands

Lights, plugs and switches of every other brand, such as IKEA, Innr, Ledvance or Sonoff. Dimming down smoothly (lower
brightness) and stop send them exactly the standard Zigbee commands a Hue bulb gets, which no known brand handles
differently, so they should work. Their other features are untested, so they run only with Experimental features on
([try it](../../device-compatibility.md#try-it-experimental-features)); raising brightness from off turns a Hue bulb
on by Hue's own command, which other brands don't get. So the card lists smooth dimming for other brands twice:
lowering should work, and raising runs only with Experimental features on. Brands differ most on turn on with timer: some turn on and
never off, or ignore the timer. If you try one, please report it whether it works or not: Integrations >
[DeviceSide](https://my.home-assistant.io/redirect/integration/?domain=deviceside) > Configure > Report a device test
result or bug. A brand with a passing report gets its own entry here.

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
  E11-G13 is refused (`execute_if_off_unsupported`): written while off, it jumps to full brightness. For the same
  reason it doesn't fade in from the bottom when raised from off, and comes back at its lowest level after a soft
  off.
- **`min_brightness` and `max_brightness`** read the light's level live. Within about 0.5 s of a brightness change
  the light is still fading, and the limit can replace the fade's end.

## Get attributes

`get_attributes` reads each light live, not from ZHA's cache, which goes stale after a remote or a command Home
Assistant didn't send. A ZHA group returns one entry per light.
