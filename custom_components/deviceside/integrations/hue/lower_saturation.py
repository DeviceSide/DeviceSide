"""Hue lower_saturation: the bridge fades the light's xy toward white, to the limit saturation at its hue (fade)."""

from typing import ClassVar

from .fade import HueFade, fade_scope
from ...core.scope import AdapterScope
from ...core.transition import SATURATION


class HueLowerSaturation(HueFade):
    action: ClassVar[str] = "lower_saturation"
    scope: ClassVar[AdapterScope] = fade_scope(SATURATION, experimental=False)
