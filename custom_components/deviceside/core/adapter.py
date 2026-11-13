import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import ClassVar

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import Unauthorized

from .errors import describe
from .models import ActionKind, EntityResult, Request, Status, Target
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
    # The action's kind, which the registry sets from the action; it decides how a failure's WARNING ends.
    kind: ActionKind = ActionKind.COMMAND

    @property
    def consequence(self) -> str:
        """How a WARNING about this adapter's failure ends: what the user is left with (docs/logging.md)."""
        if self.kind is ActionKind.QUERY:
            return "so its attributes aren't reported"
        if self.kind is ActionKind.SETTING:
            return "so the device may keep its old setting"
        return "so HA may show the old values"

    def supports(self, hass: HomeAssistant, request: RequestT, target: Target) -> str | None:
        """None if this adapter can serve the target, else a reason key. Sync and cheap: no I/O.

        The request is the one the target will get, its lacked fields and scope.drops already dropped. The default
        checks the domains, fields and capabilities in scope: a field left that nobody has tested is refused, never
        dropped. A capability is checked only when the call has something to send and capability() names one; an
        adapter refuses a target it can't name one for with its own reason, and the gate counts None as Experimental.
        """
        if target.domain not in self.scope.domains:
            return "domain_not_tested"
        if request.fields_present() - self.scope.drops - self.scope.fields.keys():
            return "fields_not_tested"
        if (
            self.scope.capabilities is not None
            and not request.nothing_to_do()
            and (capability := self.capability(hass, target)) is not None
            and capability not in self.scope.capabilities
        ):
            return "capability_not_tested"
        return None

    def capability(self, hass: HomeAssistant, target: Target) -> str | None:
        """The device-side capability the call reaches (Shelly: the RPC component), for an adapter whose scope lists
        capabilities; None otherwise, or when it can't tell. Sync and cheap: no I/O."""
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
    async def slot(self, hass: HomeAssistant) -> AsyncIterator[None]:
        """A slot under the integration's and this adapter's concurrency limits, held to the dispatcher's deadline.

        Every command to a device runs in one. Past the deadline, waiting for the slot included, it raises
        DeadlinePassed, which the caller reports as REJECTED with timeout for the targets it held; a send's own
        TimeoutError propagates as itself.
        """
        integration_limit, adapter_limit = self.limits(hass)
        budget = asyncio.timeout_at(DEADLINE.get())
        try:
            async with budget, integration_limit, adapter_limit:
                yield
        except TimeoutError as err:
            if budget.expired():
                raise DeadlinePassed from err
            raise

    async def gather(
        self, hass: HomeAssistant, targets: list[Target], send: Callable[[Target], Awaitable[EntityResult]]
    ) -> list[EntityResult]:
        """Run send() per target, each in its own slot().

        An exception from one target becomes that target's REJECTED result and does not affect the others. A target
        not done by the dispatcher's deadline is REJECTED with timeout, so a large room cut short still reports the
        lights that changed.
        """

        async def _one(target: Target) -> EntityResult:
            try:
                async with self.slot(hass):
                    return await send(target)
            except DeadlinePassed:
                _LOGGER.warning(
                    "%s on %s timed out for %s, %s", self.action, self.integration, target.entity_id, self.consequence
                )
                return self.result(target, Status.REJECTED, detail="timeout")
            except Unauthorized:
                _LOGGER.warning(
                    "%s on %s refused for %s: it needs an admin user, %s",
                    self.action,
                    self.integration,
                    target.entity_id,
                    self.consequence,
                )
                return self.result(target, Status.REJECTED, detail="admin_required")
            except Exception as err:  # noqa: BLE001 - one device's failure must not abort the room
                # describe() is repr, not str: a timeout's message is empty, and only its type says what went wrong
                _LOGGER.warning(
                    "%s on %s failed for %s: %s, %s",
                    self.action,
                    self.integration,
                    target.entity_id,
                    describe(err),
                    self.consequence,
                )
                return self.result(target, Status.REJECTED, detail="error")

        return list(await asyncio.gather(*(_one(target) for target in targets)))
