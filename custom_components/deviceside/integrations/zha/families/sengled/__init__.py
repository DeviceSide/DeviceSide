"""Sengled bulbs on ZHA: their class, and the models that drop a level written while off (internals.md, Tested
behavior)."""

from ...rules import Group, Rule
from .....core.scope import Family, FamilyScope, NotSupported, experimental

SENGLED = "sengled"

# Models that don't store a MoveToLevel while off: the Sengled E11-G13 jumps CurrentLevel to 255 with or without the
# override and comes on at full (docs/integration-internals.md, ZHA tested behavior). Read off the registry's model,
# not the class.
DROPS_WHILE_OFF = frozenset({"E11-G13"})

RULES: Group = (
    # The lab's E11-G13 reads `sengled`.
    Rule(SENGLED, "manufacturer", "(?i:sengled)"),
)

_UNTESTED = FamilyScope(capabilities=experimental(SENGLED))
_INTERNALS = "https://github.com/DeviceSide/DeviceSide/blob/main/docs/integrations/zha/internals.md"
# turn_on_for's call harms it (docs/evidence.md, When today's call harms a class): a call that would work is plausible,
# but isn't built. `harms`, so core also refuses a target it can't class.
_TURN_ON_FOR = FamilyScope(
    not_supported={
        # A host-side off would serve it; it refuses 0x42 by unicast and misses it by groupcast (Tested behavior).
        SENGLED: NotSupported(
            reason="It refuses the timer, so with brightness, a color temperature or in a group it would stay on",
            source=_INTERNALS + "#tested-behavior",
            harms=True,
        ),
    }
)

FAMILY = Family(
    key="sengled",
    maintainers=(),
    classes=frozenset({SENGLED}),
    scopes={
        "get_attributes": _UNTESTED,
        "lower_brightness": _UNTESTED,
        "lower_hue": _UNTESTED,
        "lower_saturation": _UNTESTED,
        "raise_brightness": _UNTESTED,
        "raise_hue": _UNTESTED,
        "raise_saturation": _UNTESTED,
        "set_attributes": _UNTESTED,
        "stop": _UNTESTED,
        "turn_on_for": _TURN_ON_FOR,
    },
)
