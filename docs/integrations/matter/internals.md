# Matter internals

How the Matter adapters address a target, what they send and read back, and what was measured on real hardware.
What a user sees is in [index.md](index.md) and isn't repeated here; what every integration shares is in
[internals.md](../../internals.md). Result and detail codes are in the code. Code comments cite the sections here.

## Addressing

Through the core integration's python-matter-server connection. The unique ID is
`{fabric_hex16}-{node_hex16}-{postfix}-{endpoint_id}-{key}-{cluster_id}-{attr_id}`. The Lighting feature check reads
FeatureMap bit 0 from the node data (`node_data.attributes["{endpoint}/6/65532"]`), avoiding a chip.clusters import
that `MatterEndpoint.get_attribute_value` would need.

A target is addressed only when its unique ID's cluster and attribute are OnOff.OnOff (`6-0`). HA puts other switches
on the same endpoint (Eve's child lock), and they're refused `not_addressable`
([research](research/2026-11-16-onoff-addressing.md)).

Lights take the same command and reads as plugs, behind the same Lighting feature check. A light's Level Control
(cluster 8) and Color Control (`0x0300`, 768) servers are on its OnOff entity's endpoint; one with no Level Control
server there (no CurrentLevel, `<endpoint>/8/0`, in the node cache) is refused `not_dimmable`.

## What decides the call

Read 2026-11-14, for the device classes (plan step 9). Sources at a commit: Home Assistant core
[`2bca51e`](https://github.com/home-assistant/core/blob/2bca51ea8e647696e2c86f43e4edea3bdb48ea74/homeassistant/components/matter) (`matter`, which pins matter-python-client 1.5.5), connectedhomeip
[`c55ddad`](https://github.com/project-chip/connectedhomeip/blob/c55ddad4480afad31f249af5356c16e8b53416c6), and matter.js [`06cd7ea`](https://github.com/matter-js/matter.js/commit/06cd7eaad5b868f3e81ac299d8d3d240e8fcd19b).

- **Nobody routes the call.** Home Assistant's `matter` integration never sends `OnWithTimedOff`: its switches and
  lights send only `On` and `Off` ([`switch.py`](https://github.com/home-assistant/core/blob/2bca51ea8e647696e2c86f43e4edea3bdb48ea74/homeassistant/components/matter/switch.py), [`light.py`](https://github.com/home-assistant/core/blob/2bca51ea8e647696e2c86f43e4edea3bdb48ea74/homeassistant/components/matter/light.py)). DeviceSide sends the
  command through the client to the endpoint as it is, so neither HA nor the Matter server picks the call. The
  endpoint's own On/Off server decides the outcome: the device's firmware or, on a bridge, the bridge's software,
  which runs the timer or passes it on.
- **The device type** decides only the HA domain (On/Off Plug-in Unit is a `switch`, the light types a `light`), not
  the call: every lighting and plug-in device type requires the Lighting feature (`data_model/1.4/device_types/`,
  e.g. [`OnOffPlug-inUnit.xml`](https://github.com/project-chip/connectedhomeip/blob/c55ddad4480afad31f249af5356c16e8b53416c6/data_model/1.4/device_types/OnOffPlug-inUnit.xml)).
- **The Lighting feature** (On/Off FeatureMap bit 0) makes `OnWithTimedOff`, `OnTime` and `OffWaitTime` mandatory
  ([`OnOff.xml`](https://github.com/project-chip/connectedhomeip/blob/c55ddad4480afad31f249af5356c16e8b53416c6/data_model/1.4/clusters/OnOff.xml)). It is the precondition `no_lt_feature` checks
  (Addressing), not a class: a device without it refuses the command, so it can't be harmed. A device's
  AcceptedCommandList (`<endpoint>/6/65529`, e.g. `[0, 1, 2, 64, 65, 66]`) lists `66` with it; nothing reads it, as
  the feature already says so.
- **Certification** tests the command and the reads on every device with the feature: TC-OO-2.3 (PICS `OO.S.F00`)
  sends `OnWithTimedOff` 15 times, reads OnTime and OnOff after each, on one configured endpoint (`endpoint: 1`), and checks that the device turns off when OnTime runs out (step 24c reads OnOff false
  after 40 s), always with OffWaitTime 300, never 0
  ([`Test_TC_OO_2_3.yaml`](https://github.com/project-chip/connectedhomeip/blob/c55ddad4480afad31f249af5356c16e8b53416c6/src/app/tests/suites/certification/Test_TC_OO_2_3.yaml)). The same steps, reads and
  values are in the Matter 1.0 test
  ([`v1.0.0`](https://github.com/project-chip/connectedhomeip/blob/561d23d0db215a99705ff0696e73853c8edf11b2/src/app/tests/suites/certification/Test_TC_OO_2_3.yaml)),
  so every certified Lighting device passed them. PICS are per endpoint, but nothing found says a lab runs the test
  on every On/Off endpoint of a device: the question is open upstream
  ([esp-matter #1921](https://github.com/espressif/esp-matter/issues/1921)). So the basis covers a device with one
  On/Off endpoint, and one with more is `multi_endpoint`. So certification
  covers DeviceSide's reads of OnTime and OnOff, which carry no field values, but not its command, whose OffWaitTime
  is 1 (plan Decision 75; docs/evidence.md, Levels). In the reference server OffWaitTime branches only as zero or not
  (`HandleOnWithTimedOff`), so 1 likely acts as 300 does, but that is inference, not a test. It clears OffWaitTime when
  OnTime runs out (`TimerFired`), so a non-zero one acts only after an Off mid-timer: the endpoint ignores another
  `OnWithTimedOff` for that long
  ([`OnOffLightingCluster.cpp`](https://github.com/project-chip/connectedhomeip/blob/c55ddad4480afad31f249af5356c16e8b53416c6/src/app/clusters/on-off-server/OnOffLightingCluster.cpp)).
- **A reboot drops a running timer** on any device: the reference server persists OnOff and StartUpOnOff, not OnTime
  (same file, constructor), so a device that restores its last state after a power cut comes back on with no timer.
- **A test VendorID** (0xFFF1 to 0xFFF4, [`CHIPVendorIdentifiers.hpp`](https://github.com/project-chip/connectedhomeip/blob/c55ddad4480afad31f249af5356c16e8b53416c6/src/lib/core/CHIPVendorIdentifiers.hpp),
  `IsTestVendorId`) is what no certified product carries; development kits and software that shares devices on
  Matter report one by default (HA's own test fixtures: Nordic, Silabs and Nabu Casa sample nodes,
  `tests/components/matter/fixtures/nodes/`). A real VendorID doesn't prove certification: a member can ship an
  uncertified product, or an app can be set to report one. That is what slips past `other`'s marker.
- **What HA exposes.** The device registry holds Basic Information's `vendorName` as manufacturer, `productLabel` or
  `productName` as model, `productID` as `model_id` (none on a bridged device), and the version strings
  ([`adapter.py`](https://github.com/home-assistant/core/blob/2bca51ea8e647696e2c86f43e4edea3bdb48ea74/homeassistant/components/matter/adapter.py), `_create_device_registry`), but not the VendorID, the device types or the
  clusters. Those are in the client's node cache, `node.node_data.attributes`, keyed `"<endpoint>/<cluster>/<attribute>"`:
  VendorID `0/40/2`, ProductID `0/40/4`, each endpoint's DeviceTypeList `<endpoint>/29/0` (structs keyed by field id,
  `[{"0": 266, "1": 1}]`) and FeatureMap `<endpoint>/6/65532`. A bridge has an endpoint whose DeviceTypeList holds
  the Aggregator (0x000E), and its bridged endpoints the Bridged Node (0x0013), as the client reads them
  (`matter_server/client/models/node.py`, `is_bridged_device`).

The classes those facts give, and their order: the `classes.py` docstring.

## Modules

One section per adapter module, named after it.

### `turn_on_for`

`OnOff.Commands.OnWithTimedOff(onOffControl=0, onTime=<tenths>, offWaitTime=1)`, then
reads of `OnOff.OnTime` and `OnOff.OnOff`, one path per `read_attribute`: `confirmed` when OnOff is on and OnTime
is at most the time sent and no more than 3 s under it, as on ZHA. OnTime alone is not proof: a device can hold a
stale OnTime while off.

OffWaitTime is 1 (0.1 s), not 0, since 2026-11-14 (plan Decision 46): matter.js before v0.17.2 never turns off on
OffWaitTime 0 (Upstream defects), and a non-zero value is the branch certification exercises (What decides the call). The
2026-10-28 and 2026-11-11 records ran OffWaitTime 0; the 2026-11-16 one, which holds the WiZ Smart Plug Verified, ran 1.

### `get_attributes`

Live reads of `OnTime` and `OnOff`, as the plug tested never reports OnTime on its
subscription, so the node cache reads 0 mid-timer (Tested behavior). A timer is reported only while OnOff is on.
`turns` is always `off`.

### `set_attributes`

`core/zcl_write.commands()` builds the commands from HA's `supported_color_modes`, as on ZHA (plan Decision 12), and
each goes as its own `send_device_command`, one after another, with `transitionTime=4` (`core/zcl.py`'s
`WRITE_FADE_TENTHS`), `optionsMask=1` and `optionsOverride=1`: the Options bitmap's ExecuteIfOff bit for that command
only, so a light that is off stores the value and stays off. Brightness is `LevelControl.MoveToLevel` (`level` 1–254),
never `MoveToLevelWithOnOff`, which turns the light on; color temperature `ColorControl.MoveToColorTemperature`
(mireds clamped to the light's range); color `MoveToColor` (`colorX`/`colorY` as round(x × 65535)), or
`MoveToHueAndSaturation` (both 0–254) on a light without xy. `min_brightness`/`max_brightness` alone first read
CurrentLevel (`<ep>/8/0`) live; a light already within them gets nothing (`unchanged`, `within_limits`), and a
read that fails rejects the light, as nothing was sent yet.

Then, after `WRITE_FADE_WAIT_S` (0.6 s, past the 0.4 s fade, so a mid-fade value isn't read), a live
`read_attribute` of each attribute the commands set: CurrentLevel for MoveToLevel, ColorTemperatureMireds
(`<ep>/768/7`) for MoveToColorTemperature, CurrentX and CurrentY (`/768/3`, `/768/4`) for MoveToColor, CurrentHue
and CurrentSaturation (`/768/0`, `/768/1`) for MoveToHueAndSaturation. Each must read within one step of the value
sent, as a light rounds to its own resolution: `confirmed`, else `sent` (`attributes_not_reported`), with the values
sent and read logged at DEBUG. A read that raises is `sent` (`readback_failed`). OnLevel (`<ep>/8/17`) is read only
when a brightness went to a light HA shows off, since it decides only the level the next On comes up at: non-null is
`sent` (`on_level_set`) whatever the rest reads. By the spec, and in the reference server's
`emberAfOnOffClusterLevelControlEffectCallback`, an On goes to OnLevel when it is non-null, else to CurrentLevel
([research](research/2026-11-24-level-color.md), Q2). DeviceSide never writes OnLevel: it is the user's device setting.

Why it reads back (plan Decision 8): no Matter light has run on the rig, and the quirks below make a write a light
accepted no proof it kept it. Dropping the read-back per class: `docs/deferred.md`.

Quirks:

- **A blocked command answers SUCCESS.** In the reference server, a Level or Color command the ExecuteIfOff gate
  blocks (`shouldExecuteIfOff`) returns `Status::Success` having done nothing, so a light that mishandles the
  override can't be told from one that took it except by the read-back
  ([`level-control.cpp`](https://github.com/project-chip/connectedhomeip/blob/0233fac8c37223e88d915addce8e8e034bb8a513/src/app/clusters/level-control/codegen/level-control.cpp),
  [`color-control-server.cpp`](https://github.com/project-chip/connectedhomeip/blob/0233fac8c37223e88d915addce8e8e034bb8a513/src/app/clusters/color-control-server/codegen/color-control-server.cpp);
  research, Q2).
- **IKEA KAJPLATS stores the level but comes on at its old one.** Tested with MoveToLevel and ExecuteIfOff on two IKEA
  lamps: both took the write while off (CurrentLevel moved, the lamp stayed off), but on the next `On` the VARMBLIXT
  came up at the stored level and the KAJPLATS at its previous one, though both advertise the same Level Control
  features ([home-assistant/core#174089 comment](https://github.com/home-assistant/core/pull/174089#issuecomment-4892555029);
  research, Q6). Whether its OnLevel was set wasn't reported, so the cause is open; `on_level_set` would show it.
  Labs evidence, not a class of its own yet.
- **The override is certified for brightness and xy color only.** TC-LVL-3.1 (steps 5–6) and TC-CC-5.1 send
  MoveToLevel and MoveToColor to an off light with mask 1 / override 1 since Matter 1.0; no test does so for
  MoveToHueAndSaturation or MoveToColorTemperature (plan Decision 3; research, Q1). HA core's own `matter` light sends
  all three color commands with the same override
  ([`light.py`](https://github.com/home-assistant/core/blob/112e3548608f89297987c46bbfbca9666737e5b1/homeassistant/components/matter/light.py)),
  and its brightness as `MoveToLevelWithOnOff` with none, which is why it can't set a light while off
  ([home-assistant/core#175904](https://github.com/home-assistant/core/issues/175904)).

## Tested behavior

On a WiZ Smart Plug (firmware v1.4), 2026-10-28: the node cache's `OnTime` read 0 before, during and after a 20 s
timer, as the plug never reports it on its subscription. A plain `switch.turn_on` mid-timer left it running.

Overlapping timers on the same plug, 2026-11-17 (Home Assistant 2026.10.4), a probe under the rig's Matter lock: a
second `turn_on_for` while one runs keeps the longer of the two, as the spec's OnWithTimedOff sets OnTime to the
larger of the two. 30 s, then 8 s at 3 s: off at 30.5 s, and the second call was `sent` (`timer_not_reported`), as
OnTime read back 26.9 s, over the 8 s sent. 8 s, then 20 s at 2 s: off at 22.3 s, 20.2 s after the second, which was
`confirmed`.

Its device strings (2026-11-14, Home Assistant 2026.10.4): manufacturer `Signify`, model `WiZ Smart Plug`, `model_id`
`8979`, `sw_version` and `hw_version` `v1.4`; Basic Information VendorID 4107, ProductID 8979, OnOff FeatureMap 1.
Probe: [lab-probe](../zigbee2mqtt/research/2026-11-14-lab-probe.md), §1.

## Upstream defects

Workarounds the adapters carry for behavior upstream that could be fixed there. Only the issues our code already
cites have been checked upstream: search each tracker for duplicates before filing.

- **matter.js: `OnWithTimedOff` with OffWaitTime 0 never turns off** (fixed). Its `OnOffServer` started the timed-on
  countdown only when both OnTime and OffWaitTime were non-zero, so it turned on and stayed on, from v0.9.5
  (2024-09) to v0.17.1; fixed in v0.17.2 (2026-06-09) by [#3842](https://github.com/matter-js/matter.js/pull/3842)
  ([before](https://github.com/matter-js/matter.js/blob/06cd7eaad5b868f3e81ac299d8d3d240e8fcd19b%5E/packages/node/src/behaviors/on-off/OnOffServer.ts),
  `onWithTimedOff`). Apps that share devices on Matter are built on it; nothing in the node shows its version.
  DeviceSide sends OffWaitTime 1, which every version times off: a failure on another field value is about that
  call, so the fix is the call (docs/evidence.md, Contrary evidence).
- **matter.js: a restart drops a running timer** (open), as a reboot does on any device (What decides the call). Its
  countdown is an in-memory timer that nothing rearms on restart, though OnTime persists, so the device stays on
  ([indigo-matter #203](https://github.com/simons-plugins/indigo-matter/issues/203), reproduced 2026-08-31). An app restarts more often
  than a device loses power.

Not worth filing:

- **Firmware:** a WiZ plug never reporting OnTime on its subscription. A report to WiZ at most.
