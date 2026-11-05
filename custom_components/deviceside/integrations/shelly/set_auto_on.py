from typing import ClassVar, Literal

from .auto import ShellySetAuto


class ShellySetAutoOn(ShellySetAuto):
    action: ClassVar[str] = "set_auto_on"
    which: ClassVar[Literal["off", "on"]] = "on"
