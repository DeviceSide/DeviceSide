"""Matter raise_hue: the light cycles hue up the wheel until a stop (fade)."""

from typing import ClassVar

from .fade import MatterHueMove, fade_scope
from ...actions.ramp import HUE
from ...core.scope import AdapterScope


class MatterRaiseHue(MatterHueMove):
    action: ClassVar[str] = "raise_hue"
    scope: ClassVar[AdapterScope] = fade_scope(HUE)
