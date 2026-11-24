"""The refusal reasons both Zigbee integrations' turn_on_for entries share, pinned once as the user reads them. Each
integration's tests/integrations/<x>/test_refusals.py asserts its entry uses the constant, not the text."""

from custom_components.deviceside.zigbee import reasons


def test_the_other_brand_reason_reads_as_it_does_to_the_user():
    assert reasons.OTHER_TIMER_REASON == (
        "Too few reports say its brand runs the timer, and some lights and most plugs turn on and "
        "never off, so it could stay on; DeviceSide's own off, which would serve it, isn't built"
    )


def test_the_switch_reason_reads_as_it_does_to_the_user():
    assert reasons.SWITCH_TIMER_REASON == (
        "Most plugs and switches ignore the timer or read it as a delayed toggle, so it could stay on, "
        "and the calls that would serve them, DeviceSide's own off or the plug's auto-off, aren't built"
    )
