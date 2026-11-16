"""ZHA lower_hue: the bulb cycles hue down the wheel until a stop (fade)."""

from typing import ClassVar

from . import classes
from .fade import ZHARamp, ramp_scope
from ...actions.ramp import HUE
from ...core.scope import AdapterScope


class ZHALowerHue(ZHARamp):
    action: ClassVar[str] = "lower_hue"
    scope: ClassVar[AdapterScope] = ramp_scope(HUE, classes.FADE_COLOR)
