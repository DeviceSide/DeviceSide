"""Matter lower_brightness: the light fades brightness down to the limit; to 0, a soft off that puts its level back
(fade)."""

from typing import ClassVar

from .fade import MatterFade, fade_scope
from ...core.fields import BRIGHTNESS_FIELD
from ...core.scope import AdapterScope


class MatterLowerBrightness(MatterFade):
    action: ClassVar[str] = "lower_brightness"
    attribute: ClassVar[str] = BRIGHTNESS_FIELD
    scope: ClassVar[AdapterScope] = fade_scope(attribute)
