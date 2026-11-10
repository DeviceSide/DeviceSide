"""Hue's transition cache: the core one with the bridge's settle window, the reports kept from HA, and the xy path of
each saturation transition.

While a transition is live report_filter takes the light's reports of its attribute as ours. With predicted_state on,
report_filter hides those reports from HA, and so from aiohue's models; what the bridge reported is kept here instead,
to hand back to HA once nothing predicts the light.
"""

import time
from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import asynccontextmanager

from homeassistant.core import HomeAssistant

from ...core import transition
from ...core.transition import SATURATION, Transition

# How long after a move ends (or a stop) the bridge's report still can't be trusted.
API_SETTLE_SECONDS = 15
# The dimmest step a Hue light makes (1/254), in percent; also the smallest saturation move worth sending.
MIN_BRIGHTNESS_STEP = 0.4

type XY = tuple[float, float]


class HueTransitionCache(transition.TransitionCache):
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        super().__init__(API_SETTLE_SECONDS, clock)
        # The bridge's last report of a value HA was not shown, by resource and report key (attributes.REPORT_KEYS).
        self._hidden: dict[str, dict[str, float | bool]] = {}
        # Each light's saturation transition and the straight xy line it runs, start to end.
        self._paths: dict[str, tuple[transition.Transition, XY, XY]] = {}

    def hidden(self, resource_id: str, values: dict[str, float | bool]) -> None:
        """The bridge reported these values and HA (so aiohue) was not shown them."""
        self._hidden.setdefault(resource_id, {}).update(values)

    def shown(self, resource_id: str, keys: Iterable[str]) -> None:
        """A report of these keys reached aiohue, which holds the bridge's values for them again."""
        if (hidden := self._hidden.get(resource_id)) is not None:
            for key in keys:
                hidden.pop(key, None)

    def release(self, resource_id: str) -> dict[str, float | bool]:
        """The bridge's values aiohue was not shown, now to be shown, so no longer kept here."""
        return self._hidden.pop(resource_id, {})

    @asynccontextmanager
    async def recording(self, keys: Iterable[tuple[str, str]]) -> AsyncIterator[dict[tuple[str, str], Transition]]:
        """The core recording, with each saturation key's xy path put back too on a refusal or a cancel, where it is
        still the path of the transition this block recorded."""
        keys = list(keys)
        before = {light_id: self._paths.get(light_id) for light_id, attribute in keys if attribute == SATURATION}
        recorded: dict[tuple[str, str], Transition] = {}
        try:
            async with super().recording(keys) as recorded:
                yield recorded
        except BaseException:
            for light_id, path in before.items():
                if (mine := recorded.get((light_id, SATURATION))) is None or (
                    (current := self._paths.get(light_id)) is not None and current[0] is not mine
                ):
                    continue
                if path is None:
                    self._paths.pop(light_id, None)
                else:
                    self._paths[light_id] = path
            raise

    def path(self, light_id: str, recorded: transition.Transition, start: XY, end: XY) -> None:
        """The xy line a saturation transition just recorded runs along; a stop's is its halt, start and end."""
        self._paths[light_id] = (recorded, start, end)

    def xy(self, light_id: str, reported: XY) -> XY:
        """The light's predicted xy while its saturation transition is live, else the reported one.

        The bridge reports an xy fade's end at once and nothing after. A path belongs to one transition: once that is
        forgotten or expired, the reported xy stands, and the path is dropped here rather than in forget().
        """
        if (live := self.live(light_id, SATURATION)) is None:
            self._paths.pop(light_id, None)
            return reported
        if (path := self._paths.get(light_id)) is None or path[0] is not live:
            return reported
        _, (x0, y0), (x1, y1) = path
        fraction = min((self.clock() - live.started_at) / live.duration, 1.0) if live.duration > 0 else 1.0
        return x0 + (x1 - x0) * fraction, y0 + (y1 - y0) * fraction


def transition_cache(hass: HomeAssistant) -> HueTransitionCache:
    return transition.transition_cache(hass, "hue", HueTransitionCache)
