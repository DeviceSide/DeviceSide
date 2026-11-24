"""Refusal reasons the Zigbee integrations share, for the `turn_on_for` entries whose text is the same on each. Each
integration's `refusals.py` builds its own entry from one (class, `source`, `domains`), so the entries stay the
integration's and the same device isn't explained two ways. A family's own reason is in its catalog file
(`zigbee/ikea.py`); the Tuya, Sengled and Sonoff reasons name what each integration's call does, so they aren't here.
"""

# Every other brand's lights, plugs and switches (docs/evidence.md, In Labs): no pass, and research names only some
# makers' lights as running the timer, some lights turning on and never off, and most plugs ignoring it or reading it
# as a vendor countdown. The call that would serve them, a host-side off, isn't built.
OTHER_TIMER_REASON = (
    "Too few reports say its brand runs the timer, and some lights and most plugs turn on and "
    "never off, so it could stay on; DeviceSide's own off, which would serve it, isn't built"
)

# Hue's plug and IKEA's outlets, on the switch domain alone: their bulbs keep their class's level, the plugs have no
# pass, and plugs needn't implement OnWithTimedOff. The calls that would serve them, a host-side off or the plug's
# auto-off, aren't built.
SWITCH_TIMER_REASON = (
    "Most plugs and switches ignore the timer or read it as a delayed toggle, so it could stay on, "
    "and the calls that would serve them, DeviceSide's own off or the plug's auto-off, aren't built"
)
