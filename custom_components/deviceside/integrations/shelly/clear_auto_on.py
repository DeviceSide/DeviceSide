from typing import ClassVar, Literal

from .auto import ShellyClearAuto


class ShellyClearAutoOn(ShellyClearAuto):
    action: ClassVar[str] = "clear_auto_on"
    which: ClassVar[Literal["off", "on"]] = "on"
