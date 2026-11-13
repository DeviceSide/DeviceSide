# Control4 internals

How the Control4 adapters address a target, what they send and read back, and what was measured on real hardware.
What a user sees is in [index.md](index.md) and isn't repeated here; what every integration shares is in
[internals.md](../../internals.md). Result and detail codes are in the code. Code comments cite the sections here.

## Addressing

Through the core integration's pyControl4 `C4Director` (`runtime_data.director`), borrowed for each call, so
DeviceSide holds no connection or credentials of its own. The unique ID is the Director item ID. Commands go to
`/api/v1/items/<id>/commands` (`send_post_request`), reads to `/api/v1/items/<id>/variables?varnames=…`
(`send_get_request`). A Control4 light group is one item: it takes one command and is not expanded.

## Modules

One section per adapter module, named after it.

### `director`

- **Token.** Core refreshes an expired Director token only from its own polling, so a send the Director refuses with
  `BadToken` first leaves its light's lock and its concurrency slot (`DirectorAdapter.gather`). Then Home Assistant is
  asked to update the light's entity (`async_update_entity`), under the dispatcher's deadline: core's poll meets the
  same refusal and swaps a new Director into `runtime_data`, and the refused targets are sent once more. So a light's
  lock covers only its read and its command, never the cloud round trip. Calls refused together ask once, under one
  lock per config entry, as core's coordinator debounces a second ask; the rest find the Director swapped. A target
  core swaps no new Director in for is rejected, with a WARNING, as happens when the ask lands inside the cooldown
  core's coordinator keeps after its own refresh; one whose refresh outlasts the deadline is rejected with `timeout`.
  A refused send has left its lock, so a stop sent during the refresh can land ahead of the retried move. The refresh
  rests on core's code as read (2026.10.2); it has not been run against an expired token. A read-back's reads run
  outside `gather`: one refused there reports `sent` (`readback_failed`). Core's refresh helper is not imported, which
  would need `control4` in `after_dependencies`.
- **Level.** `Brightness Percent` (0 to 100), read on the tested lights. Core also reads `LIGHT_LEVEL`
  (`CONTROL4_DIMMER_VARS` in its `control4/light.py`), which the tested lights don't report, so DeviceSide falls back
  to it, reading `Brightness Percent` first where core reads `LIGHT_LEVEL` first: the measured variable leads. Lit
  means a level above 0. `Brightness Target Percent` is where a ramp is heading and equals the level at rest. That a
  light reporting only `LIGHT_LEVEL` reports no target is assumed, not tested: none was available. A value arrives as
  a number, or as text for a light that has never reported. A level outside 0 to 100 rejects the target.
- **Ordering.** One lock per item, held by a move from its read to its ramp (a halt of a ramp already running
  included) and by a stop for its halt. Core takes it before the concurrency slot (`gather`'s `hold`), so a call
  waiting on a busy light holds no slot, and nothing under it takes a slot. With it, a stop that arrives during a move
  is sent after the ramp that move starts. A stop sent right behind a ramp halted the tested group where it was
  (Tested behavior); a light that ignored one would report `still_fading`.

### `fade`

`raise_brightness` and `lower_brightness`. A read first: the Director holds the level, refreshed about once a second
mid-ramp and exact once a ramp has halted, so no transition cache is kept and no call resolver is needed. A read that
shows a ramp (level and target half a percent or more apart) is not moved from: its level may be a second old, and a
ramp just begun still reads the level it left (0 for a ramp from off, 11 ms in), which a lower would pass by as off.
The adapter sends `SET_BRIGHTNESS_STOP` and reads again after 0.1 s and, if the ramp still shows, after 0.15 s more
(`MOVE_SETTLE_DELAYS_S`, the first two waits of `stop`'s schedule; counted from the stop's reply, as these waits are,
the second read would have shown 19 of the 20 timed halts). Those waits are inside the light's lock and the move's
concurrency slot, which is why they are cut short; if the Director still shows a ramp after them, the move starts from
that read. One ramp is left running: the adapter's own to the end this call asks for. Nothing is sent then, so a
repeated call can't re-time the ramp from a stale level, and the call reports `sent`: the ramp it asks for is running,
though an earlier call sent it. Whose ramp it is comes from the last command the adapter sent the light
(`director.own_ramp_end`: the level of its last `RAMP_TO_LEVEL`, cleared by its `stop` and forgotten once that ramp's
time plus 2 s has passed, so a ramp to the same level after that time, from a scene or from core's own turn-on, is not
taken for it; one that replaces the adapter's ramp inside that time still is, and runs on at its own speed), held in
memory and never used as the light's level. The record is per item: a stop sent to a group doesn't clear a member
bulb's. A lower to the very limit a raise is ramping to counts as the same ramp. What the Director shows can't say: it
goes on showing a ramp for a moment after a `stop` has halted it, so a press right behind a stop finds a ramp that is
no longer the adapter's own, sends a second `SET_BRIGHTNESS_STOP` (which changes nothing on a halted light) and waits
for the halt to show. A ramp halted from Control4 inside that same moment is the one case still read as running. For
up to about 70 ms after a ramp is sent the Director still shows the light at rest (Ramp start, below), so an opposite
move that arrives in that window, as two calls an automation fires together, is not halted and moves from the level
shown. The halt-then-ramp sequence ran on hardware (DeviceSide's own actions, below). Then one `RAMP_TO_LEVEL {LEVEL,
TIME}`, sent as a whole percent and whole milliseconds (the adapter's rounding; core sends fractions) for the distance
left at the `sweep_time`'s speed, at most 65535 ms for a full range (`RAMP_LIMITS`). `LEVEL` 0 ends off, as core's own
turn-off sends it (`ramp_to_level(0, ...)`); a limit above 0 is sent as at least 1. From off the level reads 0, so the
whole range is the distance. An on/off light lacks brightness, so the dispatcher leaves it unchanged
(`fields_dropped`).

### `stop`

`SET_BRIGHTNESS_STOP`, with no parameters, to every target first. Then up to four reads per target, after waits of
0.1, 0.15, 0.3 and 0.6 s, ending at the first that shows level and target within half a percent (`SETTLE_DELAYS_S`,
sized from the stop timings below); the waits hold no concurrency slot. `confirmed` when lit with level and target
equal, `sent` (`still_fading`) when they still differ (Control4 hadn't shown the halt yet, the driver ignored the
stop, or a new move began meanwhile), `sent` (`halt_not_reported`) on
a driver with no target, `unchanged` (`off`) at rest at 0. An on/off light is refused (`not_dimmable`) with nothing
sent.

### `get_attributes`

Core's entity shows the level as of its last poll of the Director (`DEFAULT_SCAN_INTERVAL`, 5 s, a user option), and
no color temperature; this reads the Director itself. One read of `Brightness Percent` (or `LIGHT_LEVEL`),
`LIGHT_STATE`, `Current CCT` and `Current Color Mode`, logged with its values as every read of the Director's
variables is (`director.read_variables`). Brightness is reported when above 0; `color_temp_kelvin` when the mode is 1
(color temperature, the only mode measured) and the light reports one. An off light with neither returns an empty row,
as does a light that reports `LIGHT_STATE` and no level. A read with neither a level nor `LIGHT_STATE` rejects the
target.

### `set_attributes`

`color_temp_kelvin` only, declared `unlisted` in the adapter's scope so the dispatcher doesn't drop it for an entity
that lists brightness alone. The `services.yaml` filter hides the field from the action's form for such an entity, so
it is sent from YAML. A read of `Navigator Dynamic Capabilities` first. A light with no such variable, or whose
`supports_color_correlated_temperature` isn't true, lacks the field: `unchanged` with `fields_dropped`, nothing sent.
Capabilities that can't be read, or that claim a color temperature without a real
`color_correlated_temperature_min`/`max` range, reject the target. The kelvin is clamped to the range and a clamped
result carries `clamped_to`. Then `SET_COLOR_TARGET {LIGHT_COLOR_TARGET_COLOR_CORRELATED_TEMPERATURE,
LIGHT_COLOR_TARGET_MODE: 1}`, as pyControl4's `set_color_temperature` sends it, to every target first. Then a
read-back per target, on `stop`'s schedule, ending at the first read that shows the light off or heading for the
kelvin: `Target CCT` equal to it with `Target Color Mode` 1, or `Current CCT` equal to it with `Current Color Mode` 1.
The target shows a new value within 0.2 s and the current one most of a second later (color temperature timing,
below), so the target is what confirms. `confirmed` when lit and heading for it, `sent` (`color_temp_not_reported`)
when lit and not, `sent` (`stored_while_off`) when off, `sent` (`readback_failed`) when a read-back fails or holds no
level. Heading for it means the Director's target shows it, in the tens of kelvin the Director holds: it reports a
color temperature rounded down to 10 K, so the kelvin sent matches a report up to 9 K below it; whether the target
also shows it for a lit bulb that can't obey, as one with no power, is unmeasured, so `confirmed` here is the
Director's word, not yet proven to be the bulb's.

## Tested behavior

Measured by one contributor on a CORE 5 controller (OS 4.3.0) with a light group (the "Light Group" driver) of three
Hue White Ambiance 5/6" downlights (`LTD010`, firmware 1.163.5) joined over Zigbee (the "Zigbee 3 Light" driver),
Home Assistant 2026.11.1 and pyControl4 2.0.2. Undated entries are from 2026-11-10, by hand: commands sent to the
group through the Director, with reads of its variables between them. Entries dated 2026-11-13 are on the same
hardware and versions, sent and timed in-process by a probe in Home Assistant. No test rig has run.

- **The level follows a ramp.** Three seconds into a 12 s `RAMP_TO_LEVEL` from 100 to 10, `Brightness Percent` read
  77.44 and `Brightness Target Rate Remaining in Milliseconds` 9000. The target read 10 throughout.
- **A release halts a ramp, either way.** A bottom-button release halted that downward ramp at 27, and an upward ramp
  from 27 toward 100 at 53. After each, level and target were equal and the time remaining 0.
- **A release at rest changes nothing.** Sent to the group at rest at 53, it left level and target at 53.
- **`SET_BRIGHTNESS_STOP` does the same, and is what `stop` sends.** By hand, during a 15 s ramp from 100 to 10, it
  halted the group at 77 with level and target equal. Through DeviceSide's own `stop`, with a level read after each:
  it halted a downward ramp at 89 and another at 55, and an upward ramp at 79, each reported `confirmed`; a second
  read after the first halt still showed 89. Sent at rest at 79, it left the group at 79. It is the command made for
  the halt, where a release is a button event.
- **The Director lags a release.** A read sent straight after the release still showed the ramp's target; a read about
  a second later showed the halt (the next read taken by hand, not the halt's timing).
- **Stop timing, 2026-11-13.** Twenty stops, each 3 s into a 15 s `RAMP_TO_LEVEL`, both directions, with reads timed
  in-process from the moment the stop's POST was sent: 16 on the group, 4 on one of its bulbs. The POST returned in 8
  to 26 ms (once 61 ms, once 365 ms on the bulb). On the group a read sent as the POST returned still showed the ramp
  in 14 of 16; the next read, sent 39 to 162 ms after the POST, showed the halt in 15 of 16, the earliest at 39 ms. In
  the other, no read up to 350 ms showed it, and the light halted about two percent on, roughly half a second late.
  The bulb showed the halt on its first read in 3 of 4, and after its 365 ms POST on the read at 516 ms. A halted
  level is a whole percent, equal to its target, and held for the rest of each capture (up to 3 s). Mid-ramp the level
  variable itself updates about once a second.
- **Ramp start, 2026-11-13.** On the group, a 15 s `RAMP_TO_LEVEL` from rest at 2 to 100 with reads every 60 ms: the
  read sent as the POST returned (8 ms) still showed the target 2, the read sent at 68 ms showed 100. The level stayed
  2 through the read sent at 980 ms and showed 8.54 from the one at 1041 ms, so its first mid-ramp update came about a
  second in. From off, a read 11 ms into a ramp showed level 0; 0.3 s in it showed 1. A `SET_BRIGHTNESS_STOP` sent
  then showed the halt, level and target 2, on the read sent 116 ms later (not on the one at 16 ms), and held it for
  the 2.4 s captured.
- **A stop right behind a ramp, 2026-11-13.** On the group at rest at 13, `RAMP_TO_LEVEL` to 100 over 15 s and
  `SET_BRIGHTNESS_STOP` straight after it (the stop's POST returned 32 ms after it was sent). The read sent as the
  stop returned showed level 13, target 100; the read 283 ms after the stop showed 13 and 13, held for the 2.5 s
  captured.
- **DeviceSide's own actions, 2026-11-13.** Run on the group through the adapters as rebuilt on main that hour (before
  the own-ramp rule), with the debug log on. A `raise_brightness` (sweep 15 s) and a `stop` 3 s later: `confirmed`,
  halted at 17. A change of direction with no stop: 1.27 s into a raise, `lower_brightness` read level 11.67 and
  target 100, sent `SET_BRIGHTNESS_STOP`, read 13 and 13 on its first read 134 ms later, and sent `RAMP_TO_LEVEL` to
  its limit of 5 for 1200 ms. A repeat the same way 1.13 s later, on the build of that hour, read 6.33 with target 5
  and sent the ramp again for 199 ms, timed from that stale level (the light was at 5 on the next read); the adapter
  now sends nothing for a repeat of its own ramp. A `stop` 1.15 s into a raise read the halt 136 ms later:
  `confirmed`. Off, `lower_brightness` and `stop` each reported `unchanged` (`off`), and a raise brought the group on
  to its limit.
- **The own-ramp rule, 2026-11-13.** Run on the group through the adapters, debug log on, before the record of an own
  ramp was given its time limit. A `raise_brightness` (sweep 15 s) from off sent `RAMP_TO_LEVEL` to 100; the same call
  1.09 s and 2.29 s later read level 1 and then 7.72 with target 100 and sent nothing, each reporting `sent`. A
  `lower_brightness` to 5 at 3.55 s read 23.16 and 100, sent `SET_BRIGHTNESS_STOP`, read 24 and 24 on its first read
  136 ms later, and ramped to 5 over 2850 ms; the same call again sent nothing. A lower to 3 read 10.55 and 5, halted
  at 8 and ramped to 3. A raise then found the light at rest at 3 and ramped; a `stop` 1.08 s later was `confirmed` at
  10, and a raise 1.1 s after that stop read the halt and ramped from it. A press within a quarter of a second of a
  stop was not run: the calls were about a second apart.
- **The own-ramp rule with its time limit, 2026-11-13.** Run on the group through the adapters, debug log on. Four
  calls within 0.52 s: a raise to a limit of 40 (800 ms ramp); 120 ms later a raise to 100, which read level 1 and
  target 40, sent `SET_BRIGHTNESS_STOP`, read 6 and 6 after 131 ms and ramped to 100; the same raise 74 ms later,
  which read 6 and 100 and sent nothing; and a lower to a limit of 10, which halted the ramp at 7 and, being below its
  limit already, reported `unchanged` (`at_limit`). Then a ramp not DeviceSide's own: 17 s after a 1.86 s raise to
  100, with a 60 s `RAMP_TO_LEVEL` to 100 sent straight to the Director and running, a raise read 28.03 and 100,
  logged no ramp of its own on record, halted it at 29 and sent its own ramp. A `stop` was `confirmed` at 67.
- **Rate ceilings.** Each light's `Navigator Dynamic Capabilities` variable gives `brightness_rate_max`: 65535 on a
  bulb, 86400000 on the group, both in milliseconds. Both give `supports_brightness_stop: true`.
- **A variable an item lacks, 2026-11-13.** A read of the group and of one bulb naming `LIGHT_LEVEL`, `Brightness
  Percent`, `Brightness Target Percent`, `LIGHT_STATE` and a made-up name returned three rows each (both lights off:
  level 0, target 0, `LIGHT_STATE` 0): no `LIGHT_LEVEL` row and none for the made-up name, with no error.
- **Text for a light that has never reported.** Bulbs added to the project but not yet paired, and a group of them,
  reported `"0"` as text for `Brightness Percent` and `LIGHT_STATE`; paired lights report numbers.
- **A color temperature is taken on or off.** With the group on, `SET_COLOR_TARGET` with the kelvin and mode 1 moved
  `Current CCT` from 3200 to 2700 by a read about a second later; a read sent straight after the command still showed
  3200, the same lag a halt has. With the group off, the same command for 4000 left it off and `Current CCT` at 2700
  on the read taken then, by hand and untimed (the 2026-11-13 entry below times what it shows meanwhile); the next
  turn-on brought it up at 4000. The same command with `LIGHT_COLOR_TARGET_X`/`Y` added to it changed nothing, on the
  group or on a bulb.
- **Color temperature timing, 2026-11-13.** Four `SET_COLOR_TARGET` commands on lit lights, two on the group and two
  on a bulb, between 3200 and 2700, read every 150 ms: `Target CCT` showed the new value on the first read (8 to 63 ms
  after the POST) in three and on the second (159 ms) in one; `Current CCT` first showed it on reads sent 0.76 to 0.91
  s after the POST (reads 150 ms apart). `Current Color Mode` and `Target Color Mode` read 1 throughout; the lights
  report `supports_color: false`, so a start from full-color mode is untested.
- **Tens of kelvin, 2026-11-13.** `SET_COLOR_TARGET` on the group, lit: 3333 read back as 3330 in `Target CCT` and
  `Current CCT`, 2956 as 2950, 6536 as 6530, 3205 as 3200 and 2203 as 2200. The Director holds tens of kelvin, rounded
  down.
- **DeviceSide's own actions, 2026-11-13.** Run on the group through the adapters as rebuilt on main that day.
  `set_attributes` 2700 on the lit group: `confirmed` on the first read-back, where `Target CCT` showed 2700 and
  `Current CCT` still 3200. With the group off, 4000: `sent` (`stored_while_off`), and a raise then brought it on at
  4000. `get_attributes` gave the level and color temperature the Director held each time. A 2000 was clamped to 2203
  and took, but with the comparison then exact it reported `sent` (`color_temp_not_reported`) against the Director's
  2200. Run again with the tens-of-kelvin match: 2000 was `confirmed` with `clamped_to` 2203, 2956 was `confirmed`,
  and 7000 was `confirmed` with `clamped_to` 6536.
- **Color presets, 2026-11-13.** Each light has an On Color and a Dim Color preset in Control4 (both 3200 K by
  default, read from its `Color Presets` variable). On a group whose presets were 2700 and 3200, Control4 itself moved
  the color temperature with the brightness on a ramp (2850 K read at 68 %). A color temperature set by
  `SET_COLOR_TARGET` held through a ramp, and an off then on from Control4 brought the light back at its On Color
  preset; which off and on commands were used was not noted.
- **A color temperature set while off, 2026-11-13.** `SET_COLOR_TARGET` for 4000 on the group while off: reads from 9
  ms to 1.2 s after it showed `Current CCT` and `Target CCT` 4000 with the level 0; the read at 1.5 s showed both back
  at 3200, as did one 3 s later. A `RAMP_TO_LEVEL` to 100 then brought the group up at 4000, which held.
- **Capabilities, 2026-11-13.** `Navigator Dynamic Capabilities` arrives as an object, `{"DynamicCapabilities": {…}}`.
  Its keys on the group: `dimmer`, `supports_target`, `supports_brightness_stop`, `supports_color` (false),
  `supports_color_correlated_temperature` (true), `supports_color_stop`, `brightness_rate_min`/`max`,
  `color_correlated_temperature_min` (2203) and `_max` (6536), `color_rate_behavior`, `color_rate_min`/`max`,
  `has_extras`, `click_rate_min`/`max`, `hold_rate_min`/`max`, `cold_start`, `supports_color_cycling`,
  `advanced_scene_support` and four `hide_proxy_…` flags: capabilities and rates, no address or name. A bulb gives the
  same keys.
- **The stored on-level holds for Control4's on only.** `SET_PRESET_LEVEL {LEVEL: 40}` on the group while off left it
  off with `PRESET_LEVEL` 40, and Control4's `ON` brought it up at 40. Home Assistant's `light.turn_on` then brought
  it up at 100: core sends its own level. So `set_attributes` takes no brightness.
- **A press and release also ramps.** `BUTTON_ACTION` press (`ACTION: 1`) on the bottom button ramped the group down
  at its hold rate until the release, from 100 to 32; the top button raised it to 94. The adapters don't send a press:
  its speed is the driver's, not the call's `sweep_time`.
