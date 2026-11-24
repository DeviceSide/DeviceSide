"""Matter raise_brightness: the light fades brightness up to the limit, turning it on (fade)."""

from typing import ClassVar

from .fade import MatterFade, fade_scope
from ...core.fields import BRIGHTNESS_FIELD
from ...core.scope import AdapterScope


class MatterRaiseBrightness(MatterFade):
    action: ClassVar[str] = "raise_brightness"
    attribute: ClassVar[str] = BRIGHTNESS_FIELD
    scope: ClassVar[AdapterScope] = fade_scope(attribute)
