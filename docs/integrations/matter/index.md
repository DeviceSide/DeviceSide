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
(`OnTime`) and that it is on, otherwise `sent`. `turn_off` cancels the timer; a plain `turn_on` doesn't. By the spec,
a second timer while one runs keeps the longer of the two, and a device turned off mid-timer ignores a new timer for
the next 0.1 s and stays off (`sent`). If the device restarts while a timer runs, after a power cut say, it can come
back on with no timer ([internals](internals.md#what-decides-the-call)).

## Get attributes

`get_attributes` reports a timer only when the device reports both a running timer and that it is on.

## Device classes

On Matter the device answers DeviceSide's call itself, so a test on one product proves nothing about another
([internals](internals.md#what-decides-the-call)). DeviceSide tells them apart by what the device reports when it
pairs: its vendor and product IDs, and whether it is a bridge. Every feature says how well it is proven for each
([levels of proof](../../device-compatibility.md#levels-of-proof)).

### WiZ Smart Plug

A Matter plug, rig-tested with turn on with timer and get attributes. It never reports its running timer on its own,
so DeviceSide reads it back ([turn on with timer](#turn-on-with-timer)). Turn on with timer now sends a slightly
different command (a 0.1 s off wait, [internals](internals.md#turn_on_for)), so it runs only with Experimental
features on until the plug is tested with it again.

### Certified devices

A device certified by the Connectivity Standards Alliance has passed a test of the timer reads that get attributes
makes, so get attributes runs on it with Experimental features off. The certification test sends the timer command
with other settings than DeviceSide's, so turn on with timer is untested and runs only with Experimental features on.
DeviceSide counts a device as certified by its vendor ID, which an uncertified product from a registered vendor also
carries: that is the case this can't catch. Like every Matter device here, it needs the On/Off cluster's Lighting
feature.

### Matter bridges

Devices a bridge exposes on Matter, such as Zigbee lights behind a hub. The bridge answers the timer, either by
running it itself or by passing it on to the device, so how it behaves depends on the bridge. Untested: both
features run only with Experimental features on. A bridge's own light or plug counts here too.

### Uncertified devices

A device that reports a test vendor ID, or none yet: development kits, apps that share other devices on Matter
(Matterbridge-style apps, bridge or not), and the odd uncertified product. Nothing has tested its timer, so both
features run only with Experimental features on. An app built on matter.js forgets a running timer when it restarts,
and the device stays on ([internals](internals.md#upstream-defects)).

## Should work

### Matter lights

A Matter light takes the plug's `OnWithTimedOff` command and reads, so they are Documented on it, at most as proven
as its class above. Its endpoint needs the On/Off cluster's Lighting feature, which the timer
needs; one without it is refused (`no_lt_feature`). On/off only: brightness and color are refused on a Matter light
until tested.
