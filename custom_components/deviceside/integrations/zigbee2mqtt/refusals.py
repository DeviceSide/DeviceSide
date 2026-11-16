"""Zigbee2MQTT's refusal entries: the classes an action refuses with a reason (NotBuilt, NoKnownMethod), by action,
then class. `classes.class_scope` puts them in each adapter's scope.

They are the integration's, not a family's (core/scope.py, FamilyScope): an entry with `harms` keeps a call from
leaving a device on or off unasked, and makes the dispatcher refuse a device not yet placed as well, so it changes
what users of every family's devices get. A family's maintainers may merge a change to their family's files alone;
this path isn't theirs, so an entry is added, changed or removed with an integration maintainer.
"""

from collections.abc import Mapping

from .docs import RESEARCH
from .families.tuya import TUYA_COUNTDOWN_HARMED, TUYA_MCU, TUYA_TS011F, TUYA_ZCL
from ...core.scope import NoKnownMethod, NotBuilt

# What the user reads after core's "can't take this action yet" (errors.py, the not_built key).
_STAYS_ON = "Zigbee2MQTT would turn it on with no timer, so it would stay on"

REFUSALS: Mapping[str, Mapping[str, NoKnownMethod | NotBuilt]] = {
    # turn_on_for. Tuya's classes off its countdown are not built yet, and harmed by today's call (plan Decisions 20,
    # 70 and 71): Z2M has no `on_time` converter for a definition built with `onOffCountdown`, or for a datapoint
    # device, so it sends a plain On and the device stays on. Each has a call that would work, Z2M's `countdown`, which
    # isn't built for them: converter A's for a TS011F Z2M shows no `countdown` for and the TS011F's kin (v0.1.0
    # builds it for the countdown plugs alone, plan Decision 72), the datapoint one for TS0601 devices (v0.1.x,
    # docs/plans/2026-11-15-tuya-datapoint-countdown.md). `harms`, so the dispatcher refuses a device not yet placed
    # as well, which could be one of them (plan Decision 26).
    "turn_on_for": {
        # Measured (Decision 16), and matched by its model so every firmware inherits the refusal.
        TUYA_TS011F: NotBuilt(reason=_STAYS_ON, source=RESEARCH + "2026-11-14-lab-probe.md", harms=True),
        TUYA_ZCL: NotBuilt(reason=_STAYS_ON, source=RESEARCH + "2026-11-14-timed-on-call-patterns.md", harms=True),
        # The harm today: a datapoint device's definition has no `on_time` converter either, so it gets a plain On
        # (timed-on call patterns); the call that would serve it is the datapoint countdown (its research note).
        TUYA_MCU: NotBuilt(reason=_STAYS_ON, source=RESEARCH + "2026-11-14-timed-on-call-patterns.md", harms=True),
        # Reported failing the countdown with harm (plan Decisions 35 and 41).
        TUYA_COUNTDOWN_HARMED: NotBuilt(
            reason="its maker string is reported to restart its timer at random, so it could stay on",
            source="https://github.com/Koenkk/zigbee2mqtt/issues/30493",
            harms=True,
        ),
    },
}
