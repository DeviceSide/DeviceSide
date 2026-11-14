import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager, nullcontext
from typing import ClassVar

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import Unauthorized

from .models import EntityResult, Request, Status, Target
from .runtime import DEADLINE, get_runtime
from .scope import AdapterScope

_LOGGER = logging.getLogger(__name__)


class DeadlinePassed(Exception):
    """The run's deadline passed before a slot's work was done, waiting for the slot included."""


class Adapter[RequestT: Request](ABC):
    """One action on one integration. Instantiated once per registry."""

    action: ClassVar[str]
    integration: ClassVar[str]
    scope: ClassVar[AdapterScope]

    def supports(self, hass: HomeAssistant, request: RequestT, target: Target) -> str | None:
        """None if this adapter can serve the target, else a reason key. Sync and cheap: no I/O.

        The request is the one the target will get, its lacked fields and scope.drops already dropped. The default
        checks the domains and fields in scope: a field left that nobody has tested is refused, never dropped. The
        dispatcher checks the target's class after this, so an adapter's own reason wins.
        """
        if target.domain not in self.scope.domains:
            return "domain_not_tested"
        if request.fields_present() - self.scope.drops - self.scope.fields.keys():
            return "fields_not_tested"
        return None

    @abstractmethod
    async def execute(self, hass: HomeAssistant, request: RequestT, targets: list[Target]) -> list[EntityResult]:
        """Send the command to every target at once, so an adapter can batch or address a native group."""

    def result(self, target: Target, status: Status, **kwargs) -> EntityResult:
        """Build every result here: it keys on target.reported_id, which the dispatcher matches results by."""
        return EntityResult(target.reported_id, status, integration=self.integration, **kwargs)

    def limits(self, hass: HomeAssistant) -> tuple[asyncio.Semaphore, asyncio.Semaphore]:
        """The integration's and this adapter's concurrency limits, which every command to a device runs under."""
        runtime = get_runtime(hass)
        integration_info = runtime.registry.integrations[self.integration]
        return (
            runtime.semaphore(f"integration:{self.integration}", integration_info.max_concurrency),
            runtime.semaphore(f"adapter:{self.action}:{self.integration}", self.scope.max_concurrency),
        )

    @asynccontextmanager
    async def slot(self, hass: HomeAssistant, hold: AbstractAsyncContextManager | None = None) -> AsyncIterator[None]:
        """A slot under the integration's and this adapter's concurrency limits, held to the dispatcher's deadline.

        Every command to a device runs in one. Past the deadline, waiting for the slot included, it raises
        DeadlinePassed, which the caller reports as REJECTED with timeout for the targets it held; a send's own
        TimeoutError propagates as itself.

        `hold`, a per-device lock, is taken under the same deadline but before the limits, so a call waiting on its
        device holds no slot another device's call could use. A section under a hold never takes a slot itself: at
        the cap, it would wait on itself until the deadline.
        """
        integration_limit, adapter_limit = self.limits(hass)
        budget = asyncio.timeout_at(DEADLINE.get())
        try:
            async with budget, hold or nullcontext(), integration_limit, adapter_limit:
                yield
        except TimeoutError as err:
            if budget.expired():
                raise DeadlinePassed from err
            raise

    async def gather(
        self,
        hass: HomeAssistant,
        targets: list[Target],
        send: Callable[[Target], Awaitable[EntityResult]],
        hold: Callable[[Target], AbstractAsyncContextManager] | None = None,
    ) -> list[EntityResult]:
        """Run send() per target, each in its own slot(), under hold(target) when given (see slot()).

        An exception from one target becomes that target's REJECTED result and does not affect the others. A target
        not done by the dispatcher's deadline is REJECTED with timeout, so a large room cut short still reports the
        lights that changed.
        """

        async def _one(target: Target) -> EntityResult:
            try:
                async with self.slot(hass, hold(target) if hold else None):
                    return await send(target)
            except DeadlinePassed:
                _LOGGER.warning("%s on %s timed out for %s", self.action, self.integration, target.entity_id)
                return self.result(target, Status.REJECTED, detail="timeout")
            except Unauthorized:
                _LOGGER.warning("%s on %s: %s needs an admin user", self.action, self.integration, target.entity_id)
                return self.result(target, Status.REJECTED, detail="admin_required")
            except Exception as err:  # noqa: BLE001 - one device's failure must not abort the room
                # repr, not str: a timeout's message is empty, and only its type says what went wrong
                _LOGGER.warning("%s on %s failed for %s: %r", self.action, self.integration, target.entity_id, err)
                return self.result(target, Status.REJECTED, detail="error")

        return list(await asyncio.gather(*(_one(target) for target in targets)))
