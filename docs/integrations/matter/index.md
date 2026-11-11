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
(`OnTime`) and that it is on, otherwise `sent`. `turn_off` cancels the timer; a plain `turn_on` doesn't.

## Get attributes

`get_attributes` reports a timer only when the device reports both a running timer and that it is on.

## Tested devices

### WiZ Smart Plug

A Matter plug, rig-tested with turn on with timer and get attributes. It never reports its running timer on its own,
so DeviceSide reads it back ([turn on with timer](#turn-on-with-timer)).

## Should work

### Matter lights

A Matter light takes the plug's `OnWithTimedOff` command, so turn on with timer and get attributes are Documented on
it. Its endpoint needs the On/Off cluster's Lighting feature, which the timer needs; one without it is refused
(`no_lt_feature`). On/off only: brightness and color are refused on a Matter light until tested.
