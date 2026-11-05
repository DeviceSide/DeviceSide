from typing import ClassVar

from .auto import SetAuto


class SetAutoOff(SetAuto):
    """After every turn-on, from any source, the device turns itself off after the duration."""

    key: ClassVar[str] = "set_auto_off"


ACTION = SetAutoOff
