# Matter

What DeviceSide's features do on Matter, their limits, and what DeviceSide changes in your setup. What applies
to every integration is in [integrations.md](../../integrations.md); which devices each feature is proven on is
on the [device compatibility page](../../device-compatibility.md); how the calls work, and what was measured, is
in [internals.md](internals.md).

Plugs and lights on the core `matter` integration whose endpoint has the On/Off cluster's Lighting feature, which
Matter's timer needs; one without it is refused (`no_lt_feature`). On/off only: brightness and color fields are
refused on a Matter light.

## Turn on with timer

The timer is read back from the device, so the result is `confirmed` only when it reports both a running timer
(`OnTime`) and that it is on, otherwise `sent`. `turn_off` cancels the timer; a plain `turn_on` doesn't. A second timer
while one runs keeps the longer of the two, so a shorter one is `sent`, not `confirmed`
([tested](internals.md#tested-behavior)). By the spec, a device turned off mid-timer ignores a new timer for
the next 0.1 s and stays off (`sent`). If the device restarts while a timer runs, after a power cut say, it can come
back on with no timer ([internals](internals.md#what-decides-the-call)).

## Get attributes

`get_attributes` reports a timer only when the device reports both a running timer and that it is on.

## Device classes

On Matter the device answers DeviceSide's call itself, so a test on one product proves nothing about another
([internals](internals.md#what-decides-the-call)). DeviceSide tells them apart by what the device reports when it
pairs: its vendor and product IDs, and whether it is a bridge. A product a run has tried, such as the WiZ Smart Plug,
is a class of its own.

### Certified devices

A device certified by the Connectivity Standards Alliance, with one on/off part, has passed a test of the timer reads
that get attributes makes, so get attributes inherits that test. The certification test sends the timer command
with other settings than DeviceSide's, so it says nothing about turn on with timer.
DeviceSide counts a device as certified by its vendor ID, which an uncertified product from a registered vendor also
carries: that is the case this can't catch. Like every Matter device here, it needs the On/Off cluster's Lighting
feature.

### Lights

A Matter light takes the same `OnWithTimedOff` command and timer reads as a plug, so it falls in the class its
vendor and product IDs give it, as a plug does, and inherits that class's features. It is on/off only, and its
endpoint needs the Lighting feature, as [above](#matter).

### Multi-outlet devices

A certified device with more than one on/off part, such as a power strip or a two-gang switch. Certification tests
one of its parts, and DeviceSide can't tell which, so neither feature is built for them yet, even with Labs on.

### Matter bridges

Devices a bridge exposes on Matter, such as Zigbee lights behind a hub. The bridge answers the timer, either by
running it itself or by passing it on to the device, so how it behaves depends on the bridge. Neither feature is
built for them yet, even with Labs on. A bridge's own light or plug counts here too.

### Uncertified devices

A device that reports a test vendor ID: development kits, apps that share other devices on Matter (Matterbridge-style
apps, bridge or not), and the odd uncertified product. Nothing has tested its timer, so neither feature is built for
them yet, even with Labs on. A device that hasn't reported its vendor ID yet is refused turn on
with timer, as unknown, until it does. An app built on matter.js forgets a running timer when it restarts, and the device stays on
([internals](internals.md#upstream-defects)).
