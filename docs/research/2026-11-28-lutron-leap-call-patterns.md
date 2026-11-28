# Lutron LEAP call patterns for DeviceSide's actions (2026-11-28)

Research date: 2026-11-28. Scope: which LEAP calls, reached through Home Assistant's `lutron_caseta` integration and its
`pylutron-caseta` `Smartbridge`, would serve DeviceSide's actions on every system core serves over LEAP: Caséta Smart
Bridge and Smart Bridge Pro, RA2 Select, RadioRA 3 and HomeWorks QSX (core also serves Athena, which `pylutron-caseta`
treats like QSX). The RA2/QS telnet Integration Protocol (core `lutron`) appears only as a comparison. Feeds the
decision in issue #660: build a `lutron_caseta` integration (which actions, classes and bridges), build part, or defer.
Nobody on the project owns Lutron hardware; nothing here was probed.

**Read in a gap pass the same day:** Lutron's Integration Protocol guide 040249 (the telnet comparison) and its
RadioRA 3 processor specification on assets.lutron.com, HA's `lutron_caseta` documentation page, community.hubitat.com
and community.home-assistant.io threads (through their JSON endpoints), a community Hubitat LEAP driver, and HA's
analytics. **Still unreachable, so not read:** support.lutron.com, www.lutron.com and forums.lutron.com (a bot
challenge answers every page, so no LEAP integration article was found), docs.hubitat.com (it redirects to a host this
sandbox refuses), and GitHub issue and PR pages of repos other than DeviceSide's. What is said of those comes from
search-result summaries, is marked [search], and is signal at most. Lutron gives its LEAP documentation to approved
partners only (S1); its public guide defines only the telnet protocol, and its processor specification names LEAP as
the integration API without defining it (S16). So no public primary source defines a LEAP call: what a call does is
settled here by what `pylutron-caseta` sends and core ships, and anything beyond that is marked unsourced.

## Evidence tags

- **[doc]**: Lutron's published guide 040249, by printed page. It defines the telnet protocol (RA2, QS, Athena), not
  LEAP.
- **[code]**: source, pinned below. It shows what a library sends, not what a bridge does with it.
- **[fixture]**: `pylutron-caseta`'s recorded bridge answers (`tests/responses/`), replayed by its tests.
- **[run-3p]**: a third party's written record of a run against a real bridge. Signal only.
- **[community]**, **[search]**: a forum post or upstream issue; a search-engine summary of a page not fetched.
- **[inferred]**: my reading, not observed.

Pinned primary sources:

- pylutron-caseta: `gurumitts/pylutron-caseta@1c25f55bef14adf0bac81c2bba43ea4f7e6826b1` (2026-10-24, v0.30.1, the
  version core pins), written `PLC/<path>#L<n>`; `smartbridge.py` and `__init__.py` are under `src/pylutron_caseta/`.
- HA core: `home-assistant/core@68475ac0d1c833aa395b1b222ee50c9c04be554c` (2026-11-28), `lutron_caseta` files written
  `HA/<file>#L<n>`, `lutron` files `HAL/<file>#L<n>`.
- pylutron (core `lutron`'s library, the telnet comparison): `thecynic/pylutron@dca79ee8537132859afbb32c56ac44f4487be407`
  (2026-09-12), written `PYL/<path>#L<n>`.
- Lutron Integration Protocol guide 040249, revision AH (2022-05-31),
  [assets.lutron.com/a/documents/040249.pdf](https://assets.lutron.com/a/documents/040249.pdf), fetched 2026-11-28,
  written `LIP p.<n>` (printed page).

Signal sources (second implementations, run records, blueprints) are pinned in section 9 and cited as S1-S16.

## 1. What core `lutron_caseta` already offers

None of DeviceSide's actions [code]:

- `light.turn_on` with `transition` sends `GoToDimmedLevel` with a `FadeTime`; without one, `GoToLevel`
  (HA/light.py#L164-L176; PLC/smartbridge.py#L482-L506). Ketra and Lumaris zones get `GoToSpectrumTuningLevel` or
  `GoToWhiteTuningLevel`, color-only calls without a `Level` (HA/light.py#L204-L231; PLC/smartbridge.py#L441-L480).
- A `button` entity per Pico and keypad button, whose press sends `PressAndRelease` to `/button/<id>/commandprocessor`
  (HA/button.py#L56-L59; PLC/smartbridge.py#L640-L651). Nothing sends a hold.
- `cover` entities send zone `Raise`, `Lower` and `Stop` (HA/cover.py#L85-L97, #L167-L183). HA sends a `Raise` or
  `Lower` before every `Stop` "to ensure it works correctly" (HA/cover.py#L87-L97).
- Button events (`press`, `release`, `multi_tap`, `long_press` from QSX's `LongHold`) on the bus and as event entities
  (HA/__init__.py#L522-L582).
- No services: the integration registers none and has no `services.yaml`.

No raise, lower or stop for lights, no timers, no set-while-off, no read beyond the pushed level.

Core defect, for `docs/defects.md` if the integration is built: `to_lutron_level` rounds HA brightness to a LEAP level
0-100 (HA/light.py#L55-L57), so `light.turn_on` with brightness 1 sends level 0 and turns the light off [code].

## 2. The bridges and the call surface

`pylutron-caseta` reads `/project` and takes one of two branches (PLC/smartbridge.py#L894-L938) [code]:

| Bridge | `ProductType` branch | Devices and zones | Zone status |
|---|---|---|---|
| Caséta Smart Bridge, Smart Bridge Pro, RA2 Select | Caséta (flat `/device`) | `/device` with `LocalZones` (PLC/smartbridge.py#L977-L1029) | each zone read once at login, then untagged `OneZoneStatus` pushes (#L928-L938, #L871-L881) |
| RadioRA 3, HomeWorks QSX, Athena | processor (`PROCESSOR_PRODUCT_TYPES`, PLC/__init__.py#L37-L43) | `/area/<id>/associatedzone`, a zone per device entry, typed by `ControlType` (PLC/smartbridge.py#L1237-L1272) | `/zone/status` subscription, `ZoneStatuses` list (#L1037, #L1524-L1535) |

Every load command is a `CreateRequest` to `/zone/<id>/commandprocessor` with a `Command.CommandType` [code]:

| CommandType | Body | Sent by `pylutron-caseta` for |
|---|---|---|
| `GoToLevel` | `Parameter: [{Type: Level, Value: 0-100}]` | switches; dimmers with no fade (PLC/smartbridge.py#L496-L506) |
| `GoToDimmedLevel` | `DimmedLevelParameters: {Level, FadeTime: "hh:mm:ss"}` | light types with a fade (#L482-L495) |
| `GoToSpectrumTuningLevel`, `GoToWhiteTuningLevel` | level, color, `FadeTime` | Ketra, Lumaris (#L441-L480) |
| `GoToFanSpeed`, `GoToTilt`, `GoToCCOLevel` | speed, tilt, `Open`/`Closed` | fans, blinds, contact closures (#L419-L433, #L539-L580) |
| `Raise`, `Lower`, `Stop` | none | covers only (#L508-L537) |

Buttons take `PressAndRelease` at `/button/<id>/commandprocessor`, scenes the same at
`/virtualbutton/<id>/commandprocessor` (#L600-L651). Smart Away is an `UpdateRequest` to `/system/away/1/status`
(#L613-L638). The library's tests pin these bodies against a fake bridge, not a real one (PLC/tests/test_smartbridge.py#L1368-L1384,
#L1429-L1492).

## 3. Moves: `raise_brightness`, `lower_brightness`, `stop` (question 1)

**Zone Raise, Lower and Stop on a dimmer.** No primary source sends them to a dimmer zone, and none says a dimmer refuses
them [code]:

- `pylutron-caseta` has them only as `raise_cover`, `lower_cover` and `stop_cover` (PLC/smartbridge.py#L519-L537), added
  in 0.7.0 as "Shades can be told to raise/lower/stop" (PLC/CHANGELOG.md#L276-L281). No version through 0.30.1 adds a
  dimmer equivalent.
- `raise_cover` doesn't check the device's type: given a dimmer's device id it would send `Raise` to the dimmer's zone,
  then write `current_state = 100` as an optimistic endpoint, since "Raise does not produce an immediate callback"
  (#L523-L529). HA's light would show full brightness until the next push. DeviceSide must not call it on a light
  [inferred]; the plain sender `_send_zone_create_request` (#L508-L517) is private.
- On processors, Raise, Lower and Stop are pinned for `OpenCloseStop` zones; the README says such a zone's push may carry
  no level and Stop may produce no push at all (PLC/README.md#L68-L103, observed on QSX).
- The telnet comparison is the same: `pylutron` sends OUTPUT actions 2, 3 and 4 (raise, lower, stop) only from
  `_MotorizedOutput`, the base of `Shade` and `Motor` (PYL/pylutron/__init__.py#L998-L1025), and core `lutron` uses
  them only for covers (HAL/cover.py#L68-L78, #L128-L138). Lutron documents them for dimmers, though: its guide says
  outputs "are dimmers, CCOs, or other devices" and lists Start Raising (2), Start Lowering (3) and Stop Raising or
  Lowering (4), with no parameter (LIP p.8); a dimmer's own page gives "Start Raising dimmer level" `#OUTPUT,1,2` and
  "Stop Raising / Lowering dimmer level" `#OUTPUT,1,4` (LIP p.143, RadioRA 2 and HomeWorks QS dimmers); and on Quantum,
  Athena and HomeWorks QS "the output's level will continue to go towards high end / low end until a Stop command is
  received" (LIP p.44, p.54, p.61) [doc]. So the move runs to the end, not a set distance. No page gives its rate,
  and none says what Raise does to an off dimmer. That is the telnet protocol; it shows the device move exists, not
  what a LEAP bridge does with a zone `Raise`.

The one record of a dimmer taking them is a third party's run: on 2026-11-22, `Raise` to a Caséta Smart Bridge dimmer's
zone at 30, then `Stop` about 4 s later, read 92 a second after; `Lower`, then `Stop` about 2 s later, read 47; each was
answered without an error (S3) [run-3p]. That puts a fixed rate somewhere near 15-25 % a second (a full sweep of roughly
4-7 s), with the read's lag unknown [inferred].

One implementation ships the call. A community Hubitat LEAP driver, for Caséta bridges and RadioRA 3 processors (QSX
and Athena offered as untested), maps `startLevelChange` to zone `Raise` or `Lower` and `stopLevelChange` to zone `Stop`
on every zone not `Switched`, and sends switches nothing (S13) [code]. Its author reports that "basics of dimmers and
switches work" on RA3 (S14) [community]; no post reports its level change, working or failing. Hubitat's built-in LEAP
integration (in beta, Caséta from 2.5.1, RA3 from 2.5.2) is closed source, so what it sends for `startLevelChange` is
unknown (S14).

What the sources leave open, each a probe in section 10:

- **Rate and `sweep_time`.** The commands take no parameter (PLC/smartbridge.py#L516), so the rate is the device's or the
  bridge's, fixed, and `sweep_time` can't be honored on this route: at best it is clamped to the measured sweep
  (`clamped_to`, `docs/action-behavior.md`). The sweep isn't published, in the telnet guide either.
- **From off.** Whether `Raise` turns an off dimmer on and from what level, and whether `Lower` stops at the low end or
  turns the load off: unsourced.
- **What `stop` reports.** The command's reply status for a dimmer: unsourced (S3 says only "without an error"). The level
  after a stop arrives as a zone push or a read (section 5).
- **Processors and RA2 Select.** No run shows a dimmer zone on RA3, QSX, Smart Bridge Pro or RA2 Select taking `Raise`.
  S13 sends it to RA3 and Caséta zones without saying which bridge models it was tried on; no source names RA2 Select.

**`limit` on this route.** `Raise` has no end point, so a move with `limit` would have to be `GoToDimmedLevel` to the
limit with a `FadeTime` from the fixed rate (section 4), and its `stop` would then have to halt a fade, which nothing
shows [inferred].

**The other route: a fade to the end.** `GoToDimmedLevel` to 100 (or 1) with `FadeTime` = `sweep_time` x the distance,
and `stop` as zone `Stop`, would honor both `sweep_time` and `limit`. It works only if `Stop` halts a fade where it is;
no source says so. One third-party driver fakes a held key this way and stops by sending a new level (S5) [code].

**The virtual Pico route.** A button hold is `PressAndHold`, then `Release`, at `/button/<id>/commandprocessor`. No
primary source sends either: `pylutron-caseta` and core send only `PressAndRelease`. openHAB sends a keypad button's
press as `PressAndHold` and its release as `Release` on every LEAP bridge it serves (S2) [code], and a 2017 forum post
gives the `PressAndHold` request for a Pico's raise button, without saying what the bridge did or how the hold ended
(S8) [community]. What it needs, by bridge:

- **Caséta Smart Bridge, Smart Bridge Pro, RA2 Select.** A `/button/<id>` exists only for a paired device's button group
  (PLC/smartbridge.py#L1308-L1346). The bridge's `/virtualbutton` entries are scenes, `PressAndRelease` only, and the
  unnamed ones are a Pico's templates, ignored (#L1291-L1306; PLC/tests/responses/scenes.json). So the route needs a
  physically paired Pico whose raise and lower buttons are programmed to the target zones. On a 3-button raise/lower
  Pico the programming is per button group (`Column`): every button acts on one shared zone list (S6) [code].
- **RadioRA 3.** A keypad's raise and lower buttons carry `SingleSceneRaiseProgrammingModel` and
  `SingleSceneLowerProgrammingModel` (PLC/tests/responses/ra3/device/5341/buttongroup.json#L66-L95) [fixture], so the
  bridge runs the move from the button's programming. It needs a real keypad or Pico button programmed in Lutron Designer
  to the target zones; no source shows a keypad with no hardware on RA3.
- **HomeWorks QSX.** `PhantomKeypad` is a known keypad type (PLC/__init__.py#L30) [code]: a keypad with no hardware,
  programmed in Designer. Whether `PressAndHold` on a phantom raise button ramps its zones: unsourced.

Why it isn't a general route: it moves whatever the button is programmed to, not the target entity, and DeviceSide
would have to find, for each target, a button whose programming is exactly that zone and that action (readable through
`/programmingmodel` and presets, S4 and S6), or write programming into the user's system. A held button also isn't
released if HA loses the connection mid-hold, and nothing shows what the bridge does then [inferred]. It is acceptable,
per the maintainer's decision, only where a user already has such a button: the QSX phantom keypad is the one case with
no hardware, and it needs installer programming.

## 4. `limit` and timed moves: `GoToDimmedLevel` (question 2)

- **Units.** `FadeTime` is a string `hh:mm:ss`; `pylutron-caseta` floors a `timedelta` to whole seconds
  (PLC/smartbridge.py#L1559-L1566), so HA's `transition: 0.5` is sent as `00:00:00` [code]. S13 sends hundredths
  (`00:00:00.75`) "as Lutron's own fade times are" [code]; whether the bridge honors them: unsourced.
- **Range.** Unsourced for LEAP. Lutron's application note for a timer dimmer gives a 0.75-15 s fade-on, a device
  setting rather than the protocol [search].
- **The telnet comparison.** On RA2 and QS a level takes an optional fade and delay, each `SS.ss`, `SS`, `MM:SS` or
  `HH:MM:SS`, 0 s to 4 hours; with none given the system fades over 1 s with no delay; fractions are rounded down to
  the nearest quarter second (LIP p.44, p.143) [doc]. The command summary says fractions are rounded *up* to the
  closest quarter second (LIP p.8), so the guide contradicts itself on the direction. S13's author reports that a
  telnet off with no fade took the device's own off fade and a LEAP one doesn't, so the driver sends off as a 2.5 s
  `GoToDimmedLevel` (S13, S14) [community].
- **Level.** An integer 0-100 (PLC/smartbridge.py#L395). DeviceSide's percent maps one to one; its 0.4 % floor isn't
  reachable unless the bridge takes a fraction, which no source sends. The telnet protocol takes two decimals
  (PYL/pylutron/__init__.py#L962-L968) [code], as the guide documents (LIP p.8) [doc].
- **A later command mid-fade.** Whether a new `GoToLevel`, `GoToDimmedLevel` or `Stop` stops a running fade where it is:
  unsourced, and the telnet guide doesn't say either.
- **`DelayTime`.** See section 6.

## 5. Reads: `get_attributes` (question 3)

- **What arrives.** A zone's `Level` (and `SwitchedLevel`, `FanSpeed`, `Tilt`, `CCOLevel`, color, warm dim) in a
  `ZoneStatus`, which `pylutron-caseta` writes to the device's `current_state` and passes to subscribers
  (PLC/smartbridge.py#L739-L768) [code]. Processors add `StatusAccuracy`, `Good` or `Bad` (PLC/tests/responses/hwqsx/zonestatus.json#L73-L80)
  [fixture]; the library ignores it.
- **A fresh read.** `ReadRequest /zone/<id>/status` answers `OneZoneStatus` (PLC/smartbridge.py#L928-L938); it is sent
  only at login on Caséta-shaped bridges, through the private `_request` [code].
- **Mid-move.** Whether a push or a read during a fade or a raise gives the level reached or the target: unsourced. S3's
  reads a second after a `Stop` gave mid-range levels [run-3p]. For QSX `OpenCloseStop` zones, a push may carry no level
  (PLC/README.md#L89-L94). Over telnet, Lutron says the system reports a fading dimmer's target, and "the actual level
  is not transmitted while dimming between levels" (LIP p.143) [doc]; S5 says a LEAP bridge pushes the running level,
  having once given the target [code]. A raise isn't a fade to a target, so neither settles what a read mid-raise gives.
- **How fast.** Unsourced for status. For commands, Lutron support says a Caséta bridge holds an integration command
  until a Pico it hears stops transmitting, about 2 s after a press (S10) [community]. A held Pico transmits for as long
  as it is held [inferred], so a `Raise` sent on a Pico's hold may not start until its release: the Pico-to-Caséta-load
  hold-to-dim could fail outright, while a non-Lutron button dimming a Caséta load, or a Pico dimming a non-Lutron
  light, would not meet this. Probe 1 should time it.

So `get_attributes` can read brightness (and Ketra color) from the zone, with the mid-move answer left to a probe.

## 6. Timers and auto-off (question 4)

- **`DelayTime`.** No primary source sends it: `pylutron-caseta` never does, and `pylutron` keeps a telnet delay
  commented out (PYL/pylutron/__init__.py#L976-L979) [code]. openHAB sends `DimmedLevelParameters` with `DelayTime` to
  any LEAP bridge when a delay is set (S2) [code], and Lutron's programming objects carry a delay per preset assignment
  (S4, S6) [code]. A `GoToDimmedLevel` to 0 with `DelayTime` = `duration`, after a turn-on, would be a timer held on the
  bridge, if the bridge holds it, a later command cancels it, and its range covers a useful duration: all unsourced.
  Over telnet a delay is documented and held by the system: 0 s to 4 hours, none by default (LIP p.8, p.143), with no
  effect on shades (LIP p.44, p.100) [doc]. The guide doesn't say whether a later command cancels a delayed one, so even
  there a timer as a delayed off is half sourced.
- **Auto-off, auto-on.** No source shows a per-zone auto-off or auto-on setting reachable over LEAP. Caséta's timed
  behaviors are programmed: schedules (timeclock events) and occupancy-sensor vacancy, both bridge programming, not
  settings on the load. Smart Away is a random on/off simulation (PLC/smartbridge.py#L613-L638) [code]. The Lutron app
  has per-dimmer countdown timers, 1 minute to 4 hours, that fade the light off over 10 s and restart on any other input
  ([support article](https://support.lutron.com/us/en/product/casetawireless/article/using-the-app/Using-Countdown-Timers-in-the-Lutron-App))
  [search]: a bridge-held auto-off, but no source shows its LEAP resource, and `pylutron-caseta`'s fixtures hold none.
  No known method.

## 7. Set while off (question 5)

`GoToLevel` and `GoToDimmedLevel` take one level; above 0 the load turns on. No source shows a parameter or resource
that stores a dimmer's level without turning it on, other than button and scene programming (preset assignments), which
is the user's system configuration [code]. No known method for brightness. For Ketra and Lumaris zones a color-only
`GoToSpectrumTuningLevel` or `GoToWhiteTuningLevel` (no `Level`) is shipped (PLC/smartbridge.py#L441-L480;
HA/light.py#L221-L223); whether it turns an off lamp on: unsourced.

## 8. Groups, devices, classes and transport (questions 6 and 7)

**Groups.** Areas are read (`/area`, PLC/smartbridge.py#L1348-L1364), and RA3 area status carries a current scene
(PLC/tests/responses/ra3/area/status.json) [fixture], but no source sends a command to an area or to several zones at
once. Scenes (`/virtualbutton`) are the only multi-zone call, and they run programmed levels. No native group: HA light
groups expand to their members.

**Device types** `pylutron-caseta` maps to the light domain (PLC/__init__.py#L45-L59) [code]: `WallDimmer`,
`PlugInDimmer`, `InLineDimmer`, `SunnataDimmer`, `TempInWallPaddleDimmer`, `WallDimmerWithPreset`, `DivaSmartDimmer`,
`PowPak0-10V` (device types, Caséta-shaped bridges), `Dimmed` (a processor zone's `ControlType`, whatever the device),
and `SpectrumTune` (Ketra), `WhiteTune` and `ColorTune` (Lumaris). Switches, `CCO` and `KeypadLED` are the switch domain;
fan controllers (`GoToFanSpeed`, five named speeds) are the fan domain, not built in DeviceSide; covers are out of scope.
On processors a zone has no model: the class must come from `ControlType` (PLC/smartbridge.py#L1255-L1270).

First cut of classes [inferred]:

| Class | Types | Moves | Limit, fades | Read | Timers | Color moves | Set while off |
|---|---|---|---|---|---|---|---|
| dimmer | the dimmer types above, `Dimmed`, `PowPak0-10V` | zone Raise/Lower/Stop, untested on processors | `GoToDimmedLevel` | zone `Level` | `DelayTime`, unsourced | n/a | no known method |
| tunable | `SpectrumTune`, `ColorTune`, `WhiteTune` | brightness as dimmer, untested | tuning-level fade | level, color | as dimmer | no known method (no hue or saturation move in any source) | color: probe |
| switched | switch types, `Switched`, `CCO` | n/a | n/a | level | `DelayTime`, unsourced | n/a | no known method |

**Transport.** Through the config entry, as core's entities do: `entry.runtime_data.bridge` is the `Smartbridge`
(HA/models.py#L15-L22; HA/__init__.py#L293) [code]. It has no public call for a dimmer move or a fresh zone read, so the
integration would use the private `_request` (PLC/smartbridge.py#L284-L319) pinned to a version, or upstream
`raise_zone`, `lower_zone`, `stop_zone` and `read_zone_status` to `pylutron-caseta` first [inferred].
Concurrency: one TLS connection per bridge, shared with core; each request carries a `ClientTag` and is matched to its
reply by it, with no lock, so requests from core and DeviceSide interleave on the one stream, each with a 5 s timeout
(PLC/leap.py#L37-L78, #L80-L119; PLC/smartbridge.py#L32) [code]. In what order the bridge executes them, and how many it
takes at once: unsourced. openHAB queues its sends and offers a configurable delay between them (S2).

## 9. Signal

Demand, failure modes and other implementations. None of it proves a call.

Pinned:

- **S1.** go-lutron's protocol notes: Lutron names its LEAP API and gives the documentation to approved partners only
  ([protocol.md#L3-L6](https://github.com/duncanite/go-lutron/blob/d6b0e571cc129cebb71c2bdb0eadc739ec19a225/docs/protocol.md#L3-L6),
  2026-11-27).
- **S2.** openHAB's Lutron binding, `leapbridge` (experimental): dimmer zones get `GoToLevel` or `GoToDimmedLevel` with
  `FadeTime` and `DelayTime`, and zone Raise/Lower/Stop only for shades
  ([OutputCommand.java#L163-L196](https://github.com/openhab/openhab-addons/blob/38702ed017dd8d37236d339c73cea70190105807/bundles/org.openhab.binding.lutron/src/main/java/org/openhab/binding/lutron/internal/protocol/OutputCommand.java#L163-L196);
  [Request.java#L53-L62](https://github.com/openhab/openhab-addons/blob/38702ed017dd8d37236d339c73cea70190105807/bundles/org.openhab.binding.lutron/src/main/java/org/openhab/binding/lutron/internal/protocol/leap/Request.java#L53-L62));
  keypad press and release as `PressAndHold` and `Release`, virtual buttons as `PressAndRelease`
  ([DeviceCommand.java#L88-L109](https://github.com/openhab/openhab-addons/blob/38702ed017dd8d37236d339c73cea70190105807/bundles/org.openhab.binding.lutron/src/main/java/org/openhab/binding/lutron/internal/protocol/DeviceCommand.java#L88-L109));
  a send queue with an optional delay ([README.md#L170](https://github.com/openhab/openhab-addons/blob/38702ed017dd8d37236d339c73cea70190105807/bundles/org.openhab.binding.lutron/README.md#L170));
  a bridge table (Smart Bridge LEAP only, Pro and RA2 Select both protocols, RA3 LEAP only) and "LIP is a publicly
  documented protocol, while LEAP is not" ([README.md#L87-L106](https://github.com/openhab/openhab-addons/blob/38702ed017dd8d37236d339c73cea70190105807/bundles/org.openhab.binding.lutron/README.md#L87-L106)).
- **S3.** go-lutron's run record, one Caséta Smart Bridge, LEAP 1.124: `GoToDimmedLevel` fades of 2 s and 10 s
  took that long by eye; zone `Raise`, `Lower`, `Stop` on a dimmer moved and stopped mid-range; `PressAndRelease` on a
  Pico's buttons drove its zone ([protocol.md#L185-L228](https://github.com/duncanite/go-lutron/blob/d6b0e571cc129cebb71c2bdb0eadc739ec19a225/docs/protocol.md#L185-L228),
  runs 2026-11-14 and 2026-11-22). Its command table lists Raise/Lower/Stop for any zone "as a held button does" (#L154-L161).
- **S4.** lutron-leap-js (the Homebridge plugin's library): presets hold `RaiseLowerAssignments`; a
  `DimmedLevelAssignment` has `DelayTime` and `FadeTime`; programming model types include the raise and lower models
  ([MessageBodyTypes.ts#L387-L395, #L583-L653](https://github.com/thenewwazoo/lutron-leap-js/blob/c09a4159fa6b4058debd428934e5c191b9599eee/src/MessageBodyTypes.ts#L583-L653)).
  The Homebridge plugin sends dimmers `GoToLevel` only
  ([WallDimmer.ts#L159](https://github.com/homebridge-plugins/homebridge-lutron-caseta-leap/blob/904be5ab2376888ef6b65bf21fda5f19509a7dee/src/WallDimmer.ts#L159)).
- **S5.** junohouse/lutron-caseta (a Rust driver): fakes a held key with a long fade to the end "since it needs no
  separate stop-tracking state", noting LEAP's native Raise/Lower/Stop
  ([lib.rs#L1520-L1523](https://github.com/junohouse/lutron-caseta/blob/f51e6c0cea2c90bd9c8145a8d5a76943f80ef3b6/leap/src/lib.rs#L1520-L1523)),
  and says the bridge pushes the zone's level as the fade runs, having once reported the target instead (#L1534-L1540).
- **S6.** leapctl's RA2 Select notes: preset assignments carry `Fade` and `Delay` in whole seconds; raise/lower Picos use
  `Column` button groups with one zone list for all five buttons
  ([leap-notes.md#L22-L45](https://github.com/corgicommander/leapctl/blob/44646278426293593987b6cdb1123d2b55829f28/docs/leap-notes.md#L22-L45)).
- **S7.** A Pico room-controller blueprint's own known issue: hold-repeat loops have no iteration cap and miss a release
  that arrives during a `light.turn_on`, so dimming runs on until the next press
  ([README.md#L34-L36, #L63](https://github.com/christcb03/ha-pico-blueprints/blob/8b41af8bd3344c0e7c9e500a97158c9c58a4b530/README.md#L34-L36),
  2026-10-04).
- **S8.** "Lutron Caseta Interface", post #82 (2017-07-16): the `CreateRequest` body for `PressAndHold` on a Pico raise
  button, offered as "Simulate pressing and holding", with no result or release given
  ([thread](https://community.home-assistant.io/t/lutron-caseta-interface/6229/82), fetched 2026-11-28).
- **S9.** "Another Blueprint for Lutron 5 button Pico with press and hold for dimming function" (from 2022-09-20): a
  repeat-while-held loop turns lights back on after an off "~20% of the time" (post #5, 2022-10-02); a user can't make
  the dim-down stop short of off (#30, 2025-10-30); its author says the blueprint "relies on the automation engine for
  timing-critical actions, and automations cannot always respond quickly on a busy system", and replaced it with a
  custom integration (#31, 2025-12-08)
  ([thread](https://community.home-assistant.io/t/another-blueprint-for-lutron-5-button-pico-with-press-and-hold-for-dimming-function/463052),
  fetched 2026-11-28). Other blueprints for the same need, not fetched [search]:
  [Pico core-integration](https://community.home-assistant.io/t/lutron-caseta-pico-core-integration-only/280419),
  [Pico to ZHA dimmer](https://community.home-assistant.io/t/lutron-caseta-pico-to-zha-zigbee-dimmer-control/457038),
  [advanced actions](https://community.home-assistant.io/t/lutron-caseta-pico-4-5-button-remote-advanced-actions-core-integration/579538).
- **S10.** "Slowness of Pico Remote controlling a Caseta Light vs a Hue Light", post #7 (2023-02-01), quoting Lutron
  support: a Pico press repeats its RF message for about 1.5 s, and the bridge "waits for the Pico remote to stop
  transmitting" before sending HA's integration command, about 2 s in all; other users see Caséta loads 1-1.5 s behind
  Zigbee ones on the same press (#4)
  ([thread](https://community.home-assistant.io/t/slowness-of-pico-remote-controlling-a-caseta-light-vs-a-hue-light/395814),
  fetched 2026-11-28).
- **S12.** A forum reply cites `pylutron-caseta` issue #86 (all button events) as why a dimmer's own paddle presses
  don't reach HA, "Not currently, or likely" (post #2, 2024-06-25)
  ([thread](https://community.home-assistant.io/t/lutron-caseta-wall-dimming-switch/743084), fetched 2026-11-28).
  No core issue or feature request for hold-to-dim, Pico emulation or fade times turned up [search].
- **S13.** A community Hubitat LEAP driver, v1.0.2 (2026-11-18), for Caséta bridges and RadioRA 3, QSX and Athena
  untested ([README.md#L1-L22](https://github.com/draperw/Hubitat/blob/25240d2917b30cc18e0be2baedde649957bce59f/drivers/Lutron-LEAP/README.md#L1-L22)):
  `startLevelChange` is zone `Raise` or `Lower`, `stopLevelChange` zone `Stop`, nothing to a `Switched` zone, and a
  comment says the bridge refuses `GoToDimmedLevel` on switches
  ([Bridge driver #L588-L606, #L627-L638](https://github.com/draperw/Hubitat/blob/25240d2917b30cc18e0be2baedde649957bce59f/drivers/Lutron-LEAP/Lutron%20LEAP%20Bridge%20%28User%29.groovy#L588-L638));
  `FadeTime` with hundredths (#L2821-L2828); off as a 2.5 s fade because "a fade-less GoToLevel 0 runs at the
  processor's own, faster rate"
  ([Dimmer driver #L43-L48, #L119-L125](https://github.com/draperw/Hubitat/blob/25240d2917b30cc18e0be2baedde649957bce59f/drivers/Lutron-LEAP/Lutron%20LEAP%20Dimmer%20%28User%29.groovy#L43-L48)).
- **S14.** Hubitat community: release notes add an experimental built-in LEAP integration, Caséta Picos, dimmers,
  switches and sensors only ([2.5.1](https://community.hubitat.com/t/release-2-5-1-available/165384), 2026-07-29), then
  RA3, keypads, fans and shades ([2.5.2](https://community.hubitat.com/t/release-2-5-2-available/166477), 2026-09-29);
  users call it "very beta for Ra3", with dimmers and switches working, and report it sometimes stops talking to the
  bridge until forced to reconnect; S13's author says LEAP doesn't apply the device's off fade to a fade-less off as
  telnet did ([thread](https://community.hubitat.com/t/leap-integration-for-lutron-caseta-and-ra3/167370), posts #3,
  #4, #15, 2026-11-08 to 2026-11-13). After a hub restart the built-in integration can stay disconnected, dropping
  every command with only a log warning, for days unnoticed
  ([thread](https://community.hubitat.com/t/lutron-leap-integration-does-not-resume-listening-after-a-hub-restart-2-5-3-123/167512),
  2026-11-15).
- **S15.** HA's [`lutron_caseta` page](https://www.home-assistant.io/integrations/lutron_caseta/) (fetched 2026-11-28):
  the light section offers nothing beyond on, off and level; keypads "do not reliably report when a button is
  released", so they get no `press_end`; `long_press` comes only from QSX and Athena's `LongHold`.
- **S16.** Lutron's RadioRA 3 processor specification: "Integration with professional A / V and security systems via
  Lutron's LEAP API", with no command given
  ([3691221](https://assets.lutron.com/a/documents/3691221_ENG.pdf), revision dated 08.06.25, p.1).

From search results, pages not fetched [search]:

- **S11.** Hubitat's Lutron Integrator speaks telnet to Smart Bridge Pro, RA2 Select and RA2/QS
  ([docs](https://docs.hubitat.com/index.php?title=Lutron_Integrator_v1)); its 2.3.1 release added a turn-on
  transition preference to the Caséta/RA2 dimmer driver ([notes](https://docs2.hubitat.com/en/release-notes/release-231)).
  Both pages still unreachable. Since 2.5.1 the Integrator also holds a LEAP integration (S14), and a community LEAP
  driver exists (S13), so "telnet only, never LEAP" no longer holds.

What the signal says:

- **Demand.** Hold-to-dim from a Pico is the recurring ask, met by blueprints with repeat-while-held loops (S7, S9) and
  custom integrations; dimming Caséta loads from other buttons is the same loop. Their failure modes are a missed release
  (runs on), a loop left running by a second press or turning lights back on after an off, timing on a busy HA, and
  stepping that can't stop short of off: what
  a native move replaces. A Pico reports its release; a Lutron keypad doesn't reliably (S15), so a keypad can start a
  move from HA but not be trusted to stop one.
- **Best practice elsewhere.** One other LEAP implementation offers a dimmer move: S13's `startLevelChange`, native zone
  Raise and Lower with Stop, the call this file proposes. openHAB and Homebridge stop at levels and fades; S5 fakes the
  move with a fade; S3 sends zone Raise to a dimmer as a protocol check. Lutron's own telnet protocol has the same three
  actions for dimmers (LIP p.8, p.143). Hubitat's failure reports are about the connection (S14), not the move: a
  dropped connection is the failure a DeviceSide move would have to raise rather than log.
- **Broad appeal.** `lutron_caseta` is on 13,933 of 745,043 active installs (1.9 %, rank 168), core `lutron` on 255
  (rank 752), against Shelly's 20.2 % (rank 33), TP-Link's 10.9 % (rank 58) and Z-Wave JS's 6.3 % (rank 87)
  (`analytics.home-assistant.io/current_data.json`, fetched 2026-11-28). CONTRIBUTING's Development principles ask that
  a feature be supportable by at least one top-30 integration, and admit a new integration that meets that criterion.
  Hold-to-dim is a feature DeviceSide already ships elsewhere, so the question is the integration, and `lutron_caseta`
  is far outside the top 30: its case rests on the feature gap and the demand above, not on its install share.

## 10. Probes for a contributor with a bridge

Each names the decision it takes.

1. **Zone Raise/Lower/Stop on a dimmer, per bridge type** (Smart Bridge, Pro or RA2 Select, RA3, QSX): time a full sweep
   from 1 to 100 and back, and record what each command answers, the pushes during the move, and a read after `Stop`.
   Decides whether moves ship on that bridge type, the fixed sweep `sweep_time` clamps to, and `stop`'s confirmation.
   Repeat it with the `Raise` sent while a Pico paired to the same bridge is held: decides whether a Pico can drive a
   move on that bridge's own loads (S10).
2. **Raise from off, Lower to the bottom.** Decides whether a move from off is sent, refused or preceded by a turn-on, and
   whether `lower_brightness` can turn a light off.
3. **`Stop` (and a new `GoToLevel`) during a `GoToDimmedLevel` fade.** Decides whether `limit` ships, and whether the
   fade route (which honors `sweep_time`) replaces zone Raise.
4. **`GoToDimmedLevel` with `DelayTime`**: is it held on the bridge, does a later command cancel it, what range does it
   take? Decides whether `turn_on_for` and `turn_off_for` get a method.
5. **A color-only tuning command to an off Ketra or Lumaris zone.** Decides `set_attributes` color while off.
6. **A fractional `FadeTime` and `Level`.** Decides sub-second fades and the brightness floor.
7. **`PressAndHold` then `Release` on a QSX phantom keypad's raise button.** Decides whether the virtual-button route
   serves QSX where probe 1 fails.
8. **A Lutron app countdown timer on a Caséta dimmer**: read the zone's and device's resources before and after
   setting one, to find where the bridge keeps it. Decides whether `set_auto_off` gets a method.

## 11. Recommendation

The gap pass strengthens the case for the call and weakens the case for the integration. For the call: besides S3's
run, a community Hubitat driver ships zone Raise, Lower and Stop to dimmer zones on Caséta and RadioRA 3 (S13), and
Lutron documents the same three actions for dimmers on its telnet systems, each running to the end until a Stop
(LIP p.8, p.44, p.143). Still open: the rate, Raise from off, a read mid-move, and whether `Stop` halts a fade. Against
the integration: `lutron_caseta` is on 1.9 % of installs, rank 168; nobody on the project has a LEAP bridge; and the
lead case, a Pico dimming a Caséta load, may not work at all if the bridge holds the `Raise` until the Pico stops
transmitting (S10, section 5). The maintainer chooses; the two options are below.

**Option A: build part, all in Labs.** What the integration would carry:

- **`raise_brightness`, `lower_brightness`, `stop`** on the dimmer class (and brightness on the tunable class) as zone
  `Raise`, `Lower`, `Stop`, on the bridges a source names: Caséta (Smart Bridge and Pro, the Caséta branch) and
  RadioRA 3 (S3, S13). Labs, the sourced-call route (`docs/evidence.md`, In Labs): an implementation ships the call and
  no real device of ours has passed. `sweep_time` is clamped to the device's fixed sweep and reported as `clamped_to`
  once probe 1 measures it; until then the integration PR decides between that and dropping the field. Calls go
  through the config entry's `Smartbridge`, never `raise_cover`, which writes a false level, and a dropped connection
  raises, not logs (S14). Until probe 1's Pico case runs, the integration's page says a Pico on the same bridge may
  only start a move once released (S10).
- **`get_attributes`** brightness (and Ketra color) from a zone status read, which every move needs.
- **Not built yet:** moves on QSX and Athena (S13 offers them untested) and RA2 Select (no source names it); `limit`
  (probe 3); `turn_on_for` and `turn_off_for` (probe 4); color while off (probe 5).
- **No known method:** `set_auto_off`, `set_auto_on` and their clears (the app's countdown timer has no known LEAP
  resource, probe 8); brightness while off; hue and saturation moves; native groups.
- **Virtual Pico route: not built.** On Caséta and RA2 Select it needs a physically paired Pico, on RA3 a real button,
  and on QSX a phantom keypad programmed by an installer; it moves the button's programming, not the target. It returns
  only for a bridge type where probe 1 shows zone Raise refused, through probe 7.
- **What it costs:** a maintainer for `IntegrationInfo.maintainers` who has no bridge to triage a report on; the private
  `_request` pinned to a `pylutron-caseta` version until upstream adds public zone calls; the `to_lutron_level` defect
  in `docs/defects.md`.

**Option B: defer.** The `docs/deferred.md` entry:

> ## Lutron LEAP integration
>
> A `lutron_caseta` integration: `raise_brightness`, `lower_brightness` and `stop` as LEAP zone Raise, Lower and Stop
> on dimmer zones, with `get_attributes`, in Labs on Caséta bridges and RadioRA 3
> (`docs/research/2026-11-28-lutron-leap-call-patterns.md`, Option A).
>
> **Why not now:** `lutron_caseta` is on 1.9 % of active installs (rank 168), nobody on the project has a LEAP bridge
> to maintain it, the move rests on one third-party run and one community driver, and a Caséta bridge may hold a move
> sent on a Pico's hold until the Pico stops transmitting (research, section 5).
>
> **Revisit when:**
> - a contributor with a LEAP bridge offers to maintain the integration, or records probe 1's result;
> - `pylutron-caseta` adds a public dimmer raise, lower or stop, or core `lutron_caseta` ships one;
> - an issue or HA feature request asks DeviceSide for hold-to-dim on Caséta or RadioRA 3 loads;
> - `lutron_caseta` enters the top 100 integrations on analytics.home-assistant.io;
> - Lutron publishes LEAP documentation for zone commands.

**Which I'd pick: B.** The call now has enough behind it for Labs, so evidence no longer decides this; ownership and
reach do. A Labs integration whose maintainer can't reproduce a report has only the "stop fixing, make it not built"
path, and at rank 168 the share of users it reaches is small next to the work of a new transport. The first reopen
condition is the one that changes both: a contributor with a bridge. If the maintainer weighs the feature gap above the
install share, Option A is ready to build as written.
