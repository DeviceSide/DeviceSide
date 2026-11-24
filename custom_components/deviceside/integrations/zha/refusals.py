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
from ...zigbee.ikea import TIMER_HARMED_REASON
from ...zigbee.reasons import OTHER_TIMER_REASON, SWITCH_TIMER_REASON

REFUSALS: Mapping[str, Mapping[str, NoKnownMethod | NotBuilt]] = {
    # turn_on_for's call harms each of these (docs/evidence.md, When today's call harms a class): it ends on with no
    # timer, or on or off long after it was asked, unwatched. The action's failure harms, so core also refuses a
    # target it can't class.
    # A call that would work is known or plausible, but isn't built (plan Decisions 70, 74 and 41): every class the
    # call harms, so none has no known method.
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
        # The countdown misbehaves on this string (Z2M #30493: the time left jumps back at random), and Tuya's inching
        # (cluster 0xE000, command 0xFB), which would plausibly serve it, isn't built (plan Decision 41).
        TUYA_COUNTDOWN_HARMED: NotBuilt(
            reason="Tuya's own timer is reported to restart at random on its maker string, so it may not turn off when "
            "asked, and the timer that would serve it isn't built",
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
