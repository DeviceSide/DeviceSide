# Shelly internals

How the Shelly adapters address a target, what they send and read back, and what was measured on real hardware.
What a user sees is in [index.md](index.md) and isn't repeated here; what every integration shares is in
[internals.md](../../internals.md). Result and detail codes are in the code. Code comments cite the sections here.

## Addressing

Through the core integration's RPC connection. The unique ID is `<mac>-<key>`; the key gives the RPC component:
`switch:N` → `Switch` (a `switch`, or a `light` for a relay set to "light"), `light:N`, `cct:N`, `rgb:N`, `rgbw:N`
and `rgbcct:N` → `Light`, `CCT`, `RGB`, `RGBW`, `RGBCCT`. Each adapter's level per component is in
`integrations/shelly/addressing.py` (`CAPABILITIES`, `AUTO_CAPABILITIES`, `DIMMING_CAPABILITIES`), as the
[evidence](../../device-compatibility.md#shelly) shows it. Any other key (virtual booleans, scripts) has no timer.
Gen1 (CoIoT) has no `toggle_after`.

## Modules

One section per adapter module, named after it.

### `rpc`

One `<Component>.Set` with `on` and `toggle_after` (device range: over 0 s to 604800 s, 0.01 s
resolution). Light fields ride in the same call, translated as the core Shelly light does: brightness to percent,
`transition` to `transition_duration`, and on `RGBCCT` the mode switched to `cct` or `rgb` to match. `CCT`, `RGB`
and `RGBW` drop color and color temperature until their calls are ported and recorded.

The read-back is `<Component>.GetStatus`; `confirmed` when the output matches and `timer_duration` equals the
`toggle_after` sent, to 0.01 s. `timer_duration` is the timer's full duration, not the time left, so another
timer's reads back different.

### `get_attributes`

One `GetStatus`. Time left is `timer_started_at` + `timer_duration` against Home Assistant's
clock (both SNTP-synced), clamped to 0 to the duration to absorb up to 5 s of skew. Further off, the device's clock
isn't synced, so the row has no timer: until SNTP syncs, `Sys.GetStatus` `unixtime` is null
([Sys](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Sys)) and `timer_started_at` reads as seconds
since boot ([forum report](https://shelly-forum.com/thread/31934-shelly-time-is-incorrect/)). Every light adds
brightness. `RGBCCT` adds the active mode's color, `CCT` its `ct`, and `RGB` and `RGBW` their `rgb`, `RGBW`'s with its
`white` mixed in by core's `color_rgbw_to_rgb`, as core's light state does; the hs and xy are derived from the rgb.
A `<Component>.GetConfig` runs alongside for `auto_off` and `auto_on`; if it fails, the row leaves both keys out
(unknown) rather than reporting them `null` (disabled).

### `set_attributes`

`RGBCCT.Set` with the `light_params` translation and no `on`: the bulb keeps its output and
stores brightness, `ct`, `rgb` and `mode` (probe, 8 Nov, Multicolor Bulb Gen3). The reply is null, so a
`GetStatus` follows; `brightness`, `ct` and `mode` must match what was sent (`not_stored`, rejected), `rgb` is not
compared until a probe has shown the device returns it unrounded. A failed read-back reports `sent`.
`min_brightness`/`max_brightness` first read `GetStatus` `brightness` (kept while off), clamp it to whole percent,
and send nothing when it is already within them; an explicit `brightness` wins.

### `fade`

Every dimming component takes the same calls (levels: `DIMMING_CAPABILITIES`). A move reads `GetStatus` first: the device reports its level exactly mid-fade (rig, 8 Nov), so no transition cache is kept and
no call resolver is needed. Then one `<Component>.Set {on: true, brightness, transition_duration}` for the distance
left at the `sweep_time`'s speed, at least 0.5 s (`TRANSITION_LIMITS`, the device's 0.5 to 10800 s); to 0 it is
`{on: false, transition_duration}`, the device's soft off, which keeps the stored level (`brightness: 0` would
leave it on at 0%). From off the device fades in from 1%.

### `stop`

`stop` sends `<Component>.DimStop {id}` first, which halts a `Set`'s fade within ~0.1 s and is a no-op with none running, then `GetStatus`: `confirmed` when on with no
`transition` object, `sent` (`still_fading`) when one remains, `unchanged` (`off`) when off. Under a second client
polling the device, round trips reach 0.7 s and the halt lands late; the read-back is still exact.

### `auto`

`<Component>.GetConfig` first, and `<Component>.SetConfig` with `{"id": N, "config": {...}}` only when the config differs: `auto_off: true` and `auto_off_delay` to set,
`auto_off: false` alone to clear (likewise `auto_on`). A delay matches to 0.01 s. `SetConfig` emits
`config_changed`, and core reloads the entry after its 60 s debounce (`shelly/coordinator.py`,
`ENTRY_RELOAD_COOLDOWN`). Read-back is a second `GetConfig`. The delay's device range is unverified: the timer's
604800 s ceiling until a rig run reads it.

## Upstream defects

None known.
