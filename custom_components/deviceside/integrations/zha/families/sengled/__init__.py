"""Sengled bulbs on ZHA: their class, and the models that drop a level written while off (internals.md, Tested
behavior)."""

from .....core.rules import Rule
from .....core.scope import Family, FamilyScope, experimental

SENGLED = "sengled"

# Models that don't store a MoveToLevel while off: the Sengled E11-G13 jumps CurrentLevel to 255 with or without the
# override and comes on at full (docs/integration-internals.md, ZHA tested behavior). Read off the registry's model,
# not the class.
DROPS_WHILE_OFF = frozenset({"E11-G13"})

RULES = (
    # The lab's E11-G13 reads `sengled`.
    Rule(SENGLED, {"manufacturer": "(?i:sengled)"}),
)

# Untested on every action but turn_on_for, whose call harms it: the integration refuses it there (refusals.py).
_UNTESTED = FamilyScope(capabilities=experimental(SENGLED))

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
    },
)
