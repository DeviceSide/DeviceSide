# The converter seed list: Zigbee2MQTT's timer routes per definition (2026-11-15)

Research date: 2026-11-15. Scope: for each zigbee-herdsman-converters (ZHC) definition, which timer call Zigbee2MQTT
sends and to which fingerprints (Zigbee model ID and manufacturer string). It is the seed list
[Decision 35](../../../plans/2026-11-14-device-classes.md) asks for (step 5 part 3, step 1), and the probe targets
of [the units research](../../../research/2026-11-14-timer-units-at-scale.md), §7, layer 2. Method and scope by plan
Decision 78.

**Research only, with no level weight** (Decision 35; units research, §8 question 2). A route is a fact of this ZHC
version, not of how a device behaves: route A holds strings known to fail its call. `_TZ3000_gjnozsaz`, a white label
on `TS011F_plug_1` (⚠ below), is doesn't work, `harms`
([Z2M #30493](https://github.com/Koenkk/zigbee2mqtt/issues/30493);
[Tuya countdown research](2026-11-14-tuya-countdown.md), §3; Decision 35).

## Source and license

- ZHC npm `26.131.0`, whose tag `v26.131.0` is `afdaa028a0972d801da762196ddfb2df631ea0cc`, the units research's pin.
  Definitions are named by ZHC's `model` and module; a module `tuya` is
  `https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/devices/tuya.ts`.
- The tables below are derived from ZHC, which is MIT-licensed:

  > MIT License. Copyright (c) 2018 Koen Kanters. Permission is hereby granted, free of charge, to any person
  > obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software
  > without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute,
  > sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so,
  > subject to the following conditions: The above copyright notice and this permission notice shall be included in
  > all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
  > KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
  > PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
  > CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR
  > IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Method: a static parse, the weaker one

The package was installed with its scripts disabled, and its compiled `dist/devices/*.js` read as text. **None of
it was run.** That is weaker than the units research's method, which prepared every definition and named each
converter by its `convertSet` function (§1).

A Python script, not committed, did the parse:

1. It split each module's definitions array (`exports.definitions = [...]`, or megaman's `const definitions`) into
   its top-level elements by bracket matching. Strings, template literals and comments were skipped, and comments
   were stripped from each definition, so a commented-out converter isn't counted.
2. Per definition, it read `model`, `zigbeeModel`, `fingerprint` (`tuya.fingerprint(model, [strings])` and
   `{modelID, manufacturerName, applicationVersion…}` objects) and `whiteLabel`'s `tuya.whitelabel(…, [strings])`.
3. It named the route by the code's own spellings:
   - **A, Tuya countdown over `0x42`** (whole seconds in both fields): `tuyaOnOff({onOffCountdown: …})` not
     `false`, or `tuya.tz.on_off_countdown` named directly. Where `onOffCountdown` is a predicate on the
     manufacturer string, the script read its equality or list, but that predicate decides only the `countdown`
     expose: the converter is installed for every string, so `on_time` has no converter on any of them
     ([Tuya countdown research](2026-11-14-tuya-countdown.md), §1).
   - **B, Tuya datapoint countdown:** a datapoint tuple `[dp, "countdown…", converter]`. The wire value is raw; the
     unit and range are read off the key's expose (`e.numeric(key)…withUnit…withValueMax`, or
     `tuya.exposes.countdown()`, seconds 0..43200).
   - **C, eWeLink countdown** (tenths): `ewelinkExtend.countdown()`.
   - **Standard tenths:** `m.onOff(`, `m.light(`, a vendor light extend, or `tz.on_off` / `tz.light_onoff_…`, with
     none of the above.

**What it misses.** A converter copied under another name (`{...tz.on_off, key: [...]}` in a local constant), and so
mostly the standard-tenths Hue copies (584 Hue definitions carry unnamed copies of the light converter: units
research, §1). It also misses any definition a call builds rather than a literal, and a fingerprint held in a
variable; this version has neither on routes A to C.

**Checked against the run's counts** (units research, §1):

| | This parse | The run |
|---|---|---|
| Definitions read | 4,667 | 4,667 |
| A: definitions, manufacturer-string fingerprints | 49, 203 | 49, 203 |
| A: fingerprints with firmware fields | 9 | 9 |
| B: definitions, fingerprints | 79, 213 | 79, 213 |
| C: definitions | 1 | 1 |
| Standard tenths: definitions | 2,132 | 811 on `tz.on_off`, 1,567 on the light converter |

**Routes A, B and C are complete:** each count matches the run. The standard route falls short of the run's, mostly by
the copies above, and is given as counts only (Decision 78).

## Findings

- **Catch-alls.** Six route A definitions match by `zigbeeModel` alone, with no fingerprint: `TS0001`, `TS0002`,
  `ZG-301Z`, `AY-601ZL`, `AY-602ZL` and `AY-603ZL`. `TS011F_plug_1` holds `TS011F` and five fingerprints, so any
  `TS011F` string no other definition lists falls to it, on route A. Both lab plugs (`_TZ3000_0zfrhq4i`,
  `_TZ3000_typdpbpg`) and `_TZ3000_gjnozsaz` are in no fingerprint: they reach route A that way.
- **White labels outside the fingerprints.** 47 white-label strings on route A definitions aren't in their
  definition's fingerprints, so they match by the catch-all or another definition (the table's last column).
- **The countdown expose by string.** Of route A's 49, 42 expose `countdown` for every string, 3 for named strings
  only, and 4 for all strings but one.
- **Route B's units, by expose**, over its 188 datapoints:
  - seconds 0..43200: 75 by `tuya.exposes.countdown()` and 52 spelled out;
  - seconds 0..86400: 24;
  - minutes: 3;
  - other seconds ranges: 3;
  - hours 0.25..12: 1, `_TZE284_z5jz7wpo`'s `countdown_hours`, whose wire value is seconds (units research, §1);
  - not read by the parse: 30.

  A template's range is a copied default, not a measurement.
- **A countdown outside the four routes:** `TS110E_1gang_2` (fingerprints `TS110E` with `_TZ3210_ngqk6jia`,
  `_TZ3210_weaqkhab`, `_TZ3210_k1msuvg6`, `_TZ3210_o235agwx`). Its `countdown` sends Tuya's private `genOnOff`
  command `tuyaCountdown`, not `0x42`.
- **Standard tenths, counts only:** 2,132 definitions read, with 253 manufacturer-string fingerprints, 149 of them
  Tuya-shaped (`_TZ…`, `_TY…`).

## Route A: Tuya countdown over `0x42`

| Definition | Fingerprints | Countdown exposed for | White-label strings outside the fingerprints |
|---|---|---|---|
| `AUT000069` (automaton) | `TS011F`: `_TZ3000_j0ktmul1` | every string |  |
| `LZWSM16-1` (avatto) | `TS0011`: `_TZ3000_hbxsdd6k` | every string |  |
| `ZG-301Z` (hobeian) | zigbeeModel `ZG-301Z` | every string |  |
| `HG06620` (lidl) | `TS0101`: `_TZ3000_br3laukf` | every string |  |
| `MG-GPO01` (makegood) | `TS011F`: `_TZ3210_bep7ccew`, `_TZ3210_qlmnxmac` | every string |  |
| `A11Z` (nous) | `TS011F`: `_TZ3210_6cmeijtd` | every string |  |
| `NFZB-2` (nova_digital) | `TS0002`: `_TZ3210_5ksufhqi` | every string |  |
| `WHD02` (tuya) | `TS0001`: `_TZ3000_hktqahrq`, `_TZ3000_q6a3tepg`, `_TZ3000_skueekg3`, `_TZ3000_npzfdcof`, `_TZ3000_5ng23zjs`, `_TZ3000_rmjr4ufz`, `_TZ3000_v7gnj3ad`, `_TZ3000_3a9beq8a`, `_TZ3000_ark8nv4y`, `_TZ3000_mx3vgyea`, `_TZ3000_fdxihpp7`, `_TZ3000_qsp2pwtf`, `_TZ3000_kycczpw8`, `_TZ3000_46t1rvdu`, `_TZ3000_bhcpnvud`, `_TZ3000_i9oy2rdq`; `TS000F`: `_TZ3000_hktqahrq`, `_TZ3000_m9af2l6g`, `_TZ3000_mx3vgyea`, `_TZ3000_skueekg3`, `_TZ3000_dlhhrhs8`, `_TZ3000_fdxihpp7`; zigbeeModel `AY301Z` | every string |  |
| `AY301Z-2CH` (tuya) | `AY301Z-2CH`: `AOYAN`; zigbeeModel `AY301Z-2CH` | every string |  |
| `SA-T2` (tuya) | `TS011F`: `_TZ3210_z1kba38n` | every string |  |
| `CMA30651` (tuya) | `TS0001`: `_TZ3210_fhx7lk3d` | every string |  |
| `TS0002_power` (tuya) | `TS0002`: `_TZ3000_aaifmpuq`, `_TZ3000_irrmjcgi`, `_TZ3000_huvxrx4i`, `_TZ3000_pxfjrzyj`, `_TZ3000_hopb2kjm` | every string |  |
| `TS0001` (tuya) | zigbeeModel `TS0001` | only `_TZ3000_udl7uyd2` | `_TZ3000_8n7lqbm0`, `_TZ3000_bzzgvet0`, `_TZ3000_cb3aangp`, `_TZ3000_ctftgjwb`, `_TZ3000_g8n1n7lg`, `_TZ3000_udl7uyd2` |
| `TS0001_switch_module_1` (tuya) | `TS0001`: `_TZ3000_myaaknbq`, `_TZ3000_cpozgbrx`, `_TZ3000_drc9tuqb` | every string |  |
| `TS0002_basic` (tuya) | `TS0002`: `_TZ3000_01gpyda5`, `_TZ3000_bvrlqyj7`, `_TZ3000_7ed9cqgi`, `_TZ3000_zmy4lslw`, `_TZ3000_ruxexjfz`, `_TZ3000_4xfqlgqo`, `_TZ3000_hojntt34`, `_TZ3000_eei0ubpy`, `_TZ3000_qaa59zqd`, `_TZ3000_lmlsduws`, `_TZ3000_fbjdkph9`, `_TZ3000_zbfya6h0`, `_TZ3000_hznzbl0x`, `_TZ3210_6smingw0`, `_TZ3210_jqg2a5yn` | only `_TZ3000_hznzbl0x`, `_TZ3210_6smingw0`, `_TZ3210_jqg2a5yn` |  |
| `TS0002_limited` (tuya) | `TS0002`: `_TZ3000_fisb3ajo`, `_TZ3000_5gey1ohx`, `_TZ3000_mtnpt6ws`, `_TZ3000_mufwv0ry`, `_TZ3000_54hjn4vs`, `_TZ3000_aa5t61rh`, `_TZ3000_in5qxhtt`, `_TZ3000_ogpla3lh`, `_TZ3000_i9w5mehz`, `_TZ3000_dershnvx` | every string |  |
| `TS0002` (tuya) | zigbeeModel `TS0002` | every string | `_TZ3000_5ksufhqi`, `_TZ3000_criiahcg`, `_TZ3000_lugaswf8`, `_TZ3000_nuenzetq`, `_TZ3000_ruldv5dt`, `_TZ3000_wnzoyohq`, `_TZ3000_ywubfuvt`, `_TZ3000_zxrfobzw`, `_TZ3210_nuenzetq` |
| `_TZ3000_a8mhmsol` (tuya) | `TS0002`: `_TZ3000_a8mhmsol` | every string |  |
| `TS0003_switch_3_gang_with_backlight` (tuya) | `TS0003`: `_TZ3000_rhkfbfcv`, `_TZ3000_empogkya`, `_TZ3000_lubfc1t5`, `_TZ3000_lsunm46z`, `_TZ3000_v4l4b0lp`, `_TZ3000_uilitwsy`, `_TZ3000_66fekqhh`, `_TZ3000_ok0ggpk7`, `_TZ3210_ok0ggpk7`, `_TZ3000_aknpkt02`, `_TZ3000_nwidmc4n`, `_TZ3000_pfc7i3kt`, `_TZ3210_xfbmf71h` | all but `_TZ3000_pfc7i3kt` |  |
| `NFZB-03` (tuya) | `TS0003`: `_TZ3000_fawk5xjv`, `_TZ3000_bvij6kod`, `_TZ3000_aracgljk`, `_TZ3210_fawk5xjv`, `_TZ3210_aracgljk` | every string |  |
| `Mercurio-3` (tuya) | `TS0003`: `_TZ3000_dyzkbcip` | every string |  |
| `TS0003_switch_module_2` (tuya) | `TS0003`: `_TZ3000_4o16jdca`, `_TZ3000_odzoiovu`, `_TZ3000_f6pgzqob`, `_TZ3000_hbic3ka3`, `_TZ3000_lvhy15ix`, `_TZ3000_mhhxxjrs`, `_TZ3000_iv4eq7eh`, `_TZ3000_mzcp0of6`, `_TZ3210_aksyshpw`, `_TZ3000_bu47m8pv` | every string |  |
| `_TZ3000_mw1pqqqt` (tuya) | `TS0003`: `_TZ3000_mw1pqqqt`, `_TZ3210_n0wbkysi` | every string |  |
| `TS0001_switch_module` (tuya) | `TS0001`: `_TZ3000_tqlv4ug4`, `_TZ3210_tqlv4ug4`, `_TZ3000_gjrubzje`, `_TZ3000_tygpxwqa`, `_TZ3000_4rbqgcuv`, `_TZ3000_veu2v775`, `_TZ3000_prits6g4`, `_TZ3000_xfxpoxe0`, `_TZ3210_9hbau615`, `_TZ3000_afgzktgb`, `_TZ3000_qamj2vnn`, `_TZ3000_n6fqajob` | all but `_TZ3000_xfxpoxe0` |  |
| `_TZ3000_pgq7ormg` (tuya) | `TS0001`: `_TZ3000_pgq7ormg` | every string |  |
| `TS011F_plug_1` ⚠ (tuya) | `TS011F`: `_TZ3008_tary5dvv`, `_TZ3210_iooniers`, `_TZ3008_iooniers`, `_TZ3008_xvfd3nkp`, `_TZ3008_qziabvzj`; zigbeeModel `TS011F` | all but `_TZ3000_cicwjqth` | `AOYAN`, `Zbeacon`, `_TZ3000_266azbg3`, `_TZ3000_2putqrmw`, `_TZ3000_2uollq9d`, `_TZ3000_3ias4w4o`, `_TZ3000_4ux0ondb`, `_TZ3000_amdymr7l`, `_TZ3000_b28wrpvx`, `_TZ3000_cicwjqth`, `_TZ3000_cjrngdr3`, `_TZ3000_gjnozsaz`, `_TZ3000_ko6v90pg`, `_TZ3000_ksw8qtmt`, `_TZ3000_okaz9tjs`, `_TZ3000_ss98ec5d`, `_TZ3000_ww6drja5`, `_TZ3000_y4ona9me`, `_TZ3000_yujkchbz`, `_TZ3000_zloso4jk`, `_TZ3008_1a8m8wd6`, `_TZ3008_avdpejns`, `_TZ3008_reatplte`, `_TZ3210_2putqrmw`, `_TZ3210_2uollq9d`, `_TZ3210_4ux0ondb`, `_TZ3210_5ct6e7ye`, `_TZ3210_cjrngdr3`, `_TZ3210_ddigca5n`, `_TZ3210_jlf1nepw`, `_TZ3210_rwmitwj4`, `_TZ3210_w0qqde0g`, `_TZ3210_zifx0xoj` |
| `TS011F_plug_2` (tuya) | `TS011F`: `_TZ3000_hyfvrar3`, `_TZ3000_v1pdxuqq`, `_TZ3000_8a833yls`, `_TZ3000_bfn1w0mm`, `_TZ3000_nzkqcvvs`, `_TZ3000_rtcrrvia`, `_TZ3000_ysiog9xi`, `_TZ3000_o1jzcxou`, `_TZ3210_nhqka112`, `_TZ3000_uyrhiafs` | every string |  |
| `TS011F_plug_3` (tuya) | `TS011F`: `_TZ3000_2uollq9d` (applicationVersion 192), `_TZ3000_9ni6xxld` (applicationVersion 67), `_TZ3000_cehuw1lw` (softwareBuildID "1.0.5\u0000"); firmware only: `TS011F` (applicationVersion 160), `TS011F` (applicationVersion 100), `TS011F` (applicationVersion 69), `TS011F` (applicationVersion 68), `TS011F` (applicationVersion 65), `TS011F` (applicationVersion 64) | every string | `_TZ3000_266azbg3`, `_TZ3000_okaz9tjs` |
| `TS011F_3_gang` (tuya) | `TS011F`: `_TZ3000_dlug3kbc`, `_TZ3000_9tg32trw` | every string |  |
| `TS0011_switch_module` (tuya) | `TS0011`: `_TZ3000_qmi1cfuq`, `_TZ3000_txpirhfq`, `_TZ3000_ji4araar`, `_TZ3000_tw4ztbp4` | every string |  |
| `TS0012_switch_module` (tuya) | `TS0012`: `_TZ3000_jl7qyupf`, `_TZ3000_nPGIPl5D`, `_TZ3000_kpatq5pq`, `_TZ3000_ljhbw1c9`, `_TZ3000_4zf0crgo` | every string |  |
| `TS0013_switch_module` (tuya) | `TS0013`: `_TZ3000_ypgri8yz`, `_TZ3000_sznawwyw`, `_TZ3000_avotanj3`, `_TZ3000_t7ugva7q` | every string |  |
| `AY-601ZL` (tuya) | zigbeeModel `AY-601ZL`, `AY-801ZL` | every string |  |
| `AY-602ZL` (tuya) | zigbeeModel `AY-602ZL`, `AY-802ZL` | every string |  |
| `AY-603ZL` (tuya) | zigbeeModel `AY-603ZL`, `AY-803ZL` | every string |  |
| `TS011F_with_threshold` (tuya) | `TS011F`: `_TZ3000_cayepv1a`, `_TZ3000_lepzuhto`, `_TZ3000_qystbcjg`, `_TZ3000_zrm3oxsh`, `_TZ3000_303avxxt`, `_TZ3000_ibefeicf`, `_TZ3000_zjchz7pd`, `_TZ3000_zv6x8bt2`, `_TZ3000_yi0n4xfd`, `_TZ3000_3o7r0mno` | every string |  |
| `TS0001_switch_1_gang` (tuya) | `TS0001`: `_TZ3000_bmqxalil`, `_TZ3000_w1tcofu8`, `_TZ3000_ma3mhpx2`, `_TZ3000_wijoqjk1`, `_TZ3000_5rpu3r0d`, `_TZ3000_bbebkwjk` | only `_TZ3000_5rpu3r0d` |  |
| `TS011F_5` (tuya) | `TS011F`: `_TZ3000_cfnprab5`, `_TZ3000_o005nuxx`, `_TZ3000_gdyjfvgm`, `_TZ3000_pl5v1yyy`, `_TZ3000_djgzdba9` | every string |  |
| `TS0004_switch_module_2` (tuya) | `TS0004`: `_TZ3000_5ajpkyq6`, `_TZ3000_knoj8lpk`, `_TZ3000_3n2minvf`, `_TZ3000_tyg4yiat`, `_TZ3210_wts1g2oh` | every string |  |
| `SA-4W` (tuya) | `TS0004`: `_TZ3210_iymfxdis` | every string |  |
| `TYZGTH4CH-D1RF` (tuya) | `TS000F`: `_TZ3218_ya5d6wth` | every string |  |
| `TS0003_3_gang_switch` (tuya) | `TS0003`: `_TZ3000_g9chy2ib` | every string |  |
| `TS0001_1_gang_switch` (tuya) | `TS0001`: `_TZ3000_qvmiyxuk` | every string |  |
| `TS0726_1_gang_scene_switch` (tuya) | `TS0726`: `_TZ3000_5kxl9esg`, `_TZ3002_jn2x20tg`, `_TZ300A_rncj86af`, `_TZ3002_xkxgfxsg` | every string |  |
| `TS0726_2_gang_scene_switch` (tuya) | `TS0726`: `_TZ3000_ezqbvrqz`, `_TZ3002_ymv5vytn`, `_TZ3002_6ahhkwyh`, `_TZ3002_zjuvw9zf`, `_TZ3002_a4kvf6zd`, `_TZ300A_ohjmifiz`, `_TZ3002_tlsvxhxc` | every string |  |
| `TS0726_3_gang_scene_switch` (tuya) | `TS0726`: `_TZ3000_noru9tix`, `_TZ3002_rbnycsav`, `_TZ3002_kq3kqwjt`, `_TZ3002_ybtqbyk3`, `_TZ3002_iedhxgyi`, `_TZ3002_vsom92pp`, `_TZ300A_vqrs45nj`, `_TZ3000_cziew6eu`, `_TZ3000_r2fgo9ks` | every string |  |
| `TS0726_4_gang_scene_switch` (tuya) | `TS0726`: `_TZ3000_rsylfthg`, `_TZ3002_umdkr64x`, `_TZ3002_hkaktryd`, `_TZ3002_pzao9ls1`, `_TZ300A_vkflnsl0`, `_TZ3002_eda6eitk`, `_TZ3000_hurauima`, `_TZ3002_tdf2m4ch` | all but `_TZ3002_tdf2m4ch` |  |
| `ZMO-606-P2` (zemismart) | `TS011F`: `_TZ3000_xeumnff9` | every string |  |
| `ZMO-606-20A` (zemismart) | `TS011F`: `_TZ3000_b1q8kwmh` | every string |  |

## Route B: Tuya datapoint countdown

| Definition | Fingerprints | Datapoints: number, key, converter, expose's unit and range |
|---|---|---|
| `CH8Z` (automaton) | `TS0601`: `_TZE284_1oft6qso` | 9 `countdown_l1` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 10 `countdown_l2` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 11 `countdown_l3` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 12 `countdown_l4` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 13 `countdown_l5` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 14 `countdown_l6` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 15 `countdown_l7` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 16 `countdown_l8` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `ZDMS16-US-W2` (avatto) | `TS0601`: `_TZE204_sdykkwsu` | 6 `countdown_l1` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 12 `countdown_l2` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `ZDMS16-1` (avatto) | `TS0601`: `_TZE204_5cuocqty`, `_TZE204_nqqylykc`, `_TZE28C1000000_nqqylykc`, `_TZE204_2cyb66xl`, `_TZE204_tgdnh7pw`, `_TZE284_nqqylykc`, `_TZE204_huu3td85`, `_TZE284_huu3td85`, `_TZE28C1000000_huu3td85` | 6 `countdown` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `ZDMS16-2` (avatto) | `TS0601`: `_TZE204_o9gyszw2`, `_TZE204_jtbgusdc`, `_TZE284_jtbgusdc`, `_TZE204_fjms2pi9`, `_TZE284_fjms2pi9`, `_TZE28C1000000_jtbgusdc` | 6 `countdown_l1` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 12 `countdown_l2` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `ZBS16` (avatto) | `TS0601`: `_TZE284_udaucpdi` | 103 `countdown` tuya.valueConverter.raw, seconds 0..7210 |
| `ZOT60` (avatto) | `TS011F`: `_TZ3218_pfnjjx6a`, `_TZ3218_fv20refe` | 9 `countdown` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `FK_V02` (frankever) | `TS0601`: `_TZE200_wt9agwf3`, `_TZE200_5uodvhgc`, `_TZE200_1n2zev06` | 9 `countdown` tuya.valueConverter.countdown, s 0..43200 |
| `FK-BV05` (frankever) | `TS0601`: `_TZE200_nbqnmkee` | 11 `countdown` tuya.valueConverter.raw, s 0..86400 |
| `GL-SPI-206P` (gledopto) | `TS0601`: `_TZE204_8fffc3kb`, `_TZE284_gt5al3bl`, `_TZE28C1000000_gt5al3bl` | 7 `countdown` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `ZG-308Z` (hobeian) | `TS0601`: `_TZD200_y0rvjm11`; zigbeeModel `ZG-308Z`, `HS308Z` | 11 `countdown` tuya.valueConverter.raw, s 0..86400 |
| `VM-Zigbee-S02-0-10V` (lonsonho) | `TS0603`: `_TZE600_wxq8dpha\u0000` | 6 `countdown_l1` tuya.valueConverter.raw, s 0..43200 (tuya.exposes.countdown); 12 `countdown_l2` tuya.valueConverter.raw, s 0..43200 (tuya.exposes.countdown) |
| `MG-GPO02Z` (makegood) | `TS0601`: `_TZE200_lq0ffndf` | 7 `countdown_l1` countdownConverter, s 0..43200 (tuya.exposes.countdown); 8 `countdown_l2` countdownConverter, s 0..43200 (tuya.exposes.countdown) |
| `MG-AU03` (makegood) | `TS0601`: `_TZE200_4jvmbiph` | 7 `countdown_l1` countdownConverter, s 0..43200 (tuya.exposes.countdown); 8 `countdown_l2` countdownConverter, s 0..43200 (tuya.exposes.countdown); 9 `countdown_l3` countdownConverter, s 0..43200 (tuya.exposes.countdown) |
| `MG-AU01ZLMV01-XX` (makegood) | `TS0601`: `_TZE200_xnwxmj8z` | 7 `countdown_l1` countdownConverter, s 0..43200 (tuya.exposes.countdown) |
| `MH03-1Z-OLED` (manhot) | `TS0601`: `_TZE284_ncc7uahd`, `_TZE28C1000000_ncc7uahd` | 7 `countdown_1` tuya.valueConverter.raw, s 0..43200 |
| `MH03-2Z-OLED` (manhot) | `TS0601`: `_TZE284_dnhhp8ew`, `_TZE28C1000000_dnhhp8ew` | 7 `countdown_1` tuya.valueConverter.raw, s 0..43200; 8 `countdown_2` tuya.valueConverter.raw, s 0..43200 |
| `MH03-3Z-OLED` (manhot) | `TS0601`: `_TZE284_59dz7ioi`, `_TZE28C1000000_59dz7ioi` | 7 `countdown_1` tuya.valueConverter.raw, s 0..43200; 8 `countdown_2` tuya.valueConverter.raw, s 0..43200; 9 `countdown_3` tuya.valueConverter.raw, s 0..43200 |
| `MH03-4Z-OLED` (manhot) | `TS0601`: `_TZE284_esnu2jxv`, `_TZE28C1000000_esnu2jxv` | 7 `countdown_1` tuya.valueConverter.raw, s 0..43200; 8 `countdown_2` tuya.valueConverter.raw, s 0..43200; 9 `countdown_3` tuya.valueConverter.raw, s 0..43200; 10 `countdown_4` tuya.valueConverter.raw, s 0..43200 |
| `MH03-6Z-OLED` (manhot) | `TS0601`: `_TZE284_zykra2yj`, `_TZE28C1000000_zykra2yj`, `_TZE284_wkvfb2ld`, `_TZE28C1000000_wkvfb2ld` | 7 `countdown_1` tuya.valueConverter.raw, s 0..43200; 8 `countdown_2` tuya.valueConverter.raw, s 0..43200; 9 `countdown_3` tuya.valueConverter.raw, s 0..43200; 10 `countdown_4` tuya.valueConverter.raw, s 0..43200; 11 `countdown_5` tuya.valueConverter.raw, s 0..43200; 12 `countdown_6` tuya.valueConverter.raw, s 0..43200 |
| `MH03-8Z-OLED` (manhot) | `TS0601`: `_TZE284_hwv3by9k`, `_TZE28C1000000_hwv3by9k`, `_TZE284_4ngwn2pj`, `_TZE28C1000000_4ngwn2pj` | 7 `countdown_1` tuya.valueConverter.raw, s 0..43200; 8 `countdown_2` tuya.valueConverter.raw, s 0..43200; 9 `countdown_3` tuya.valueConverter.raw, s 0..43200; 10 `countdown_4` tuya.valueConverter.raw, s 0..43200; 11 `countdown_5` tuya.valueConverter.raw, s 0..43200; 12 `countdown_6` tuya.valueConverter.raw, s 0..43200; 116 `countdown_7` tuya.valueConverter.raw, s 0..43200; 117 `countdown_8` tuya.valueConverter.raw, s 0..43200 |
| `ZS-D1` (moes) | `TS0601`: `_TZE284_a1ovdobn`, `_TZE200_a1ovdobn` | 6 `countdown_1` tuya.valueConverter.raw, s 0..86400 |
| `ZS-D2` (moes) | `TS0601`: `_TZE200_rlqamjhp` | 6 `countdown_1` tuya.valueConverter.raw, s 0..86400; 12 `countdown_2` tuya.valueConverter.raw, s 0..86400 |
| `ZS-D3` (moes) | `TS0601`: `_TZE284_vizxbhco` | 6 `countdown_1` tuya.valueConverter.raw, s 0..86400; 12 `countdown_2` tuya.valueConverter.raw, s 0..86400; 20 `countdown_3` tuya.valueConverter.raw, s 0..86400 |
| `SFD02-Z` (moes) | `TS0601`: `_TZE284_t88bjhfu` | 6 `countdown` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `SFD02-Z_2` (moes) | `TS0601`: `_TZE284_z98viqa6` | 6 `countdown` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `SFL02-Z-1` (moes) | `TS0601`: `_TZE200_stvgmdjz`, `_TZE284_stvgmdjz`, `_TZE200_ydkqbmpt`, `_TZE200_z3u99qxt` | 30 `countdown_l1` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `SFL02-Z-2` (moes) | `TS0601`: `_TZE200_uenof8jd`, `_TZE284_uenof8jd`, `_TZE200_tzyy0rtq`, `_TZE200_hktk6hze` | 30 `countdown_l1` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 31 `countdown_l2` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `SFL02-Z-3` (moes) | `TS0601`: `_TZE200_rd8cdssd`, `_TZE200_wv9ukqca`, `_TZE200_zo0cfekv` | 30 `countdown_l1` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 31 `countdown_l2` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 32 `countdown_l3` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `SFL02-Z-4` (moes) | `TS0601`: `_TZE200_dq8bu0pt`, `_TZE200_hmabvy81`, `_TZE200_9dhenr94` | 30 `countdown_l1` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 31 `countdown_l2` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 32 `countdown_l3` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 33 `countdown_l4` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `NAS-WV03B` (neo) | `TS0601`: `_TZE204_rzrrjkz2`, `_TZE284_rzrrjkz2`, `_TZE204_uab532m0`, `_TZE284_uab532m0`, `_TZE204_nnhwcvbk`, `_TZE284_nnhwcvbk`, `_TZE204_z7a2jmyy`, `_TZE284_z7a2jmyy`, `_TZE204_4fblxpma`, `_TZE284_4fblxpma` | 5 `countdown` tuya.valueConverter.raw, not read; 6 `countdown_left` tuya.valueConverter.raw, not read |
| `NAS-WV03B2` (neo) | `TS0601`: `_TZE204_a9ojznj8`, `_TZE284_a9ojznj8` | 5 `countdown` tuya.valueConverter.raw, not read; 6 `countdown_left` tuya.valueConverter.raw, not read |
| `D5Z` (nous) | `TS0601`: `_TZE204_t9ffmdin` | 105 `countdown` tvc.raw, not read |
| `D1Z` (nous) | `TS0601`: `_TZE204_vfnf7zhq` | 105 `countdown` tvc.raw, not read |
| `SA-WK 4X4` (nova_digital) | `TS0601`: `_TZE204_bb5xlia1` | 7 `countdown_l1` tuya.valueConverter.raw, s 0..43200; 8 `countdown_l2` tuya.valueConverter.raw, s 0..43200; 9 `countdown_l3` tuya.valueConverter.raw, s 0..43200; 10 `countdown_l4` tuya.valueConverter.raw, s 0..43200; 11 `countdown_l5` tuya.valueConverter.raw, s 0..43200; 12 `countdown_l6` tuya.valueConverter.raw, s 0..43200 |
| `QADZ1LR` (qa) | `TS0601`: `_TZE28C1000000_brx4eku5` | 6 `countdown` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `ZBN-DJ-63` (tuya) | `TS0601`: `_TZE204_lb0fsvba` | 105 `countdown` tuya.valueConverter.countdown, s 0..43200 |
| `ZN2S-RS02E` (tuya) | `TS0601`: `_TZE204_zpvusbtv`, `_TZE284_zpvusbtv` | 7 `countdown_l1` tuya.valueConverter.countdown, s 0..86400; 8 `countdown_l2` tuya.valueConverter.countdown, s 0..86400 |
| `TS0601_3gang_rkbxtclc` (tuya) | `TS0601`: `_TZE204_rkbxtclc` | 7 `countdown_l1` tuya.valueConverter.countdown, s 0..86400; 8 `countdown_l2` tuya.valueConverter.countdown, s 0..86400; 9 `countdown_l3` tuya.valueConverter.countdown, s 0..86400 |
| `TS0601_4gang_7ytnacie` (tuya) | `TS0601`: `_TZE204_7ytnacie`, `_TZE204_hewlydpz` | 7 `countdown_l1` tuya.valueConverter.countdown, s 0..86400; 8 `countdown_l2` tuya.valueConverter.countdown, s 0..86400; 9 `countdown_l3` tuya.valueConverter.countdown, s 0..86400; 10 `countdown_l4` tuya.valueConverter.countdown, s 0..86400 |
| `TS0601_dimmer_1_gang_1` (tuya) | `TS0601`: `_TZE200_ip2akl4w`, `_TZE200_1agwnems`, `_TZE200_la2c2uo9`, `_TZE200_579lguh2`, `_TZE200_vucankjx`, `_TZE200_4mh6tyyo`, `_TZE204_hlx9tnzb`, `_TZE204_n9ctkb6j`, `_TZE204_9qhuzgo0`, `_TZE200_9cxuhakf`, `_TZE200_a0syesf5`, `_TZE200_3p5ydos3`, `_TZE200_swaamsoy`, `_TZE200_ojzhk75b`, `_TZE200_w4cryh2i`, `_TZE200_dfxkcots`, `_TZE204_68utemio`, `_TZE200_9i9dt8is`, `_TZE200_ctq0k47x`, `_TZE200_ebwgzdqq`, `_TZE204_vevc4c6g`, `_TZE200_0nauxa0p`, `_TZE200_ykgar0ow`, `_TZE284_m1cvyneb`, `_TZE200_0hb4rdnp`, `_TZE200_gne0e6mk`, `_TZE284_68utemio`, `_TZE200_itp8dt7f`, `_TZE28C1000000_68utemio`, `_TZE284_xc7dve2g` | 6 `countdown` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `TS0601_dimmer_1_gang_2` (tuya) | `TS0601`: `_TZE200_whpb9yts` | 6 `countdown` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `TS0601_dimmer_3` (tuya) | `TS0601`: `_TZE200_vm1gyrso`, `_TZE204_1v1dxkck`, `_TZE204_znvwzxkq`, `_TZE284_znvwzxkq`, `_TZE200_vizxbhco` | 6 `countdown_l1` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 12 `countdown_l2` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 20 `countdown_l3` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `TS0601_dimmer_4` (tuya) | `TS0601`: `_TZE200_bxoo2swd`, `_TZE204_bxoo2swd`, `_TZE200_tsxpl0d0` | 6 `countdown_l1` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 12 `countdown_l2` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `TS0601_dimmer_5` (tuya) | `TS0601`: `_TZE204_dcnsggvz`, `_TZE200_dcnsggv`, `_TZE200_dcnsggvz` | 6 `countdown` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `OXT-4CH-RELAY-AC` (tuya) | `TS0601`: `_TZE28C1000000_f5efvtbv`, `_TZE204_m9dzckna` | 7 `countdown_l1` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 8 `countdown_l2` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 9 `countdown_l3` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 10 `countdown_l4` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `TS0601_switch_6_gang` (tuya) | `TS0601`: `_TZE200_mwvfvw8g`, `_TZE200_wnp4d4va`, `_TZE200_cduqh1l0`, `_TZE204_cduqh1l0`, `_TZE200_emxxanvi`, `_TZE204_g4au0afs`, `_TZE204_w1wwxoja`, `_TZE204_lmgrbuwf`, `_TZE204_wskr3up8`, `_TZE204_gxbdnfrh`, `_TZE284_g1enhdsi`, `_TZE284_r731zlxk`, `_TZE284_znkkcauq`, `_TZE284_1iii6x0y` | 7 `countdown_l1` tuya.valueConverter.raw, not read; 8 `countdown_l2` tuya.valueConverter.raw, not read; 9 `countdown_l3` tuya.valueConverter.raw, not read; 10 `countdown_l4` tuya.valueConverter.raw, not read; 11 `countdown_l5` tuya.valueConverter.raw, not read; 12 `countdown_l6` tuya.valueConverter.raw, not read |
| `TO-6 W/B` (tuya) | `TS0601`: `_TZE200_rqhnxkqu` | 30 `countdown_l1` tuya.valueConverter.raw, s 0..43200; 31 `countdown_l2` tuya.valueConverter.raw, s 0..43200; 32 `countdown_l3` tuya.valueConverter.raw, s 0..43200; 33 `countdown_l4` tuya.valueConverter.raw, s 0..43200; 34 `countdown_l5` tuya.valueConverter.raw, s 0..43200; 35 `countdown_l6` tuya.valueConverter.raw, s 0..43200 |
| `TO-WK-1W/B` (tuya) | `TS0601`: `_TZE284_3xnyj4ga` | 7 `countdown_l1` tuya.valueConverter.raw, s 0..43200; 8 `countdown_l2` tuya.valueConverter.raw, s 0..43200 |
| `TO-WK-2W/B` (tuya) | `TS0601`: `_TZE284_exfilann` | 7 `countdown_l1` tuya.valueConverter.raw, s 0..43200; 8 `countdown_l2` tuya.valueConverter.raw, s 0..43200; 9 `countdown_l3` tuya.valueConverter.raw, s 0..43200 |
| `TO-DM-W/B` (tuya) | `TS0601`: `_TZE284_5yah8qx4` | 6 `countdown` tuya.valueConverter.raw, s 0..86400 |
| `MG-ZG01W` (tuya) | `TS0601`: `_TZE200_gbagoilo`, `_TZE284_xnwxmj8z` | 7 `countdown` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `_TZE28C1000000_jlbsptkl` (tuya) | `TS0601`: `_TZE28C1000000_jlbsptkl` | 7 `countdown` tuya.valueConverter.raw, s 0..43200 |
| `_TZE28C1000000_jaunkx9g` (tuya) | `TS0601`: `_TZE28C1000000_jaunkx9g` | 7 `countdown_1` tuya.valueConverter.raw, s 0..43200; 8 `countdown_2` tuya.valueConverter.raw, s 0..43200 |
| `_TZE28C1000000_usmqzgdm` (tuya) | `TS0601`: `_TZE28C1000000_usmqzgdm` | 7 `countdown_1` tuya.valueConverter.raw, s 0..43200; 8 `countdown_2` tuya.valueConverter.raw, s 0..43200; 9 `countdown_3` tuya.valueConverter.raw, s 0..43200 |
| `TS0049` (tuya) | zigbeeModel `TS0049` | 111 `countdown` tuya.valueConverter.raw, s 0..43200 (tuya.exposes.countdown) |
| `LYAI-14` (tuya) | `TS0049`: `_TZ3290_ixd9mvv4` | 11 `countdown` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `TS0601_water_switch` (tuya) | `TS0601`: `_TZE284_eaet5qt5`, `_TZE284_fhvpaltk` | 13 `countdown_l1` tuya.valueConverter.raw, not read; 14 `countdown_l2` tuya.valueConverter.raw, not read |
| `TS0601_fan_switch` (tuya) | `TS0601`: `_TZE200_r32ctezx`, `_TZE204_r32ctezx`, `_TZE28C1000000_z5jz7wpo` | 2 `countdown` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `TS0601_switch_8_2` (tuya) | `TS0601`: `_TZE204_adlblwab`, `_TZE284_adlblwab` | 9 `countdown_l1` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 10 `countdown_l2` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 11 `countdown_l3` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 12 `countdown_l4` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 13 `countdown_l5` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 14 `countdown_l6` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 15 `countdown_l7` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 16 `countdown_l8` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `ZS-TYG3-SM-61Z` (tuya) | `TS0601`: `_TZE200_0j5jma9b`, `_TZE200_h2rctifa` | 7 `countdown_l1` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 8 `countdown_l2` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 9 `countdown_l3` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 10 `countdown_l4` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 11 `countdown_l5` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 12 `countdown_l6` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `ZS-TYG3-SM-21Z` (tuya) | `TS0601`: `_TZE200_wunufsil` | 7 `countdown_l1` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 8 `countdown_l2` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `ZS-TYG3-SM-31Z` (tuya) | `TS0601`: `_TZE200_vhy3iakz` | 7 `countdown_l1` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 8 `countdown_l2` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 9 `countdown_l3` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `ZS-TYG3-SM-41Z` (tuya) | `TS0601`: `_TZE200_k6jhsr0q`, `_TZE204_unsxl4ir` | 7 `countdown_l1` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 8 `countdown_l2` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 9 `countdown_l3` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown); 10 `countdown_l4` tuya.valueConverter.countdown, s 0..43200 (tuya.exposes.countdown) |
| `GX03` (tuya) | `TS0601`: `_TZE284_8zizsafo`, `_TZE284_iilebqoo`, `_TZE284_n41i9jyt` | 13 `countdown_1` tuya.valueConverter.countdown, min ?..?; 14 `countdown_2` tuya.valueConverter.countdown, min ?..? |
| `EPJ-ZB` (tuya) | `TS0601`: `_TZ3210_emqmwtym`; zigbeeModel `5rta89nj` | 108 `countdown` tuya.valueConverter.raw, s 10..90 |
| `_TZE284_z5jz7wpo` (tuya) | `TS0601`: `_TZE284_z5jz7wpo` | 2 `countdown_hours` inline converter, h 0.25..12 |
| `DS-1450WN` (tuya) | `TS0601`: `_TZE204_mvtclclq`, `_TZE284_mvtclclq` | 7 `countdown_usb_a` tuya.valueConverter.countdown, s 0..86400; 8 `countdown_usb_c` tuya.valueConverter.countdown, s 0..86400; 9 `countdown_plug_1` tuya.valueConverter.countdown, s 0..86400; 10 `countdown_plug_2` tuya.valueConverter.countdown, s 0..86400 |
| `RM28-LE` (tuya) | `TS0601`: `_TZE200_fodv6bkr` | 8 `countdown` inline converter, not read; 9 `countdown_left` tuya.valueConverter.raw, s ?..? |
| `ZVL-PRO` (tuya) | `TS0601`: `_TZE200_fphxkxue` | 11 `countdown` tuya.valueConverter.raw, s 0..86400 |
| `TS0601_smart_temperature_switch` (tuya) | `TS0601`: `_TZE284_roujjevx` | 4 `countdown` tuya.valueConverter.countdown, not read |
| `TS0601_multifunction_switch` (tuya) | `TS0601`: `_TZE284_7e6v8u9f`, `_TZE28C1000000_rzdkn5rx` | 7 `countdown` tuya.valueConverter.countdown, s 0..86400 |
| `TS0601_power_monitoring_switch` (tuya) | `TS0601`: `_TZE204_apiu8k13`, `_TZE284_q9qytwfa` | 7 `countdown` tuya.valueConverter.countdown, m 0..120 |
| `ZMS-206US-1` (zemismart) | `TS0601`: `_TZE204_sa2ueffe`, `_TZE204_zuepxzck`, `_TZE284_lnyz4a6v` | 7 `countdown` tuya.valueConverter.raw, s 0..43200 |
| `ZMS-206EU-2` (zemismart) | `TS0601`: `_TZE284_3ctwoaip`, `_TZE204_3ctwoaip`, `_TZE284_dmckrsxg`, `_TZE28C1000000_dmckrsxg` | 7 `countdown_l1` tuya.valueConverter.raw, not read; 8 `countdown_l2` tuya.valueConverter.raw, not read |
| `ZMS-206EU-3` (zemismart) | `TS0601`: `_TZE204_k7v0eqke`, `_TZE204_iyki9kjp`, `_TZE284_k7v0eqke`, `_TZE284_e4pf6l87`, `_TZE28C1000000_e4pf6l87` | 7 `countdown_l1` tuya.valueConverter.raw, not read; 8 `countdown_l2` tuya.valueConverter.raw, not read; 9 `countdown_l3` tuya.valueConverter.raw, not read |
| `ZMS-206US-4` (zemismart) | `TS0601`: `_TZE204_wwaeqnrf`, `_TZE284_wwaeqnrf`, `_TZE204_y4jqpry8`, `_TZE284_y4jqpry8`, `_TZE204_xibaabmu`, `_TZE284_xibaabmu`, `_TZE28C1000000_xibaabmu`, `_TZE204_08qc13ct`, `_TZE28C1000000_y4jqpry8`, `_TZE28C1000000_pmbxyf97` | 7 `countdown_l1` tuya.valueConverter.raw, not read; 8 `countdown_l2` tuya.valueConverter.raw, not read; 9 `countdown_l3` tuya.valueConverter.raw, not read; 10 `countdown_l4` tuya.valueConverter.raw, not read |
| `ZMS-208US-2` (zemismart) | `TS0601`: `_TZE284_a2teqi5u`, `_TZE28C1000000_a2teqi5u` | 7 `countdown_l1` tuya.valueConverter.raw, not read; 8 `countdown_l2` tuya.valueConverter.raw, not read |
| `ZMS-208US-3` (zemismart) | `TS0601`: `_TZE284_xvywzhmi`, `_TZE28C1000000_xvywzhmi` | 7 `countdown_l1` tuya.valueConverter.raw, not read; 8 `countdown_l2` tuya.valueConverter.raw, not read; 9 `countdown_l3` tuya.valueConverter.raw, not read |
| `ZMZ609-2` (zemismart) | `TS0601`: `_TZE284_o409r73p`, `_TZE28C1000000_o409r73p` | 7 `countdown_l1` tuya.valueConverter.countdown, s 0..43200; 8 `countdown_l2` tuya.valueConverter.countdown, s 0..43200 |

## Route C and the private Tuya command

| Definition | Fingerprints | Route |
|---|---|---|
| `CK-BL702-MSW-01(7010)` (ewelink) | zigbeeModel `CK-BL702-MSW-01(7010)`, `CK-BL702-MSW-01(7011)-1` | C |
| `TS110E_1gang_2` (tuya) | `TS110E`: `_TZ3210_ngqk6jia`, `_TZ3210_weaqkhab`, `_TZ3210_k1msuvg6`, `_TZ3210_o235agwx` | Tuya's private command |
