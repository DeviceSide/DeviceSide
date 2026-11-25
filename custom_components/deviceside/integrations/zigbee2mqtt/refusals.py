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
from .families.aqara import AQARA
from .families.hue import HUE
from .families.ikea import IKEA, IKEA_TIMER_HARMED
from .families.sonoff import SONOFF_INCHING, SONOFF_S60
from .families.tuya import COUNTDOWNS, TUYA_COUNTDOWN_HARMED, TUYA_INCHING, TUYA_MCU, TUYA_TS011F, TUYA_ZCL
from ...core.scope import OTHER, NoKnownMethod, NotBuilt
from ...zigbee.ikea import TIMER_HARMED_REASON
from ...zigbee.reasons import OTHER_TIMER_REASON, SWITCH_TIMER_REASON
from ...zigbee.tuya import COUNTDOWN_HARMED_REASON

# What the user reads after core's "can't take this action yet" (errors.py, the not_built key).
_STAYS_ON = "Zigbee2MQTT would turn it on with no timer, so it would stay on"

_S60_NOT_BUILT = NotBuilt(
    reason="Its inching can't be turned off: Zigbee2MQTT's DISABLE is reported to have no effect on it, so it would "
    "keep turning itself off",
    source=RESEARCH + "sonoff/2026-11-24-inching.md",
)

REFUSALS: Mapping[str, Mapping[str, NoKnownMethod | NotBuilt]] = {
    # turn_on_for. Tuya's classes off its countdown are not built yet, and harmed by today's call (plan Decisions 20,
    # 70 and 71): Z2M has no `on_time` converter for a definition built with `onOffCountdown`, or for a datapoint
    # device, so it sends a plain On and the device stays on. Each has a call that would work, Z2M's `countdown`, which
    # isn't built for them: converter A's for a TS011F Z2M shows no `countdown` for and the TS011F's kin (v0.1.0 serves
    # it to the countdown plugs alone, Verified or in Labs, plan Decision 72), the datapoint one for the TS0601 devices
    # outside the datapoint classes (families/tuya/datapoint.py serves the single-endpoint ones research names). The
    # action's failure harms, so the dispatcher refuses a device not yet placed as well, which could be one of them
    # (plan Decision 26).
    "turn_on_for": {
        OTHER: NotBuilt(
            reason=OTHER_TIMER_REASON,
            source=RESEARCH + "2026-11-14-timed-on-call-patterns.md",
        ),
        **dict.fromkeys(
            (HUE, IKEA),
            NotBuilt(
                reason=SWITCH_TIMER_REASON,
                source=RESEARCH + "2026-11-14-timed-on-call-patterns.md",
                domains=frozenset({Platform.SWITCH}),
            ),
        ),
        IKEA_TIMER_HARMED: NotBuilt(
            reason=TIMER_HARMED_REASON,
            source="https://github.com/Koenkk/zigbee2mqtt/issues/29158",
        ),
        # Measured (Decision 16), and matched by its model so every firmware inherits the refusal.
        TUYA_TS011F: NotBuilt(reason=_STAYS_ON, source=RESEARCH + "2026-11-14-lab-probe.md"),
        **dict.fromkeys(
            (TUYA_ZCL, TUYA_INCHING),  # inching left `tuya_zcl` for its auto-off, so keeps its entry (families/tuya)
            NotBuilt(reason=_STAYS_ON, source=RESEARCH + "2026-11-14-timed-on-call-patterns.md"),
        ),
        # The datapoint devices outside the datapoint classes: multi-gang ones and every countdown named per endpoint
        # (they need per-endpoint addressing), timers in minutes, hours or an enum, the definitions left out by
        # datapoint.py, and any research hasn't read. Their definition has no `on_time` converter either, so they get a
        # plain On (timed-on call patterns); the call that would serve most is the datapoint countdown (its research
        # note), addressed per endpoint.
        TUYA_MCU: NotBuilt(reason=_STAYS_ON, source=RESEARCH + "2026-11-14-timed-on-call-patterns.md"),
        # Sonoff's classes, which left `other` for inching: the same entry, as no pass or research says their firmware
        # takes the timer (families/sonoff).
        **dict.fromkeys(
            (SONOFF_INCHING, SONOFF_S60),
            NotBuilt(reason=OTHER_TIMER_REASON, source=RESEARCH + "2026-11-14-timed-on-call-patterns.md"),
        ),
        # Measured on the T2 E27: from off, `on_time` (0x42) never turned the bulb on, and it has no OnTime or
        # OffWaitTime (families/aqara; the probe, section 3).
        AQARA: NotBuilt(
            reason="Its bulb ignores the timer, so it would stay off",
            source=RESEARCH + "aqara/2026-11-25-agl003-probe.md",
        ),
        # Reported failing the countdown with harm (plan Decisions 35 and 41).
        TUYA_COUNTDOWN_HARMED: NotBuilt(
            reason=COUNTDOWN_HARMED_REASON,
            source="https://github.com/Koenkk/zigbee2mqtt/issues/30493",
        ),
    },
    # set_auto_off and clear_auto_off, on the S60 plugs, whose inching DISABLE is reported to have no effect (Z2M
    # #31799, closed as a duplicate of #31604), so clear_auto_off would leave the plug pulsing; set_auto_off is left
    # out with it, as an auto-off nothing can clear isn't offered.
    "set_auto_off": {SONOFF_S60: _S60_NOT_BUILT},
    "clear_auto_off": {SONOFF_S60: _S60_NOT_BUILT},
    # get_attributes. On a countdown plug the only thing the read adds is the timer, and its time left can't be read:
    # `/get` and the plug's reports carry the countdown last set (internals.md, Tuya's countdown, P6). A read, whose
    # failure doesn't harm (Action.failure_harms; docs/evidence.md, When today's call harms a class). The TS011Fs off
    # the countdown are in no scope: no other action serves them, so there is nothing to read back around
    # (docs/evidence.md, "A read serves only"). The datapoint classes, which turn_on_for and turn_off_for serve, are in
    # no scope here either and hold no entry: whether they report the time left is unprobed, so the read is not built
    # yet, and the registry refuses a not_built entry on a read, whose failure doesn't harm.
    "get_attributes": dict.fromkeys(
        COUNTDOWNS,
        NoKnownMethod(
            what="Tuya TS011F plugs",
            reason="Its timer reads back the time it was set to, not the time left, so DeviceSide can't read it",
            source=RESEARCH + "2026-11-15-tuya-countdown-probe.md",
        ),
    ),
}
