# What Zigbee light vendors publish about their ZCL calls, and what certification tests (2026-11-25)

Research for [the Aqara Verified plan](../plans/2026-11-24-aqara-verified.md), Decision 6. Question: can a call pattern a
vendor or the Zigbee spec documents make another vendor's Zigbee lights **Documented** in DeviceSide without a hardware
pass on them? It answers the terms of [docs/evidence.md](../evidence.md), Levels: Documented by **(a) a sibling's call**
(the vendor's own documentation gives the call identically for both classes; a class spanning vendors is never
Documented by another vendor's pass; a field never is) or **(b) a certified read** (certification sends the same read to
every device the class holds, the class keys on a marker certified devices carry, a write never qualifies).

It extends, and does not redo, [other brands: ExecuteIfOff writes and reads](../integrations/zigbee2mqtt/research/2026-11-24-other-brands-execute-if-off-and-reads.md),
[other brands: dimming](../integrations/zigbee2mqtt/research/2026-11-24-other-brands-dimming.md),
[ZCL rev 8: Level Control and On/Off](2026-11-17-zcl-rev8-level-and-onoff.md) and
[timed-on call patterns](../integrations/zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md). No device was
touched. All pages were read on 2026-11-24 unless a row says otherwise.

Method: four researchers (Aqara and Tuya; Signify, Sengled and Gledopto; Innr, Ledvance and IKEA; certification) read
primary sources only (vendor documentation, vendor SDK documentation, CSA specifications, listings and compliance
documents). Secondary sources are labeled. The fetch tool summarizes pages with a model, so quotes taken that way are
marked "extract" and were not checked against raw HTML; CSA certificate IDs and compliance-zip links were re-checked with
raw `curl`. The CSA test-spec and PICS text was read locally from the downloaded files.

## Synthesis

- **No vendor publishes its lights' ZCL calls in a form that could satisfy (a).** Aqara, Innr, Ledvance, IKEA, Sengled,
  Gledopto and Signify publish no document that says "moveToLevel / move / stop / moveToColor / onWithTimedOff work like
  this on our lights", identical to the ZCL spec or otherwise. Tuya is the one vendor that lists ZCL command ids for
  lights, without payload fields. What they do publish is the radio-level claim ("Zigbee 3.0", "Zigbee Light Link") and,
  through the CSA, certification paperwork.
- **The CSA paperwork is the only primary source that reaches the call level, and it is public per product.** Each
  Zigbee 3.0 listing on csa-iot.org links a "Compliance Document" zip with no login. It holds the vendor's PICS (some
  filled, some blank templates) and, in some, the CSA's own ZCL cluster test specifications.
- **Those test specs run DeviceSide's exact ExecuteIfOff call.** LC-TC-07S (Level Control) and CC-TC-09S (Color Control)
  send moveToLevel / moveToColor with OptionsMask 0x01, OptionsOverride 0x01, transition 0 to an off light, and read
  CurrentLevel or CurrentX/Y back. Move, Stop and Step with ExecuteIfOff are "assumed", not run. Every other step sends
  the commands with the option fields omitted.
- **Reads: only the mandatory attributes are guaranteed.** Certification reads every mandatory attribute (CurrentLevel,
  OnOff, Options, ClusterRevision). ColorMode, ColorCapabilities, ColorTemperatureMireds, hue, saturation and OnTime are
  optional and tested only when the vendor's PICS says Yes.
- **onWithTimedOff is not guaranteed.** On With Timed Off (0x42), OnTime and OffWaitTime are Optional in the On/Off PICS;
  a certified Ledvance bulb declares No, an IKEA white bulb declares Yes.
- **No per-product test result is public.** The compliance zips hold the PICS and test-spec templates, not pass or fail
  logs, and the current test plan and tool are members-only. A pass is inferred from "certified, and the PICS says Options
  is implemented", never shown.
- **Not readable:** ZLO 15-0014, ZCL 7 and 8 and Base Device Behavior from csa-iot.org (HTTP 403 to scripted clients, behind
  a request form), the Hue developer API pages (login), Aqara's open-platform docs (JS shell and 403). Each is
  UNVERIFIED below, and no workaround was used.

## Part 1: What each vendor publishes

Legend for the last column, against the ZCL spec as quoted in
[2026-11-17](2026-11-17-zcl-rev8-level-and-onoff.md): **same** (states the call with the spec's fields), **ids only**,
**none**.

| Vendor | Published, where | Call-level content | Same as spec? |
|---|---|---|---|
| Aqara | Studio and cloud pairing docs, product spec pages | none | none |
| Tuya | Developer platform lighting access standard and light kit pages | ZCL command ids and names | ids only |
| Signify (Hue) | Public Zigbee 3.0 post; developer API docs are login-gated; CSA PICS and test specs | PICS "Yes" answers; test specs in the CSA bundle | CSA's text, not Signify's |
| Sengled | nothing found | none | none |
| Gledopto | manual and shop pages | none | none |
| Innr | EU Data Notice (attributes), CSA listings | attribute names only | none |
| Ledvance | FAQ, datasheets, CSA PICS | PICS declarations | CSA's text, not Ledvance's |
| IKEA | release notes, OTA feed, CSA PICS | PICS declarations | CSA's text, not IKEA's |

### Aqara

- **Nothing published on ZCL light calls.** No Level Control or Color Control usage, ExecuteIfOff, attribute read list,
  onWithTimedOff or 0xFCC0 attribute table was reachable.
- Reachable docs cover pairing, Aqara Studio and the cloud API only: the Studio Zigbee page says "This document explains
  how to connect Aqara Zigbee devices to Aqara Studio" (extract,
  <https://docs.aqara.com/docs/aqara-studio/device-integration/zigbee/>). The T2 bulb spec page lists "Connectivity
  protocol: Thread, Zigbee, Bluetooth" and no clusters
  (<https://eu.aqara.com/en-eu/pages/product-specs/aqara-led-bulb-t-2-e-27>, extract).
- **Blocked, UNVERIFIED:** <https://developer.aqara.com/> returns a JS shell with no content; <https://opendoc.aqara.com/en/docs/>
  returns HTTP 403; the T2 user manuals were seen only as search snippets (radio spec, "in Zigbee mode, users can access
  exclusive Aqara features ... via an Aqara hub"); a guessed GitHub org URL returned 404.
- **CSA:** the product finder (keyword "aqara", End Products,
  <https://www.csa-iot.org/csa-iot_products/?p_keywords=aqara&p_type%5B%5D=14>) showed 12 Lumi "Aqara Smart Light"
  listings on page 1, all Matter, none Zigbee 3.0. Only page 1 of 42 was seen, so a Zigbee 3.0 certificate for an Aqara
  light is UNVERIFIED either way.
- Secondary only (not evidence of what Aqara publishes): community threads and the Z2M device database show cluster
  presence and 0xFCC0 reverse engineering for the bulb (e.g.
  <https://github.com/Koenkk/zigbee2mqtt/issues/26684>, endpoint 1 lists 0x0008 for `lumi.light.agl003`).

### Tuya

The one vendor whose own docs name the standard ZCL commands for lights.

- Lighting access standard (<https://developer.tuya.com/en/docs/iot/tuya-zigbee-lighting-access-standard?id=K9ik6zvod83fi>,
  extract): On/Off 0x0006 commands 0x00 Off and 0x01 On, plus Tuya's own 0xF0 CountDown (attribute 0xF000); Level Control
  0x0008 commands 0x00 to 0x07 (the with-on/off variants included) and attribute CurrentLevel; Color Control 0x0300
  attributes ColorMode (0x0008) and ColorCapabilities (0x400A) and commands 0x00 to 0x0A, 0x47, 0x4B, 0x4C. Attribute read
  and write are "defined by Zigbee Cluster Library Specification" (extract). **No transition time field, no
  OptionsMask/OptionsOverride, no ExecuteIfOff semantics, no onWithTimedOff (0x42).**
- Light kit (<https://developer.tuya.com/en/docs/iot-device-dev/tuyaos_zigbee_light_product_development_kit?id=Kd6efghkquo9d>,
  extract): lists the Options attribute (0x000F, map8, default 0x00) with its bits unexplained; fade time appears only as
  `LIGHT_ON_GRADUAL_TIME_MS` / `LIGHT_OFF_GRADUAL_TIME_MS` "a Tuya-specific feature"; "The kit includes handlers for most
  standard Zigbee 3.0 commands" ("most" is not all).
- **The documented color path is private.** Color temperature and color go through Tuya-specific Color Control commands
  0xE0 and 0xE1 (DP4 and DP5), brightness DP3 through Level Control 0xF0; Tuya's "standard instruction set" for lights
  (<https://developer.tuya.com/en/docs/iot/dj?id=K9i5ql3v98hn3>, extract) is a cloud DP schema that never mentions ZCL.
  The private cluster 0xEF00 carries DP data
  (<https://developer.tuya.com/en/docs/iot/tuya-zigbee-universal-docking-access-standard?id=K9ik6zvofpzql>, extract).
- **Docs vary per product type:** the dimmer-switch page lists only Level Control 0x00, 0x02, 0x04 and no Color Control
  (<https://developer.tuya.com/en/docs/iot/tuya-smart-dimmer-switch-single-phrase-input-without-neutral-line?id=K9ik6zvokodvn>,
  extract). The lighting page cannot speak for the whole Tuya class.
- Tuya's own timer is the private CountDown (0xF0 / 0xF000), a different call from ZCL's onWithTimedOff; see
  [2026-11-14](../integrations/zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md).
- UNVERIFIED: the Tuya SDK repos (<https://github.com/tuya>) were listed, not read; their Level Control handler would show
  transition and options handling. One support page (<https://support.tuya.com/en/help/_detail/K9i6hux6c5oo2>) failed on
  redirects.

### Signify (Hue)

- **Developer API docs are login-gated.** The Lights API, v2, "Watch that Transition Time!" and the system-performance
  pages (under <https://developers.meethue.com/develop/>) returned the login page. Contents UNVERIFIED. They are bridge
  REST calls (`transitiontime`, v2 `dynamics.duration`), not ZCL, so even when readable they do not state the Zigbee call.
  A web-archive copy was not used to get past the login.
- Public Zigbee 3.0 post (<https://developers.meethue.com/zigbee-3-0-support-in-hue-ecosystem/>, 2018-02-15): "Since launch
  in 2012, Philips Hue has supported open interoperability using the Zigbee Light Link standard." and "Philips Hue is
  committed to certify new products launched in 2018 using Zigbee 3.0 instead of Zigbee Light Link." It states the
  interoperability basis and no commands. The 2025-06-10 news item "Hue lights are now able to update their state while
  being off, and the change will apply when the light is back on" (home page excerpt, body gated) describes a bridge
  feature, not ZCL ExecuteIfOff.
- No official "Friends of Hue" technical page was found (press and blogs only, secondary).
- **CSA, ZLL listing:** <https://csa-iot.org/csa_product/philips-hue-product-family-010c/> (ZIG16140ZLL10346-24, 2016-09-27).
  Its PICS (ZigBee 11-0038-05, ZLL profile, completed 2016-09-27) answers "Yes" to Level Control Move To Level, Move, Step,
  Stop and their with-on/off forms, to On/Off "on with timed off command" (OOCSCR6, M under the ZLL profile) and to Color
  Control move to hue, hue and saturation, color, color temperature and the enhanced and step variants. It predates ZCL
  rev 7: **no Options attribute, nothing on ExecuteIfOff.** It cites the ZLL and ZCL clauses by reference, so its call
  identity is "same as the standard, by clause number".
- **CSA, Zigbee 3.0 listing:** <https://csa-iot.org/csa_product/philips-hue-product-family-0111-4/> (ZIG18181ZB330229-24,
  2018-12-07). Its compliance zip includes the CSA test specs Level Control 16-02860-005 and Color Control 16-02862-004
  (both dated 2017-07-03); see Part 2. That the product passed those cases is UNVERIFIED (no result list).

### Sengled

- **Nothing published at the call level.** No developer portal or ZCL documentation found; the "Sengled API" results are
  community cloud-API reverse engineering (secondary, and Wi-Fi, not Zigbee). Support page returned HTTP 402.
- CSA: keyword searches for "sengled" returned "No Entries Found". A Zigbee 3.0 certificate for one model (E21-N13,
  ZIG19051ZB330293-24, 2019-03-27) is known only from a search-engine summary of a `zigbeealliance.org` page that now
  redirects: **UNVERIFIED**. No compliance document reached.

### Gledopto

- **Nothing published at the call level.** The manual (<https://www.gledopto.com/201p-manual-en.pdf>) says "The product
  works with many ZigBee 3.0 Gateways like Philips Hue, Amazon ECho Plus or SmartThings" and describes Touch Link pairing;
  the shop page says "compatible with most ZigBee ZLL and ZigBee 3.0 gateways ... tested with Philips Hue" (reseller,
  <https://www.gledopto.eu/rgbcct-led-controller-zigbee-compatible-eng>). No cluster, command or profile statement.
- Its certificate page lists FCC, SAA, CE, RoHS and no CSA certificate (<https://www.gledopto.com/h-col-383.html>);
  CSA keyword "gledopto" returned no entries. Firmware and catalogue pages showed navigation only.

### Innr

- **No developer or integration documentation** (<https://www.innr.com/service>: manuals, declarations of conformity, FAQs).
  Product pages returned HTTP 429 (not retried in a loop): UNVERIFIED.
- The EU Data Notice, Zigbee Products v2.0 (DocID innr-SAR-000-0002-EN, 2026-01-06; only a Vattenfall-hosted copy was
  found, <https://www.vattenfall.nl/media/1.-thuis/energie-besparen/energiebesparen/innr-data-act.pdf>) names attributes by
  cluster: OnOff and StartUpOnOff; CurrentLevel, OnOffTransitionTime ("used for fading on/off"), StartUpCurrentLevel;
  CurrentX/Y, hue, saturation, color temperature. It says "The only way in which Innr Zigbee products allow to retrieve
  their product data is by means of the Zigbee protocol". **Attributes only: no commands, no Options, no ExecuteIfOff, no
  onWithTimedOff.**
- CSA: Innr listings are Zigbee 3.0, 2018 to 2019, for example <https://csa-iot.org/csa_product/innr-zigbee-3-0-e27-bulb-rgbw/>
  (ZIG18043ZB330091-24, 2018-05-29) and <https://csa-iot.org/csa_product/innr-dimmable-retrofit-lights/> (ZIG19100ZB330342-24,
  2019-05-14, "support Zigbee On/Off and Level Control clusters for remote switching and stepless dimming", the one
  cluster statement on any listing read). Their zips hold **blank** CSA test specs and a filled Base Device Behavior PICS,
  and no filled Level or Color Control PICS, so there is no per-product declaration of Innr's commands or Options
  (UNVERIFIED for Options).

### Ledvance (and Osram Lightify)

- **No developer or ZCL documentation.** The SMART+ FAQ
  (<https://www.ledvance.com/en-int/home-lighting/services/faq/faq-for-smart-zigbee-products>) covers pairing and power-on
  defaults only. Datasheets and an EU Data Act PDF (2025-08-11) say "ZigBee 3.0" and "Datenformat gemäß ZigBee Cluster
  Library". <https://docs.lightify-api.com/> (Osram Lightify) is a cloud API whose content could not be retrieved: UNVERIFIED.
- CSA: Ledvance listings are Zigbee 3.0 (e.g. <https://csa-iot.org/csa_product/a60-tw-z3/>, ZIG18157ZB330205-24, 2018-10-15;
  <https://csa-iot.org/csa_product/a60-rgbw-t-2/>; <https://csa-iot.org/csa_product/par16-rgbw-z3/>); Osram Lightify is ZLL
  (2014, <https://csa-iot.org/csa_product/lightify-flex-rgbw/>). The A60 RGBW T and A60 TW zips hold filled PICS with the
  eight Level Control commands, Options (0x000F), and for the RGBW part Color Control commands 0x06, 0x07, 0x0A and
  ColorCapabilities. The A60 TW (a color-temperature bulb) answers N to the hue and saturation commands. The A60 DIM Z3 zip
  (<https://csa-iot.org/csa_product/a60-dim-z3/>) holds blank test specs only.

### IKEA

- **No developer or ZCL documentation.** Release notes (<https://ww8.ikea.com/ikeahomesmart/releasenotes/releasenotes.html>)
  and the OTA feed (<http://fw.ota.homesmart.ikea.net/feed/version_info.json>, image metadata only) contain no ZCL,
  transition or ExecuteIfOff text. The DIRIGERA and TRADFRI gateway APIs are community reverse-engineered (secondary); the
  DIRIGERA announcement (<https://www.ikea.com/global/en/newsroom/innovation/ikea-dirigera-matter-bridge-240911/>) is not a
  developer document.
- CSA: a mix. TRADFRI STD WW (<https://csa-iot.org/csa_product/tradfri-std-ww-2/>, Zigbee 3.0, ZIG23100ZB331568-24,
  2023-08-09) has a filled ZCL 8 XML PICS: the eight Level Control commands, Options (0x000F), OnLevel, and On/Off **On With
  Timed Off (0x42)** with OnTime and OffWaitTime. The TRADFRI CWS bulb (<https://csa-iot.org/csa_product/tradfri-led-bulb-cws/>)
  is a **ZLL** listing (ZIG20011ZLL10647-24, 2020-06-16) with a ZLL PICS answering Yes to Move To Level (with and without
  on/off), Move To Color and Stop Move Step. The TRADFRI Driver is Zigbee 3.0 (2021), zip not opened.

## Part 2: What certification tests

All from CSA documents inside product compliance zips (the CSA specification-download page lists no test specs,
<https://csa-iot.org/developer-resource/specifications-download-request/>). Read: Ledvance A60 TW (editors copies, 2018),
Ledvance PAR16 RGBW (2018), Innr RB 245 (clean 2017 PDFs, <https://csa-iot.org/csa_product/innr-zigbee-3-0-e14-candle-warm-white/>),
and the Hue 0111 bundle (errata copies dated 2017-07-03). The spec text is the Zigbee Alliance's; the zips are copies the
vendor filed. Documents: Level Control 15-0312-05 / 15-0311-05 and 16-02860-005, Color Control 15-0314 / 15-0313-05 and
16-02862-004, On/Off 15-0310 / 15-0309-05. Versions "1.0", April 2016, written against the ZLO 1.0 drafts (they already
carry Options, which [2026-11-17](2026-11-17-zcl-rev8-level-and-onoff.md) places in ZCL rev 7, November 2017).

| Question | What the primary documents show |
|---|---|
| moveToLevel with ExecuteIfOff and OptionsMask/OptionsOverride | **Yes.** LC-TC-07S: light off, Options written 0x00; moveToLevel level 0x01, transition 0, fields omitted: "DUT SERVER does nothing", CurrentLevel read stays 0x80; mask 0x01 override 0x00: nothing; **mask 0x01 override 0x01: the light stays off and CurrentLevel reads 0x01**. Then Options = 0x01: moveToLevel 0x80 with the fields omitted executes (light stays off, CurrentLevel 0x80); mask 0x01 override 0x00 with 0xfe suppresses it (CurrentLevel stays 0x80); mask 0x01 override 0x01 with 0xfe reads 0xfe. |
| ExecuteIfOff on Move, Stop, Step | Not run: "it is assumed that the Step, Move and Stop commands exhibit the same behavior. If preferred, the tester can either repeat the test for each command or substitute a random command". |
| Color Control | CC-TC-09S mirrors it with moveToColor, read back through CurrentX/Y (mask 1 override 1 on an off light reads the new X/Y). Run "If supported in the ColorCapabilities of the DUT SERVER"; the note says other color commands are assumed to behave the same. |
| Option fields elsewhere | "Unless otherwise specified, when the Move to level, Step, Move and Stop commands are used, the OptionsMask and OptionsOverride fields of SHALL NOT be included." Ordinary test traffic is the legacy form. |
| Options attribute | M in both Level Control (LC.S.A000f) and Color Control PICS. LC-TC-01S reads each mandatory attribute and writes the default back; LC-TC-07S writes 0x00 then 0x01. |
| Attribute reads | LC-TC-01S and CC-TC-01S read each mandatory attribute; an optional attribute the device lacks must answer a non-success status, not time out. LC-TC-02S reads CurrentLevel, OnOff, RemainingTime; CC-TC-02S reads ColorCapabilities, RemainingTime, CurrentX/Y, ColorMode, EnhancedColorMode; CC-TC-04S reads ColorTempPhysicalMin/Max and ColorTemperatureMireds. Hue and saturation reads depend on the PICS (O). |
| Guaranteed to answer a read | CurrentLevel, OnOff, Options, ClusterRevision, and per the PICS status CurrentX/Y (status M, but the CCT-only Ledvance A60 marks it ambiguous). ColorMode, ColorCapabilities (0x400A), ColorTemperatureMireds, hue, saturation, OnTime: Optional, not guaranteed. |
| Color commands on a light without hue and saturation | Not sent: steps carry "If supported in the ColorCapabilities". PICS items for the hue and saturation commands are O (CCT Ledvance: N). What such a light must answer if sent anyway is not specified by the tests. |
| Whose field values | Level, rate, step and transition values are fixed in the spec. Color X/Y and hue are the vendor's own PIXIT values (CC.PIXIT01 to 06). Color temperature is random within the vendor's declared physical range. |
| onWithTimedOff, OnTime | On With Timed Off 0x42 and OnTime 0xA4001, OffWaitTime 0xA4002: **O**; the certified Ledvance A60 declares N; the IKEA STD WW declares Yes; the Hue ZLL PICS answers Yes under the ZLL profile (where the command is M). |
| Variable-rate fades | "If the device is not able to move at a variable rate then the transition time and rate fields ... may be ignored and a fixed rate used instead"; time reads tolerate plus or minus 15 percent. A light that jumps still passes. |

Also read, as vendor SDK documentation: NXP's Level Control Move To Level page restates the Options and
OptionsMask/OptionsOverride semantics the way ZCL 8 does
(<https://mcuxpresso.nxp.com/mcuxsdk/25.12.00/html/middleware/wireless/zigbee/Docs/JNUG3132/Level_Control_cluster/topics/level_control_cluster.html>);
TI's product-certification page says "All mandatory features ... are tested. All implemented optional features ... are
tested", names the Zigbee 3.0 Test Tool, and says Zigbee Light Link and HA "may no longer be certified"
(<https://software-dl.ti.com/simplelink/esd/simplelink_lowpower_f3_sdk/latest/exports/docs/zigbee/html/zboss/product_certification.html>).
Silicon Labs says its tool chain does not perform the Zigbee 3.0 testing
(<https://docs.silabs.com/zigbee/latest/certifying-zigbee-3-devices/>).

### What certification does not give

- **No per-product result.** The listings show "TIS/TRP Tested: Yes", a certificate ID, firmware and hardware versions and
  "Specification Version 1.0". The zip holds the PICS and the test-spec templates, not pass logs. Whether a given product
  passed LC-TC-07S is inferred.
- **Current test plan unknown.** The Zigbee 3.0 Test Tool and test plan are members-only, and the documents read date from
  2016 to 2018. What a 2024 or later certification runs (ZCL 8, BDB 3.x) is UNVERIFIED.
- **No wire-visible marker.** The certificate is per SKU and firmware version (certification by similarity lets later
  firmware inherit it, per the TI page). Nothing on the air says "certified"; a class keyed on certification would be a
  model and firmware list built from CSA listings. UNVERIFIED that Zigbee2MQTT's definitions expose one.
- **PICS is a self-declaration.** The Ledvance A60 TW compliance copy is an editors version with tracked changes and merged
  cells ("[NY]"), so a Support cell can be ambiguous. The Innr RB 245 zip has no filled Level or Color Control PICS.
- **Certified lights depart in the field.** [2026-11-24 ExecuteIfOff note](../integrations/zigbee2mqtt/research/2026-11-24-other-brands-execute-if-off-and-reads.md)
  records Sengled E11-G13 (jumps to full and comes on) and IKEA KAJPLATS (stores, wakes at the old level), and
  [2026-11-14](../integrations/zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md) records Hue replacing a running
  timer where the spec keeps the longer one. Whether those exact models carry a Zigbee 3.0 certificate was not checked here
  (UNVERIFIED), so this shows that passing a test spec's one case does not settle the rest of a call, not that a certified
  model failed its test.
- **Not readable, UNVERIFIED:** ZLO 15-0014, so whether ZLO makes onWithTimedOff, OnTime or ColorCapabilities mandatory
  for lights; ZCL 7 and 8, Base Device Behavior and Silicon Labs AN1118 (all HTTP 403 to scripted clients, behind a request
  form). One retry that spoofed browser headers against that form was blocked by the permission layer and not repeated. A
  third-party mirror of ZCL 8 (<https://etc.athom.com/zigbee_cluster_specification.pdf>) was already used by the earlier
  notes. The CSA GitHub organization holds only Matter ledger code.

## Part 3: What this means for the rule

Against the two Documented routes in [docs/evidence.md](../evidence.md):

- **Route (a), a sibling's call.** Needs the vendor's own documentation giving the call identically for both classes. No
  vendor in the set provides it: seven publish nothing at the call level, and Tuya lists ids without fields. The rule
  also bars a pass on one vendor's firmware from covering another's, so the Aqara bulb's pass would not reach Innr,
  Ledvance or IKEA by this route, however standard the call.
- **Route (b), a certified read.** The ZCL test specs do send the same reads to every certified light, so the route holds
  for **mandatory** attributes only (CurrentLevel, OnOff, Options, ClusterRevision). It fails the rule's other terms for
  ColorMode, ColorCapabilities, hue, saturation and OnTime (optional), for any write, and for any class without a marker:
  certification is per SKU and firmware, with no wire-visible marker.
- **The spec route DeviceSide does not have.** What the research does show is that the exact DeviceSide ExecuteIfOff
  moveToLevel and moveToColor call is a step in the certification test spec. That is evidence the call is standard and
  that a conforming light honors it, not a record that a given vendor's light passed it, and a write never qualifies today.

Options for the maintainer (no decision made here):

1. **Keep the rule as written.** Other vendors' lights stay in Labs on their cited sources (the 2026-11-24 notes), and move
   to Documented only by a certified read or a sibling within one vendor. Cost: no vendor-spanning route, so each new
   maker waits for its own pass.
2. **Add a narrow certified-read route for mandatory attributes.** Name the marker as "a CSA Zigbee 3.0 listing for the
   model and firmware" and the attributes as the mandatory set. Needs a source of the model list (the CSA search UI is
   JS-driven and was not queried), and what slips past it (Optional attributes, models certified under ZLL only, firmware
   not yet listed) goes in the PR. Reads such as CurrentLevel and OnOff would qualify; `get_attributes` reads of
   ColorMode and hue would not.
3. **Add a call-pattern route for writes keyed on a vendor's PICS.** Treat a filed PICS that declares the command
   (and Options) as the vendor's own statement of the call, per model, with the CSA test spec as the call's definition.
   This changes "a write never qualifies" and "the vendor's own documentation". Today only Ledvance A60 RGBW T, the Ledvance
   PAR16 RGBW (annotated), the Ledvance A60 TW (an editors copy) and the IKEA STD WW were found with a filled PICS, and it is a self-declaration with no
   pass on record (tenet 7: maintainers judge sufficiency). Move, Stop and Step ExecuteIfOff stay "assumed" by the test spec.
4. **Per-model Documented from a PICS, nothing class-wide.** The narrowest form of option 3: a model whose filed PICS
   declares what an action sends is Documented for that action; its class stays Labs. Larger bookkeeping, no new class
   argument.
5. **Keep Labs and lean on Verified by contributors.** The rule's current path for the default class: build from a sourced
   call to Labs and treat the first device report as the probe (tenet 2, "a vendor's document alone still needs the probe").

Anything that changes Documented is a binding-rule change (`docs/evidence.md`) with its own plan and an Opus audit, per
the plan's step 6.

## Not confirmed

- Hue developer API docs, Aqara open-platform docs, ZLO 15-0014 and ZCL 7 and 8 from CSA: not reachable (login, 403,
  request form).
- Sengled's Zigbee 3.0 certificate: a search summary only. Whether any Aqara light holds a Zigbee 3.0 certificate: only
  page 1 of 42 of the CSA search was read.
- Whether any product passed LC-TC-07S or CC-TC-09S: no result is published.
- Tuya SDK source for the Level Control handler: not read.
- innr.com product pages and the Lightify docs: HTTP 429 and client-rendered.
- The fetch tool's page summaries (Aqara, Tuya, Ledvance, IKEA, CSA listing fields) were not checked against raw HTML;
  re-read a page before citing a quote from it in a record.
