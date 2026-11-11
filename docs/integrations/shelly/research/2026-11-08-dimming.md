# Shelly stoppable dimming: upstream research (2026-11-08)

Question: what does upstream know about stoppable dimming transitions on Shelly lights, so DeviceSide's
Shelly adapter (`integrations/shelly/rpc.py`, today `Light.Set` + `transition_duration`) doesn't reinvent it?

Marks: **[V]** verified in a primary source (vendor docs, source, issue tracker). **[U]** unverified: community
excerpt, secondhand, or inference. **[GAP]** nobody documents it; needs a live device (the rig).
Three research fragments were merged; contradictions between them are in "Conflicts" below.

## Bottom line

1. Shelly Gen2+ has **two unrelated mechanisms**. `Light.Set {transition_duration}` is a fixed-duration fade to a
   target. `Light.DimUp` / `DimDown` / `DimStop` is an open-ended ramp (the Zigbee Move/Stop analogue).
2. **Nothing official documents stopping a `transition_duration` fade.** `DimStop` is documented for
   DimUp/DimDown only, but it halts a timed fade on a Gen3 bulb (see "Rig results").
3. Best public working reference: **`nohat/dynamic_dimming`** (HACS, v0.7.0). It uses `DimUp`/`DimDown`/`DimStop`
   for move/stop and claims `DimStop` also halts `Light.Set` fades. **[U]** that claim comes from its code and
   README, not from a device test.
4. **No upstream path will give us this for free soon.** aioshelly has no helpers for these calls; HA core's
   Shelly light never calls `DimStop`; core PR #183698 (`light.stop_transition`) is open and names Shelly only as a
   future follow-up.
5. The rig has since answered the core questions on a Gen3 RGBCCT bulb (see "Rig results"): `DimStop` halts both
   mechanisms, a new `Set` restarts a fade from the current level but does not cancel a `DimUp` ramp, and `DimStop`
   does not jump.

## Learnings for dimming Gen2+ Shelly lights

Shelly documents a way to start and stop an open-ended ramp, but none to stop a timed fade. Most of what a
stoppable dim would lean on is unverified until the rig tests it.

**Solid (vendor docs or source)**
- Two unrelated mechanisms: `Light.Set {transition_duration}` (fixed-length fade) and `DimUp`/`DimDown`
  (`fade_rate` 1-5) ended by `DimStop`, which leaves the light at the level reached.
- `Dim*` needs fw >= 1.4.0 (ProDimmer 0/1-10V PM: >= 1.5.0); the DALI Dimmer Gen3 returned 404 for `DimUp` early on.
- RPC duration is seconds, HTTP is milliseconds; HA core floors RPC at 0.5 s and we copy that.
- Always send `brightness` with `Light.Set {on:true}`, or the device restores its last stored level.
- `Light.GetStatus` shows a `transition` object only while a fade runs.
- aioshelly has no `Dim*` helpers; HA core's Shelly light never calls `DimStop`.

**Working patterns**
- Hold-to-dim: `DimUp`/`DimDown` on press, `DimStop` on release (Shelly's own pattern; forum scripts match).
- Reference implementation: `dynamic_dimming` (HACS) uses `Dim*` for move/stop and `Light.Set` with
  `transition_duration` for timed fades, and uses `DimStop` to halt fades **[U]**.
- No client-side step loops: HA core's maintainer rejected emulating fades that way (#45310).

**Unverified or undocumented**
- Does `DimStop` halt a timed fade? Vendor docs silent; only `dynamic_dimming` assumes so.
- Does a new `Light.Set` replace or restart a running fade? One Gen1 forum post only.
- Does a new command interrupt a `DimUp`/`DimDown` ramp? One forum member's claim.
- What `brightness` reports mid-fade, and whether `NotifyStatus` sends intermediate levels.
- Whether RPC ramps stop at 0% / 100% (documented for button mode only).

**Sharp edges**
- Gen3 `DimStop` jump to 100% (up) or minimum (down): one user, no firmware version, never retested.
- Pro Dimmer 2PM steps and skips on any rate except its fixed ~10 %/s; reported native `fade_rate` speeds are
  5, 7, 10, 15, 20 %/s (one user).
- A longer device-side default may override a shorter per-call duration (cause unconfirmed, see Conflicts).
- Older Gen3 firmware reset the default transition after reboot and rejected sub-0.5 s values (fixed by 2.0.1).
- `min_brightness_on_toggle` and LED flicker at low levels can stop a ramp short of 0.

**Implication for DeviceSide `stop` / `ramp` on Shelly:** before the rig, `DimUp`/`DimDown`/`DimStop` looked like
the stoppable ramp. The rig showed the ramps are stepped and a timed `Light.Set` fade stops cleanly on `DimStop`, so
DeviceSide fades with `Set` and stops with `DimStop` ("Rig results").

## Mechanisms

### A. `Light.Set` + `transition_duration` (fixed fade)

- Params: `id`, `on`, `brightness` 0-100, `transition_duration` (seconds), `toggle_after` (seconds, needs `on`),
  `offset` (-100..100, exclusive with `brightness`), `tag`. **[V]** Light component docs.
- HTTP form `/light/{id}?transition=` is **milliseconds**, 500-10,800,000, i.e. 0.5 s to 10,800 s. **[V]**
  RPC seconds range is presumably the same; the RPC docs do not state it. The 0.5 s floor on the RPC side is HA
  core's (`RPC_MIN_TRANSITION_TIME_SEC`), which DeviceSide copies. **[V]** `rpc.py:28`.
- `Light.GetStatus` carries a `transition` object only while a fade runs:
  `{target: {output, brightness}, started_at, duration}`. **[V]**
- **[GAP]** Whether top-level `brightness` is the instantaneous level or the target during a fade. Whether
  `NotifyStatus` emits intermediate levels. HA core never reads the `transition` object, and sees pre-fade
  brightness until a push arrives.
- Config `limits.transition` = `[min, max]` from `Shelly.GetComponents` (fw >= 2.0.0, some devices only), no values
  published. **[V]**
- Device-side config `transition_duration` is a default. Gen3/Gen4 (fw 1.7.1) reportedly ignore a shorter per-call
  value when the device default is longer (workaround: set device default to 0.5 s). **[U]** HA #159526, see Conflicts.
- With `transition_duration` set, `min_brightness_on_toggle` is **not** applied (fw 1.1.0). **[V]**
- `Light.Set {on:true}` with no `brightness` restores the device's **last stored** level, not the HA-cached one
  (HA #170017, Wall Dimmer US). Always send `brightness` when targeting a level. **[V]**
- Fixed since: 1.0.7 (Set with transition set brightness 0%), 1.3.0 (transition notifications), 1.5.0 / 1.6.0
  (Gen3 transition lost after reboot / power cycle), 2.0.0 (Gen4 too-long transition), 2.0.1 (Gen3/Gen4 accept 0).
  **[V]** changelog.

### B. `Light.DimUp` / `DimDown` / `DimStop` (open-ended ramp)

- `DimUp`/`DimDown` take `id` and optional `fade_rate` 1-5 (5 fastest; default config `button_fade_rate`, 3).
  `DimStop` takes only `id`. All return `null`. Same methods on CCT, RGB, RGBW. **[V]**
- Added fw 1.4.0 (2024-07-31) for Light/RGB/RGBW; fw 1.5.0 (2025-02-20) for ProDimmer 0/1-10V PM. **[V]**
- Shelly DALI Dimmer Gen3 returned 404 for `DimUp` in early firmware; current status unknown. **[U]**
- Documented stop at 100% / 1% applies to **button** mode (`in_mode` dim/dual_dim). **[GAP]** for RPC calls.
- `fade_rate` to %/s mapping is undocumented. Wave docs hint ~10 %/s at the slowest (about a 10 s full sweep). **[U]**
- Shelly's own hold-to-dim script (shelly.guide): `long_push` -> `DimUp` or `DimDown` (direction toggled in script
  state), `btn_up` -> `DimStop`. Same shape as DeviceSide's raise/lower + stop.
- Gen1 (Dimmer 1/2): HTTP `/light/0?dim=up|down|stop&step=N`, `transition` 0-5000 ms. Bulb/Vintage/Duo/RGBW2 have no
  `dim`. Gen1-style `dim=up` does not work on Gen2+ Pro Dimmer (use RPC). **[V]** Gen1 docs, Pro Dimmer part **[U]**.

## Stopping and interrupting: what is known

| Situation | What upstream says | Status |
|---|---|---|
| `DimStop` during DimUp/DimDown | Stops at the current level (documented) | **[V]** |
| `DimStop` during a `transition_duration` fade | `dynamic_dimming` uses it for both | **[U]**, vendor docs silent |
| New `Light.Set` during a fade | Community: replaces it and jumps to the new target immediately (a Gen1 Dimmer 2 report, shelly-forum.com thread 7730, and a shelly.guide excerpt) | **[U]**, Gen1 evidence only; the thread is one post, no reply or staff answer, and covers a brightness change during a turn-on fade |
| New command during DimUp/DimDown | Forum topic 1498 (read in full; a member, not Shelly staff, Oct 2024): ramp stops on DimStop "or another command"; he warned a script sending calls perpetually can abort dimming | **[U]** |
| Stop a fade by `Light.Set` to current level | Racy: the fade keeps moving during the `GetStatus` round trip, so the level read is stale and the set can snap | inference, **[U]** |
| Read level right after `DimStop` | Nobody documents what status shows | **[GAP]** |

Related fix: fw 2.0.0 "BTHomeControl: Stop running dimming on new Set request" (that subsystem only; it implies
the behavior is not universal).

## Sharp edges worth designing around

- **Gen3 Dimmer `DimStop` jump:** a first-hand report (forum topic 2959, 2025-01-25, read in full) says `DimStop`
  sends the Gen3 Dimmer to 100% when dimming up and to the minimum when dimming down; the same user still called
  it bugged on 2025-02-09 and scripted around it. Firmware version not given; not in the changelog; never retested
  on later firmware in the thread. **[U]** (single user). Test on fw >= 2.0.1.
- **Stepping and end jumps:** the same thread reports Pro Dimmer 2PM ramps run at a fixed internal ~10 %/s, so
  any other rate (including native `fade_rate` and `transition_duration`) steps or skips; Gen3 fixed the stepping
  but still jumped to min/100% on long ramps. Same user's list of native `fade_rate` speeds: 5, 7, 10, 15, 20 %/s
  (assumed to be rates 1 to 5). **[U]** single user.
- **Device transition default resets:** Gen3 config `transition_duration` reverts to 3 s after a reboot or a
  Bluetooth toggle (fixed in fw 1.5.0 / 1.6.0). Workaround then: `Light.SetConfig` at startup. Via RPC, per-call
  values under 0.5 s were rejected on Gen3; 0 needed omitting it and setting config to 0 (fixed in 2.0.1). **[U]**
- **Request flooding: not applicable.** Forum topic 8162 (read in full) is a **Z-Wave** Wave Pro Dimmer driven
  through Z-Wave JS, where a reply said the dimmer has a fixed 3 s command dimming. It says nothing about Wi-Fi
  RPC. Earlier versions of this note treated it as a Gen2+ finding; that was wrong.
  Still prefer one fade or one DimUp/DimStop pair over a client-side step loop (HA core's stance, #45310).
- **Client-side step loops are rejected upstream:** HA core maintainer declined to emulate transitions with a
  software loop (#45310). **[V]**
- **Off-to-scene jump:** from Off, sending a scene ignores `transition` and jumps (Tasmota #19643, Dimmer 2); same on
  original Shelly firmware. **[U]** for current Gen2+.
- **Low-end flicker / floors:** some LEDs flicker below 5-7%; Gen3 default `min_brightness_on_toggle` 3%; the ramp
  can stop at the floor rather than reach 0. `range_map` (not `brightness_min/max`, which do not exist) remaps the
  output range. **[V]/[U]**
- **ProDimmer2PM:** fw 2.0.0 fixed dimming on one channel being interrupted by a command to the other. **[V]**
- **Auth:** `dynamic_dimming` talks HTTP directly with digest auth, 3 s timeout, because aioshelly lacks helpers.
  We should prefer the existing authenticated RPC path (`call_rpc("Light.DimStop", ...)`).

## Upstream status (HA / aioshelly / others)

- HA core `shelly/light.py` (RPC): `Set` with `transition_duration = max(t, 0.5)`; same floor on turn_off; no
  `DimStop` anywhere. Gen1: ms, capped at 5000. **[V]** source.
- PR #183698 "Add light.stop_transition" (open, 2026-09-30; confirmed open today): adds
  `LightEntityFeature.STOP_TRANSITION = 64`; freezes the light at its reached level; no-op when idle; never turns
  off; names Shelly as a follow-up. Blocked on architecture discussion #1094. **[V]**
- Architecture discussion #1094 (`light.move` / start-stop dimming): old, no decision. **[V]**
- aioshelly: no `Light.Set`/`DimUp`/`DimDown`/`DimStop` helpers (only `ledstrip_set`). **[V]**
- ShellyForHASS (Gen1): nothing relevant.
- openHAB: Gen1 `dim=up/down/stop/cycle` mapped; Gen2+ goes through brightness `Light.Set`. ioBroker: `dim=` added
  in #248 after the dev found the announced endpoint was missing from settings JSON (direct HTTP worked). **[U]**
- HA #139367 (fixed, PR #139601): `brightness=0` with `transition_duration` caused a `TypeError` in aioshelly
  `wsrpc.py` frame merge on Gen3. **[U]** from one fragment.
- Zigbee analogue: Move to Level = `Light.Set` with duration; Move = `DimUp/Down`; Stop = `DimStop`. Z2M:
  `brightness_move_up/down`, `brightness_stop`. Zigbee Stop leaves the light at its current level.

## Conflicts between sources (unresolved)

1. **Does `DimStop` stop a `transition_duration` fade?** HA-core fragment says yes ("confirmed by
   `dynamic_dimming`"); vendor fragment says undocumented. Resolution: only code/README evidence, no device test.
   Settled by the rig: it does (see "Rig results").
2. **HA #159526 root cause.** One fragment: device default overrides a shorter HA value. Another: the reporter later
   said the cause was "something else on my end" and it was closed not planned. The first claim may be wrong. I
   re-read the issue: the thread shows only bot comments, so I could not settle it. Treat as **[U]**.
3. **HA #45310.** One fragment says HA added Gen1 transitions after fw 1.11.0 and the list
   `MODELS_SUPPORTING_LIGHT_TRANSITION` grew; the other says it closed with no code change. The thread I read shows
   the maintainer refusing a software loop and filing a firmware request; the later outcome is not in what I read.
   Irrelevant to Gen2+; ignore.
4. **Auto-stop at 100%/1%.** Community fragment put it under RPC DimUp/DimDown; the vendor docs scope it to
   button mode. Vendor wins: **[GAP]** for RPC.
5. **`brightness_min`/`brightness_max`:** appeared in one search result; vendor fragment found the real field is
   `range_map`.

## Rig results (2026-11-08)

One Shelly Multicolor Bulb Gen3 (`RGBCCT` component, fw 2.0.3), through the rig as a probe, one run each. Everything
here is **[V]** for that device and firmware only. Other components and firmware are untested.

| Question | Result |
|---|---|
| `DimStop` during a `transition_duration` fade | **Halts it.** A 10 s fade stopped at 3 s held at 34% for 8 s. |
| New `Set` mid-fade | **Restarts from the current level, no jump.** A fade to 20% over 4 s ran smoothly from 34%; a 0.5 s one went ~32% to 20%. |
| New `Set` mid-`DimUp` | **Does not cancel the ramp.** After `Set 10` the ramp resumed (20, 30, 40, 50). Only `DimStop` stops it. |
| Readback mid-fade | Top-level `brightness` advances continuously (~3.5%/s on a 10 s fade); `transition` holds `target`, `started_at`, `duration`. |
| Readback during `DimUp`/`DimDown` | Moves in coarse steps (5, 10 or 20 points) about once a second. |
| `DimStop` jump on Gen3 | **None** on 2.0.3: level held from the moment of the stop, 1 s later, for `DimUp`, `DimDown` and timed fades. |
| Ramp end-stops | `DimDown` stops at 1% and stays on, never off. `DimUp` stops at 100%. `DimUp` at 100% returns RPC error -108 "Reached the maximum 100 of brightness". |
| `fade_rate` | 1 ~4 %/s, 3 ~10 %/s, 5 ~18-23 %/s (a few samples each). No `fade_rate` uses the config value. One run reached 80% in 2 s at the default rate, two runs of ~10 %/s did not; unexplained. |
| Device default vs per-call transition | **Per-call honored** (1 s ran in 1.0 s with the default at 3 s and 5 s). HA #159526 does not reproduce here. |
| `Set` with no `transition_duration` | Looked instant even with the default at 5 s (the 5% start level was not read back). |
| Ranges | Per-call `transition_duration` 0.5 to 10800 s (0 rejected, error -103). Config default 0 to 5 s. |

Still open: `Light` and `RGBW` components, dimmers (ProDimmer, DALI), other firmware, the unexplained fast `DimUp`.

### Second probe: `DimStop` on timed fades, repeated (2026-11-08)

Same bulb and firmware, default transition 3 s. 10 s fades from 5% to 100% and back, stopped at 1 s, 5 s and 9.5 s,
two runs each, plus a stop 0.05 s after the `Set`; 8 s fades sampled every 0.2 s; HA's entity state sampled alongside.

| Question | Result |
|---|---|
| `DimStop` halts a timed fade | **Every run, both directions**, early, mid, late and right after the `Set`. The level then holds. |
| How soon | Within ~0.1 s of the send when nothing else is polling the device: the halt level was within 1 point of the linear interpolation at the stop (six runs). Its round trip is ~0.05 s. |
| Under load | With a second client reading `GetStatus` every 0.2 s, round trips reached 0.7 s and fades ran on 0.3 to 1.8 s past the stop (up to 11 points). One `GetStatus` read after the stop still gives the exact halt level. |
| `transition` on stop | **Clears**; `brightness` is settled at the first read after the stop's reply. |
| Readback mid-fade | Matches the linear interpolation from the `Set`, within a point or two (a start lag of ~0.1 s). |
| A completed fade | Ends **exactly** at the target (73, 17, 20 read back as sent). |
| `DimStop` with no fade | Accepted (null), changes nothing, on or off. |
| What HA sees | The start, sometimes one mid-fade update, then the end or the halt level ~0.2 s after the device settles. Mid-fade `brightness` in HA is stale. `deviceside.get_attributes` reads the device's own level. |
| `Set {on:false, transition_duration}` | **A native soft off**: fades to off over the duration, and keeps the stored level (a plain on came back at 80). `DimStop` during it leaves the light **on** at the halt level. Adding `brightness` stores that level for the next on. |
| `Set {on:true, brightness:0, transition_duration}` | Fades to 0 but stays **on at 0%**: not a way to turn off. |
| Fade to 1% then `on:false` | Works, but the stored level becomes 1%: worse than the native soft off. |
| `Set {on:true, brightness, transition_duration}` from off | Fades in **from 1%**, not from the stored level: no preset needed. |

So a stoppable fade is one `Set` with `transition_duration`, halted by `DimStop`, with the halt level read back by
`GetStatus`. Lowering to 0 is `Set {on:false, transition_duration}`.

## Primary sources

- Light: https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Light/ (CCT, RGBW siblings)
- Changelog: https://shelly-api-docs.shelly.cloud/gen2/changelog/
- Notifications: https://shelly-api-docs.shelly.cloud/gen2/General/Notifications/
- Gen1: https://shelly-api-docs.shelly.cloud/gen1/
- shelly.guide hold-to-dim: https://shelly.guide/en/application-guide/dimming-with-input-module/
- HA core: `components/shelly/light.py`, `const.py`; issues #159526, #170017, #139367, #45310; PRs #159527, #183698,
  #139601; architecture discussion #1094
- `nohat/dynamic_dimming` (HACS)
- ioBroker.shelly #248, #507; Tasmota discussion #19643; node-red-contrib-shelly #165
- Shelly forum topics, read in full with Playwright (WebFetch gets HTTP 403, so use a browser):
  - 1498 https://community.shelly.cloud/topic/1498-api-call-to-startstop-dimming/
  - 2959 https://community.shelly.cloud/topic/2959-rd-please-fix-the-internal-dimming-speeds/
  - 8162 https://community.shelly.cloud/topic/8162-changing-brightness-for-dimmer-every-500ms-completely-ddoses-device/ (Z-Wave, not relevant)
  - 7730 https://shelly-forum.com/thread/7730-transition-cancels-when-a-brightness-change-happens-mid-turn-on-transition/
    (read in full; one post, Gen1 Dimmer 2 on fw 1.9.4 via HA CoIoT, no replies; earlier notes said fw 1.8.5, wrong)
