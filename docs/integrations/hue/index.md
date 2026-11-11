# Hue

What DeviceSide's features do on Hue, their limits, and what DeviceSide changes in your setup. What applies
to every integration is in [integrations.md](../../integrations.md); which devices each feature is proven on is
on the [device compatibility page](../../device-compatibility.md); how the calls work, and what was measured, is
in [internals.md](internals.md).

A Hue Bridge v2 or Bridge Pro on the core `hue` integration. The v1 bridge isn't built: it lacks the v2 API and
event stream DeviceSide uses, and Signify no longer supports it
([Home Assistant](https://www.home-assistant.io/integrations/hue/#support-for-legacy-v1-hue-bridges)), so it is
refused (`bridge_v1`). Rooms and zones are targets in their own right.

**No `turn_on_for` or `turn_off_for`**: see [what can't be done](../../integrations.md#what-cant-be-done-and-why).

**No auto-off or auto-on.** Neither a light nor a room stores one in the CLIP v2 API, and v2 has no programmable rule engine to
build one from. The v1 rule engine could, but Signify advises against it as "it will not be available long term"
([Hue API V2](https://developers.meethue.com/develop/hue-api-v2/)). A timer kept by Home Assistant wouldn't survive
it going offline, which is the point of auto-off.

## Smooth dimming

The bridge runs the fade. A room fades as one, and its lights converge on the end point.

**Fix Hue Bridge brightness reports while dimming** (on by default). When a fade starts, the bridge reports 0 % or
100 % brightness, and only snaps back to the light's actual level about 10 s later. With this option on, Home
Assistant shows the brightness the fade started at while it runs, where a `stop` halted it, and the end once the fade
has run, so a dashboard slider holds still, then jumps. Color is always shown as the bridge reports it. A change from
the Hue app, a dimmer switch or a bridge scene shows at once, except a brightness change or a turn on within 15 s of a
fade. A restart or bridge reconnect mid-fade shows what the bridge reports. Turn the option off in DeviceSide's
options to see the bridge's own reports.

## Smooth color changes

There are no hue moves ([why](../../integrations.md#what-cant-be-done-and-why)). Saturation keeps each light's current hue, so a white
deepens toward its own tint (a warm white toward amber). 100 % saturation is the edge of Home Assistant's color
space, a little short of the deepest colors the Hue app can reach.

## Flash-free turn-on

- **`set_attributes`** writes a room light by light, as a room write misses lights that are off.
- **`set_scene`** reads the scene live, so edits in the Hue app apply. A light the scene turns off is turned off.
  Dynamic scenes set their first frame; gradients and effects are skipped. Smart (All-Day) scenes are refused
  (`smart_scene`). Lights are written one after another: an 8-light scene takes under a second.

## Get attributes

`get_attributes` reads the bridge's live event stream, so it sends nothing to the bridge. During a fade it returns
DeviceSide's estimate of where the fade has reached. A room averages the lights that are on, or all of them
when every light is off, as the Hue integration shows it.

## Sharp edges

- **A room turned off with a transition keeps its level.** Turning the room on without a brightness brings every
  light back at that level, overriding one set on its own while off. Set the room instead.
- **Lights without an entity in Home Assistant** are skipped by `set_attributes` and `get_attributes` on their
  room, though `set_scene` writes them. A disabled entity still counts.

## Doesn't work

### Hue smart scenes

A smart (All-Day) scene switches between scenes by time of day, so it has no fixed settings to write. Set scene
refuses it (`smart_scene`) ([flash-free turn-on](#flash-free-turn-on)).
