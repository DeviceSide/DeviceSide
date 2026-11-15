from dataclasses import replace

from .models import TimedRequest
from .scope import DurationLimits

# Nothing shorter than 50 ms: a relay can't switch faster, and nobody needs more than 10 Hz.
MIN_DURATION_S = 0.05


def clamp[RequestT: TimedRequest](request: RequestT, limits: DurationLimits | None) -> tuple[RequestT, float | None]:
    """Fit a request's duration to the 50 ms floor and an adapter's limits; a duration in range passes through,
    rounded to the limits' step where they have one (half up, then kept in range). The request carries the limits it
    was fitted to (TimedRequest.limits).

    clamped_to is set only when the value sent differs from the one requested: it lay outside the range, or the step
    rounded it, since that is the case a caller needs to know about (docs/action-behavior.md).
    """
    low = max(limits.min_s, MIN_DURATION_S) if limits else MIN_DURATION_S
    fitted = max(request.duration_s, low)
    if limits:
        fitted = min(fitted, limits.max_s)
        if limits.step_s:
            fitted = min(max(int(fitted / limits.step_s + 0.5) * limits.step_s, low), limits.max_s)
    clamped_to = fitted if fitted != request.duration_s else None
    return replace(request, duration_s=fitted, limits=limits), clamped_to
