"""Hue raise_brightness: the bridge fades brightness up to the limit, turning the light on (fade)."""

from typing import ClassVar

from .fade import HueFade, fade_scope
from ...core.fields import BRIGHTNESS_FIELD
from ...core.scope import AdapterScope


class HueRaiseBrightness(HueFade):
    action: ClassVar[str] = "raise_brightness"
    scope: ClassVar[AdapterScope] = fade_scope(BRIGHTNESS_FIELD)
