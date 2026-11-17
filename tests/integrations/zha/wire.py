"""ZHA's wire boundaries for the call transcripts (tests/transcripts.py).

Cluster and group commands (`zcl.command`, `zcl.group_command`) reach the device through
`zha.issue_zigbee_cluster_command` / `issue_zigbee_group_command` on HA's service registry, which the recorder already
records, so they are not listed. The calls that go to zigpy directly, or read it, are:

- `zcl.read_attributes`: an attribute read off the device (address, cluster, attribute ids); its reply is the values.
- `zcl.hue_turn_on`: Hue's multiColor request to the cluster (address, level), with True for sent and False for a light
  without Hue's cluster.
- `zcl.color_capabilities`: the light's ColorCapabilities bits, from zigpy's cache or a read. A cached read sends
  nothing, but it is a read the action makes and its reply steers the move, so it is recorded. When it does read the
  device it calls `read_attributes`, which records too: the two names differ, so neither is a call to itself.

`hass` is dropped. Callers reach each as `zcl.<name>`, so a test's `monkeypatch.setattr(zcl, ...)` mock is wrapped
too. Each is only ever called directly, never passed as a callback."""

BOUNDARIES = [
    ("custom_components.deviceside.integrations.zha.zcl", "read_attributes", 1),
    ("custom_components.deviceside.integrations.zha.zcl", "hue_turn_on", 1),
    ("custom_components.deviceside.integrations.zha.zcl", "color_capabilities", 1),
]
