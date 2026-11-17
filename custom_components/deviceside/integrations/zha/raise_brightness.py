"""ZHA raise_brightness: the bulb fades brightness up to the limit, turning the light on (fade)."""

from typing import ClassVar

from .fade import ZHARamp, ramp_scope
from ...core.fields import BRIGHTNESS_FIELD
from ...core.scope import AdapterScope


class ZHARaiseBrightness(ZHARamp):
    action: ClassVar[str] = "raise_brightness"
    scope: ClassVar[AdapterScope] = ramp_scope(action, BRIGHTNESS_FIELD)
