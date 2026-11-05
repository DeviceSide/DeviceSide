from typing import ClassVar

from .auto import ClearAuto


class ClearAutoOff(ClearAuto):
    """Stop the device turning itself off after every turn-on."""

    key: ClassVar[str] = "clear_auto_off"


ACTION = ClearAutoOff
