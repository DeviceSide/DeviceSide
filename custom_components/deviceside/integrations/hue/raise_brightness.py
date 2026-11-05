"""Hue raise_brightness: the bridge fades brightness up to the limit, turning the light on (fade)."""

from typing import ClassVar

from .fade import HueFade, fade_scope
from ...core.scope import AdapterScope
from ...core.transition import BRIGHTNESS


class HueRaiseBrightness(HueFade):
    action: ClassVar[str] = "raise_brightness"
    scope: ClassVar[AdapterScope] = fade_scope(BRIGHTNESS, experimental=False)
