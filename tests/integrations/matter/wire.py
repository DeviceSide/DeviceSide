"""Matter's wire boundaries for the call transcripts (tests/transcripts.py).

python-matter-server's `MatterClient` is the one place a call reaches the node, through the server's websocket:

- `MatterClient.send_device_command`: a cluster command, as the node id, the endpoint id and the command (chip's
  `OnOff.OnWithTimedOff`, which records as its name and fields); its reply is the server's result.
- `MatterClient.read_attribute`: a live attribute read, as the node id and the attribute path
  (`<endpoint>/<cluster>/<attribute>`); its reply is `{attribute_path: value}`.

`get_node` reads the client's cache, sends nothing and isn't listed.

matter_server and chip aren't dev dependencies, so the boundaries are the fake in tests/fixtures/matter.py, a class
whose methods take what DeviceSide passes the client and await each test's mocks; no test replaces one on an
instance. The instance, the first arg, is dropped. Neither method calls the other or itself, so nothing nests, and
each is only ever called directly through the class (`client.read_attribute(...)`), never through a reference
captured before the wrap."""

BOUNDARIES = [
    ("tests.fixtures.matter", "MatterClient.send_device_command", 1),
    ("tests.fixtures.matter", "MatterClient.read_attribute", 1),
]
