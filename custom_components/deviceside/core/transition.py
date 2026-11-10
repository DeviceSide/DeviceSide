"""What a light is doing mid-move, which its integration doesn't report.

While a transition runs, an integration may report the end value at once, and after a stop mid-flight report where the
light halted late or not at all. Each move and stop is recorded here so the next move, stop or read starts from the
value the light is really at, which is what makes a hold, release, hold sequence continue smoothly.

A transition is recorded just before its write, as the integration may report before the write returns. Each
integration keeps its own cache, with its own settle window: how long after a move ends (or a stop) its report still
can't be trusted.
"""

import time
from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from homeassistant.core import HomeAssistant

from .models import Target
from .runtime import get_runtime

# What the recording() block running in this task has recorded so far, by (resource_id, attribute).
_RECORDED: ContextVar[dict[tuple[str, str], Transition] | None] = ContextVar("transition_recorded", default=None)

BRIGHTNESS = "brightness"  # in percent
SATURATION = "saturation"  # in percent


@dataclass(frozen=True, slots=True)
class Transition:
    start: float
    target: float
    duration: float
    started_at: float

    def value(self, now: float) -> float:
        if self.duration <= 0:
            return self.target
        return self.start + (self.target - self.start) * min((now - self.started_at) / self.duration, 1.0)


class TransitionCache:
    """Transitions keyed by (resource_id, attribute); a stop is a transition of zero duration at the halt value.

    An entry is live for its duration plus settle_seconds. Record a transition inside recording(), so a write the
    integration refuses leaves the prediction it had.
    """

    def __init__(self, settle_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.settle_seconds = settle_seconds
        self.clock = clock
        self._transitions: dict[tuple[str, str], Transition] = {}

    def value(self, resource_id: str, attribute: str, reported: float) -> float:
        """The predicted value inside the guard window, else the reported one."""
        if (transition := self.live(resource_id, attribute)) is None:
            return reported
        return transition.value(self.clock())

    def tracks(self, resource_id: str, attribute: str) -> bool:
        """Whether a move or stop on this resource is still inside its guard window."""
        return self.live(resource_id, attribute) is not None

    def running(self, resource_id: str, attribute: str) -> Transition | None:
        """The move still under way on this resource, if any; a stop or a finished move is not one."""
        if (transition := self.live(resource_id, attribute)) is None:
            return None
        return transition if self.clock() < transition.started_at + transition.duration else None

    def halted(self, resource_id: str, attribute: str) -> bool:
        """Whether a stop on this resource is still inside its guard window."""
        return (transition := self.live(resource_id, attribute)) is not None and transition.duration == 0

    def attributes(self, resource_id: str) -> list[str]:
        """The attributes of the resource a move or stop is still inside its guard window for."""
        keys = [key for key in self._transitions if key[0] == resource_id]
        return [attribute for rid, attribute in keys if self.live(rid, attribute)]

    def follows(self, resource_id: str) -> bool:
        """Whether a move or stop on the resource is still inside its guard window."""
        return bool(self.attributes(resource_id))

    def resource_ids(self) -> set[str]:
        """The resources a move or stop is still inside its guard window for."""
        return {rid for rid, attribute in list(self._transitions) if self.live(rid, attribute)}

    def forget(self, resource_id: str, attribute: str | None = None) -> dict[tuple[str, str], Transition]:
        """A real change made elsewhere: drop the resource's predictions (only the attribute's, if given), returned for
        restore."""
        keys = [key for key in self._transitions if key[0] == resource_id and attribute in (None, key[1])]
        return {key: self._transitions.pop(key) for key in keys}

    def clear(self) -> None:
        """A real change made elsewhere to every resource: drop every prediction."""
        self._transitions.clear()

    def restore(self, transitions: dict[tuple[str, str], Transition]) -> None:
        """Put back what forget dropped, for a write the integration refused."""
        self._transitions.update(transitions)

    @asynccontextmanager
    async def recording(self, keys: Iterable[tuple[str, str]]) -> AsyncIterator[dict[tuple[str, str], Transition]]:
        """Around a write and the transitions it makes, recorded first: the integration may report before the write
        returns. Yields what this block records. A refusal puts back what each (resource_id, attribute) held before,
        but only where the entry is still the one this block recorded: a move that overlapped it owns the key now."""
        before = {key: self._transitions.get(key) for key in keys}
        recorded: dict[tuple[str, str], Transition] = {}
        token = _RECORDED.set(recorded)
        try:
            yield recorded
        except Exception:
            for key, transition in before.items():
                if key not in recorded or self._transitions.get(key) is not recorded[key]:
                    continue
                if transition is None:
                    self._transitions.pop(key, None)
                else:
                    self._transitions[key] = transition
            raise
        finally:
            _RECORDED.reset(token)

    def live(self, resource_id: str, attribute: str) -> Transition | None:
        """The entry inside its guard window, pruning it once expired."""
        key = (resource_id, attribute)
        if (transition := self._transitions.get(key)) is None:
            return None
        if self.clock() - transition.started_at > transition.duration + self.settle_seconds:
            del self._transitions[key]
            return None
        return transition

    def moving(
        self,
        resource_id: str,
        attribute: str,
        start: float,
        target: float,
        duration: float,
        started_at: float | None = None,
    ) -> Transition:
        """Record before the write is sent, as the device starts the fade once it has it; started_at re-records one
        already running."""
        transition = Transition(start, target, duration, self.clock() if started_at is None else started_at)
        self._transitions[(resource_id, attribute)] = transition
        if (recorded := _RECORDED.get()) is not None:
            recorded[(resource_id, attribute)] = transition
        return transition

    def stopped(self, resource_id: str, attribute: str, value: float) -> Transition:
        return self.moving(resource_id, attribute, value, value, 0.0)


def transition_cache[C: TransitionCache](hass: HomeAssistant, integration: str, make: Callable[[], C]) -> C:
    """The integration's cache, made on first use."""
    state = get_runtime(hass).integration_state
    key = f"{integration}_transitions"
    if (cache := state.get(key)) is None:
        cache = state[key] = make()
    return cache


def reported_brightness(light: Target) -> float:
    """HA's brightness in percent, 0 while off: a move from off starts at the bottom."""
    brightness = light.state.attributes.get("brightness") if light.state and light.state.state == "on" else None
    return brightness / 255 * 100 if brightness is not None else 0.0


def light_brightness(cache: TransitionCache, light: Target) -> float:
    return cache.value(light.entity_id, BRIGHTNESS, reported_brightness(light))


def lit_where[L](
    cache: TransitionCache, lights: list[L], key: Callable[[L], str], is_on: Callable[[L], bool]
) -> list[L]:
    """The lights that are on, or predicted above 0 %: a soft off may report off before its fade has run. key names
    the light's cache entry; an integration's own light type passes how it reads those."""
    return [light for light in lights if is_on(light) or cache.value(key(light), BRIGHTNESS, 0.0) > 0]


def lit(cache: TransitionCache, lights: list[Target]) -> list[Target]:
    return lit_where(
        cache, lights, lambda light: light.entity_id, lambda light: bool(light.state and light.state.state == "on")
    )


def hs_color(light: Target) -> tuple[float, float] | None:
    return light.state.attributes.get("hs_color") if light.state else None
