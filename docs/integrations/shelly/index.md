# Shelly

What DeviceSide's features do on Shelly, their limits, and what DeviceSide changes in your setup. What applies
to every integration is in [integrations.md](../../integrations.md); which devices each feature is proven on is
on the [device compatibility page](../../device-compatibility.md); how the calls work, and what was measured, is
in [internals.md](internals.md).

Gen2 and later (Plus, Pro, Gen3, Gen4): relays, whether Home Assistant shows them as a switch or a light, Multicolor
(RGBCCT) bulbs, dimmers, and CCT, RGB and RGBW LED controllers, all on the same calls; the LED controllers can also be
sent color or color temperature ([below](#device-classes)). Gen1 isn't built: it has Shelly's older
[HTTP API](https://shelly-api-docs.shelly.cloud/gen1/), not the
[Gen2+ RPC calls](https://shelly-api-docs.shelly.cloud/gen2/) the adapters send, so it is refused
(`gen1_unsupported`).

## Device classes

DeviceSide tells Shelly devices apart by the component behind each output (`Switch`, `Light`, `CCT`, `RGB`, `RGBW`
or `RGBCCT`), which Home Assistant's unique ID for it names ([internals](internals.md#addressing)). Each component is a
class of its own, as a run on one proves nothing about another.

### Relays and plugs

The `Switch` component, whether Home Assistant shows the relay as a switch or as a light: both take the same calls.
Gen4 relays, such as the Shelly 1 Mini Gen4, have the same `Switch` component as Gen3
([Shelly Switch API](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Switch)), so a run on either
counts for both.

### Multicolor bulbs

The `RGBCCT` component, as in the Shelly Multicolor Bulb Gen3: brightness, color temperature and color in one light.
Smooth dimming and stop rely on how it halts a fade: `DimStop` stops it where it is, without a jump, and dimming to
0 % is the bulb's soft off ([internals](internals.md#stop)).

### Dimmers

Gen2+ dimmers (the `Light` component). Shelly documents the `Light` component's timer, auto-off/on and status calls
as it does the relay's and the bulb's ([Shelly Light API](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Light/)),
so a dimmer takes the same calls: get attributes reports its timer, auto-off, auto-on and brightness.

Smooth dimming and stop rely on `DimStop` halting a fade without a jump, which only the multicolor bulb has shown:
Shelly documents it for no component, and a Gen3 Dimmer is reported jumping to the end
([Shelly forum](https://community.shelly.cloud/topic/2959-rd-please-fix-the-internal-dimming-speeds/)). If you try it,
please report whether stop halts the fade: Integrations >
[DeviceSide](https://my.home-assistant.io/redirect/integration/?domain=deviceside) > Configure > Report a device test
result or bug (the form for any report on this page). One report per component settles it.

### LED controllers

CCT, RGB and RGBW controllers (the `CCT`, `RGB` and `RGBW` components). Shelly documents their calls as the dimmer's,
field for field ([research](research/2026-11-17-set-on-sibling-components.md)), so they take the dimmer's calls with
brightness, and their color as core's Shelly light sends it, by Home Assistant's own conversions from any other color
or a color temperature:

| Controller | Color sent |
|---|---|
| CCT | Its color temperature |
| RGB | `rgb` |
| RGBW | `rgb` and `white` |

Nobody has yet run these calls on a device. If you have one, please report whether the color or color temperature
lands, as for dimmers. Smooth dimming and stop are as on [dimmers](#dimmers).

## Turn on with timer

The device runs the timer and confirms it. A transition is at least 0.5 s. A color temperature outside the bulb's
range is clamped. `hs_color` and `xy_color` are sent as the RGB color Home Assistant would send for them, whatever
mode the bulb is in. On an RGB or RGBW controller a color temperature is sent as that color instead,
unclamped, as core does.

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
then send one fade of at least 0.5 s that the bulb runs itself; `stop` halts it and reads back where it halted.
Lowering to 0 % is the bulb's soft off: it fades out, turns off and comes back on at its old level; a `stop` during it
leaves the bulb on. Raising a bulb that is off fades it in from the bottom.

Other dimmable Shelly lights take the same calls on their own component; whether `stop` halts them without a jump is
open ([dimmers](#dimmers)).

## Flash-free turn-on

`set_attributes` sends one `<Component>.Set` without `on`, which Shelly documents identically for every light
component, so a light that is off stores the values and stays off, and the next plain on comes up with them. The
device answers a `Set` with nothing, so DeviceSide reads the status back, and the call fails (`not_stored`) unless
what it checks reads as written:

| Light | Sent | Read back |
|---|---|---|
| Multicolor Bulb (RGBCCT) | Brightness, color temperature, color | Brightness, color temperature and mode; not the color |
| Dimmer | Brightness | Brightness |
| CCT controller | Brightness, color temperature | Brightness, color temperature |
| RGB controller | Brightness, color ([LED controllers](#led-controllers)) | Brightness, `rgb` |
| RGBW controller | Brightness, color | Brightness, `rgb` and `white` |

`min_brightness` and `max_brightness` clamp the brightness the light has stored, read first, so they work while it is
off; a light already within them is `unchanged`.

## Get attributes

On every Shelly light, `get_attributes` reports the timer, auto-off/on, brightness, and the color its component
keeps: color temperature on a CCT light, color on an RGB or RGBW light (with its white mixed in, as Home Assistant
shows it). While the device's clock hasn't synced (after a reboot, or with no time server), its row has no timer, even
while one runs ([internals](internals.md#get_attributes)).
