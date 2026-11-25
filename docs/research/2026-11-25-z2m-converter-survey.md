# What tells a Zigbee2MQTT light takes the standard calls: a converter and issue survey (2026-11-25)

Research for [the v0.2.0 plan](../plans/2026-11-25-v0.2.0-backlog.md), step 1. Question: what on a Zigbee2MQTT (or ZHA)
device tells that a light takes the standard ZCL calls DeviceSide sends, so step 2 can key a standard-call route to
Documented on it (Decision 1) and split known failures off as `NotBuilt`. It extends, and does not redo,
[other brands: dimming](../integrations/zigbee2mqtt/research/2026-11-24-other-brands-dimming.md),
[other brands: ExecuteIfOff writes and reads](../integrations/zigbee2mqtt/research/2026-11-24-other-brands-execute-if-off-and-reads.md)
and [vendor call documentation](2026-11-25-vendor-call-documentation.md) (it lands with #609): no vendor publishes its
calls, the CSA test specs run DeviceSide's exact ExecuteIfOff moveToLevel and moveToColor, and certification leaves no
wire-visible marker.

**A missing flag means unreported, not tested.** Every share below counts definitions where zigbee-herdsman-converters
(ZHC) encodes no departure. A definition without a flag has had no failure reported and fixed in ZHC; nobody has run
DeviceSide's calls on it. No device was touched for this note (Part 5).

## Sources and method

- **ZHC** at `03b37655f540668d94975c47550f249fc0d16e26` (release 26.137.0), the pin the 2026-11-24 notes use; MIT-licensed, Copyright (c) 2018 Koen
  Kanters. Zigbee2MQTT (Z2M) facts at `3c841fdfd66c92239921ef84fde8f039c64e1662` (master, the dimming note's pin).
- **Part A, the converter table** (a script, not committed): ZHC was built at the pin and each of its 4,704 definitions
  resolved with ZHC's own `prepareDefinition` ([index.ts L420](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/index.ts#L420)), which applies every
  `extend` and prepends the generic converters, so `toZigbee` and `meta` are what Z2M runs. A TypeScript AST pass over
  `src/devices/*.ts` named each definition's light extend and arguments; the two passes agree (4,704 against 4,702
  literals, the two missing built by a Giex helper). A **light** is a definition whose resolved exposes hold a `light`.
  For each key DeviceSide publishes, the resolved converter was compared by identity with ZHC's standard one, and each
  flag's effect was checked by running the converters against a recording fake endpoint. Dependencies were installed
  without the lockfile (pnpm 12 wasn't at hand), so transitive versions may differ from the pin's (**unverified**).
- **Family** is approximated by vendor string, with Tuya strings first, after `families/__init__.py`'s order; it is not
  DeviceSide's classifier output. `other` below means "no family DeviceSide has code for".
- **Part B, the issues:** three bounded `gh search` runs over Koenkk/zigbee2mqtt and Koenkk/zigbee-herdsman-converters
  (about 135 searches and 70 issue or PR reads in all), split by call: fades; stop and raw `command` writes; reads.
  GitHub's search ANDs words and was rate-limited, so a missing report is "not found". Issues the 2026-11-24 notes
  already cite are not repeated here unless a row adds to them.

## Synthesis

- **No published field is a marker.** Z2M's `bridge/devices` carries `supported`, `definition.source` (`native`,
  `generated`, `external`), `model`, `vendor`, `exposes`, `options`, `supports_ota`, `version`, and the device's
  `model_id`, `manufacturer`, `software_build_id`, `date_code` and endpoint cluster lists
  ([bridge.ts L867-L886, L943-L953](https://github.com/Koenkk/zigbee2mqtt/blob/3c841fdfd66c92239921ef84fde8f039c64e1662/lib/extension/bridge.ts#L867)).
  It carries no ZCL version, stack version, profile or device type, and not the definition's `meta`, where every
  departure ZHC encodes lives. No option or expose separates a flagged definition from a plain one (Part 1d).
- **The marker DeviceSide can have is the ZHC definition itself:** a model whose definition, at a pinned ZHC, sends the
  standard call for an action with no flag or override touching it. That is an allowlist derived offline from ZHC's
  source and keyed on the definition model Z2M publishes. Of `other`'s 848 light definitions (1,091 model strings),
  **642 (75.7%; 870 strings, 79.7%) are plain** on every DeviceSide call; per action the share is higher (Part 3).
- **Certification can't key a class.** No field carries it, and the CSA listing is per SKU and firmware
  ([vendor call documentation](2026-11-25-vendor-call-documentation.md), Part 2). Read off the wire, the nearest thing
  is the cluster revision (Part 5): a partial probe got no revision from any light.
- **DeviceSide's `set_attributes` and `get_attributes` bypass every flag.** Z2M's generic `command` and `read`
  converters are prepended to every definition and honor no light flag; `command` passes only
  `disableDefaultResponse` ([toZigbee.ts L217-L248](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L217;
  [index.ts L430](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/index.ts#L430)). So the payload reaches the wire as DeviceSide builds it on every
  definition, generated ones included, and a flag ZHC added for a failure doesn't protect DeviceSide's raw call from
  it: the flag marks a **known failure** of that call, a `NotBuilt` candidate.
- **Fades, stop and the hue and saturation moves ride ZHC's own converters,** so Z2M users of those lights already send
  the call, and the flags apply. Only `turnsOffAtBrightness1` and `supportsHueAndSaturation` change what DeviceSide's
  fades send, and both by design (Part 1c).
- **Known failures cluster in four places:** pre-ZCL-rev-7 lights rejecting the option fields (Paul Neuhaus, Schneider,
  RIBAG, dresden elektronik FLS-PP3 on color); lights advertising color attributes they lack (Paulmann, Müller Licht);
  the soft off ending at about 1 % (AwoX, EGLO, Iluminize); and definitions ZHC overrides wholesale (ORVIBO DD10Z,
  Control4, Inovelli, Legrand). Part 4 lists them as `NotBuilt` candidates.
- **Records:** only Hue classes pass these calls on hardware, on Zigbee2MQTT and ZHA; the Aqara bulb's pass is in #609
  (Part 6). Nothing here is a pass on any `other` light.

## Part 1: The converter table

### 1a. Counts

| | Definitions | `zigbeeModel` strings | Fingerprints | White labels | Plain definitions | Plain strings |
|---|---|---|---|---|---|---|
| All lights | 1,743 | 2,180 | 403 | 350 | 741 (42.5%) | 999 of 2,583 (38.7%) |
| Families DeviceSide has | 895 | 1,309 | 183 | 278 | 99 (11%) | 129 of 1,492 (9%) |
| `other` | 848 | 871 | 220 | 72 | **642 (75.7%)** | **870 of 1,091 (79.7%)** |

A model string is one `zigbeeModel` or one fingerprint. **Plain:** every DeviceSide key resolves to ZHC's standard
converter (or a copy with the same `convertSet`), and no flag that changes a DeviceSide call (class A, 1c) is set.
Strict plain also drops the shape flags (`supportsHueAndSaturation`, `multiEndpoint`): 528 of `other`'s definitions
(62.3%), 695 strings (63.7%).

Per family: Hue 1 of 586 plain (`philips.m.light` brings its own converters and `turnsOffAtBrightness1`,
[philips.ts L315](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/lib/philips.ts#L315)); IKEA 0 of 70 (`ikeaLight` wraps each converter in
`trackFreezing`, [ikea.ts L112](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/lib/ikea.ts#L112), and sets `noOffTransitionWhenOff`); Tuya 42 of 94;
Sengled 23 of 23; Gledopto 5 of 89 (`gledoptoLight` swaps all four light converters,
[gledopto.ts L335](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/devices/gledopto.ts#L335)); Aqara 27 of 32; Sonoff 1 of 1.

`other` by vendor, definitions / plain: Innr 108 / 2, LEDVANCE 47 / 47, OSRAM 40 / 40, Paulmann 30 / 29, ADEO 29 / 0,
Namron 25 / 20, Sunricher 21 / 21, Müller Licht 21 / 17, Sylvania 20 / 20, Candeo 18 / 15, AduroSmart 17 / 17,
Iluminize 17 / 17, Schneider Electric 17 / 16, Hornbach 14 / 14, Aurora Lighting 13 / 12, AwoX 10 / 8, Paul Neuhaus 9 / 0;
167 vendors in all. By shape, `other`'s plain ones are 78 hs color, 77 xy-only color, 171 color temperature and 316
dimmable or on/off.

### 1b. Unsupported devices

A device no definition matches gets a generated one
([generateDefinition.ts L378-L463](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/lib/generateDefinition.ts#L378)): a plain `m.light` built from its
clusters and its `colorCapabilities` bits (`philips.m.light` for a Signify manufacturer code). It carries no flag, so it
is plain by construction, and Z2M publishes it as `supported: false`, `source: "generated"`. Plain here means only
that nobody has written a definition for it.

### 1c. Flags on light definitions

The full list of `meta` keys found on the 1,743. Defs: all lights / `other`.

| Flag | What it does to DeviceSide's calls (run on the converters) | Defs |
|---|---|---|
| `turnsOffAtBrightness1` | `raise_brightness`'s first step from off, brightness 1, goes out as level **2** ([toZigbee.ts L1378](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L1378)); ZHC's fix for lights that turn off at 1, since 2020: [a87ed9095](https://github.com/Koenkk/zigbee-herdsman-converters/commit/a87ed90956a2eebd5b6e3d9f11934499c05bd518) (2020-08-10) narrowed the flag to brightness 1 and sent it as 0 (off); [97d0f072b](https://github.com/Koenkk/zigbee-herdsman-converters/commit/97d0f072b7214e658241da6dec4326ab8e571bca) (2020-08-20, [Z2M #1348](https://github.com/Koenkk/zigbee2mqtt/issues/1348)) made it 2, and the 2022 rewrite ([ZHC #4211](https://github.com/Koenkk/zigbee-herdsman-converters/pull/4211)) kept it | 738 / 132 (Innr 92, ADEO 28) |
| `omitOptionalLevelAndColorParams` | drops `optionsMask`/`optionsOverride` from ZHC's own light converters ([toZigbee.ts L68](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L68) and on); **not from `command`**, so `set_attributes` still sends them | 11 / 11 (Paul Neuhaus 9, RIBAG Air O, Schneider WDE002386) |
| `supportsEnhancedHue` | `{hue, saturation}` goes out as `enhancedMoveToHueAndSaturation`; a saturation-only color and `hue_move` are unchanged | 360 / 45 (Innr 17, Müller Licht 4) |
| `disableDefaultResponse` | the light sends no default response to ZHC's commands, **`command` included**, so a refused `set_attributes` write shows only in the read-back ([utils.ts L530](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/lib/utils.ts#L530)) | 18 / 11 |
| `moveToLevelWithOnOffDisable` | brightness goes as `moveToLevel` plus a separate on | 5 / 0 (Tuya) |
| `noOffTransitionWhenOff` | a soft off to a light already off drops its transition | 68 / 0 (IKEA, Tuya) |
| `tuyaDatapoints`, `separateWhite`, `tuyaColorTempInMireds` | Tuya datapoint path, no ZCL light call | 28 / 0 |
| `supportsHueAndSaturation` (shape) | the hs path; **without it a saturation or hue-and-saturation color goes out as `moveToColor`** in xy ([toZigbee.ts L135-L162](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L135)). Matches `color_hs` in the exposes for all but 6 Tuya lights | 547 / 151 |
| `multiEndpoint`, `multiEndpointSkip` (shape) | endpoint-suffixed keys (`state_l1`) | 81 / 57 |
| `applyRedFix`, `disableActionGroup`, `overrideHaDiscoveryPayload`, `thermostat` | none of DeviceSide's calls | 62 / 34 |

**Overrides in `other`** (14 definitions): AwoX EBF_RGB_Zm (its own soft off), Centralite 4256050-ZHAC and
4257050-ZHAC, Control4 VB-FTW-A19 and VB-RGBTW-A19 (brightness 0-100, ON restores the last level,
[control4.ts L8](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/devices/control4.ts#L8)), CTM Lyng CTM_MBD_Dim, Savolar SAV-DL6IN-24V-12W (`gledoptoLight`),
Inovelli VZM30-SN, VZM31-SN, VZM32-SN and VZM36, Legrand 067797, Livolo TI0001-dimmer, and ORVIBO DD10Z
(`moveToLevel` only, as the "device doesn't support moveToLevelWithOnOff", [orvibo.ts L35](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/devices/orvibo.ts#L35)).

### 1d. What Z2M publishes, against the flags

- `definition.options` lists converter options, not flags: `transition` is on 1,702 of the 1,743, flagged or not; the
  only departure it shows is IKEA's `unfreeze_support`.
- `definition.exposes` gives the shape (`color_hs` against `color_xy`, `color_temp`), so it mirrors
  `supportsHueAndSaturation`, and none of the class A flags or overrides. A generated light and a native `m.light` with
  the same arguments publish the same exposes.
- `definition.version` is `"0.0.0"` unless a definition sets it to force a re-configure
  ([types.ts L297](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/lib/types.ts#L297)).
- `definition.model` and `vendor` name the definition, which is what an allowlist would key on.

## Part 2: The issues, by call

Rows the 2026-11-24 notes hold are cited there; these add to them.

### 2a. Fades and transitions

| Issue | Device | What happens | Cause, fix |
|---|---|---|---|
| [Z2M #16884](https://github.com/Koenkk/zigbee2mqtt/issues/16884), [Z2M #20108](https://github.com/Koenkk/zigbee2mqtt/issues/20108), [ZHC #11197](https://github.com/Koenkk/zigbee-herdsman-converters/issues/11197), [ZHC #13041](https://github.com/Koenkk/zigbee-herdsman-converters/issues/13041) | unnamed; EGLO EGLO_ZM_RGB_TW; Hue; Iluminize 5120.1100 | after Z2M's soft off a remote, or a plain on, brings the light back at about 1 % | ZHC fakes the soft off as `moveToLevelWithOnOff` level 0, which overwrites the stored level; no fix in code, the user empties the Transition option |
| [Z2M #22030](https://github.com/Koenkk/zigbee2mqtt/issues/22030), [Z2M #23825](https://github.com/Koenkk/zigbee2mqtt/issues/23825) | IKEA LED2103G5 and others | an off with a transition to a light already off turns it on at about 1 % | `noOffTransitionWhenOff` (IKEA family) |
| [Z2M #28531](https://github.com/Koenkk/zigbee2mqtt/issues/28531) | Inovelli VZM31-SN, VZM36 | transition replaced by the device's ramp rate | definition had `tz.on_off`; [ZHC #9983](https://github.com/Koenkk/zigbee-herdsman-converters/pull/9983) |
| [ZHC #12937](https://github.com/Koenkk/zigbee-herdsman-converters/issues/12937) | Legrand 067797 | transition ignored | explicit `tz.on_off` over `m.light`; now a Legrand converter |
| [Z2M #33113](https://github.com/Koenkk/zigbee2mqtt/issues/33113), [Z2M #33106](https://github.com/Koenkk/zigbee2mqtt/issues/33106) | Sonoff MINI-ZBDIM | per-call transition ignored | firmware, per Sonoff's reply (Sonoff family) |
| [Z2M #33611](https://github.com/Koenkk/zigbee2mqtt/issues/33611) | Hue LCA016 | `saturation_move: stop` doesn't stop a saturation fade | generic converter; DeviceSide already sends a raw `stopMoveStep` |
| [ZHC #11467](https://github.com/Koenkk/zigbee-herdsman-converters/issues/11467), [ZHC #13034](https://github.com/Koenkk/zigbee-herdsman-converters/issues/13034), [Z2M #31085](https://github.com/Koenkk/zigbee2mqtt/issues/31085) | MiBoxer, Lidl (Tuya) | colors wrong, no fade | Tuya family |

Not found: a non-Tuya light ignoring a `moveToSaturation` or `moveToHueAndSaturation` transition, or rejecting
`hue_move`.

### 2b. Stop and raw `command` writes

| Issue | Device | What happens | Cause, fix |
|---|---|---|---|
| [Z2M #30603](https://github.com/Koenkk/zigbee2mqtt/issues/30603), [Z2M #30705](https://github.com/Koenkk/zigbee2mqtt/issues/30705) | Paul Neuhaus 100.110.51, NLG-CCT (firmware 2015) | MALFORMED_COMMAND on `moveToLevelWithOnOff` since Z2M 2.7.2; on and off still work | zigbee-herdsman 8 sends the option fields; [ZHC #12221](https://github.com/Koenkk/zigbee-herdsman-converters/pull/12221) adds `omitOptionalLevelAndColorParams` |
| [Z2M #30701](https://github.com/Koenkk/zigbee2mqtt/issues/30701) | Schneider NHPB/DIMMER/1 | MALFORMED_COMMAND or a silent drop | same; [ZH #1619](https://github.com/Koenkk/zigbee-herdsman/pull/1619), [ZHC #11340](https://github.com/Koenkk/zigbee-herdsman-converters/pull/11340) |
| [ZHC #11921](https://github.com/Koenkk/zigbee-herdsman-converters/issues/11921) | dresden elektronik FLS-PP3 | `moveToColor` and `moveToColorTemp` rejected MALFORMED_COMMAND; level fine | the option fields on color commands; closed stale, **no flag at the pin** |
| [Z2M #33679](https://github.com/Koenkk/zigbee2mqtt/issues/33679) | L&S 756200030 | brightness set while off: Z2M shows ON, load stays off | ZHC's `moveToLevelWithOnOff`; `state: null` sends `moveToLevel` and behaves |
| [Z2M #31164](https://github.com/Koenkk/zigbee2mqtt/issues/31164) | Tuya TS0052 | no Options attribute; `moveToLevel` while off ignored | Tuya family |
| [Z2M #22653](https://github.com/Koenkk/zigbee2mqtt/issues/22653) | IKEA | a color set while off is lost or turns the light on | ZHC's send with options 0/0; IKEA family |

Not found: a light that turns on, or doesn't store, under a per-command ExecuteIfOff override (mask 1, override 1); a
non-Hue light failing `brightness_move: stop` or `hue_move: stop`; `stopMoveStep` failing on any light.

### 2c. Reads

| Issue | Device | What happens | Cause, fix |
|---|---|---|---|
| [Z2M #33439](https://github.com/Koenkk/zigbee2mqtt/issues/33439), [Z2M #12720](https://github.com/Koenkk/zigbee2mqtt/issues/12720) | Paulmann 924.70 (RGBW), Müller Licht GU10 | a color read fails UNSUPPORTED_ATTRIBUTE | advertises xy without CurrentX/Y; ZHC's own read still asks for them ([light.ts L17-L50](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/lib/light.ts#L17)) |
| [ZHC #2037](https://github.com/Koenkk/zigbee-herdsman-converters/issues/2037), [ZHC #11840](https://github.com/Koenkk/zigbee-herdsman-converters/pull/11840) | Innr RB 250 C, RB 285 C, Müller Licht Tint | advertise enhanced hue in ColorCapabilities and reject it | per-model `enhancedHue: false`, now the default; a contributor says ColorCapabilities "doesn't always match" |
| [ZHC #1346](https://github.com/Koenkk/zigbee-herdsman-converters/pull/1346) | IKEA LED1624G9 | hue and saturation read fails | xy only; `supportsHueAndSaturation` added |
| [Z2M #28757](https://github.com/Koenkk/zigbee2mqtt/issues/28757), [ZHC #13408](https://github.com/Koenkk/zigbee-herdsman-converters/pull/13408) | Tuya TS0502B, IKEA LED2110R3 | reports a ColorMode it doesn't support (a CT-only light keeps hs) | not fixed (PR closed) |
| [Z2M #20528](https://github.com/Koenkk/zigbee2mqtt/issues/20528) | an unsupported device | generated definition's ColorCapabilities read fails at start | "fixed in dev"; **unverified** |

DeviceSide reads only the attributes of the color modes HA lists for the light
([`read.py`](../../custom_components/deviceside/integrations/zigbee2mqtt/read.py)), which come from the definition's
exposes, so a light that advertises a mode it lacks fails the read whatever DeviceSide asks. Not found: a read changing
or waking a light.

## Part 3: Per action

| DeviceSide action | Path | Definitions in `other` whose flags or overrides touch it | Known failures |
|---|---|---|---|
| `raise_brightness` | ZHC `light_onoff_brightness`: `moveToLevelWithOnOff` | `turnsOffAtBrightness1` (132: the from-off step sends 2, ZHC's own compensation); `omitOptional…` (11: no option fields, which these lights need); overrides (14) | Müller Licht tint, older firmware: a turn-on transition below level 103 flashes off ([Z2M #15832](https://github.com/Koenkk/zigbee2mqtt/issues/15832), dimming note) |
| `lower_brightness` | same; to 0, the soft off (`moveToLevelWithOnOff` level 0) | as above | soft off ends on at about 1 %: AwoX, EGLO, Iluminize (2a; dimming note) |
| `raise_saturation`, `lower_saturation` | ZHC `light_color`: `moveToSaturation`, or `moveToHueAndSaturation` | `supportsEnhancedHue` (45: enhanced form for hue and saturation); without `supportsHueAndSaturation` the call is `moveToColor`, a different call from Hue's | none found |
| `raise_hue`, `lower_hue` | ZHC `light_hue_saturation_move`: `moveHue` | none | none found |
| `stop` | `brightness_move: stop`, `hue_move: stop` (ZHC); raw `stopMoveStep` (DeviceSide) | overrides (14) on `brightness_move` | none on a non-Hue light (2b) |
| `set_attributes` | raw `command`, options 1/1, then a read-back | **no flag applies** but `disableDefaultResponse` (11) | the option fields: Paul Neuhaus, Schneider WDE002386, RIBAG Air O (flagged), dresden elektronik FLS-PP3 color (not flagged) |
| `get_attributes` | raw `read` | **no flag applies** | advertised attributes missing: Paulmann 924.70, Müller Licht GU10; ColorMode or ColorCapabilities wrong |

Share of `other` a definition marker would cover, by what it excludes: every class A flag and override, 642 of 848
definitions (870 of 1,091 strings); only the flags and overrides that make a call fail (`omitOptional…`, overrides,
Tuya datapoints), 823 (1,063); those and `disableDefaultResponse`, 814 (1,049). `turnsOffAtBrightness1` alone decides
most of the gap: it holds 92 of Innr's 108 definitions and all 28 of ADEO's.

## Part 4: Candidate `NotBuilt` entries

Each is a known failure of DeviceSide's call or a call that isn't the one on record. Step 2 decides which become entries
and how they are keyed (definition model, vendor, or a flag read off ZHC).

| Candidate | Actions | Source |
|---|---|---|
| Definitions with `omitOptionalLevelAndColorParams`: Paul Neuhaus (9), RIBAG Air O, Schneider WDE002386 | `set_attributes` (raw command carries the fields they reject) | [Z2M #30603](https://github.com/Koenkk/zigbee2mqtt/issues/30603), [Z2M #30705](https://github.com/Koenkk/zigbee2mqtt/issues/30705), [Z2M #30701](https://github.com/Koenkk/zigbee2mqtt/issues/30701); [paul_neuhaus.ts L56](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/devices/paul_neuhaus.ts#L56) |
| dresden elektronik FLS-PP3 | `set_attributes` color and color temperature | [ZHC #11921](https://github.com/Koenkk/zigbee-herdsman-converters/issues/11921) |
| Paulmann 924.70, Müller Licht GU10 | `get_attributes` color | [Z2M #33439](https://github.com/Koenkk/zigbee2mqtt/issues/33439), [Z2M #12720](https://github.com/Koenkk/zigbee2mqtt/issues/12720) |
| AwoX (EBF_RGB_Zm overridden; the rest exposed), EGLO EGLO_ZM_RGB_TW, Iluminize 5120.1100 | `lower_brightness` to 0 | [Z2M #19007](https://github.com/Koenkk/zigbee2mqtt/issues/19007), [Z2M #31956](https://github.com/Koenkk/zigbee2mqtt/issues/31956), [Z2M #20108](https://github.com/Koenkk/zigbee2mqtt/issues/20108), [ZHC #13041](https://github.com/Koenkk/zigbee-herdsman-converters/issues/13041) |
| Müller Licht tint, older firmware (45327, 45328, 404065) | `raise_brightness` from off | [Z2M #15832](https://github.com/Koenkk/zigbee2mqtt/issues/15832) |
| The 14 overridden definitions (ORVIBO DD10Z, Control4 VB-*, Inovelli VZM3*, Legrand 067797, Centralite, CTM, Livolo, Savolar, AwoX EBF_RGB_Zm) | the fades and `stop`: not the standard call | Part 1c |
| Definitions without `supportsHueAndSaturation` | saturation fades: `moveToColor`, not the call on record | [toZigbee.ts L135](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L135) |

## Part 5: Marker options

| Option | What it keys on | Covers in `other` | Holds | Doesn't |
|---|---|---|---|---|
| 1. A ZHC definition on the standard converters with no flag touching the action's call | the definition model, from a table built off a pinned ZHC | 642 of 848 definitions on every call; up to 823 if only failing flags exclude | DeviceSide sends exactly the call Z2M sends Hue, per action; ZHC's own fixes split known failures off | a missing flag is unreported, not tested; a ZHC bump can change a row, so the table needs regenerating and a check; generated definitions are plain only because nobody wrote one |
| 2. Certification (Zigbee 3.0 listing) | a CSA model and firmware list | unknown: the CSA search wasn't queried | the test spec runs DeviceSide's ExecuteIfOff call | no field carries it; per SKU and firmware; certified lights depart in the field (vendor note) |
| 3. A device field read off the wire | Level Control and Color Control ClusterRevision (0xFFFD) of 2 or more, or the Options attribute (0x000F) answering; Basic ZCLVersion | unknown: not read on any device | the ZCL 8 revision history ties Options and the option fields to cluster revision 2 (ExecuteIfOff note, Part 1.1), the exact cause of the MALFORMED failures | self-declared; no light gave its revision in the partial probe (below); a read per device at placement; says nothing about fades or reads |
| 4. Per-vendor classes | a vendor whose definitions are all plain | LEDVANCE, OSRAM, Sylvania: 107 definitions (127 strings), all plain | small, and the three vendors with most of the Zigbee 3.0 PICS on file (vendor note) | no vendor publishes its calls (route (a) needs it); Innr, the largest vendor, is 2 of 108 plain |
| 5. The standard call plus N passing vendors | the call, with records on N vendors | all of `other` | tenet 5's "same call, same class" | a class spanning vendors is never Documented by another's pass today |

Options 1 and 3 combine: the definition says DeviceSide's call is the standard one, and the cluster revision says the
light knows the option fields that `set_attributes` sends.

**Device fields: a partial probe** (2026-11-25, run by a maintainer through ha-rig's HAClient; a script, not
committed). Per Z2M and ZHA light it read Basic ZCLVersion, StackVersion and AppVersion, Level and Color Control
ClusterRevision, Level Options and ColorCapabilities: ZCL reads only, one attribute per read, 10 s for an answer.

| Light | ZCLVersion | StackVersion | AppVersion | Level ClusterRevision | Level Options | Color ClusterRevision | ColorCapabilities |
|---|---|---|---|---|---|---|---|
| Aqara T2 E27 (`lumi.light.agl003`, family `aqara`) | 3 | 27 | 31 | not read | 0 | not read | 24 (xy, color temperature) |
| Linkind ZL1000100-CCT-US-V1A02, firmware 2.2 (`other`), two | no answer | no answer | no answer | no answer | no answer | no answer | no answer |

- **ClusterRevision went unread on every light:** Z2M's generic `read` took it by name, `clusterRevision`, and
  returned nothing, the Aqara bulb included, which answered its other reads. A read by ID (0xFFFD) is untried, so option 3
  is still untested, not refuted.
- The Aqara bulb answers Options, the attribute ZCL ties to cluster revision 2 or more; a ZCLVersion of 3 is the Basic
  cluster's own field and doesn't say which revision its Level and Color Control clusters are.
- The two Linkind bulbs answered nothing, Basic included, so this says nothing about them beyond that.
- **ZHA:** the ZHA half timed out before it read any light. No ZHA row.

## Part 6: Which classes pass the calls today

From `docs/integrations/*/test-records/`: on Zigbee2MQTT and ZHA, the fades, `stop`, `set_attributes` and
`get_attributes` pass on Hue bulbs only (LCA016, LTA009, LWA012; the hue and saturation actions on LCA016 alone). #609
adds the Aqara bulb (`lumi.light.agl003`, family `aqara`, an `lumiLight` definition: plain in Part 1, whose extend leaves
the light converters standard). No `other` light has a record. A Hue definition is not plain (Part 1a), so the Hue
passes are evidence for the ZCL call, not for ZHC's standard converters.

## Not confirmed

- That a plain definition accepts DeviceSide's calls on hardware: no record, only no report.
- Device fields (Part 5): ClusterRevision not read on any light (by name, through Z2M); no ZHA light read.
- Transitive dependency versions in the Part A build, and whether a Z2M release matches the master lines cited.
- Fixes for [ZHC #11872](https://github.com/Koenkk/zigbee-herdsman-converters/issues/11872), [ZHC #12937](https://github.com/Koenkk/zigbee-herdsman-converters/issues/12937) and [Z2M #20528](https://github.com/Koenkk/zigbee2mqtt/issues/20528); the device in [Z2M #27743](https://github.com/Koenkk/zigbee2mqtt/issues/27743); Sonoff's support reply in
  [Z2M #33106](https://github.com/Koenkk/zigbee2mqtt/issues/33106).
- Family is approximated by vendor string; a Tuya-inside light under another vendor's definition lands in `other` here
  (Lidl HG06337, for one: `classes.py`).
