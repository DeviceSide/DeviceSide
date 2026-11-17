"""ZHA lower_brightness: the bulb fades brightness down to the limit, or to a soft off at 0 % (fade)."""

from typing import ClassVar

from .fade import ZHARamp, ramp_scope
from ...core.fields import BRIGHTNESS_FIELD
from ...core.scope import AdapterScope


class ZHALowerBrightness(ZHARamp):
    action: ClassVar[str] = "lower_brightness"
    scope: ClassVar[AdapterScope] = ramp_scope(action, BRIGHTNESS_FIELD)
