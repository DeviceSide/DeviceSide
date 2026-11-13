"""Control4 lower_brightness: the light ramps brightness down to the limit, or to off (fade)."""

from typing import ClassVar

from .fade import Control4Fade, fade_scope
from ...core.scope import AdapterScope


class Control4LowerBrightness(Control4Fade):
    action: ClassVar[str] = "lower_brightness"
    scope: ClassVar[AdapterScope] = fade_scope()
