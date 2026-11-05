"""Hue raise_saturation: the bridge fades the light's xy toward its hue at the limit saturation (fade)."""

from typing import ClassVar

from .fade import HueFade, fade_scope
from ...core.scope import AdapterScope
from ...core.transition import SATURATION


class HueRaiseSaturation(HueFade):
    action: ClassVar[str] = "raise_saturation"
    scope: ClassVar[AdapterScope] = fade_scope(SATURATION, experimental=False)
