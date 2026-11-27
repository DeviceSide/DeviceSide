# Z-Wave internals

How the Z-Wave adapters address a target, what they send and read back. What a user sees is in [index.md](index.md) and
isn't repeated here; what every integration shares is in [internals.md](../../internals.md). Result and detail codes
are in the code. Code comments cite the sections here.

## Addressing

Through the core `zwave_js` config entry's client (`entry.runtime_data.client.driver.controller.nodes`), never
importing the integration. A light's unique ID is `{home_id}.{value_id}` and a value ID
`{node_id}-{command_class}-{endpoint}-{property}`, so the node and endpoint come from the ID. Calls go through the
endpoint's `async_invoke_cc_api`, which returns the command class's result. An endpoint with no Multilevel Switch
command class is refused `not_dimmable`.

## Device classes

What decides a call's outcome on Z-Wave: Z-Wave JS gives every vendor's dimmer the same Multilevel Switch API, and the
device's firmware answers it. A class keys on the node's identity or the Multilevel Switch version the endpoint
reports.

| Class | Rule |
|---|---|
| `lzw42` | Inovelli LZW42: manufacturer 0x031e, product type 0x0005, product ID 0x0001 ([Z-Wave JS config](https://github.com/zwave-js/zwave-js/blob/473703662970725e75fcf8d6f2d226c48dc4f3ba/packages/config/config/devices/0x031e/lzw42.json)) |
| `v1` | Multilevel Switch version 1, which has no duration |
| `other` | Any other Multilevel Switch endpoint |
