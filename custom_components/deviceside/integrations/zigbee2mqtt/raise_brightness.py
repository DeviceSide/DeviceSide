"""Zigbee2MQTT raise_brightness: the bulb fades brightness up to the limit, turning the light on (fade)."""

from typing import ClassVar

from .fade import Z2MRamp, ramp_scope
from ...core.fields import BRIGHTNESS_FIELD
from ...core.scope import AdapterScope


class Z2MRaiseBrightness(Z2MRamp):
    action: ClassVar[str] = "raise_brightness"
    scope: ClassVar[AdapterScope] = ramp_scope("raise_brightness", BRIGHTNESS_FIELD)
