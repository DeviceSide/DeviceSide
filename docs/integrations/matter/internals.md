# Matter internals

How the Matter adapters address a target, what they send and read back, and what was measured on real hardware.
What a user sees is in [index.md](index.md) and isn't repeated here; what every integration shares is in
[internals.md](../../internals.md). Result and detail codes are in the code. Code comments cite the sections here.

## Addressing

Through the core integration's python-matter-server connection. The unique ID is
`{fabric_hex16}-{node_hex16}-{postfix}-{endpoint_id}-{key}-{cluster_id}-{attr_id}`. The Lighting feature check reads
FeatureMap bit 0 from the node data (`node_data.attributes["{endpoint}/6/65532"]`), avoiding a chip.clusters import
that `MatterEndpoint.get_attribute_value` would need.

Lights take the same command and reads as plugs, behind the same Lighting feature check.

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
- **Certification** tests the call on every device with the feature: TC-OO-2.3 (PICS `OO.S.F00`) sends
  `OnWithTimedOff` 15 times and checks that the device turns off when OnTime runs out (step 24c reads OnOff false
  after 40 s), always with OffWaitTime 300, never 0
  ([`Test_TC_OO_2_3.yaml`](https://github.com/project-chip/connectedhomeip/blob/c55ddad4480afad31f249af5356c16e8b53416c6/src/app/tests/suites/certification/Test_TC_OO_2_3.yaml)). The reference server
  clears OffWaitTime when OnTime runs out, so a non-zero one only guards, after an Off mid-timer, against another
  `OnWithTimedOff` for that long ([`OnOffLightingCluster.cpp`](https://github.com/project-chip/connectedhomeip/blob/c55ddad4480afad31f249af5356c16e8b53416c6/src/app/clusters/on-off-server/OnOffLightingCluster.cpp),
  `TimerFired`, `HandleOnWithTimedOff`).
- **A test VendorID** (0xFFF1 to 0xFFF4, [`CHIPVendorIdentifiers.hpp`](https://github.com/project-chip/connectedhomeip/blob/c55ddad4480afad31f249af5356c16e8b53416c6/src/lib/core/CHIPVendorIdentifiers.hpp),
  `IsTestVendorId`) is what no certified product carries; development kits and software that shares devices on
  Matter report one (HA's own test fixtures: Nordic, Silabs and Nabu Casa sample nodes, `tests/components/matter/fixtures/nodes/`).
- **What HA exposes.** The device registry holds Basic Information's `vendorName` as manufacturer, `productLabel` or
  `productName` as model, `productID` as `model_id` (none on a bridged device), and the version strings
  ([`adapter.py`](https://github.com/home-assistant/core/blob/2bca51ea8e647696e2c86f43e4edea3bdb48ea74/homeassistant/components/matter/adapter.py), `_create_device_registry`), but not the VendorID, the device types or the
  clusters. Those are in the client's node cache, `node.node_data.attributes`, keyed `"<endpoint>/<cluster>/<attribute>"`:
  VendorID `0/40/2`, ProductID `0/40/4`, each endpoint's DeviceTypeList `<endpoint>/29/0` (structs keyed by field id,
  `[{"0": 266, "1": 1}]`) and FeatureMap `<endpoint>/6/65532`. A bridge has an endpoint whose DeviceTypeList holds
  the Aggregator (0x000E), and its bridged endpoints the Bridged Node (0x0013), as the client reads them
  (`matter_server/client/models/node.py`, `is_bridged_device`).

So a class keys on the node, read sync from that cache (`classes.py` holds the rules and their order): a test
VendorID first, as certification hasn't tested it; then a bridge, whose software answers; then a measured product by
VendorID and ProductID, which name its firmware; else the default. The lab's plug is the one product measured.

## Modules

One section per adapter module, named after it.

### `turn_on_for`

`OnOff.Commands.OnWithTimedOff(onOffControl=0, onTime=<tenths>, offWaitTime=1)`, then
reads of `OnOff.OnTime` and `OnOff.OnOff`, one path per `read_attribute`: `confirmed` when OnOff is on and OnTime
is at most the time sent and no more than 3 s under it, as on ZHA. OnTime alone is not proof: a device can hold a
stale OnTime while off.

OffWaitTime is 1 (0.1 s), not 0, since 2026-11-14 (plan Decision 46): it puts the call on the path certification tests
(What decides the call), and matter.js before v0.17.2 never turns off on OffWaitTime 0 (Upstream defects). The
2026-10-28 and 2026-11-11 records ran OffWaitTime 0.

### `get_attributes`

Live reads of `OnTime` and `OnOff`, as the plug tested never reports OnTime on its
subscription, so the node cache reads 0 mid-timer (Tested behavior). A timer is reported only while OnOff is on.
`turns` is always `off`.

## Tested behavior

On a WiZ Smart Plug (firmware v1.4), 2026-10-28: the node cache's `OnTime` read 0 before, during and after a 20 s
timer, as the plug never reports it on its subscription. A plain `switch.turn_on` mid-timer left it running.

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
  DeviceSide sends OffWaitTime 1, which every version times off.
- **matter.js: a restart drops a running timer** (open). The countdown is an in-memory timer that nothing rearms on
  restart, though OnTime persists, so the device stays on
  ([indigo-matter #203](https://github.com/simons-plugins/indigo-matter/issues/203), reproduced 2026-08-31). Why
  uncertified devices and bridges stay untested (index.md).

Not worth filing:

- **Firmware:** a WiZ plug never reporting OnTime on its subscription. A report to WiZ at most.
