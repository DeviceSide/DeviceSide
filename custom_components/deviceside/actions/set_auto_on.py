from typing import ClassVar

from .auto import SetAuto


class SetAutoOn(SetAuto):
    """After every turn-off, from any source, the device turns itself back on after the duration."""

    key: ClassVar[str] = "set_auto_on"


ACTION = SetAutoOn
