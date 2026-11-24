# Matter lighting research (Level Control / Color Control, ExecuteIfOff)

Pinned SHAs (resolved with `gh api`, 2026-11-24):
- CHIP master  `0233fac8c37223e88d915addce8e8e034bb8a513` (project-chip/connectedhomeip)
- CHIP v1.0.0.2 `4088a77f557e8571a39338fad51a1d8eb0131d79` (tag v1.0.0.2, 2022-12-21; the v1.0 line)
- HA core dev  `112e3548608f89297987c46bbfbca9666737e5b1`
- python-matter-server main `4c820ed12bac349dda372031e9757c67b9fd9048` (repo now matter-js/python-matter-server)
Link form: https://github.com/project-chip/connectedhomeip/blob/<sha>/<path>

Abbrevs: M = master SHA, V = v1.0.0.2 SHA. CERT = src/app/tests/suites/certification.

## Q1. Certification coverage

Spec conformance (data model XML, 1.0): LevelControl commands 0x00-0x07 (MoveToLevel, Move, Step, Stop and the four
WithOnOff) are all `mandatoryConform`, and `OptionsMask`/`OptionsOverride` are `mandatoryConform` fields (map8, default 0)
on every one. ColorControl: same, both fields mandatory on every command with Options (e.g. MoveToHue fields 3,4).
So yes: both fields are mandatory in every Level/Color command since 1.0 (the 1.0 XML already says so; a few
commands without them are Color Control's ColorLoopSet-type ones: it too carries them, StopMoveStep carries them).
- LVL: [data_model/1.0/clusters/LevelControl.xml @M](https://github.com/project-chip/connectedhomeip/blob/0233fac8c37223e88d915addce8e8e034bb8a513/data_model/1.0/clusters/LevelControl.xml) lines 251-280
- CC: [data_model/1.0/clusters/ColorControl.xml @M](https://github.com/project-chip/connectedhomeip/blob/0233fac8c37223e88d915addce8e8e034bb8a513/data_model/1.0/clusters/ColorControl.xml) lines 637-690
- `Options` attribute 0x000F is mandatory in both; bit 0 `ExecuteIfOff` mandatory (CC xml line 221-229). LVL Options bit1
  CoupleColorTempToLevel is LT-conditional (UNVERIFIED reading, not needed here).
- Color command gating (1.0 xml): MoveToHue/MoveHue/StepHue/MoveToSaturation/MoveSaturation/StepSaturation/
  MoveToHueAndSaturation need feature HS; MoveToColor/MoveColor/StepColor need XY; MoveToColorTemperature (0x0A),
  MoveColorTemperature (0x4B), StepColorTemperature (0x4C) need CT; Enhanced* (0x40-0x43) need EHUE; ColorLoopSet CL;
  StopMoveStep (0x47) needs HS|XY|CT. All lines in cc10.xml: 637-1368.

Tests (same YAML structure at V and M; file lists identical in names apart from `_Simulated` renames). PICS are the
`LVL.S.Cxx.Rsp` / `CC.S.Cxx.Rsp` (command supported) plus the feature bit for CC.

(a) MoveToLevel/WithOnOff + TransitionTime + CurrentLevel reads
- TC-LVL-3.1 (Test_TC_LVL_3_1.yaml): step 4a MoveToLevel Level=200 TransitionTime=300 (30 s); reads CurrentLevel at
  +10 s (85..115), +20 s (127..173), +30 s (170..200), +35 s (=200). These reads are gated `LVL.S.M.VarRate`
  (device manufacturer-flag: variable rate); devices without it only get a final-value read (step 4f).
  [@M L143-240](https://github.com/project-chip/connectedhomeip/blob/0233fac8c37223e88d915addce8e8e034bb8a513/src/app/tests/suites/certification/Test_TC_LVL_3_1.yaml#L143-L240)
  So a live mid-transition read returning an interpolated value is REQUIRED only when VarRate is claimed (optional PICS).
  Present at V (file Test_TC_LVL_3_1.yaml exists in the V tree; transition steps UNVERIFIED line by line).
- MoveToLevelWithOnOff: TC-LVL-3.1 step 2; TC-LVL-2.3 (python, TC_LVL_2_3.py, M only: not in the V tree) uses
  MoveToLevelWithOnOff TransitionTime=100 and subscription reports (see Q3).
- TC-LVL-9.1 (python, M): `MoveToLevel(level=0, transitionTime=0, optionsMask=1, optionsOverride=1)`, then CurrentLevel==MinLevel.
  [TC_LVL_9_1.py L190-196 @M](https://github.com/project-chip/connectedhomeip/blob/0233fac8c37223e88d915addce8e8e034bb8a513/src/python_testing/TC_LVL_9_1.py#L190-L196)

(b) Move / Stop / StopWithOnOff
- TC-LVL-4.1 (Move): PICS `LVL.S.C01.Rsp`; rate-based reads at 5/10/19 s (`VarRate` gated for mid reads). Step 4h: Move
  Rate=0 must return INVALID_COMMAND (with mask=1 override=1).
  [Test_TC_LVL_4_1.yaml L225-312 @M](https://github.com/project-chip/connectedhomeip/blob/0233fac8c37223e88d915addce8e8e034bb8a513/src/app/tests/suites/certification/Test_TC_LVL_4_1.yaml#L225-L312)
- TC-LVL-6.1 (Stop): On, MoveToLevel 50, Move up Rate 5, wait 5 s, `Stop` (PICS `LVL.S.C03.Rsp`), then read CurrentLevel
  in 64..86 (so it holds near 75 = held where it stopped). Same with `StopWithOnOff` (`C07.Rsp`), expects 85..115.
  Includes a UserPrompt "device physically stopped" gated on PICS_USER_PROMPT.
  [Test_TC_LVL_6_1.yaml L87-196 @M](https://github.com/project-chip/connectedhomeip/blob/0233fac8c37223e88d915addce8e8e034bb8a513/src/app/tests/suites/certification/Test_TC_LVL_6_1.yaml#L87-L196)
  Stop tests run with the light ON (Options=0). No test sends Stop to an off light.
- Color: TC-CC-8.1 `StopMoveStep` (0x47, PICS `CC.S.C47.Rsp`) after MoveHue (rate 5, 5 s), then CurrentHue 221..229
  and unchanged 2 s later (holds); same for MoveSaturation, MoveColorTemperature (`C4b`), EnhancedMoveHue.
  [Test_TC_CC_8_1.yaml L55-139 @M](https://github.com/project-chip/connectedhomeip/blob/0233fac8c37223e88d915addce8e8e034bb8a513/src/app/tests/suites/certification/Test_TC_CC_8_1.yaml#L55-L139)
  TC-CC-5.2 also uses StopMoveStep after MoveColor.

(c) ExecuteIfOff / OptionsMask / OptionsOverride on an OFF light: YES, tested.
- TC-LVL-3.1 steps 5 and 6 (Options attr first set to 0, then 1):
  - Options=0, light Off: MoveToLevel(120, mask0/over0) -> CurrentLevel stays 100 (5g/5h, no change).
  - Options=0, Off: MoveToLevel(140, mask=1, over=0) -> stays 100 (5i/5j).
  - Options=0, Off: MoveToLevel(160, mask=1, over=1) -> CurrentLevel == 160 (5k/5l). THIS is the ExecuteIfOff override case.
  - Options=1, Off: MoveToLevel(120, 0/0) -> 120 (6g/6h); (140, mask1/over0) -> stays 120 (6i/6j); (160, 1/1) -> 160.
  [Test_TC_LVL_3_1.yaml L242-470 @M](https://github.com/project-chip/connectedhomeip/blob/0233fac8c37223e88d915addce8e8e034bb8a513/src/app/tests/suites/certification/Test_TC_LVL_3_1.yaml#L242-L470)
  Identical value sequence at V (lines 234-431 list On/Off, 100/120/140/160, Options writes): [@V](https://github.com/project-chip/connectedhomeip/blob/4088a77f557e8571a39338fad51a1d8eb0131d79/src/app/tests/suites/certification/Test_TC_LVL_3_1.yaml#L234-L431). So this cert case exists since 1.0.
  Gated by `LVL.S.C00.Rsp && LVL.S.A0000` and `LVL.S.A000f` (Options). All use TransitionTime=0 only.
- TC-CC-5.1 (MoveToColor, PICS `CC.S.F03 && CC.S.C07.Rsp`): Off, then MoveToColor(0x3333,0x3333,mask0/over0) -> X/Y unchanged (4g/4h);
  (mask1/over0) -> unchanged; (0x6666,0x8000, mask1/over1) -> X in 22282..30146, Y in 27853..37683 (changed while off) (4k/4i).
  Repeated with Options attr=1 (step 5). Cases at V lines 253-350 ([@V](https://github.com/project-chip/connectedhomeip/blob/4088a77f557e8571a39338fad51a1d8eb0131d79/src/app/tests/suites/certification/Test_TC_CC_5_1.yaml#L253-L350)).
  [@M L264-395](https://github.com/project-chip/connectedhomeip/blob/0233fac8c37223e88d915addce8e8e034bb8a513/src/app/tests/suites/certification/Test_TC_CC_5_1.yaml#L264-L395)
  CC.S.F03 = XY feature. ONLY MoveToColor (XY) has an off+override case. Hue/Sat (HS), ColorTemperature (CT), Enhanced
  tests all use mask0/over0 with the light On: ExecuteIfOff on MoveToHueAndSaturation / MoveToColorTemperature is NOT
  certified (rg of OptionsMask value 1 over all CC YAMLs at M: only CC_5_1; only LVL_3_1, LVL_4_1(step 4h), plus python LVL_9_1).
- LVL 4.1 step 4h (Move Rate=0 error) is the only other non-zero mask; no Move/Step/Stop to an off light with override.
- No python or YAML test sends a color command, Stop, or Move to an OFF light with override other than the above.

(d) Color Control commands: per test and PICS (all M-tested and in V tree)
- TC-CC-3.1 MoveToHue (HS+C00), 3.2 MoveHue (C01), 3.3 StepHue (C02); 4.1 MoveToSaturation (C03), 4.2 MoveSaturation (C04),
  4.3 StepSaturation (C05), 4.4 MoveToHueAndSaturation (`CC.S.F00 && CC.S.C06.Rsp`), 5.1-5.3 MoveToColor/MoveColor/StepColor
  (XY, C07-C09), 6.1-6.3 MoveToColorTemperature/Move/Step (CT, C0a, C4b, C4c), 7.1-7.4 Enhanced* (EHUE, C40-C43),
  8.1 StopMoveStep (C47), 9.x ColorLoopSet (CL, C44). All in Matter 1.0 (V tree has all Test_TC_CC_* files).
  Python additions at M: TC_CC_2_1/2_2 (attributes), TC_CC_6_5, TC_CC_10_1 (UNVERIFIED content).
- Transition reads: CC tests wait (100 ms after TransitionTime=0 commands) then read X/Y/Hue; mid-transition read
  assertions exist for MoveHue/MoveSaturation (Rate) tests via StopMoveStep ranges.

## Q2. Reference server behavior (ember codegen, `src/app/clusters/level-control/codegen/level-control.cpp` @M)
[file @M](https://github.com/project-chip/connectedhomeip/blob/0233fac8c37223e88d915addce8e8e034bb8a513/src/app/clusters/level-control/codegen/level-control.cpp)
- Mid-transition read: YES instantaneous. A timer (`emberAfLevelControlClusterServerTickCallback`, L398) steps
  CurrentLevel every `eventDurationMs = transitionTimeMs / |delta|` (L982) via `SetCurrentLevelQuietReport`; the stored
  attribute is the current interpolated level. Only *reporting* is throttled (Q3), not the stored/read value.
  (Reading the tick body L398-560 only partly verified; the Set call at L452 and quiet setter at L367-395 confirmed.)
- Stop (L1292-1318): cancels the timer, `SetCurrentLevelQuietReport(..., state->quietCurrentLevel.value(), true)` (publishes
  the value where it is), sets RemainingTime 0. It holds. `Stop` is gated by ExecuteIfOff (below); `StopWithOnOff` is not.
- ExecuteIfOff gate `shouldExecuteIfOff` (L566-648): returns true (executes) unless ALL of: command is a non-WithOnOff command
  (`commandId > Stop::Id` returns true, so the four WithOnOff commands ignore the gate), On/Off server exists on endpoint,
  OnOff attribute false, and the temp-options ExecuteIfOff bit is 0, where temp = Options attribute with
  `OptionsMask` bit overriding from `OptionsOverride`. When blocked: handler returns **Status::Success without doing anything**
  (L872-875: `return Status::Success`). So a controller cannot tell the command was ignored.
- MoveToLevel (not WithOnOff) on an OFF light with ExecuteIfOff: runs; clips level to [min,max]; schedules the timer;
  updates CurrentLevel to the target (immediately if TransitionTime=0). It does NOT touch OnOff (only WithOnOff does
  `setOnOffValue`, L995-1000 region; "light that is off stays off"). So the light stays off and CurrentLevel moves.
- Next On (`emberAfOnOffClusterLevelControlEffectCallback`, L1322-1438): reads CurrentLevel; if OnLevel attribute exists and is
  non-null -> `useOnLevel`, target = OnLevel; if OnLevel is null (or absent) -> target = CurrentLevel. Sets CurrentLevel to min,
  then MoveToLevel(target, OnOffTransitionTime). So: **OnLevel non-null overrides the level you set while off** (light comes up
  at OnLevel); OnLevel null -> comes up at the level you set. (Null-OnLevel-uses-CurrentLevel was itself a recent fix for the
  code-driven server: [PR #74405](https://github.com/project-chip/connectedhomeip/pull/74405).)
- Turning Off with OnLevel null: moves to min over OnOffTransitionTime then restores `storedLevel` as CurrentLevel at the end
  (L1431-1437). With OnLevel set, CurrentLevel is left at min after the fade.
- Color Control ember (`color-control-server/codegen/color-control-server.cpp` @M): same `shouldExecuteIfOff` (L521-581, no WithOnOff
  distinction; every handler does `VerifyOrReturnValue(shouldExecuteIfOff(...), Status::Success)` e.g. L1435, 1532, 1644, 1684, 1765,
  2239, 2261, 2350, 2694, 2788, 2818). With override it runs on an off light: attributes (X/Y, Hue/Sat, Mireds) are updated and the
  light stays off. There is no OnLevel analogue; no color reset on On (UNVERIFIED for StartUp color temp: `StartUpColorTemperatureMireds`
  applied only at boot, L2603).
  [file @M](https://github.com/project-chip/connectedhomeip/blob/0233fac8c37223e88d915addce8e8e034bb8a513/src/app/clusters/color-control-server/codegen/color-control-server.cpp)
- StopMoveStep (L479-515): no effect on active color loop; else `stopAllColorTransitions` and RemainingTime 0 (holds current values);
  gated by ExecuteIfOff like others.
- Code-driven (new) servers diverged and were fixed in Sept 2026: [#74269](https://github.com/project-chip/connectedhomeip/issues/74269)
  (StopWithOnOff and MoveWithOnOff-down wrongly gated; MoveToLevel(0) CONSTRAINT_ERROR), [#74550](https://github.com/project-chip/connectedhomeip/issues/74550)
  (ExecuteIfOff gate runs before field validation: Rate=0 returns SUCCESS on an off light). Both closed.
- Spec nuance (from #74378 text): spec section 1.6.6.9 suppresses only "Move, Move to Level, Step, or Stop" when off without ExecuteIfOff.

## Q3. Reporting quality
- Quieter reporting ("Q") is NOT in LevelControl 1.3 data model (only `CurrentFrequency reportable`); it appears in data_model/1.4:
  LVL CurrentLevel (0x0000) and RemainingTime (0x0001) `quieterReporting="true"`
  ([LevelControl.xml 1.4 @M L118-131](https://github.com/project-chip/connectedhomeip/blob/0233fac8c37223e88d915addce8e8e034bb8a513/data_model/1.4/clusters/LevelControl.xml#L118-L131)).
  CC 1.4: CurrentHue, CurrentSaturation, RemainingTime, CurrentX, CurrentY, ColorTemperatureMireds, EnhancedCurrentHue
  ([ColorControl.xml 1.4 @M L244-306, 674](https://github.com/project-chip/connectedhomeip/blob/0233fac8c37223e88d915addce8e8e034bb8a513/data_model/1.4/clusters/ColorControl.xml#L244-L306)). Still Q in 1.5, 1.6.
- Rate (ember server): during a transition, CurrentLevel reports at most once per `max(1000 ms, transitionTime/4)`; always report
  at start and end (`SetCurrentLevelQuietReport`, L367-395). Color: `max(1000 ms, transitionTime_ds * 25)`; infinite (0xFFFF) -> 10 s
  interval (`SetQuietReportAttribute`, color-control-server.cpp L2990-3040). Thus a 30 s fade reports ~every 7.5 s (>=4 reports); a 10 s fade every 2.5 s.
- RemainingTime report: on 0 -> >10 (ds), on a command-caused change of >10, and on reaching 0 (comment at color-control-server.cpp ~L3049).
- Cert: TC-LVL-2.3 (python, M): 10 s MoveToLevelWithOnOff to max, subscription (MinInterval 0, MaxInterval 30), over 30 s expects <=12
  CurrentLevel reports (>0), first >= start, last == max, monotonic; RemainingTime reports exactly 3 (~100, ~150, 0).
  [TC_LVL_2_3.py L130-216 @M](https://github.com/project-chip/connectedhomeip/blob/0233fac8c37223e88d915addce8e8e034bb8a513/src/python_testing/TC_LVL_2_3.py#L130-L216)
- Conclusion: a subscription cannot give per-step live level (only ~1 per second at best, usually sparser); do a read for a live value.
  Devices on <1.4 have no Q rules (may report every step or never mid-transition). UNVERIFIED: how real devices behave.

## Q4. Home Assistant core matter/light.py @ dev 112e354
[light.py @HA-dev](https://github.com/home-assistant/core/blob/112e3548608f89297987c46bbfbca9666737e5b1/homeassistant/components/matter/light.py)
- Color commands send ExecuteIfOff: `MoveToColor` (L118-136), `MoveToHueAndSaturation` (L138-156), `MoveToColorTemperature` (L158-176),
  each with `transitionTime=int(transition*10)`, `optionsMask=1, optionsOverride=1` ("allow setting the color while the light is off").
- Brightness: `LevelControl.MoveToLevelWithOnOff(level, transitionTime=int(transition*10))`, NO options (L177-192), so it always turns the
  light on (this is issue #175904's complaint).
- `async_turn_on` (L311-340): transition = kwargs.get(ATTR_TRANSITION, 0) (default 0 = immediate), zeroed if device in
  `TRANSITION_BLOCKLIST` (Espressif Matter-1.0 transition bug, vendor/product list L56-75, issue #113775). Order: color command first
  (hs, else xy, else color temp, only one), then brightness command (and return), else `OnOff.On()`. A turn_on with only a color
  therefore sets color with ExecuteIfOff but does not turn the light on if brightness is None? NOTE: it falls through to `OnOff.On()` after the color
  command when brightness is None, so it does turn on.
- turn_off: `OnOff.Off()`; no transition (PR #174089 would add MoveToLevelWithOnOff(minLevel) fade-out; open).
- Color mode read: `ColorControl.ColorMode` attribute mapped via COLOR_MODE_MAP (kCurrentHueAndCurrentSaturation->HS, kCurrentXAndCurrentY->XY,
  kColorTemperatureMireds->COLOR_TEMP; L41-46, `_get_color_mode` L285-309). Unknown/None -> `ColorMode.UNKNOWN`.
- `send_device_command(command, **kwargs)` in entity.py wraps `matter_client.send_device_command(node_id, endpoint_id, command, **kwargs)`.
- Issue [#175904](https://github.com/home-assistant/core/issues/175904) (open; filed 2026-07-07 by DienoX, HA 2026.7.1): user cannot change
  brightness without turning on; IKEA KAJPLATS; verified in the matter.js server UI by sending LevelControl MoveToLevel with the
  "Execute if Off" checkbox: "bulb updates its internal brightness state but remains physically off". Comments: TheJulianJES says
  likely depends on architecture discussion [home-assistant/architecture#537](https://github.com/home-assistant/architecture/discussions/537);
  stale bot 2026-10-07; reporter says still unsolved. No fix, no linked PR.
- Open PRs touching ExecuteIfOff: search of home-assistant/core PRs for "ExecuteIfOff" returned none. Related open: [PR #174089](https://github.com/home-assistant/core/pull/174089)
  (light.turn_off with transition via MoveToLevelWithOnOff(minLevel)); open issue [#160066](https://github.com/home-assistant/core/issues/160066) (no off transition).

## Q5. python-matter-server / chip.clusters
- `MatterClient.send_device_command(node_id, endpoint_id, command: ClusterCommand, response_type=None, timed_request_timeout_ms=None, interaction_timeout_ms=None)`;
  payload = `dataclass_to_dict(command)`; the command name is the class name. [client.py L445-470 @PMS](https://github.com/matter-js/python-matter-server/blob/4c820ed12bac349dda372031e9757c67b9fd9048/matter_server/client/client.py#L445-L470)
  HA entity wrapper: [entity.py L444-456 @HA](https://github.com/home-assistant/core/blob/112e3548608f89297987c46bbfbca9666737e5b1/homeassistant/components/matter/entity.py#L444-L456)
  (omits node/endpoint args; passes **kwargs through).
- Field names (chip/matter.clusters Objects): `optionsMask`, `optionsOverride` on every LevelControl and ColorControl command
  with Options (python tests at M: `MoveToLevel(level=0, transitionTime=0, optionsMask=1, optionsOverride=1)` TC_LVL_9_1.py L192;
  `MoveToLevelWithOnOff(level=..., transitionTime=100, optionsMask=0, optionsOverride=0)` TC_LVL_2_3.py L142; HA uses the same kwargs).
  Other names (camelCase): `level`, `transitionTime`, `moveMode`, `rate`, `stepMode`, `stepSize`, `colorX`, `colorY`, `hue`, `saturation`
  Checked against [Objects.py @M](https://github.com/project-chip/connectedhomeip/blob/0233fac8c37223e88d915addce8e8e034bb8a513/src/controller/python/matter/clusters/Objects.py) (step 1 of the plan, 2026-11-24): LevelControl MoveToLevel/MoveToLevelWithOnOff
  `level, transitionTime (nullable), optionsMask, optionsOverride`; Move `moveMode, rate (nullable)`; Stop/StopWithOnOff
  `optionsMask, optionsOverride`; ColorControl MoveToHueAndSaturation `hue, saturation`, MoveToColor `colorX, colorY`,
  MoveToColorTemperature `colorTemperatureMireds`, MoveHue/EnhancedMoveHue/MoveSaturation `moveMode, rate`, StopMoveStep
  `optionsMask, optionsOverride`, each with `transitionTime` where it has one. Attribute IDs: LevelControl (0x0008)
  CurrentLevel 0x0000, OnLevel 0x0011, Options 0x000F; ColorControl (0x0300) CurrentHue 0x0000, CurrentSaturation 0x0001,
  CurrentX 0x0003, CurrentY 0x0004, ColorTemperatureMireds 0x0007, ColorMode 0x0008, EnhancedCurrentHue 0x4000, FeatureMap
  0xFFFC (HS 0x1, EHUE 0x2, CL 0x4, XY 0x8, CT 0x10).
- The server is matter.js: its log of an HA call shows omitted options sent as `optionsMask: { executeIfOff: false, coupleColorTempToLevel: false }`
  (issue 168257 comment), i.e. omitted = mask 0 = no override. matter.js server UI exposes an "Execute if Off" checkbox (issue 175904).
- Level-control Options bit names: ExecuteIfOff (bit 0), CoupleColorTempToLevel (bit 1).

## Q6. Firmware quirks found
- IKEA: [PR #174089 comment (jhbruhn, 2026-07-06)](https://github.com/home-assistant/core/pull/174089#issuecomment-4892555029): tested MoveToLevel + ExecuteIfOff
  on two lamps. Both honor the write while off (CurrentLevel updates, stays off), but next `On()` differs: IKEA VARMBLIXT resumes at the stored level,
  KAJPLATS ignores it and resumes at its previous level, though they advertise identical LevelControl features. (Consistent with OnLevel being set/ignored;
  OnLevel value not reported there: UNVERIFIED cause.)
- Global scene: plain `On` does not recall it; only `OffWithEffect` stores / `OnWithRecallGlobalScene` recalls ([same PR, comment 2026-06-26](https://github.com/home-assistant/core/pull/174089#issuecomment-4810984453)).
- Philips Hue bridge (Matter): [home-assistant/apps#4708](https://github.com/home-assistant/apps/issues/4708) (closed): MoveToLevelWithOnOff fails silently when bulb's last
  brightness differs from commanded (Matter Server 9.0.x); Apollon77 cites it as a reason a WithOnOff off-transition could break on Hue ([PR #174089 comment 2026-08-12](https://github.com/home-assistant/core/pull/174089#issuecomment-5265658192)).
  Hue A67/A60/GU10 expose no OnTransitionTime/OffTransitionTime ([#174188](https://github.com/home-assistant/core/issues/174188)).
- Govee Matter lights: [#182739](https://github.com/home-assistant/core/issues/182739) (closed no logs): color ignored when color+brightness are sent together; 150 ms gap works.
  Also a Govee/Matter bulb ignoring brightness after quick off/on (#168257 comment by ChadH360, later retracted).
- Intermediate-level stored on off during transition: [#168257](https://github.com/home-assistant/core/issues/168257) (KAJPLATS: turning off mid-transition makes next On come up at the intermediate level).
- Espressif Matter-1.0 devices with broken transitions: HA TRANSITION_BLOCKLIST (light.py L49-75), issue #113775 (not read here).
- Nanoleaf: HA #119981 (sluggish color translation, Thread strip) closed; no ExecuteIfOff/Move/Stop-specific report found. Eve, WiZ, Meross, Nanoleaf
  ExecuteIfOff/Stop quirks: NONE FOUND (UNVERIFIED; GitHub search is weak; gh search returned nothing for esp-matter and no matter.js device-quirk issues).
- matter.js (controller/device code) bug fixed: [PR #4326](https://github.com/matter-js/matter.js/pull/4326) (device server StopWithOnOff / With-OnOff commands honored Options) — device side, not firmware quirk.
- Zigbee comparison (not Matter): Z2M `execute_if_off` on IKEA bulbs ([HA #121347](https://github.com/home-assistant/core/issues/121347)).

## Headlines (see Q1/Q2)
1. Cert covers ExecuteIfOff on an off light with MoveToLevel (TC-LVL-3.1 5k/6k, in 1.0) and MoveToColor XY (TC-CC-5.1 4k, in 1.0). Not covered: Hue/Sat, ColorTemp, Move/Step/Stop with override.
2. OptionsMask/OptionsOverride are mandatory fields on every Level and Color command since 1.0.
3. Gate failure returns SUCCESS silently; WithOnOff level commands ignore the gate in the reference server.
4. Mid-transition read is instantaneous; reports throttled >=1 s and Q only from 1.4.
5. Stop holds current level. On-after-ExecuteIfOff comes up at the set level only if OnLevel is null; some IKEA bulbs ignore it anyway.
