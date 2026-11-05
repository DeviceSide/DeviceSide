from typing import ClassVar

from .auto import ClearAuto


class ClearAutoOn(ClearAuto):
    """Stop the device turning itself back on after every turn-off."""

    key: ClassVar[str] = "clear_auto_on"


ACTION = ClearAutoOn
