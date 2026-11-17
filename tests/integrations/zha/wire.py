"""ZHA's wire boundaries for the call transcripts (tests/transcripts.py).

Cluster and group commands (`zcl.command`, `zcl.group_command`) reach the device through
`zha.issue_zigbee_cluster_command` / `issue_zigbee_group_command` on HA's service registry, which the recorder already
records, so they are not listed. The rest go to the zigpy cluster that `zcl`'s helpers (`read_attributes`,
`color_capabilities`, `hue_turn_on`) get from zha's gateway, built and sent by the real helpers in every test:

- `Cluster.read_attributes`: an attribute read, as the cluster's address, the attribute ids and the cache flags; its
  reply is zigpy's `(success, failure)`.
- `Cluster.request`: a cluster command zha has no action for (Hue's multiColor), as the address, the general flag,
  the command id, the schema, the payload and the manufacturer code; its reply is the Default Response.

zigpy isn't a dev dependency, so there is no production class below the helpers to wrap: the boundary is the fake
zigpy cluster in tests/fixtures/zha.py, whose methods take what the helpers pass zigpy. Its instance, the first arg,
records as its address (ieee, endpoint, cluster). A cache read (`Cluster.get`) sends nothing and isn't recorded: the
read it saves is, when the cache is empty, and the result shows what it steered. Every cluster class the fixtures
make inherits both methods, and no test replaces one on an instance. Neither calls the other or itself, so nothing
nests, and each is only ever called directly."""

BOUNDARIES = [
    ("tests.fixtures.zha", "Cluster.read_attributes", 0),
    ("tests.fixtures.zha", "Cluster.request", 0),
]
