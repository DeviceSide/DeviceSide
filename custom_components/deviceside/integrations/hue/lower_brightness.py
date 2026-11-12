"""Hue lower_brightness: the bridge fades brightness down to the limit, or soft off at 0 % (fade)."""

from typing import ClassVar

from .fade import HueFade, fade_scope
from ...core.scope import AdapterScope
from ...core.transition import BRIGHTNESS


class HueLowerBrightness(HueFade):
    action: ClassVar[str] = "lower_brightness"
    scope: ClassVar[AdapterScope] = fade_scope(BRIGHTNESS)
