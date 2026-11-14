"""Control4 raise_brightness: the light ramps brightness up to the limit, turning on (fade)."""

from typing import ClassVar

from .fade import Control4Fade, fade_scope
from ...core.scope import AdapterScope


class Control4RaiseBrightness(Control4Fade):
    action: ClassVar[str] = "raise_brightness"
    scope: ClassVar[AdapterScope] = fade_scope()
