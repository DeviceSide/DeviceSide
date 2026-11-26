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

The timer is read back from the device:

| Case | Result |
|---|---|
| The device reports a running timer (`OnTime`) and that it is on | `confirmed` |
| Any other read | `sent` |
| A second timer while one runs | The longer of the two runs; a shorter second one is `sent` ([tested](internals.md#tested-behavior)) |
| A new timer within 0.1 s of the device being turned off mid-timer | Ignored, by the spec: the device stays off (`sent`) |
| The device restarts mid-timer, after a power cut say | It can come back on with no timer ([internals](internals.md#what-decides-the-call)) |

`turn_off` cancels the timer; a plain `turn_on` doesn't.

## Smooth dimming

`raise_brightness` and `lower_brightness` read the light's level live, mid-fade included, then send one fade the light
runs itself; `stop` halts it and reads where it halted. A full-range `sweep_time` runs 0.1 s to about 109 minutes; one
outside that is clamped (`clamped_to`).

- **Soft off.** Once a fade to 0 % has run, the light's old level is put back while it stays off, so the next plain on
  comes back there. A brightness move, a `stop`, a brightness `set_attributes` or a Home Assistant light call first
  cancels that; a light turned on elsewhere keeps its level. A `stop` mid-fade leaves the light on where it halted. A
  Home Assistant restart before the restore leaves the light at its lowest level.
- **`stop`** reads where the light halted: `confirmed` when it held still, `sent` (`still_fading`) when it kept
  moving. A slow move, such as a long hue cycle, can read `confirmed` while it still moves
  ([internals](internals.md#stop)). A light that is off is `unchanged` (`off`).

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
  (`attributes_not_reported`, or `readback_failed` when the read fails). A light that ignores the command while off
  still answers that it took it, so `sent` is the result to check ([internals](internals.md#set_attributes)).
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

A device certified by the Connectivity Standards Alliance, with one on/off part, has passed certification's test of
the timer reads get attributes makes, so get attributes inherits it. The test sends the timer command with other
settings than DeviceSide's, so turn on with timer inherits nothing ([internals](internals.md#what-decides-the-call)).
DeviceSide counts a device as certified by its vendor ID, which an uncertified product from a registered vendor also
carries: that is the case this can't catch.

### Lights

A Matter light takes a plug's `OnWithTimedOff` command and timer reads, so it is classed by its vendor and product
IDs, as a plug is. Its light features are admitted by research, not a run: certification tests the fade, move and stop
commands on a light that is on, and, since Matter 1.0, the set-while-off command for brightness and xy color
([research](research/2026-11-24-level-color.md), Q1). No Matter light has had a run yet: a
[device report](../../../CONTRIBUTING.md#how-to-help) moves them up.

### Multi-endpoint devices

A certified device with more than one on/off part: a power strip, a two-gang switch, a light with several lit parts.
Certification tests the timer on one part, and DeviceSide can't tell which, so turn on with timer and get attributes
aren't built for them yet, even with Labs on. The light features are admitted as on a single-part device: they take no
credit from the timer test, and each part has its own brightness and color server.

### Matter bridges

Devices a bridge exposes on Matter, such as Zigbee lights behind a hub. The bridge answers the timer, either by
running it itself or by passing it on to the device, so how it behaves depends on the bridge. None of the features
is built for them yet, even with Labs on. A bridge's own light or plug counts here too.

### Uncertified devices

A device that reports a test vendor ID: development kits, apps that share other devices on Matter (Matterbridge-style
apps, bridge or not), and the odd uncertified product. Nothing has tested its timer or its light commands, so no
feature is built for them yet, even with Labs on. Until a device reports its vendor ID, turn on with timer refuses it
as unknown. An app built on matter.js forgets a running timer when it restarts, leaving the device on
([internals](internals.md#upstream-defects)).
