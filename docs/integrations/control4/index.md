# Control4

What DeviceSide's features do on Control4, their limits, and what DeviceSide changes in your setup. What applies
to every integration is in [integrations.md](../../integrations.md); which devices each feature is proven on is
on the [device compatibility page](../../device-compatibility.md); how the calls work, and what was measured, is
in [internals.md](internals.md).

Lights on the core `control4` integration: dimmers and Control4 light groups alike. DeviceSide uses that
integration's own connection to the controller, so it needs no sign-in of its own. A light it can't tie to a Control4
item is refused (`not_addressable`). Every action here is Experimental ([try it](#try-it-experimental-features)).

## Smooth dimming

The light runs the ramp itself, and `stop` reads back where it halted.

- A ramp takes at most about 65 s, so a longer `sweep_time` is clamped.
- Changing direction, or the limit, mid-ramp with no `stop` between costs that move up to a quarter of a second: the
  light is halted first, then moved from where it stopped.
- Calling the same raise or lower again while its ramp runs, as a remote that repeats while held does, sends nothing.
  The ramp keeps its speed.

## Flash-free turn-on

`set_attributes` sets `color_temp_kelvin` and nothing else. Home Assistant shows a Control4 light as brightness-only,
so this is the only way to set its color temperature, and the field is missing from the action's form: send it in
YAML.

- The kelvin is clamped to the light's own range, and the result carries `clamped_to`.
- A light with no color temperature is left `unchanged` (`fields_dropped`), so the rest of a room still changes.
- A light that is off stays off and comes on at the new value. It reports `sent` (`stored_while_off`), not
  `confirmed`.
- The color temperature lasts until Control4 next applies the light's On Color preset.
- `brightness`, `min_brightness` and `max_brightness` are refused (`fields_not_tested`): Home Assistant's own turn-on
  always sends a level, so one stored while off would be lost. Colors are dropped: no full-color Control4 light has
  been tested.

## Get attributes

`get_attributes` reads `brightness` and `color_temp_kelvin` from Control4 itself. Home Assistant shows no color
temperature for these lights.

- Brightness is up to a second old mid-ramp. Home Assistant's own state can be several seconds old.
- Control4 keeps color temperature in tens of kelvin, so a light set to 2203 reads 2200.
- A light that is off reports no brightness.

## Try it: Experimental features

### Control4 lights

On a Control4 dimmer or light group, a test shows that a raise or lower ramps smoothly from where the light is, and
that `stop` halts it where it is, whichever way it runs. One contributor saw this on a light group of [Hue
downlights](#hue-white-ambiance-56-retrofit-downlight) on Control4 OS 4.3
([measurements](internals.md#tested-behavior)). Control4 documents none of it, and no other driver has been tried. One
report per driver.

### Hue White Ambiance 5/6" Retrofit Downlight

`LTD010` (Philips 5996411U5), joined to Control4 over Zigbee on its "Zigbee 3 Light" driver, three of them in a
Control4 light group. Flagged experimental like every Control4 light, so it isn't listed under Works.
