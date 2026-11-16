# Which Matter entities are an endpoint's On/Off (2026-11-16)

Question: can a Matter `switch` or `light` that isn't its endpoint's On/Off reach the Matter adapters, which took
the endpoint from the unique ID and checked only that endpoint's Lighting feature? Code only, no device run. Sources:
Home Assistant core `dev` at
[`49efa55`](https://github.com/home-assistant/core/tree/49efa558cf00133728207413b883f2bfd398e1e7): `matter/entity.py`,
`switch.py`, `light.py`, `discovery.py`, and the Matter test snapshots and node fixtures.

## Bottom line

1. **Yes, on real devices.** HA's snapshots hold config switches on the same endpoint as an On/Off with the Lighting
   feature (`{endpoint}/6/65532 = 1` in the fixture):

   | Fixture | Extra `switch` on endpoint 1 (unique ID tail) | Endpoint 1's On/Off |
   |---|---|---|
   | `eve_energy_plug`, `eve_energy_plug_patched` | `EveChildLock-319486977-319422481`, config | `MatterPlug-6-0` |
   | `eve_energy_20ecn4101` (two outlets) | `EveChildLock-319486977-319422481`, config | `MatterPlug-6-0` |
   | `aqara_led_strip_t2` | `AqaraLedStripMusicSyncEnabled-291503119-19` | the strip's `light` |

   Before #459, `turn_on_for` on the child lock passed the check and sent `OnWithTimedOff` to the plug, and
   `get_attributes` reported the plug's timer as the child lock's.
2. **The unique ID names the entity's own attribute.** `entity.py` builds it as
   `{node_device_id}-{endpoint_id}-{key}-{cluster_id}-{attribute_id}` from the schema's primary attribute, which
   `discovery.py` takes as `required_attributes[0]`.
3. **Every switch or light that drives On/Off has `OnOff.OnOff` as its primary attribute, so its tail is `6-0`:**
   `MatterPlug`, `MatterPowerToggle`, `MatterSwitch`, `MatterMuteToggle` and all four `light` schemas, the
   color fallbacks included. Every other `switch` (child locks, door-lock options, EVSE charging, alarm enables,
   reverse motor direction, indicators) has another cluster. So "the tail is `6-0`" is the test for "this entity is
   its endpoint's On/Off", which #459 adds.
4. **Two `6-0` switches are not plain on/off, and stay addressed.** `MatterMuteToggle` (speakers) is inverted: a
   timer on it unmutes the speaker for its duration. It runs only on a speaker whose On/Off has the Lighting
   feature, and no fixture has one. IKEA ALPSTUGA's `MatterSwitch` is a config switch for the display, but it is
   that endpoint's On/Off, so a timer does what the entity shows.
5. **Device classes are unaffected.** `multi_endpoint` counts On/Off clusters in the node's attributes, not HA
   entities, so a child lock never adds to it.
