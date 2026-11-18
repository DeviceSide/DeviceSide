"""Zigbee2MQTT's refusal entries: the classes an action refuses with a reason (NotBuilt, NoKnownMethod), by action,
then class. `classes.class_scope` puts them in each adapter's scope.

They are the integration's, not a family's (core/scope.py, FamilyScope): an entry on an action whose failure harms
keeps a call from leaving a device on or off unasked, and makes the dispatcher refuse a device not yet placed as
well, so it changes what users of every family's devices get. A family's maintainers may merge a change to their
family's files alone; this path isn't theirs, so an entry is added, changed or removed with an integration
maintainer.
"""

from collections.abc import Mapping

from homeassistant.const import Platform

from .docs import RESEARCH
from .families.hue import HUE
from .families.ikea import IKEA, IKEA_TIMER_HARMED
from .families.tuya import COUNTDOWNS, TUYA_COUNTDOWN, TUYA_COUNTDOWN_HARMED, TUYA_MCU, TUYA_TS011F, TUYA_ZCL
from ...core.scope import OTHER, NoKnownMethod, NotBuilt

# What the user reads after core's "can't take this action yet" (errors.py, the not_built key).
_STAYS_ON = "Zigbee2MQTT would turn it on with no timer, so it would stay on"

REFUSALS: Mapping[str, Mapping[str, NoKnownMethod | NotBuilt]] = {
    # turn_on_for. Tuya's classes off its countdown are not built yet, and harmed by today's call (plan Decisions 20,
    # 70 and 71): Z2M has no `on_time` converter for a definition built with `onOffCountdown`, or for a datapoint
    # device, so it sends a plain On and the device stays on. Each has a call that would work, Z2M's `countdown`, which
    # isn't built for them: converter A's for a TS011F Z2M shows no `countdown` for and the TS011F's kin (v0.1.0
    # builds it for the countdown plugs alone, plan Decision 72), the datapoint one for TS0601 devices (v0.1.x,
    # docs/plans/2026-11-15-tuya-datapoint-countdown.md). The action's failure harms, so the dispatcher refuses a device
    # not yet placed as well, which could be one of them (plan Decision 26).
    "turn_on_for": {
        # Every other brand's lights, plugs and switches (docs/evidence.md, On trial): no pass, and research names only
        # some makers' lights as running the timer, some lights turning on and never off, and most plugs ignoring it
        # or reading it as a vendor countdown. The call that would serve them, a host-side off, isn't built.
        OTHER: NotBuilt(
            reason="Too few reports say its brand runs the timer, and some lights and most plugs turn on and "
            "never off, so it could stay on; DeviceSide's own off, which would serve it, isn't built",
            source=RESEARCH + "2026-11-14-timed-on-call-patterns.md",
        ),
        # Hue's plug and IKEA's outlets, on the switch domain alone: their bulbs keep their class's level, the plugs
        # have no pass, and plugs needn't implement OnWithTimedOff. The calls that would serve them, a host-side off or
        # the plug's auto-off, aren't built.
        **dict.fromkeys(
            (HUE, IKEA),
            NotBuilt(
                reason="Most plugs and switches ignore the timer or read it as a delayed toggle, so it could stay on, "
                "and the calls that would serve them, DeviceSide's own off or the plug's auto-off, aren't built",
                source=RESEARCH + "2026-11-14-timed-on-call-patterns.md",
                domains=frozenset({Platform.SWITCH}),
            ),
        ),
        # Reported turned on by a unicast timer and never off, while the same call by group did turn them off; the
        # cause is unknown. A host-side off would serve them.
        IKEA_TIMER_HARMED: NotBuilt(
            reason="It is reported to turn on with the timer and never turn off, and DeviceSide's own off, which would "
            "serve it, isn't built",
            source="https://github.com/Koenkk/zigbee2mqtt/issues/29158",
        ),
        # Converter A's TS011Fs without a record of their own (docs/evidence.md, On trial: a pass admits only the
        # maker string it ran on). Route A holds about 200 strings, each an OEM build, and some are reported to ignore
        # the countdown. Tuya's countdown is built; what it lacks is a pass on the string.
        TUYA_COUNTDOWN: NotBuilt(
            reason="Tuya's own timer, which DeviceSide sends the plugs it was tested on, is untested on its maker "
            "string, and Zigbee2MQTT's timer would leave it on",
            source=RESEARCH + "2026-11-15-converter-seed-list.md",
        ),
        # Measured (Decision 16), and matched by its model so every firmware inherits the refusal.
        TUYA_TS011F: NotBuilt(reason=_STAYS_ON, source=RESEARCH + "2026-11-14-lab-probe.md"),
        TUYA_ZCL: NotBuilt(reason=_STAYS_ON, source=RESEARCH + "2026-11-14-timed-on-call-patterns.md"),
        # The harm today: a datapoint device's definition has no `on_time` converter either, so it gets a plain On
        # (timed-on call patterns); the call that would serve it is the datapoint countdown (its research note).
        TUYA_MCU: NotBuilt(reason=_STAYS_ON, source=RESEARCH + "2026-11-14-timed-on-call-patterns.md"),
        # Reported failing the countdown with harm (plan Decisions 35 and 41).
        TUYA_COUNTDOWN_HARMED: NotBuilt(
            reason="its maker string is reported to restart its timer at random, so it could stay on",
            source="https://github.com/Koenkk/zigbee2mqtt/issues/30493",
        ),
    },
    # get_attributes. On a countdown plug the only thing the read adds is the timer, and its time left can't be read:
    # `/get` and the plug's reports carry the countdown last set (internals.md, Tuya's countdown, P6). A read, whose
    # failure doesn't harm (Action.failure_harms; docs/evidence.md, When today's call harms a class). The TS011Fs off
    # the countdown are in no scope: no other action serves them, so there is nothing to read back around
    # (docs/evidence.md, "A read serves only").
    "get_attributes": dict.fromkeys(
        COUNTDOWNS,
        NoKnownMethod(
            what="Tuya TS011F plugs",
            reason="Its timer reads back the time it was set to, not the time left, so DeviceSide can't read it",
            source=RESEARCH + "2026-11-15-tuya-countdown-probe.md",
        ),
    ),
}
