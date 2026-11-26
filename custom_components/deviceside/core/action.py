from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

import probatio
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .models import ActionKind, EntityResult, Request

if TYPE_CHECKING:
    from .dispatcher import Dispatcher


async def _nothing() -> list[EntityResult]:
    return []


@dataclass(frozen=True, slots=True)
class Routed:
    """The entities an action routes itself, once planned (Action.route): `results`, those known before anything is
    sent (a skip, a refusal), and `run`, which sends the rest and gives their results."""

    results: list[EntityResult] = field(default_factory=list)
    run: Callable[[], Awaitable[list[EntityResult]]] = _nothing


@dataclass(frozen=True, slots=True)
class Ride:
    """An action that serves some targets through another's adapters (Action.route): that action's key, and the
    targets it serves beyond its own adapters', as a domain on an HA integration. Generators derive its cells from
    the ridden action's."""

    action: str
    domain: str
    integration: str


class Action[RequestT: Request](ABC):
    """One action. Subclasses are classes, never instantiated: a module exports ACTION = <the class>."""

    key: ClassVar[str]
    kind: ClassVar[ActionKind]
    # Whether the call's failure harms (docs/evidence.md, When today's call harms a class): deferred and unattended,
    # leaving a device on or off unasked after the user stopped watching. The timed and auto on/off actions alone.
    failure_harms: ClassVar[bool] = False
    domains: ClassVar[frozenset[str]]
    supports_response: ClassVar[SupportsResponse] = SupportsResponse.OPTIONAL
    fields: ClassVar[dict[probatio.Marker, Any]] = {}
    # The action whose adapters serve the targets it routes itself (route), and which; None for one with no route.
    rides: ClassVar[Ride | None] = None

    @classmethod
    def schema(cls):
        return cv.make_entity_service_schema(cls.fields)

    @classmethod
    @abstractmethod
    def parse(cls, hass: HomeAssistant, call: ServiceCall) -> RequestT:
        """Build the request from validated call data; raise ServiceValidationError on input the schema can't catch."""

    @classmethod
    def claims(cls, hass: HomeAssistant, entity_id: str) -> bool:
        """Whether the action routes this entity itself (route), so the dispatcher doesn't resolve it. None by
        default."""
        return False

    @classmethod
    def route(cls, hass: HomeAssistant, request: RequestT, claimed: dict[str, bool], dispatcher: Dispatcher) -> Routed:
        """Plan the entities claimed (each entity_id to whether the caller named it), sending nothing: a named one
        that can never take the action raises here, before anything is sent. The dispatcher sends the rest by
        Routed.run, beside its own targets' runs."""
        return Routed()
