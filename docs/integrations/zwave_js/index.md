# Z-Wave

What DeviceSide's features do on Z-Wave, their limits, and what DeviceSide changes in your setup. What applies
to every integration is in [integrations.md](../../integrations.md); which devices each feature is proven on is
on the [device compatibility page](../../device-compatibility.md).

Lights on the core `zwave_js` integration whose endpoint has the Multilevel Switch command class. One without it is
refused (`not_dimmable`).

## Device classes

DeviceSide sends Z-Wave JS the same Multilevel Switch calls for every light, and the device's firmware decides what
each does, so DeviceSide tells lights apart by the node's identity and the command class version the endpoint reports.

### Other dimmers and bulbs

Any dimmer or bulb whose Multilevel Switch is version 2 or later, of any brand. `get_attributes` reads its level with
the same Multilevel Switch Get that Home Assistant's own polling sends every brand.

### Inovelli LZW42

Inovelli's LZW42 bulb (manufacturer 0x031e, product type 0x0005, product ID 0x0001). Its Start Level Change version 3
jumps to the end level, so its moves will run as timed sets.

### Version 1 dimmers

A Multilevel Switch version 1 has no transition duration, so no move can be timed on it. It isn't built yet.
