"""Shelly raise_brightness: the device fades brightness up to the limit, turning the light on (fade)."""

from typing import ClassVar

from .fade import ShellyFade, fade_scope
from ...core.scope import AdapterScope


class ShellyRaiseBrightness(ShellyFade):
    action: ClassVar[str] = "raise_brightness"
    scope: ClassVar[AdapterScope] = fade_scope()
