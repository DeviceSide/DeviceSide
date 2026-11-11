# ZHA

What DeviceSide's features do on ZHA, their limits, and what DeviceSide changes in your setup. What applies
to every integration is in [integrations.md](../../integrations.md); which devices each feature is proven on is
on the [device compatibility page](../../device-compatibility.md); how the calls work, and what was measured, is
in [internals.md](internals.md).

Lights on the core `zha` integration.

**Admin only.** DeviceSide uses ZHA's admin-only actions, so a call made by a non-admin user fails
(`admin_required`). Automations run without a user and pass.

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
- **Saturation on a group** sends every light that is on one color, at the hue of the first of them. A group whose
  lights sit at different hues ends at one hue.

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
