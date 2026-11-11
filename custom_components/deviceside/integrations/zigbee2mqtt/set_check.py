"""Whether Zigbee2MQTT sent a call's sets: a failure Z2M logs makes the target that published it `rejected`.

Z2M reports a set it couldn't send only on bridge/logging, at error level, as
`Publish 'set' '<key>' to '<friendly name>' failed: '<error>'`, and goes on to the message's next key; it publishes
the message's state only after every key, so a key's failure line comes before that message's state publish. The
cause that matters is herdsman's Ember adapter: a groupcast goes out as one send and throws at once on BUSY (~20 ms),
while a unicast retries BUSY three times 500 ms apart before it throws (docs/integrations/zigbee2mqtt/internals.md,
Upstream defects). Without this, such a call answers `sent` for a command nothing received, as core's MQTT light
would; `docs/action-behavior.md` has a device or integration failure propagate, so the target fails.

`checked` replaces an adapter's `gather`. Each target's send runs under a watch (a ContextVar), and `publish_set`
(and turn_on_for's light.turn_on, which HA publishes as a set) calls `note` before each publish: the first publish
to an entity subscribes its state topic, and each one stamps it as unanswered. The watch listens to the bridge
cache's bridge/logging.

**The check never delays a publish.** Publishes go out as before, back to back where a sequence's timing is the
feature (stop's halts, a fade's per-light then group writes). The check is a settle after the sends, outside the
concurrency slots, so it holds none: it ends once every entity published to has a non-retained state publish since
its last publish or a failure line, else at its last publish plus `BOUND_S` (a unicast's retries take ~1.5 s), and
never past the dispatcher's deadline less a margin. Only the response waits.

Keys whose publish draws no state from Z2M run every settle to the bound: hue_move (a rate or stop), a raw `command`
(stop's stopMoveStep) and on_time (turn_on_for's timer). `brightness_move: stop` does draw state (Z2M reads the light,
or a group's first member, back), so a plain stop ends early.

Off (answering as before, with no subscription and no wait) when the bridge cache isn't live: its bridge/logging
subscription might not be either, and a groupcast's BUSY would be missed. set_attributes checks without the settle
(`settle=False`): its fade wait and reads outlast a groupcast's BUSY, and a missed unicast one shows as not_stored.

A failure counts for each target whose send published to that entity (a group's member written in its own send is
the group's). A `read` key is Reader's, which reports its own failure, so it is never counted here.

Known limits: a state publish for another reason (a device's report) can end a settle early; a failure line from
another caller's set to the same entity inside the window counts; an earlier message of a sequence could, in theory,
fail after a later one's state publish has ended the settle.
"""

import asyncio
import dataclasses
import logging
import re
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback

from . import bridge_cache
from .addressing import state_topic
from ...core.adapter import Adapter
from ...core.models import EntityResult, Status, Target
from ...core.runtime import DEADLINE

_LOGGER = logging.getLogger(__name__)

# Past the last publish to an entity: a groupcast's BUSY is logged in ~20 ms, a unicast's after herdsman's 3 × 500 ms.
BOUND_S = 2.0
# The settle ends this long before the dispatcher's deadline, so the results still reach it.
DEADLINE_MARGIN_S = 0.25
_PREFIX = "Publish 'set' '"
_STATUS = re.compile(r"status=(\w+)")
SEND_FAILED = "send_failed"  # a failure line that names no status

type Send = Callable[[Target], Awaitable[EntityResult]]


@dataclasses.dataclass(slots=True)
class _Entity:
    """An entity published to in this call."""

    name: str  # Z2M's friendly name, which its log lines and state topic use
    owners: set[str]
    unsubscribe: Callable[[], None]
    published_at: float = 0.0
    answered: bool = False
    failure: str | None = None  # the first failure line Z2M logged for it


class Watch:
    """One call's publishes, their state publishes and their failure lines."""

    def __init__(self, hass: HomeAssistant, cache: bridge_cache.BridgeCache) -> None:
        self.hass = hass
        self.closed = False
        self.entities: dict[str, _Entity] = {}
        self._changed = asyncio.Event()
        self._stop_listening = cache.listen_log(self._on_log)

    def owning(self, send: Send) -> Send:
        """send, run with its target as the owner of each publish it notes."""

        async def owned(target: Target) -> EntityResult:
            token = _CURRENT.set((self, target.reported_id))
            try:
                return await send(target)
            finally:
                _CURRENT.reset(token)

        return owned

    async def note(self, target: Target, owner: str) -> None:
        if (entity := self.entities.get(target.entity_id)) is None:
            if (light_topic := state_topic(target)) is None:
                return
            try:
                # HA's own entity subscribes to this topic, so the subscription is live at once (as state_reply).
                unsubscribe = await mqtt.async_subscribe(self.hass, light_topic, self._on_state(target.entity_id))
            except Exception as err:  # noqa: BLE001 - the publish goes out unchecked, as before
                _LOGGER.debug("Couldn't subscribe to %s, so a failed send isn't seen: %s", light_topic, err)
                return
            # Another send may have noted the entity during the subscribe (a group's member that is a target too).
            if self.closed or (entity := self.entities.get(target.entity_id)) is not None:
                unsubscribe()
                if entity is None:
                    return
            else:
                entity = self.entities[target.entity_id] = _Entity(target.device.name, set(), unsubscribe)
        entity.owners.add(owner)
        entity.published_at = self.hass.loop.time()
        entity.answered = False

    def _on_state(self, entity_id: str) -> Callable[[mqtt.ReceiveMessage], None]:
        @callback
        def received(msg: mqtt.ReceiveMessage) -> None:
            # A retained message is old state the broker resends on subscribe, not Z2M's answer.
            # Until the subscribe returns, the entity isn't noted yet, and no publish has gone out to answer.
            if not msg.retain and (entity := self.entities.get(entity_id)) is not None:
                entity.answered = True
                self._changed.set()

        return received

    @callback
    def _on_log(self, message: str) -> None:
        if not message.startswith(_PREFIX) or message[len(_PREFIX) :].startswith("read'"):
            return
        for entity in self.entities.values():
            if entity.failure is None and f"' to '{entity.name}' failed: " in message:
                entity.failure = message
                self._changed.set()

    async def settle(self) -> None:
        """Wait until each entity published to is answered or failed, or past its bound, or the deadline's cap."""
        deadline = DEADLINE.get()
        cap = None if deadline is None else deadline - DEADLINE_MARGIN_S
        while waiting := [e for e in self.entities.values() if not e.answered and e.failure is None]:
            until = max(e.published_at for e in waiting) + BOUND_S
            if cap is not None:
                until = min(until, cap)
            self._changed.clear()
            try:
                async with asyncio.timeout_at(until):
                    await self._changed.wait()
            except TimeoutError:
                return

    def close(self) -> None:
        self.closed = True
        self._stop_listening()
        for entity in self.entities.values():
            entity.unsubscribe()

    def failures(self) -> dict[str, str]:
        """Each owner's failure line: the first of the entities it published to."""
        failed: dict[str, str] = {}
        for entity in self.entities.values():
            if entity.failure is not None:
                for owner in entity.owners:
                    failed.setdefault(owner, entity.failure)
        return failed


_CURRENT: ContextVar[tuple[Watch, str] | None] = ContextVar("deviceside_z2m_set_watch", default=None)


async def note(hass: HomeAssistant, target: Target) -> None:
    """Note a set about to be published to the target, under the running call's watch; nothing outside one."""
    if (current := _CURRENT.get()) is not None and not current[0].closed:
        await current[0].note(target, current[1])


def detail(message: str) -> str:
    """The result's detail for a failure line: the status it names, lowercased (`busy`), else send_failed."""
    return status.group(1).lower() if (status := _STATUS.search(message)) else SEND_FAILED


async def checked(
    adapter: Adapter, hass: HomeAssistant, targets: list[Target], send: Send, *, settle: bool = True
) -> list[EntityResult]:
    """adapter.gather(hass, targets, send), with each target whose sets Z2M logged as failed `rejected`."""
    if (cache := bridge_cache.get(hass)) is None or not cache.replies_live:
        return await adapter.gather(hass, targets, send)
    watch = Watch(hass, cache)
    try:
        results = await adapter.gather(hass, targets, watch.owning(send))
        if settle:
            await watch.settle()
    finally:
        watch.close()
    if not (failed := watch.failures()):
        return results
    checked_results = []
    for result in results:
        if (message := failed.get(result.entity_id)) is not None and result.status is not Status.UNSUPPORTED:
            _LOGGER.warning(
                "%s on %s failed for %s: Zigbee2MQTT logged: %s",
                adapter.action,
                adapter.integration,
                result.entity_id,
                message,
            )
            result = dataclasses.replace(result, status=Status.REJECTED, detail=detail(message), clamped_to=None)
        checked_results.append(result)
    return checked_results
