# Z-Wave call patterns for DeviceSide's actions: Inovelli and Zooz (2026-11-27)

Research date: 2026-11-27. Scope: which Z-Wave calls, reached through Home Assistant's `zwave_js` integration, would serve DeviceSide's actions on Inovelli and Zooz dimmers, switches, plugs and bulbs, and what core already offers. Feeds the decision: what a `zwave_js` integration's first scope holds. A Z-Wave integration was approved on 2026-11-27 without weighing it against the broad-appeal principle, since Z-Wave users are mostly power users.

## Evidence tags

- **[code]**: source, pinned below.
- **[config-db]**: Z-Wave JS's device config database (`packages/config/config/devices/<manufacturer>/`; Inovelli `0x031e`, Zooz `0x027a`).
- **[docs]**: Z-Wave JS or Home Assistant documentation.
- **[vendor]**: a manufacturer's own page or driver.
- **[inferred]**: my reading, not observed. No probe or rig run backs anything here.

Pinned sources:

- Z-Wave JS: `zwave-js/zwave-js@473703662970725e75fcf8d6f2d226c48dc4f3ba` (2026-11-25), written `ZJS/<path>#L<n>`.
- HA core: `home-assistant/core@66e9f19b16aa03edd174127b65cc80d066b8a39e` (2026-11-27), `zwave_js` files written `HA/<file>#L<n>`.
- zwave-js-server-python: `home-assistant-libs/zwave-js-server-python@6ddab45f8fc93c45c47e866dc5909be21a7a1511` (2026-11-23), written `ZJSP/<path>#L<n>`.
- HA docs: `home-assistant/home-assistant.io@d45b04b37845bbf845ebc89cd8c2df84d7be87b7`, `source/_integrations/zwave_js.markdown`.
- Inovelli Hubitat drivers: `InovelliUSA/Hubitat@d2a274b189cd83e8f67a0f5222ac7bc8ef386734`, `Drivers/`, written `INOV/<driver>`.

## 1. What core `zwave_js` already offers

None of DeviceSide's actions. Core has raw building blocks [code]:

- `light.turn_on` with `transition` sends Multilevel Switch Set with a `transitionDuration` of `"<n>s"`, or `"default"` when none is given; color goes first, then brightness (HA/light.py#L237-L249, #L340-L374).
- `zwave_js.invoke_cc_api` can call any CC method, Start/Stop Level Change included, but returns nothing to the caller (`-> None`, registered without `supports_response`; HA/services.py#L971). The admin websocket command `zwave_js/invoke_cc_api` returns the result (HA/api.py#L3124-L3165).
- `zwave_js.set_value` (with `options`, `wait_for_result`), `zwave_js.multicast_set_value`, `zwave_js.refresh_value`, `zwave_js.set_config_parameter` (HA/services.yaml).
- Every configuration parameter becomes a number, select or switch entity, disabled by default (HA/discovery.py#L1592-L1640). Auto-off is settable per device that way, under each vendor's label and unit.

No raise, lower or stop for lights, no cross-vendor auto-off or auto-on, no read of the device's mid-move level.

## 2. Generic calls (any vendor)

| DeviceSide action | Z-Wave call | Z-Wave JS API |
|---|---|---|
| `raise_brightness`, `lower_brightness` | Multilevel Switch Start Level Change (`direction`, `ignoreStartLevel: true`, `duration` from V2) | `startLevelChange` (ZJS/docs/api/CCs/MultilevelSwitch.md) |
| `stop` | Multilevel Switch Stop Level Change | `stopLevelChange` |
| a move with `limit` | Multilevel Switch Set (target 0-99, `duration` from V2) | `set(targetValue, duration)` |
| `get_attributes` (brightness) | Multilevel Switch Get, then Report | `get()` returns `currentValue`, and `targetValue` and `duration` on a V4 Report (ZJS/packages/cc/src/cc/MultilevelSwitchCC.ts#L712-L735) |
| color writes and reads | Color Switch Set and Get per component, `duration` from V2 | `set`, `get(component)` (ZJS/docs/api/CCs/ColorSwitch.md) |

- **Levels.** 0-99, with 255 meaning "restore previous" (MultilevelSwitchCC.ts#L298-L303). The lowest level is 1, about 1 %, coarser than the 0.4 % of a Zigbee level 1 [code]. HA maps 0-255 to 0-99 with a floor of 1 (HA/light.py#L96-L101).
- **Durations.** 0-127 s, then 1-127 min (`(payload & 0x7F) + 1`), 0xFF "default" on a Set; Z-Wave JS takes strings such as `"5s"` and rounds anything over 127 s to whole minutes (ZJS/packages/core/src/values/Duration.ts#L73-L115) [code]. `sweep_time` over 127 s loses precision.
- **Start Level Change duration.** The Inovelli and Zooz configs describe it as the time for the full range [vendor], which matches `sweep_time`. Z-Wave JS's docs and code don't state it; the spec (SDS13781) does, and wasn't read for this file [inferred].
- **Supervision.** Z-Wave JS wraps singlecast Multilevel Switch Set, Start Level Change and the Color Switch equivalents in Supervision when the node supports it (MultilevelSwitchCC.ts#L614, #L875; ColorSwitchCC.ts#L950, #L1068). The result is Success, Fail, NoSupport or Working with a remaining duration; without Supervision the set reports `SUCCESS_UNSUPERVISED` (acked, not confirmed) (ZJS/docs/api/driver.md#L806-L822; ZJSP/zwave_js_server/const/__init__.py#L445) [code]. HA's docs say Working and Fail never come back (zwave_js.markdown#L932); the driver code contradicts that.
- **Color moves.** Color Switch has a per-component Start/Stop Level Change (duration from V3), so a warm-white or red channel can move, but no hue or saturation move exists [docs]. Raising hue or saturation has no known method on Z-Wave.
- **Writing while off.** A non-zero Multilevel Switch Set turns the light on. Nothing in Z-Wave JS says whether Color Switch Set turns an off light on; no compat flag touches it (ZJS/docs/config-files/file-format.md#L402-L695) [docs]. A probe decides `set_attributes` color on Z-Wave bulbs.

### Reaching it from DeviceSide

As the Matter adapter does, through the config entry: `entry.runtime_data.client.driver.controller.nodes` (HA/models.py#L31-L35; HA/services.py#L913-L918) [code]. Then:

- `node.async_invoke_cc_api(command_class, method_name, *args, wait_for_result=None)` returns the CC result, and raises `NotFoundError` when the CC is absent (ZJSP/zwave_js_server/model/node/__init__.py#L775-L785; model/endpoint.py#L214-L236).
- `node.async_set_value(value, new_value, options=None, wait_for_result=None)` checks each option against the value's `value_change_options` (ZJSP/.../node/__init__.py#L622-L648).

### Groups

HA has no Z-Wave group entity. `multicast_set_value` takes `options`, so durations pass through, but Z-Wave JS follows every multicast with singlecasts to each node; it removes the waterfall without cutting traffic. S0 nodes get singlecast only, and mixed security classes go separately (ZJS/docs/api/controller.md#L789-L835) [docs]. Supervision is never used for multicast. Whether Start Level Change can be multicast through the `levelChangeUp`/`levelChangeDown` values isn't stated [inferred].

## 3. No timed on

Z-Wave has no OnWithTimedOff equivalent. The `duration` on Basic, Binary Switch and Multilevel Switch Set is a fade time [docs]. Neither the Inovelli drivers nor the Zooz configs have a single-command timed on [vendor]. Every Inovelli and Zooz timer is a persistent configuration parameter. Emulating `turn_on_for` by writing auto-off, turning on, then restoring it leaves a stale timer if HA loses the device mid-sequence, and races a person at the switch [inferred].

## 4. Auto-off and auto-on: `$purpose`

Z-Wave JS's config DB tags parameters with a purpose, including `timer.auto_off` ("Automatic turn-off after a delay when turned on") and `timer.auto_on`, with 0 meaning disabled (ZJS/docs/config-files/parameter-purpose.md#L45-L66) [docs]. The purpose is exposed at runtime on the parameter's metadata (ZJS/packages/cc/src/cc/ConfigurationCC.ts#L397; ZJSP/zwave_js_server/model/value.py#L108, #L290-L292, server schema 46+) [code]. Core never reads it.

- **Coverage.** 67 parameters tagged `timer.auto_off` and 24 `timer.auto_on` across 24 manufacturers (rg over the DB, 2026-11-27) [config-db]. A minority of devices: untagged ones need a per-model table.
- **Units aren't normalized.** The purpose gives the meaning; each parameter's `unit` gives seconds, minutes or hours (parameter-purpose.md#L334) [docs]. Inovelli is seconds, most Zooz minutes.
- **Ramp purposes** (`dimming_duration`, `ramp_rate`, each with `.zwave` and `.manual` variants) also exist (parameter-purpose.md#L72-L96).

A generic `set_auto_off`/`clear_auto_off` (and `set_auto_on`) could find the parameter by purpose and convert units. Untagged models and enable flags (below) need family code.

## 5. Inovelli

From INOV drivers, cross-checked against the config DB.

| Pattern | Driver call |
|---|---|
| fade to level | `switchMultilevelSet(value: value<100?value:99, dimmingDuration: duration)` (INOV/inovelli-dimmer-red-series-vzw31-sn, `setLevel(value, duration)`) |
| move | `switchMultilevelStartLevelChange(upDown, dimmingDuration, ignoreStartLevel: true, startLevel)`, then `switchMultilevelGet` (same file, `startLevelChange`) |
| stop | `switchMultilevelStopLevelChange`, then Get |
| color | `switchColorSet(red, green, blue, warmWhite, coldWhite, dimmingDuration)` (INOV/inovelli-bulb-multi-color-lzw42) |

- **Auto-off** is a parameter, 0-32767 s, 0 = off; number by model [vendor][config-db]: VZW30-SN, VZW31-SN, VZW32-SN 12; LZW31 and LZW31-SN 8 (`$purpose: timer.auto_off`, ZJS/packages/config/config/devices/0x031e/lzw31-sn.json#L128-L135); LZW30 3; LZW45 6; NZW30 5; NZW36 2. No auto-on.
- **Ramp rates.** Separate Z-Wave and manual parameters (LZW31-SN 1-4; VZW3x-SN "Dimming Speed" and "Ramp Rate" up/down, remote/local) [config-db]. Whether an explicit Set duration overrides them isn't documented.
- **Driver duration bug.** The VZW31-SN driver encodes durations over 127 s as `128 + round(d/60)`. Duration.ts decodes 0x80 as 1 min, so the driver asks for one minute too many [code]. It doesn't affect DeviceSide, which hands Z-Wave JS a duration string.
- The Zigbee Blue series (VZM3x) is out of this file's scope; Zigbee2MQTT's research covers it.

## 6. Zooz

From the config DB, templates resolved; Zooz support pages for ZEN72 and ZEN77 [vendor]: [ZEN72 advanced settings](https://www.support.getzooz.com/kb/article/538-zen72-dimmer-switch-advanced-settings/), [ZEN77 advanced settings](https://www.support.getzooz.com/kb/article/550-zen77-s2-dimmer-advanced-settings/).

**Auto timers.** Zooz has auto-on as well as auto-off on most models, but the parameter shape varies:

| Models | Off / on params | Unit, range | Extra |
|---|---|---|---|
| ZEN71-77 | 3 / 5 | minutes, 0-65535, 0 = off | tagged `timer.auto_off`/`auto_on` |
| ZEN04 2/3, ZEN05 2/4, ZEN12 5/4, ZEN32 and ZEN35 16/17, ZEN14 2-3 / 4-5 (per outlet) | as listed | minutes, 0-65535 | tagged |
| ZEN78 | 13 / 14 | minutes, 0-65535 | |
| ZEN30 | 8 dimmer, 10 relay / 9, 11 | minutes | |
| ZEN16, ZEN17 | 6/8/10 off, 7/9/11 on (per relay) | 0-65535 | unit params 15-20 (min, s, h), ZEN16 from fw 1.1 |
| ZEN51, ZEN52, ZEN54, ZEN56 | per model | min or s | separate unit parameter |
| ZEN57, ZEN58 | 7 / 8 | seconds, 0-2678400 | |
| ZEN21-27, ZEN20, ZEN25, ZEN07 | enable param + duration param | minutes, 1-65535 | separate enable flag; some firmware-gated (`$if`) |
| ZEN15 | 34 / 33 | minutes, 0-99 | fw 1.6+ |

**Ramp rates.** ZEN72, ZEN74 and ZEN77 from fw 10.20/10.10 split them: 9 manual on, 27 manual off, 28 Z-Wave on, 29 Z-Wave off, 0-99 s; 28 and 29 default to 255, "match manual" [vendor][config-db]. Older firmware has one shared parameter 9. ZEN12, ZEN30, ZEN35, ZEN54 and ZEN56 have similar Z-Wave/manual pairs, with "match manual" sentinels of 255 or 100. ZEN31 (RGBW) uses the Z-Wave duration encoding for its ramp parameters.

**Unknown, needs a probe:** whether ZEN72, ZEN74 and ZEN77 honor an explicit Multilevel Switch Set or Start Level Change duration over parameters 28 and 29. Neither the DB nor Zooz's pages say. HA's own transitions depend on the same answer.

## 7. What differs between the two vendors

- Units: Inovelli seconds; Zooz mostly minutes, some seconds, some unit-selectable.
- Enable flags: older Zooz (ZEN2x, ZEN07, ZEN20, ZEN25) need an enable parameter written with the duration.
- Firmware-conditional parameters (`$if`) on Zooz move parameter numbers between firmware versions.
- Per-outlet and per-relay timers on multi-channel Zooz devices; Inovelli's are single-load.
- Zooz has auto-on; Inovelli doesn't.

## 8. Summary for scope

| Action | Generic Z-Wave | Notes |
|---|---|---|
| `raise_brightness`, `lower_brightness`, `stop` | Start/Stop Level Change | duration honoring unverified on Zooz |
| `limit` on a move | Set with duration | |
| `get_attributes` | Multilevel Switch Get (V4 for target and remaining time), Color Switch Get, Configuration Get | through the client, not the service |
| `set_auto_off`, `clear_auto_off`, `set_auto_on`, `clear_auto_on` | Configuration Set by `$purpose`, family tables where untagged | units, enable flags, `$if` |
| `turn_on_for`, `turn_off_for` | none | no known method |
| `raise_hue`, `raise_saturation` and lowers | none | no known method |
| `set_attributes` brightness while off | none | Set turns the light on |
| `set_attributes` color while off | Color Switch Set | probe: does it turn the light on? |
| groups | multicast with singlecast follow-up | no traffic saved; defer |

Probes that would decide open points: (1) a ZEN72/74/77 with parameters 28/29 at 255, sent Set and Start Level Change with explicit durations; (2) an LZW42 sent Color Switch Set while off; (3) Start Level Change duration on Inovelli, timed against `sweep_time`.
