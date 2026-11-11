# Shelly

What DeviceSide's features do on Shelly, their limits, and what DeviceSide changes in your setup. What applies
to every integration is in [integrations.md](../../integrations.md); which devices each feature is proven on is
on the [device compatibility page](../../device-compatibility.md); how the calls work, and what was measured, is
in [internals.md](internals.md).

Gen2 and later (Plus, Pro, Gen3, Gen4): relays, whether Home Assistant shows them as a switch or a light, RGBCCT
bulbs, and the other Shelly lights (dimmers, CCT, RGB and RGBW devices: the Light, CCT, RGB and RGBW components),
which take the same calls. CCT, RGB and RGBW devices take brightness but not color or color temperature yet: either
is left out of the call, which reports `fields_dropped`. Gen1 isn't built: it has Shelly's older
[HTTP API](https://shelly-api-docs.shelly.cloud/gen1/), not the [Gen2+ RPC calls](https://shelly-api-docs.shelly.cloud/gen2/)
the adapters send, so it is refused (`gen1_unsupported`).

## Turn on with timer

The device runs the timer and confirms it. A transition is at least 0.5 s. A color temperature outside the bulb's
range is clamped. `hs_color` and `xy_color` are sent as the RGB color Home Assistant would send for them, whatever
mode the bulb is in.

## Turn off with timer

The device runs the timer and confirms it, as for turn on.

**Cancelling either timer.** Any on or off cancels the timer, whoever sends it: Home Assistant, the Shelly app or
another integration. A wall switch wired to the device's input is untested and may depend on the input mode.

## Auto-off/on

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

## Smooth dimming

On a Multicolor Bulb (RGBCCT), `raise_brightness` and `lower_brightness` read the bulb's own level, mid-fade included,
then send one fade the bulb runs itself; `stop` halts it and reads back where it halted. A fade is at least 0.5 s.
Lowering to 0 % is the bulb's own soft off: it fades out, turns off, and comes back on at its old level; a `stop`
during it leaves the bulb on. Raising a bulb that is off fades it in from the bottom. Other Shelly lights take the same
calls on their own component.

## Flash-free turn-on

On a Multicolor Bulb (RGBCCT) `set_attributes` sends one `RGBCCT.Set` without `on`, so a bulb that is off stores the
values and stays off, and the next plain on comes up with them. The device answers a `Set` with nothing, so DeviceSide
reads the status back: brightness, color temperature and mode must read as written, or the call fails (`not_stored`).
A color is not compared, only the mode it switches to. `min_brightness` and `max_brightness` clamp the brightness the
bulb has stored, read first, so they work while it is off; a bulb already within them is `unchanged`. Other Shelly
lights don't take `set_attributes` yet.

## Get attributes

On lights other than the Multicolor Bulb, `get_attributes` reports the timer and auto-off/on but not brightness or
color.

## Tested devices

### Shelly 1 Mini Gen3

A relay (the `Switch` component), rig-tested with turn on and turn off with timer, auto-off and auto-on, and get
attributes. Home Assistant may show a relay as a switch or as a light; both take the same calls.

### Shelly 1 Mini Gen4

A relay, rig-tested with turn on with timer. It has the same `Switch` component as the
[Gen3](#shelly-1-mini-gen3), which carries the other relay tests.

### Shelly Multicolor Bulb Gen3

A color bulb (the `RGBCCT` component), rig-tested with turn on and turn off with timer, smooth dimming, set without
turning on, and get attributes. Auto-off and auto-on are Documented on it: see
[Shelly multicolor bulbs](#shelly-multicolor-bulbs).

## Should work

### Shelly dimmers

Gen2+ dimmers (the `Light` component) take the relay's and bulb's timer, auto-off and auto-on calls
([Shelly Light API](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Light/)). On them, get
attributes reports the timer, auto-off and auto-on, but not brightness. Smooth dimming is Experimental: see
[Help us test](#help-us-test).

### Shelly LED controllers

CCT, RGB and RGBW controllers (the `CCT`, `RGB` and `RGBW` components) take the same calls as the dimmers, brightness
but not color or color temperature yet ([above](#shelly)). A record proves one component, so each needs its own.

### Shelly multicolor bulbs

Auto-off and auto-on on an `RGBCCT` bulb, such as the [Multicolor Bulb Gen3](#shelly-multicolor-bulb-gen3): the same
calls the relay test passes, confirmed by reading the stored setting back.

## Help us test

### Shelly dimmers and LED controllers: smooth dimming

On a Gen2+ dimmer, CCT, RGB or RGBW device, a test shows that `DimStop` halts a fade where it is, without a jump, and
that dimming to 0% is a soft off. The rig proved this on the multicolor bulb only, Shelly doesn't document it for any
component, and one user reports a Gen3 Dimmer jumping to the end on `DimStop`
([Shelly forum](https://community.shelly.cloud/topic/2959-rd-please-fix-the-internal-dimming-speeds/)). One report
per component.
