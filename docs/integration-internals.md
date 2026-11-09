# Integration internals

How each adapter addresses a target, what it sends and reads back, and what was measured on real hardware. What a
user sees is in [integrations.md](integrations.md) and isn't repeated here; result and detail codes are in the
code. Code comments cite the Tested behavior sections.

## Shared

- **Resolution.** An entity belongs to an integration by its entity registry platform (Z2M: by its device
  identifier, below). A `switch_as_x` light is served as the switch it wraps, keyed on the light's entity ID; one
  wrapping another helper is `not_addressable`.
- **Fades.** Brightness and saturation are one command to the end point (the limit, or the end of the range) with a
  transition of `sweep_time` × the fraction of the range left; the device runs it. A brightness and a saturation
  fade can overlap. Saturation is Home Assistant's `hs_color` saturation, written as the light's current hue at the
  end saturation, so one automation behaves alike everywhere. Each raise, lower and stop is remembered for its
  duration plus a settle time (Zigbee 2 s, Hue 15 s) and its position predicted meanwhile; a light or scene call
  from Home Assistant to the light, its group or `all` drops that at once (`call_resolver`).
- **Writes while off.** `set_attributes` never sends `on`. On Zigbee it sends the Level and Color `MoveTo…`
  commands (never `…WithOnOff`) with the ZCL `ExecuteIfOff` override (options mask and override 1) and a 0.4 s
  transition, Hue's default. Given a color and a color temperature, only the color is sent.
- **Kept levels.** After an off with a transition, Z2M and Home Assistant (for ZHA and Hue) keep the old level and
  resend it on the next plain on, undoing a level written while off. Each `set_attributes` level write also
  replaces that kept level: on Z2M by publishing `{"state": null, "brightness": <level>, "transition": 0.4}`, which
  the off light ignores; on ZHA and Hue on the light entity, and on the group or room entity for an explicit
  `brightness` there.

## Shelly

Through the core integration's RPC connection. The unique ID is `<mac>-<key>`; the key gives the RPC component:
`switch:N` → `Switch` (a `switch`, or a `light` for a relay set to "light"), `light:N`, `cct:N`, `rgb:N`, `rgbw:N`
and `rgbcct:N` → `Light`, `CCT`, `RGB`, `RGBW`, `RGBCCT`. Only `Switch` and `RGBCCT` are in scope. Any other key
(virtual booleans, scripts) has no timer. Gen1 (CoIoT) has no `toggle_after`.

- **Timers.** One `<Component>.Set` with `on` and `toggle_after` (device range: over 0 s to 604800 s, 0.01 s
  resolution). Light fields ride in the same call, translated as the core Shelly light does: brightness to percent,
  `transition` to `transition_duration`, and on `RGBCCT` the mode switched to `cct` or `rgb` to match.
- **Read-back.** `<Component>.GetStatus`; `confirmed` when the output matches and `timer_duration` is present.
- **`get_attributes`.** One `GetStatus`. Time left is `timer_started_at` + `timer_duration` against Home Assistant's
  clock (both SNTP-synced), clamped to 0 to the duration to bound skew. `RGBCCT` adds brightness and the active
  mode's color, the others derived from it. A `<Component>.GetConfig` runs alongside for `auto_off` and `auto_on`;
  if it fails, the row leaves both keys out (unknown) rather than reporting them `null` (disabled).
- **`set_attributes`.** `RGBCCT.Set` with the `light_params` translation and no `on`: the bulb keeps its output and
  stores brightness, `ct`, `rgb` and `mode` (probe, 8 Nov, Multicolor Bulb Gen3). The reply is null, so a
  `GetStatus` follows; `brightness`, `ct` and `mode` must match what was sent (`not_stored`, rejected), `rgb` is not
  compared until a probe has shown the device returns it unrounded. A failed read-back reports `sent`.
  `min_brightness`/`max_brightness` first read `GetStatus` `brightness` (kept while off), clamp it to whole percent,
  and send nothing when it is already within them; an explicit `brightness` wins.
- **`raise_brightness`, `lower_brightness`, `stop`.** `RGBCCT` only (`DIMMING_CAPABILITIES`). A move reads
  `GetStatus` first: the device reports its level exactly mid-fade (rig, 8 Nov), so no transition cache is kept and
  no call resolver is needed. Then one `<Component>.Set {on: true, brightness, transition_duration}` for the distance
  left at the `sweep_time`'s speed, at least 0.5 s (`TRANSITION_LIMITS`, the device's 0.5 to 10800 s); to 0 it is
  `{on: false, transition_duration}`, the device's soft off, which keeps the stored level (`brightness: 0` would
  leave it on at 0%). From off the device fades in from 1%. `stop` sends `<Component>.DimStop {id}` first, which
  halts a `Set`'s fade within ~0.1 s and is a no-op with none running, then `GetStatus`: `confirmed` when on with no
  `transition` object, `sent` (`still_fading`) when one remains, `unchanged` (`off`) when off. Under a second client
  polling the device, round trips reach 0.7 s and the halt lands late; the read-back is still exact.
- **Auto-off and auto-on.** `<Component>.GetConfig` first, and `<Component>.SetConfig` with
  `{"id": N, "config": {...}}` only when the config differs: `auto_off: true` and `auto_off_delay` to set,
  `auto_off: false` alone to clear (likewise `auto_on`). A delay matches to 0.01 s. `SetConfig` emits
  `config_changed`, and core reloads the entry after its 60 s debounce (`shelly/coordinator.py`,
  `ENTRY_RELOAD_COOLDOWN`). Read-back is a second `GetConfig`. The delay's device range is unverified: the timer's
  604800 s ceiling until a rig run reads it.

## Zigbee2MQTT

Only devices Z2M registered through MQTT discovery are found: the device carries the identifier
`("mqtt", "zigbee2mqtt_<address>")`.

- **Devices** use the IEEE address: topic `zigbee2mqtt/<ieee>/set`. Z2M's `resolveEntity` matches the IEEE-keyed
  `devices` map before `friendly_name`, so a rename doesn't break it.
- **Groups** have address `<encoded base topic>_<group ID>`, the base topic as character codes with no separator
  (`1221051039810110150109113116116` for `zigbee2mqtt`; `getEncodedBaseTopic` in Z2M's
  `lib/extension/homeassistant.ts`), and topic `zigbee2mqtt/<group ID>/set`. `resolveEntity` falls back to the
  ID-keyed `groups` map, so a rename doesn't break it either, but a device whose friendly name is that number wins.
  Members come from `zigbee2mqtt/bridge/groups`, features from `zigbee2mqtt/bridge/devices`.
- **Both assume the default base topic.** A group's identifier carries it, so another is refused; a device's
  doesn't, so its publish goes nowhere.

### Options DeviceSide sets

- **Color modes.** The Home Assistant override is set to `xy`, `hs` and, where present, `color_temp`, on lights
  exposing both `color_xy` and `color_hs`, and on groups whose members all qualify. Z2M re-announces at once and
  Home Assistant keeps the entity. Rerun at setup and on every device or group announcement, reading Z2M's settings
  each time. Z2M can't delete an override (`null` strips the key from the announcement instead), so opting out
  writes back the modes Z2M announces by itself, wherever the value is still DeviceSide's. Z2M declined to
  announce both by default, as some lights handle mixed modes badly
  ([#33025](https://github.com/Koenkk/zigbee2mqtt/issues/33025)).
- **`hue_native_control`** makes Z2M send on, brightness, color and color temperature as one Philips command
  rather than ZCL ones. Each action that needs it one way declares it (`NEED` in `native_control.py`): on for a
  `turn_on_for` with a color or color temperature (a Hue bulb, manufacturer `Philips`, lights in the new color and
  keeps the timer) and for a saturation fade (it fades in xy and holds its hue); off for a brightness fade (native,
  a long raise runs about 2.3x faster than its transition, and a soft off reports `onOff: 0` at once). Where the
  setting differs, it's set (Z2M's settings read on each call, up to 5 s for Z2M), the command published, and the
  user's value written back after Z2M's next state publish for the target (1 s cap). Z2M reads a command's options
  as it takes it (`lib/extension/publish.ts`), so a fade already sent runs on unchanged. One lock per device or
  group holds from the set to the restore. A group uses its own options, not its members', so it's set on the
  group when any member is a Hue bulb. A failed set or restore logs a warning, and the command goes out anyway.
- **`filtered_cache`** gets `deviceside_read` appended. Z2M deep-merges a read's answer into the cached state that
  every later message carries, so an unfiltered answer would look fresh forever. If it can't be set, the read
  raises.

### Turn on with timer

Publishes `{"state": "ON", "on_time": <s>}`; Z2M sends `OnWithTimedOff` (`on_time` to 0.1 s; max 6553.4 s). With
fields, `light.turn_on` goes first, and the timer waits for Z2M's state publish on `zigbee2mqtt/<friendly name>`
(up to 5 s). Sent straight after, Z2M would publish the light's state from before the fields landed, which Home
Assistant keeps, and the two would contend on the mesh, delaying the timer by seconds.

Z2M publishes no state for a timed command (the `on_time` branch of `on_off` in zigbee-herdsman-converters returns
none) and turns reporting off for Hue bulbs. So DeviceSide publishes `{"state": ""}` to the get topic 1 s after
the start (without fields only), and at the end + 1 s and end + max(5 s, 2 % of the duration), for a slow bulb
clock. A new call replaces pending reads. Attribute reporting isn't used instead: it would need setting up on every
bulb, and Z2M turned it off for Hue on purpose. A group gets one publish and one groupcast read; Z2M shows it off
once every member is.

### `set_attributes`

Z2M's generic `command` payload, one per field. A color goes as xy, or hue and saturation on a light without xy.
Z2M publishes no state after a raw command, so each written cluster is read back live from each light, which also
updates Z2M's and Home Assistant's state. Level and color temperature are compared (`not_stored` if they differ);
color isn't, as the bulb clamps it to its gamut. A group is one groupcast per field, then every member is read.
`min_brightness`/`max_brightness` alone clamp each member from its own level, so each gets its own commands; an off
light is clamped from the brightness Z2M holds.

### `get_attributes`

Z2M's generic read, `{"read": {"cluster", "attributes", "state_property": "deviceside_read"}}`, one cluster at a
time, answered on the state topic:

- `genOnOff` (`onOff`, `onTime` in tenths): the timer.
- `genLevelCtrl` (`currentLevel`), only when the light is on. An off light's brightness is Z2M's, from the state the
  `genOnOff` answer carries: after an off with a transition the bulb holds 0.4 % while Z2M keeps the level it
  restores, a Hue bulb's own fade dims it for about a second after a plain off, and reading it would overwrite
  Z2M's kept level.
- `lightingColorCtrl`: `colorMode`, then only the attributes of the light's own modes, since one missing attribute
  fails the whole read.

A failed read raises at once when Z2M logs it on `zigbee2mqtt/bridge/logging`, else after 5 s. A group reads its
members in turn: averages over the lit ones (all, when all are off), and a `timer` only when every lit member has
one, the longest.

### Moves and `stop`

- `raise_brightness`: `{"state": "ON", "brightness", "transition"}`. An off bulb keeps its level and would fade up
  from it, so it first gets `{"state": "ON", "brightness": 1, "transition": 0}` (one publish to an all-off group,
  else per off member).
- `lower_brightness` to 0 %: `{"state": "OFF", "transition"}`, Z2M's soft off.
- Saturation: `{"color": {"hue", "saturation"}, "transition"}`; with `hue_native_control` the bulb fades in xy and
  holds its hue.
- Hue: `hue_move` at `254 / sweep_time` steps per second (ZCL allows 1 to 254).
- `stop`: `brightness_move: stop`, `hue_move: stop` for a running hue cycle, and a raw `stopMoveStep` for a
  saturation fade, since `saturation_move: stop` halts the attribute and lets the xy fade drift on. Each is its own
  publish, color first: Z2M reads back about 0.7 s after a brightness stop before sending the next key.

Z2M publishes a fade's end value at once and reads back within a second of a brightness or hue stop. Once a fade has
run, DeviceSide gets `{"state": "", "brightness": ""}`, in case a mid-fade `get_attributes` overwrote the end
value. A saturation stop is raw, and after an xy stop Z2M's read-back carries its cached end-point x/y, so Device
Side gets `{"color": ""}` 1 s after a saturation stop and at the end of a saturation fade. Z2M reads a group's stop
back from its first member only, so these reads go to each member. After a hue or saturation command the bulb is in
hs mode; Home Assistant accepts that only with the color-modes option on.

### Tested behavior

Measured 2026-10-28 on Z2M 2.14.2 with Hue bulbs (a CT bulb and the A60), Home Assistant 2026.10.2.

- **Color-mode override.** It deep-merges into the device's options, and Z2M republishes the discovery message at
  once, with no restart; Home Assistant's entity keeps its entity ID and shows `color_temp`, `hs` and `xy`. A
  group's options behave the same. A `null` can't remove it: `supported_color_modes: null` deletes the key from the
  announcement, `light: null` drops the light from discovery, and `homeassistant: null` the whole device.
- **Stops, by eye** (a 10 s fade halted 3 s in). Brightness and hue stops freeze cleanly. Every color temperature
  stop jumps, whichever command halts it, the Hue bridge's own included. With brightness and color temperature in
  one fade, a brightness stop leaves the color temperature fading on to its end. `saturation_move: stop` lets an xy
  fade drift on for about 3 s; a raw `stopMoveStep` holds it.
- **After an xy stop,** Z2M's read-back carries its cached end-point x/y, not where the bulb halted; a
  `{"color": ""}` get publishes the halted x/y.

## ZHA

Commands go through `zha.issue_zigbee_cluster_command` and `zha.issue_zigbee_group_command` (admin-only; Device
Side passes the caller's context). The unique ID is `{ieee}-{endpoint_id}`; a longer one on the same endpoint (a
quirk's extra entity) is `not_addressable`, so a timer can't land on the wrong entity. A ZHA group entity
(`{platform}_zha_group_0x{group_id:04x}`) expands to its members for results; commands use the group where noted.

### Turn on with timer

`OnWithTimedOff` (cluster `0x0006`, command `0x42`, `on_off_control: 0`, `off_wait_time: 0`), after
`light.turn_on` when there are fields. Then OnOff (`0x0000`) and OnTime (`0x4001`) are read in one uncached
request: `confirmed` when on and OnTime is above 0, at most the request and no more than 3 s under it.

A group gets one `light.turn_on` and one group `OnWithTimedOff`; per-member commands would start about 0.7 s apart
across 8 lights. A group command gets no reply, so every member is still read back. A slow end device (the rig's
Sengled) can read `not_on` before it takes the group's `light.turn_on` (Tested behavior).

### `set_attributes`

Commands go one after another: `brightness` as a percent of level 254 (`0` sends level 1), color temperature as
mireds clamped to the light's range, color as `MoveToColor`, or `MoveToHueAndSaturation` on a light without xy. A
color light without color temperature takes one as a color, as core does. `min_brightness`/`max_brightness` read
CurrentLevel live. Then `homeassistant.update_entity`, since ZHA never applies a color temperature report; ZHA skips
it while the light is transitioning (1.5 s after a plain off), so DeviceSide waits up to 3 s, and after a longer
off fade refreshes again when it ends. Models in `zcl.DROPS_WHILE_OFF` are refused.

### `get_attributes`

Uncached reads, one cluster at a time: OnOff and OnTime always, Level when the light dims, Color when it has a color
mode. Color is the active mode (EnhancedColorMode where present, else ColorMode). The timer counts only while the
light reads on, as a TS011F counts OnTime down while off.

### Moves and `stop`

- `raise_brightness`: `MoveToLevelWithOnOff`. A light that is off first gets `MoveToLevel` to 1 with
  `ExecuteIfOff` and no transition. A Hue bulb ignores that and fades from its stored level, so it is turned on at
  level 1 by Signify's `multiColor` (cluster `0xFC03`, as Z2M's `hue_native_control` sends), straight through
  zigpy, as ZHA has no action for it; the same admin check applies.
- `lower_brightness`: `MoveToLevel` to a limit; to 0 %, `MoveToLevelWithOnOff`, which leaves the bulb at level 1.
  1 s after the fade should end, OnOff is read and an off light gets `MoveToLevel` back to its starting level with
  `ExecuteIfOff`. A stop or a new brightness call cancels that restore.
- Saturation: `MoveToColor` to the xy of the current hue at the end saturation.
- Hue: `EnhancedMoveHue` at `65535 / sweep_time` steps per second; a light without enhanced hue in
  ColorCapabilities (zigpy's cache, else one live read) gets `fields_dropped`.
- `stop`: `StopMoveStep` where a color move runs, then Level `Stop`.

A transition longer than ZCL's 6553.4 s runs at that. The bulb reports brightness during a fade, never color, so
DeviceSide calls `homeassistant.update_entity` 1 s after a fade should end and straight after a stop; raw commands
leave ZHA's transition guard down, so the read is the bulb's.

ZHA can't tell a change from a remote or app from the bulb's own reports, so the remembered position can go stale.
To keep hold-to-dim instant, the brightness fade is sent first and CurrentLevel read just after; the read, timed at
the middle of its round trip, lies on the bulb's ramp, so DeviceSide fits the ramp's real start to it. A brightness
call the remembered value says is `at_limit` or `off` is replanned from Home Assistant's state.

A group gets one command when every light in it moves; otherwise, such as a soft off with a member off, each moving
member gets its own, since a group soft off would drop an off member's stored level. The bottom level and the
restore are always per member.

### Tested behavior

Timers, on a Philips Hue LTA004 (firmware `0x01001416`, Home Assistant 2026.10.2). Firmware decides this, so other
devices may differ.

- OnTime counts down in tenths (a 30 s timer read 290, 250, 200 and 99 at 1, 5, 10 and 20 s; off at 30.2 s) and
  reads 0 with no timer.
- A new timer replaces the old one, longer or shorter.
- `light.turn_on`, plain (`On`) or with brightness (`move_to_level_with_on_off`), leaves the timer running.
  `light.turn_off` clears it.
- Nothing ends a timer with the light left on: writing OnTime 0 (status `SUCCESS`), `OnWithTimedOff` with
  `on_time: 0`, or a 0.1 s timer each turned the bulb off within 0.3 s. Writing OnTime resets the time left (100
  with 15.6 s left: off 10 s later). With no timer running, writing 0 changes nothing.

Writes while off: the LTA004, LWA012, LTA009 and LCA016 store `MoveToLevel` and `MoveToColorTemp` with `ExecuteIfOff`, at any delay
0 to 2 s after a plain off, and drop them without it. A Sengled E11-G13 (firmware `0x00000009`) takes `MoveToLevel`
while on, but while off, with the override or without, jumps CurrentLevel to 255 and comes on at full.

Moves, on the LTA004: a Level `Stop` 3 s into a 6 s soft off from 200
held at 100 with the bulb on, and Home Assistant showed 100 from the bulb's report. A 4 s fade read its end level by
3.9 s; a 4 s soft off read off, at level 1, by 4.3 s. Group `MoveToLevelWithOnOff` and `Stop` act as the unicast
ones.

Groups (2026-10-27, the LTA004, a Sengled E11-G13 and a plug): a unicast `turn_on_for` takes about 0.23 s per member
(0.34 s with brightness), so under `max_concurrency` 2 the last of 8 lights starts 0.7 to 1 s after the first. A
group `OnWithTimedOff` returns in 0.02 s, zigpy's own success with no delivery feedback, and a member that refuses
the command (the Sengled, `UNSUP_CLUSTER_COMMAND` by unicast) misses it silently, so each member is read back.

## Matter

Through the core integration's python-matter-server connection. The unique ID is
`{fabric_hex16}-{node_hex16}-{postfix}-{endpoint_id}-{key}-{cluster_id}-{attr_id}`. The Lighting feature check reads
FeatureMap bit 0 from the node data (`node_data.attributes["{endpoint}/6/65532"]`), avoiding a chip.clusters import
that `MatterEndpoint.get_attribute_value` would need.

- **Turn on with timer.** `OnOff.Commands.OnWithTimedOff(onOffControl=0, onTime=<tenths>, offWaitTime=0)`, then
  reads of `OnOff.OnTime` and `OnOff.OnOff`, one path per `read_attribute`: `confirmed` when OnTime is non-zero and
  OnOff is on. OnTime alone is not proof: a device can hold a stale OnTime while off.
- **`get_attributes`.** Live reads of `OnTime` and `OnOff`, as the plug tested never reports OnTime on its
  subscription, so the node cache reads 0 mid-timer (Tested behavior). A timer is reported only while OnOff is on.
  `turns` is always `off`.
- **Lights** (Documented) take the same command and reads as plugs, behind the same Lighting feature check.

### Tested behavior

On a WiZ Smart Plug (firmware v1.4), 2026-10-28: the node cache's `OnTime` read 0 before, during and after a 20 s
timer, as the plug never reports it on its subscription. A plain `switch.turn_on` mid-timer left it running.

## Hue

Through the core integration's aiohue connection, CLIP v2 only. The unique ID is the bridge resource ID: a light, a
scene, or a room's or zone's `grouped_light` (`is_hue_group`). A room's lights are those the bridge lists that have
a light entity. Reads come from aiohue's copy of the bridge's state, kept current by the event stream.

- **No timer adapter.** The bridge's timers survive a plain on or off and can only be removed on the bridge, and a
  bulb without power when one fires misses it, with no retry.
- **`set_attributes`** writes each light without `on`; a `grouped_light` write misses lights that are off. Colors
  convert to xy; `rgb_color` wins over `hs_color` over `xy_color`. `min_brightness`/`max_brightness` move the
  stored brightness. A `0` leaves `min_brightness`, `max_brightness` or `color_temp_kelvin` unset, as hue_dimmer did.
- **`set_scene`** has no off-preserving recall in the Hue API, so it reads the scene from aiohue and writes each
  action as a light write: `on: true` dropped, `on: false` kept, gradients, effects and dynamics skipped. The bridge
  takes 3 requests at once and aiohue retries the rest.
- **`get_attributes`** leaves out `color_temp_kelvin` in color mode, as the bridge's value is stale. A room with a
  light on uses the bridge's brightness and averages color over lit lights; with all off, over all of them.

### Moves and `stop`

One write of the end point with a duration; a room is one `grouped_light` write. Saturation uses the room's hue
(the mean xy of its lit color lights), each light clamped to its gamut by the bridge. `lower_brightness` to 0 % is
`on: false` with the duration, which keeps the stored brightness.

`stop` sends the dimming stop. The bridge has no xy stop, so a saturation fade is halted by writing its predicted xy
with no duration, in the same write (per light for a room). The bridge refuses a dimming stop during a soft off, so
DeviceSide's own soft off is cut with `on: true` at the predicted brightness and no duration.

Reports during a remembered move can't be told apart by value (Tested behavior), so every report of what the move
changed (brightness and on, or color) is taken as DeviceSide's, except a switch to off while fading to or halted at
a lit level, and a report of anything the move didn't change; those, a bridge scene recall (`status.active`), and a
Home Assistant call end the prediction. With `predicted_state` on, the reports taken as DeviceSide's are hidden from
aiohue and Home Assistant is sent the prediction instead; a raise from off shows 0.4 %, where the fade starts.

### Tested behavior

Measured 2026-10-26 on a BSB002 bridge (software 6.1.1978418030) and two LTA009 bulbs (firmware 1.163.1), Home
Assistant 2026.10.2, aiohue 4.9.0, unless dated otherwise. Home Assistant shows each event as it arrives.

- **A transition reports its end value at once,** about 70 ms after the write (80 % reads 79.84), and nothing when it
  ends. A transition to the value the bridge holds sends nothing.
- **Where a stopped light halted is reported late or never:** 0.1 to 27 s after the stop, varying as if from the
  bulb; after 4 of 16 stops, nothing within 30 s. Reports that came were within 0.3 % brightness and 1 mirek of a
  straight line. Once (2026-10-27, a zone) a bulb reported the brightness from before the move: 56 % against a
  40 % halt.
- **A mid-transition report can come,** and be the last: about 1 s stale but on the path. Every stop report was
  within 0.4 % of the straight line.
- **Rooms and zones:** each light reports its end at once, the `grouped_light` the average about 1 s later; after a
  stop the lights report separately, up to 16 s apart.
- **A change from elsewhere is reported promptly:** a Home Assistant `light.turn_on` within 0.25 s, a Hue app
  slider about once a second.
- **Dimming to off** reports `on: false` (and brightness 0, if written) at once; in 1 of 2 runs a mid-fade report
  then showed it on at 17 %, with nothing after. A dimming stop is refused during it, but `on: true` with a
  brightness and no duration ends it there without a jump. `on: false` with a duration keeps the stored brightness;
  with brightness 0 in the write, the next on comes back at the minimum.
- **Brightness 0 left on** (`on: true`, 0, with a duration) ends on at `min_dim_level` (0.2 % on the LTA009);
  Home Assistant shows it on at 0. A dimming stop halts it.
- **Color temperature** reports only `color_temperature`, and its transitions and stop (`color_temperature_delta`)
  behave as brightness, on a light and a zone. Brightness and color temperature fade independently, in either
  order; one write of both reports two events; one write takes both stops (2026-10-27).
- **xy** (a gamut C bulb, 2026-11-03) behaves as brightness: the end at once, nothing after. An xy with no duration
  mid-fade halts it, reported at once. One write takes a dimming stop and an xy. An xy fade and a brightness fade
  0.5 s apart both run. A zone xy write changes only its color bulbs.
- **A brightness write never reports a color:** across the full Hue rig suite (2026-10-27), only `on` and `dimming`.
- **A bridge scene recall** sets `status.active` to `static` within about 1 s of its lights' reports. A light whose
  color the scene leaves alone reports only `on` and `dimming`, so only the scene's report shows the change came
  from elsewhere.
- **Moving a bulb between networks** (2026-10-31, the A60 on firmware 1.164.2): a CLIP v2 `DELETE device/<id>`
  sends it a Leave, as Z2M's and ZHA's removes do, and it joins the next network in about 10 s. On older firmware,
  a v1 light delete left it on no network, until a delete in the Hue app released it.
