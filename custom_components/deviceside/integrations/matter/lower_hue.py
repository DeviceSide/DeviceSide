"""Matter lower_hue: the light cycles hue down the wheel until a stop (fade)."""

from typing import ClassVar

from .fade import MatterHueMove, fade_scope
from ...actions.ramp import HUE
from ...core.scope import AdapterScope


class MatterLowerHue(MatterHueMove):
    action: ClassVar[str] = "lower_hue"
    scope: ClassVar[AdapterScope] = fade_scope(HUE)
