from typing import ClassVar, Literal

from .auto import ShellyClearAuto


class ShellyClearAutoOff(ShellyClearAuto):
    action: ClassVar[str] = "clear_auto_off"
    which: ClassVar[Literal["off", "on"]] = "off"
