"""Matter lower_saturation: the light fades saturation down to the limit at its own hue (fade)."""

from typing import ClassVar

from .fade import MatterFade, fade_scope
from ...core.scope import AdapterScope
from ...core.transition import SATURATION


class MatterLowerSaturation(MatterFade):
    action: ClassVar[str] = "lower_saturation"
    attribute: ClassVar[str] = SATURATION
    scope: ClassVar[AdapterScope] = fade_scope(attribute)
    # An off light is unchanged with off: a color fade would turn it on (plan Decision 6).
    raises_from_off: ClassVar[bool] = False
