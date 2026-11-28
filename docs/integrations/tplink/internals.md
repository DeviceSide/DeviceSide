# TP-Link internals

What a user sees is in [index.md](index.md) and isn't repeated here; what every integration shares is in
[internals.md](../../internals.md). Code comments cite the sections here.

## Addressing

A device's class is read from the core tplink config entry's python-kasa device object,
`entry.runtime_data.parent_coordinator.device` and its `children`, by name: neither `kasa` nor
`homeassistant.components.tplink` is imported. The entity is the device's primary entity, whose unique_id is core's
`legacy_device_id(device)` (`tplink/entity.py`, `_get_feature_unique_id`), or for a light the mac, unless it has a
parent or children or is an IOT dimmer (`tplink/light.py`, `_get_backwards_compatible_light_unique_id`). Sources:
[research](../../research/2026-11-28-tplink-call-patterns.md#6-transport-and-classes).
