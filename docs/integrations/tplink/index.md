# TP-Link

What DeviceSide's features do on TP-Link's Kasa and Tapo devices, their limits, and what DeviceSide changes in your
setup. What applies to every integration is in [integrations.md](../../integrations.md); which devices each feature is
proven on is on the [device compatibility page](../../device-compatibility.md); how the calls work, and what was
measured, is in [internals.md](internals.md).

This page is a stub: the package's classes are in place, and its actions land in the steps that follow.

## Device classes

DeviceSide tells TP-Link devices apart by python-kasa's device type, and by whether the device is a Kasa one (the
older IOT protocol) or a Tapo one (SMART), read from Home Assistant's own TP-Link integration
([internals](internals.md#addressing)).

### Kasa plugs and switches

Kasa plugs and wall switches (KP115, HS100, KP105, HS200 and the like).

### Kasa strip outlets

The outlets of a Kasa power strip (HS300, KP303, KP400).

### Tapo plugs and switches

Tapo plugs and wall switches that aren't on a strip or hub.

### Tapo strip outlets

The outlets of a Tapo power strip (P300, P304M).

### Tapo hub switches

Tapo smart switches paired to a Tapo hub (S210, S220).

### Tapo lights

Tapo bulbs, dimmers and light strips, and a dimmer that is a child of another Tapo device (KS240).

### Kasa lights

Kasa bulbs, dimmers and light strips. They aren't built: the countdown namespace they take isn't known.
