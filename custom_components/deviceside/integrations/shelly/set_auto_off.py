from typing import ClassVar, Literal

from .auto import ShellySetAuto


class ShellySetAutoOff(ShellySetAuto):
    action: ClassVar[str] = "set_auto_off"
    which: ClassVar[Literal["off", "on"]] = "off"
