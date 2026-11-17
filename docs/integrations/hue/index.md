# Hue

What DeviceSide's features do on Hue, their limits, and what DeviceSide changes in your setup. What applies
to every integration is in [integrations.md](../../integrations.md); which devices each feature is proven on is
on the [device compatibility page](../../device-compatibility.md); how the calls work, and what was measured, is
in [internals.md](internals.md).

A Hue Bridge v2 or Bridge Pro on the core `hue` integration. Rooms and zones are targets in their own right.

**The v1 (round) bridge isn't supported, and won't be.** Its API can't change a light while it's off, so neither
flash-free turn-on can work, and it has no push updates, so Home Assistant learns of a change only when it next polls,
up to 5 s later. Signify ended its support in 2020 ([research](research/2026-11-14-v1-api.md)). Every action refuses
its lights and scenes (`integration_not_supported`), saying why.

**No `turn_on_for` or `turn_off_for`**: see [what can't be done](../../integrations.md#what-cant-be-done-and-why).

**No auto-off or auto-on.** Neither a light nor a room stores one in the CLIP v2 API, and v2 has no programmable rule
engine to build one from. The v1 rule engine could, but Signify advises against it as "it will not be available long
term" ([Hue API V2](https://developers.meethue.com/develop/hue-api-v2/)). A timer kept by Home Assistant wouldn't
survive it going offline, which is the point of auto-off.

## Device classes

The bridge sends each light its own commands, and lights of other brands can answer them differently, so a test on a
Hue light proves nothing about another brand's. DeviceSide tells them apart by the manufacturer the bridge reports for
each light. Every feature says how well it is proven for each ([levels of
proof](../../device-compatibility.md#levels-of-proof)).

- **Hue lights** (manufacturer `Signify Netherlands B.V.`) are tested: every feature on this page has passed on them.
- A **scene** is proven as far as its lights: one with a light of another brand counts as that brand's.
- A **room or zone** is proven as far as its weakest light. With Experimental features off, one with a light of
  another brand falls back to its lights, each on its own, so the Hue lights still run; with them on, it runs as one
  room. A light the bridge has in the room but Home Assistant has no light entity for still counts, as the room's
  command reaches it.

### Other brands

Lights of other brands paired to the bridge (IKEA, Innr, LEDVANCE and the rest, Friends of Hue ones included) are
untested, so every feature runs on them only with Experimental features on. The Hue lights' tests don't prove them,
as other brands are known to answer the same Zigbee commands differently: some fade only one of brightness and color
at a time, some come on when written while off, and some don't report color temperature as Hue lights do
([internals](internals.md#device-classes)). A test on one adds a class for its brand.

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

There are no hue moves ([why](../../integrations.md#what-cant-be-done-and-why)). Saturation keeps each light's current
hue, so a white deepens toward its own tint (a warm white toward amber). 100 % saturation is the edge of Home
Assistant's color space, a little short of the deepest colors the Hue app can reach.

## Flash-free turn-on

- **`set_attributes`** writes a room light by light, as a room write misses lights that are off.
- **`set_scene`** reads the scene live, so edits in the Hue app apply. A light the scene turns off is turned off.
  Dynamic scenes set their first frame; gradients and effects are skipped. Smart (All-Day) scenes
  [don't work](#hue-smart-scenes). Lights are written one after another: an 8-light scene takes under a second.

## Get attributes

`get_attributes` reads the bridge's live event stream, so it sends nothing to the bridge. During a fade it returns
DeviceSide's estimate of where the fade has reached. A room averages the lights that are on, or all of them
when every light is off, as the Hue integration shows it.

## Sharp edges

- **A room turned off with a transition keeps its level.** Turning the room on without a brightness brings every
  light back at that level, overriding one set on its own while off. Set the room instead.
- **Lights without an entity in Home Assistant** are skipped by `set_attributes` and `get_attributes` on their
  room, though `set_scene` writes them. A disabled entity still counts.

## No known method

### Hue smart scenes

A smart (All-Day) scene switches between scenes by time of day, so it has no fixed settings to write. Set scene
refuses it (`no_known_method`), saying why ([flash-free turn-on](#flash-free-turn-on)).
