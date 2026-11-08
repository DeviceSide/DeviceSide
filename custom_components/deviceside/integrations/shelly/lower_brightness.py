"""Shelly lower_brightness: the device fades brightness down to the limit, or to off with its own soft off (fade)."""

from typing import ClassVar

from .fade import ShellyFade, fade_scope
from ...core.scope import AdapterScope


class ShellyLowerBrightness(ShellyFade):
    action: ClassVar[str] = "lower_brightness"
    scope: ClassVar[AdapterScope] = fade_scope()
