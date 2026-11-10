"""Shelly raise and lower brightness: one <Component>.Set with a transition for the distance left, from the level the
device reports. Each action's adapter is a ShellyFade."""

from typing import ClassVar

from homeassistant.core import HomeAssistant

from .addressing import DIMMING_CAPABILITIES, RpcComponent, unsupported_reason
from .rpc import TRANSITION_LIMITS, get_status, set_fade
from ...actions.ramp import RampRequest
from ...core.adapter import Adapter
from ...core.models import EntityResult, Status, Target
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


def fade_seconds(distance: float, sweep_time: float) -> float:
    """How long a fade over `distance` percent takes at the sweep_time's speed, at least the device's shortest."""
    return round(max(distance / 100 * sweep_time, TRANSITION_LIMITS.min_s), _DURATION_DIGITS)


class ShellyFade(RpcComponent, Adapter[RampRequest]):
    """A GetStatus for the device's level, then one Set to the limit (or range end) with a transition for the distance
    left; the device runs the fade.

    The device reports its level exactly mid-fade (rig, 8 Nov), so a move after a stop or mid-fade starts from where
    the light is, with no prediction kept, and a change made elsewhere can't leave one stale. Raising turns a light
    that is off on, fading in from the bottom; lowering passes it by, unchanged with off. Lowering to 0 is the
    device's soft off. A sweep_time outside what a full-range fade can take on the device (0.5 to 10800 s) is clamped,
    with clamped_to; a shorter fade than the device's shortest runs at that, unreported. A relay shown as a light
    lacks brightness, so the dispatcher leaves it unchanged with fields_dropped.
    """

    integration: ClassVar[str] = "shelly"

    def supports(self, hass: HomeAssistant, request: RampRequest, target: Target) -> str | None:
        if (reason := super().supports(hass, request, target)) is not None:
            return reason
        # Nothing left to send: the dispatcher reports it unchanged with fields_dropped, whatever the component.
        return None if request.nothing_to_do() else unsupported_reason(target, self.scope.capabilities)

    async def execute(self, hass: HomeAssistant, request: RampRequest, targets: list[Target]) -> list[EntityResult]:
        sweep_time = min(max(request.sweep_time, TRANSITION_LIMITS.min_s), TRANSITION_LIMITS.max_s)
        clamped_to = sweep_time if sweep_time != request.sweep_time else None

        async def move(target: Target) -> EntityResult:
            status = await get_status(target)
            lit = bool(status["output"])
            if not request.up and not lit:
                return self.result(target, Status.UNCHANGED, detail="off")
            current = status["brightness"] if lit else 0.0
            end = request.end()
            if (end - current if request.up else current - end) < MIN_STEP:
                return self.result(target, Status.UNCHANGED, detail="at_limit")
            await set_fade(hass, target, end, fade_seconds(abs(end - current), sweep_time))
            return self.result(target, Status.SENT, clamped_to=clamped_to)

        return await self.gather(hass, targets, move)
