# Shelly color transitions: upstream research (2026-11-08)

Companion to [shelly-dimming-research.md](shelly-dimming-research.md), which covers brightness and whose findings
are not repeated. Question: what does upstream know about hue and saturation transitions (fades, stoppable moves)
on Shelly Gen2+ color lights?

Marks: **[V]** verified in a primary source read in full. **[U]** unverified, excerpt-only or inference.
**[GAP]** undocumented; needs a live device (the rig).

## Bottom line

1. **No native hue or saturation move exists on Shelly Gen2+.** `DimUp`/`DimDown`/`DimStop` on RGB, RGBW and RGBCCT
   change brightness only (plus the white level on RGBW/RGBCCT) and never touch `rgb`. **[V]**
2. **The color API is plain RGB.** `rgb` is `[r,g,b]` 0-255; there is no hue, saturation or XY parameter. **[V]**
3. **`transition_duration` on `RGB/RGBW/RGBCCT/CCT.Set` fades color and brightness together** to one fixed target
   ("from current brightness level and color to desired ..."). It is a timed fade, not an open-ended move. **[V]**
4. **No documented stop for a color fade.** `DimStop` is documented for `DimUp`/`DimDown` only. Whether it also halts
   a timed color fade is the same unverified `dynamic_dimming` claim as for brightness. **[U]**
5. **Upstream has nothing to reuse.** HA core's Shelly light never calls `Dim*`, takes color only as RGB (HA's light
   helper converts hs/xy before the platform sees it), and aioshelly has no color or `Dim*` helpers beyond
   `call_rpc`. **[V]**
6. **Fit with DeviceSide's design:** the principle "On the device" (`docs/design.md`) rules out HA-side loops, and
   Hue already has "no hue moves" because a hue rotation isn't a straight line in one command. A Shelly hue move
   hits the same wall (see "Implications").

## Reading state during a fade

`RGB.GetStatus` (and siblings): top-level `rgb` is documented as the "current" level and, in the docs' example,
differs from `transition.target.rgb` (`[0,0,127]` against `[20,30,40]`). So the instantaneous color is readable
mid-fade. **[V]** for the documentation; **[U]** that a real device advances it continuously, which nobody has
measured. The same question for brightness is still **[GAP]** in the dimming note. `transition` carries
`target.rgb` (RGBW adds `white`, RGBCCT adds `ct` but not `mode`), `started_at`, `duration`. **[V]**

## Component notes

| Component | Color params on `.Set` | `transition_duration` fades | `Dim*` affects |
|---|---|---|---|
| RGB | `rgb`, `brightness` | rgb + brightness | brightness |
| RGBW | `rgb`, `white` (0-255), `brightness` | rgb, white, brightness | brightness + white level |
| RGBCCT | `rgb`, `ct`, `mode` (`rgb`/`cct`), `brightness` | color or ct, per mode | brightness + white level |
| CCT | `ct`, `brightness` | ct + brightness | brightness |

All **[V]** (component docs). `Dim*` on RGB/RGBW arrived in fw 1.4.0; the CCT and RGBCCT firmware gate is **[GAP]**
(the 1.4.0 changelog names Light, RGB and RGBW only).

- RGBCCT `mode` must accompany color params to switch; `rpc.py:light_params()` already sends `rgb` or `cct`
  accordingly. **[V]** (existing code, HA core does the same.)
- HA core passes `rgb` through unconverted and takes RGBW's fourth value as `white`, with no white derivation from
  color. **[V]** (source). Core has no special handling for saturation 0 or hue wrap.
- Gen1 is out of DeviceSide's scope. For the record: RGBW2 `/color/0` has a one-shot `transition` (0-5000 ms); the Bulb
  page lists none, and its effects are preset animations.

## Color interpolation space: **[GAP]**

No vendor document, community source or staff statement says how the device interpolates during a fade (linear RGB,
gamma-corrected, or along a hue path). Community practice assumes linear RGB. That matters:

- **Saturation** change at a fixed hue is a straight line in RGB, so a single fade is correct under linear RGB.
  **[U]** (inference.)
- **Hue** change is not: red `[255,0,0]` to cyan `[0,255,255]` passes through grey `[127,127,127]`. A fade-to-end
  cuts across the wheel; staying on it needs waypoints (steps of up to ~15 degrees). **[U]** (inference.)

Shelly's own color-cycling example (`ALLTERCO/shelly-script-examples`, `rgbw/color.shelly.js`, "under development",
read in full) does exactly the waypoint thing, with hand-picked saturated RGB targets, `transition_duration: 2` every
4 s, and no stop. **[V]** shelly.guide's "RGBW Loop Controller" scripts work the same way, but their source was not
retrievable. **[U]**

## Known bugs and sharp edges (color)

- HA #158788 (Plus RGBW PM "mixes white into RGB"): maintainer could not reproduce; closed stale. **[U]**
- node-red-contrib-shelly #189: `RGBW.Set` works only in color mode; in white mode the device exposes `Light`
  components instead. **[U]**
- Mode switch (`rgb` to `cct`) mid-fade, and white-channel flash or drift without an explicit `white: 0`: **[GAP]**.
- A new `RGB.Set` mid-fade: jump to the new target, or restart from the current color? **[GAP]** (the brightness
  analogue rests on one Gen1 report; see the dimming note).
- Per-channel gamma and LED low-duty flicker: **[GAP]**; `range_map` remaps the output range. **[V]**
- fw 1.5.0 fixed "RGB/RGBW color picker jumps ..." (pre-1.5.0 only). **[V]**
- HA core PR #189831 (open) adds a separate brightness-only entity for the RGBW white channel; PR #155197 (merged)
  added the RGBCCT entity. No color-transition issues exist upstream. **[V]**
- community.shelly.cloud has no thread on Shelly color cycling or transitions (searched directly). **[V]**

## Other platforms (conceptual comparison)

- **Zigbee:** Z2M `hue_move` / `saturation_move` (rate, stopped with `0`) and ZHA's equivalents are device
  primitives; the hub only starts and stops them. Shelly has no equivalent. **[V]**/**[U]** (stop-with-0 for hue
  specifically is not shown on the device page).
- **Tasmota:** has `HSBColor` and device-side hue-cycle `Scheme`s, and `Dimmer !` stops a brightness fade. Shelly
  exposes only RGB channels plus `transition_duration`. **[V]**
- **openHAB Shelly binding:** Gen1 `hsb` channel and named colors; no transition or move commands. **[U]**

## Implications for `raise_hue` / `lower_hue` / `raise_saturation` / `lower_saturation` on Shelly

Both research passes proposed a client-side loop (an mJS script stepping HSV to `RGB.Set` per tick, stopped by a
`GetStatus` read plus `RGB.Set`). **That conflicts with `docs/design.md`**: "No HA-side timers, polling or
emulation", and deploying a script onto the user's device is a larger step still. Reconciled:

| Action | Shape that fits the design | Open |
|---|---|---|
| `raise_saturation` / `lower_saturation` | One `RGB.Set` fade to the saturation endpoint at the current hue, duration scaled from `sweep_time` and distance | Stop: `DimStop`, or `GetStatus` then `RGB.Set` at the read color (racy); interpolation space |
| `raise_hue` / `lower_hue` | Not expressible as one command (same reason Hue has none). Refuse, like Hue, unless the maintainers choose to allow emulation | Design decision for Jason, not research |
| `stop` | Whatever the rig shows works for brightness, extended to color | See experiments 1-4 |

Brightness findings (use `DimUp`/`DimDown`/`DimStop`) are in the dimming note. RGBCCT in `cct` mode: a saturation
move needs `mode: "rgb"`, or the call should be refused; behavior mid-fade is **[GAP]**.

## Rig experiments for color (add to the brightness list)

1. Fade `RGB.Set {rgb, transition_duration: 20}`; poll `RGB.GetStatus` every 2 s. Does top-level `rgb` advance
   continuously, or only at the end? (Also settles the brightness readback gap.)
2. Does the fade interpolate in linear RGB? Fade green to red over 10 s, sample `rgb` at the middle. Then red to cyan:
   does it pass through grey?
3. `RGB.DimStop` during a color fade: does it stop the color, only brightness, or nothing?
4. Stop by `GetStatus` then `RGB.Set` at the read color with no duration: how far does it snap?
5. A new `RGB.Set` mid-fade: instant jump or restart from the current color?
6. `RGBW.DimUp`/`DimDown`: `rgb` untouched, `brightness` and `white` move?
7. RGBW white channel: does it drift across a color fade without an explicit `white: 0`?
8. RGBCCT: `mode` switch mid-fade; saturation fade while in `cct` mode.
9. Saturation fade at fixed hue: does the visible hue stay constant (the straight-line assumption)?
10. If emulation is ever allowed: minimum `RGB.Set` interval before the device queues or drops calls.

## Sources

- Component docs: https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/RGB/ (also `/RGBW/`, `/CCT/`,
  `/RGBCCT/`), changelog https://shelly-api-docs.shelly.cloud/gen2/changelog/
- Gen1: https://shelly-api-docs.shelly.cloud/gen1/
- HA core `components/shelly/light.py`, `const.py`, `utils.py`; PRs #155197, #189831; issues #158788, #76067
- aioshelly `rpc_device/device.py`
- Shelly script example: https://github.com/ALLTERCO/shelly-script-examples/blob/main/rgbw/color.shelly.js
- node-red-contrib-shelly #189: https://github.com/windkh/node-red-contrib-shelly/issues/189
- Z2M `hue_move`/`saturation_move`: https://www.zigbee2mqtt.io/devices/929003053001.html; Tasmota commands:
  https://tasmota.github.io/docs/Commands/#light
- community.shelly.cloud topic 1498 (brightness `Dim*`), 15416 (RGBW PM preset bug)
