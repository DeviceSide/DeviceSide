"""Shelly raise and lower brightness: one <Component>.Set with a transition for the distance left, from the level the
device reports. Each action's adapter is a ShellyFade."""

from typing import ClassVar

from homeassistant.core import HomeAssistant

from .addressing import DIMMING_CAPABILITIES, RpcComponent, unsupported_reason
from .rpc import TRANSITION_LIMITS, get_status, set_fade
from ...core.level_fade import LevelFade
from ...core.models import Target
from ...core.scope import AdapterScope, verified
from ...core.transition import BRIGHTNESS

# The device keeps brightness in whole percent.
MIN_STEP = 1.0
# The device keeps a transition to 0.01 s.
_DURATION_DIGITS = 2


def fade_scope() -> AdapterScope:
    return AdapterScope(
        domains=verified("light"),
        fields=verified(BRIGHTNESS),
        capabilities=DIMMING_CAPABILITIES,
    )


class ShellyFade(RpcComponent, LevelFade):
    """core.level_fade's read and set: a GetStatus for the level, then one Set with a transition for the distance left.

    The device reports its level exactly mid-fade (rig, 8 Nov), which is what LevelFade relies on. Lowering to 0 is
    the device's soft off. A full-range fade takes 0.5 to 10800 s (TRANSITION_LIMITS). A relay shown as a light lacks
    brightness, so the dispatcher leaves it unchanged with fields_dropped.
    """

    integration: ClassVar[str] = "shelly"
    fade_limits = TRANSITION_LIMITS
    min_step: ClassVar[float] = MIN_STEP

    def unaddressable(self, target: Target) -> str | None:
        return unsupported_reason(target)

    async def read(self, hass: HomeAssistant, target: Target) -> tuple[bool, float]:
        status = await get_status(target)
        return bool(status["output"]), status["brightness"]

    async def fade_to(self, hass: HomeAssistant, target: Target, end: float, seconds: float) -> None:
        await set_fade(hass, target, end, seconds)

    def seconds(self, distance: float, sweep_time: float) -> float:
        return round(super().seconds(distance, sweep_time), _DURATION_DIGITS)
