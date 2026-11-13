"""Shelly raise and lower brightness: one <Component>.Set with a transition for the distance left, from the level the
device reports. Each action's adapter is a ShellyFade."""

from typing import ClassVar

from homeassistant.core import HomeAssistant

from .addressing import DIMMING_CAPABILITIES, RpcComponent, unsupported_reason
from .rpc import TRANSITION_LIMITS, get_status, set_fade
from ...core.level_fade import LevelFade
from ...core.models import Target
from ...core.scope import AdapterScope, DurationLimits, verified
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


def fade_seconds(distance: float, sweep_time: float) -> float:
    """How long a fade over `distance` percent takes at the sweep_time's speed, at least the device's shortest."""
    return round(max(distance / 100 * sweep_time, TRANSITION_LIMITS.min_s), _DURATION_DIGITS)


class ShellyFade(RpcComponent, LevelFade):
    """A GetStatus for the device's level, then one Set to the limit (or range end) with a transition for the distance
    left; the device runs the fade (core.level_fade).

    The device reports its level exactly mid-fade (rig, 8 Nov), so a move after a stop or mid-fade starts from where
    the light is, with no prediction kept, and a change made elsewhere can't leave one stale. Raising turns a light
    that is off on, fading in from the bottom; lowering passes it by, unchanged with off. Lowering to 0 is the
    device's soft off. A sweep_time outside what a full-range fade can take on the device (0.5 to 10800 s) is clamped,
    with clamped_to; a shorter fade than the device's shortest runs at that, unreported. A relay shown as a light
    lacks brightness, so the dispatcher leaves it unchanged with fields_dropped.
    """

    integration: ClassVar[str] = "shelly"
    fade_limits: ClassVar[DurationLimits] = TRANSITION_LIMITS
    min_step: ClassVar[float] = MIN_STEP

    def unaddressable(self, target: Target) -> str | None:
        return unsupported_reason(target)

    async def read(self, hass: HomeAssistant, target: Target) -> tuple[bool, float]:
        status = await get_status(target)
        lit = bool(status["output"])
        return lit, status["brightness"] if lit else 0.0

    async def fade_to(self, hass: HomeAssistant, target: Target, end: float, seconds: float) -> None:
        await set_fade(hass, target, end, seconds)

    def seconds(self, distance: float, sweep_time: float) -> float:
        return fade_seconds(distance, sweep_time)
