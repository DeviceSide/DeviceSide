"""ZHA's refusal entries: the classes an action refuses with a reason (NotBuilt, NoKnownMethod), by action, then
class. `classes.class_scope` puts them in each adapter's scope.

They are the integration's, not a family's (core/scope.py, FamilyScope): an entry on an action whose failure harms
keeps a call from leaving a device on or off unasked, and makes core refuse a target it can't class as well, so it
changes what users of every family's devices get. A family's maintainers may merge a change to their family's files
alone; this path isn't theirs, so an entry is added, changed or removed with an integration maintainer.
"""

from collections.abc import Mapping

from homeassistant.const import Platform

from .docs import INTERNALS, RESEARCH
from .families.hue import HUE
from .families.ikea import IKEA, IKEA_TIMER_HARMED
from .families.sengled import SENGLED
from .families.sonoff import SONOFF_SWV
from .families.tuya import TUYA_COUNTDOWN, TUYA_COUNTDOWN_HARMED, TUYA_MCU, TUYA_ZCL
from ...core.scope import OTHER, NoKnownMethod, NotBuilt

REFUSALS: Mapping[str, Mapping[str, NoKnownMethod | NotBuilt]] = {
    # turn_on_for's call harms each of these (docs/evidence.md, When today's call harms a class): it ends on with no
    # timer, or on or off long after it was asked, unwatched. The action's failure harms, so core also refuses a
    # target it can't class.
    # A call that would work is known or plausible, but isn't built (plan Decisions 70, 74 and 41): every class the
    # call harms, so none has no known method.
    "turn_on_for": {
        # Every other brand's lights, plugs and switches (docs/evidence.md, In Labs): no pass, and research names only
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
        # The countdown misbehaves on this string (Z2M #30493: the time left jumps back at random), and Tuya's inching
        # (cluster 0xE000, command 0xFB), which would plausibly serve it, isn't built (plan Decision 41).
        TUYA_COUNTDOWN_HARMED: NotBuilt(
            reason="Tuya's own timer is reported to jump back at random on it, so it may not turn off when asked, and "
            "the timer that would serve it isn't built",
            source="https://github.com/Koenkk/zigbee2mqtt/issues/30493",
        ),
        # Tuya's recipe would serve it, parked (internals.md, "Tuya's recipe, parked"); today's tenths harm it (Tested
        # behavior, the TS011F).
        TUYA_COUNTDOWN: NotBuilt(
            reason="ZHA's timer can turn it on long after the time asked and leave it on",
            source=RESEARCH + "2026-11-14-lab-probe.md",
        ),
        # The recipe or a countdown is plausible; the spec's tenths may be read as seconds, as the countdown models do.
        TUYA_ZCL: NotBuilt(
            reason="ZHA's timer can turn it on or off long after the time asked",
            source=RESEARCH + "2026-11-14-timed-on-call-patterns.md",
        ),
        # A datapoint countdown is plausible; the quirk refuses 0x42, and with fields the light.turn_on before it stays
        # on.
        TUYA_MCU: NotBuilt(
            reason="ZHA refuses its timer, so with brightness or a color temperature it would turn on and stay on",
            source=INTERNALS + "#classes",
        ),
        # A host-side off would serve the Sengled; it refuses 0x42 by unicast and misses it by groupcast (Tested
        # behavior).
        SENGLED: NotBuilt(
            reason="It refuses the timer, so with brightness, a color temperature or in a group it would stay on",
            source=INTERNALS + "#tested-behavior",
        ),
        # Z2M's call in whole seconds (on_off_fixed_on_time) works on Sonoff's valve; ZHA's tenths would run ten times
        # as long.
        SONOFF_SWV: NotBuilt(
            reason="It reads ZHA's timer in seconds, so it would stay open about ten times longer than asked",
            source=RESEARCH + "2026-11-14-tuya-countdown.md",
        ),
    },
}
