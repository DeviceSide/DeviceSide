# Matter

What DeviceSide's features do on Matter, their limits, and what DeviceSide changes in your setup. What applies
to every integration is in [integrations.md](../../integrations.md); which devices each feature is proven on is
on the [device compatibility page](../../device-compatibility.md); how the calls work, and what was measured, is
in [internals.md](internals.md).

Plugs and lights on the core `matter` integration whose endpoint has the On/Off cluster's Lighting feature, which
Matter's timer needs; one without it is refused (`no_lt_feature`). A light can also be dimmed and faded
([below](#smooth-dimming)) and set without turning on ([below](#flash-free-turn-on)); one with no brightness control on
that endpoint is refused these (`not_dimmable`).

## Turn on with timer

The timer is read back from the device, so the result is `confirmed` only when it reports both a running timer
(`OnTime`) and that it is on, otherwise `sent`. `turn_off` cancels the timer; a plain `turn_on` doesn't. A second timer
while one runs keeps the longer of the two, so a shorter one is `sent`, not `confirmed`
([tested](internals.md#tested-behavior)). By the spec, a device turned off mid-timer ignores a new timer for
the next 0.1 s and stays off (`sent`). If the device restarts while a timer runs, after a power cut say, it can come
back on with no timer ([internals](internals.md#what-decides-the-call)).

## Smooth dimming

`raise_brightness` and `lower_brightness` read the light's level live, mid-fade included, then send one fade the light
runs itself; `stop` halts it and reads where it halted. A full-range `sweep_time` runs 0.1 s to about 109 minutes; one
outside that is clamped (`clamped_to`).

- **Soft off.** About 1 s after a fade to 0 % has run, the light's old level is put back while it stays off, so the
  next plain on comes back there. A brightness move, a `stop` or a light call from Home Assistant before then cancels
  that, and a `stop` during the fade leaves the light on at the level it halted at. A light turned on elsewhere in the
  meantime keeps its level. A restart of Home Assistant before the restore loses it, and the light comes back at its
  lowest level.
- **`stop`** reads the light twice, 0.2 s apart: `confirmed` when it held still, `sent` (`still_fading`) when it
  kept moving. A light that is off gets nothing (`unchanged`, `off`).

## Smooth color changes

- **Saturation** fades as brightness does, on a light that is on. It doesn't turn on a light that is off
  (`unchanged`, `off`).
- **Hue moves** cycle the color wheel until `stop`, with a `sweep_time` of 1 to 65535 s, or 1 to 254 s on a light
  without enhanced hue; one outside that is clamped (`clamped_to`). A light that is off is `unchanged` (`off`).
- A light without hue and saturation (its Color Control lacks the HS feature) keeps its color: saturation and hue
  moves leave it `unchanged` (`fields_dropped`).
- `stop` halts a color move too, and on a light with hue and saturation its read-back covers them.

## Flash-free turn-on

`set_attributes` sets brightness, color temperature and color without turning the light on: each command tells the
light to apply it even while off (the spec's ExecuteIfOff), so a light that is off stores the values and stays off, and
the next plain on comes up with them. Research admitted it on [certified lights](#certified-devices) and
[multi-endpoint ones](#multi-endpoint-devices), not a run; bridged and uncertified lights aren't built yet
([research](research/2026-11-24-level-color.md)).

- **Read back.** The result is `confirmed` only when the light reads back what was sent; otherwise it is `sent`
  (`attributes_not_reported`, or `readback_failed` when the read fails). A light that ignores the command while off still answers that it took it, so `sent`
  is the result to check ([internals](internals.md#set_attributes)).
- **On Level.** A light whose On Level setting holds a value comes on at that level, not at the brightness set while
  off: that is the spec. DeviceSide never changes On Level, as it is your device's setting, so a brightness set on such
  a light that is off reports `sent` (`on_level_set`). Clear the setting for the light to come on at the stored level.
- **Some lights ignore the stored level.** An IKEA KAJPLATS was reported taking the brightness while off but coming on
  at its old one ([internals](internals.md#set_attributes)).
- **`min_brightness` and `max_brightness`** read the light's level live, so they work while it is off; a light already
  within them is `unchanged`.

## Get attributes

`get_attributes` reports a timer only when the device reports both a running timer and that it is on.

## Device classes

On Matter the device answers DeviceSide's call itself, so a test on one product proves nothing about another
([internals](internals.md#what-decides-the-call)). DeviceSide tells them apart by what the device reports when it
pairs: its vendor and product IDs, and whether it is a bridge. A product a run has tried, such as the WiZ Smart Plug,
is a class of its own.

### Certified devices

A device certified by the Connectivity Standards Alliance, with one on/off part, has passed a test of the timer reads
that get attributes makes, so get attributes inherits that test. The certification test sends the timer command
with other settings than DeviceSide's, so it says nothing about turn on with timer.
DeviceSide counts a device as certified by its vendor ID, which an uncertified product from a registered vendor also
carries: that is the case this can't catch. Like every Matter device here, it needs the On/Off cluster's Lighting
feature.

### Lights

A Matter light takes the same `OnWithTimedOff` command and timer reads as a plug, so it falls in the class its
vendor and product IDs give it, as a plug does, and inherits that class's features. Its endpoint needs the Lighting
feature, as [above](#matter). Smooth dimming, smooth color changes and set without turning on are admitted by
research, not a run, and no Matter light is on the rig yet: certification tests the fade, move and stop commands on a
light that is on, and the set-while-off command on a light that is off for brightness and xy color, since Matter 1.0
([research](research/2026-11-24-level-color.md), Q1). A device report is how they move up.

### Multi-endpoint devices

A certified device with more than one on/off part, such as a power strip, a two-gang switch or a light with several
lit parts. Certification tests the timer on one of its parts, and DeviceSide can't tell which, so turn on with timer
and get attributes aren't built for them yet, even with Labs on. The light features (smooth dimming, smooth color
changes, set without turning on) are admitted, as on a single-part device: they earn no certification credit from
the timer test anyway, and each part has its own brightness and color server, so the number of parts doesn't change
how one part takes the call.

### Matter bridges

Devices a bridge exposes on Matter, such as Zigbee lights behind a hub. The bridge answers the timer, either by
running it itself or by passing it on to the device, so how it behaves depends on the bridge. None of the features
is built for them yet, even with Labs on. A bridge's own light or plug counts here too.

### Uncertified devices

A device that reports a test vendor ID: development kits, apps that share other devices on Matter (Matterbridge-style
apps, bridge or not), and the odd uncertified product. Nothing has tested its timer or its light commands, so none
of the features is built for them yet, even with Labs on. A device that hasn't reported its vendor ID yet is refused turn on
with timer, as unknown, until it does. An app built on matter.js forgets a running timer when it restarts, and the device stays on
([internals](internals.md#upstream-defects)).
