from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

import probatio
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .models import ActionKind, EntityResult, Request, Target

if TYPE_CHECKING:
    from .dispatcher import Dispatcher


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

    @classmethod
    def schema(cls):
        return cv.make_entity_service_schema(cls.fields)

    @classmethod
    @abstractmethod
    def parse(cls, hass: HomeAssistant, call: ServiceCall) -> RequestT:
        """Build the request from validated call data; raise ServiceValidationError on input the schema can't catch."""

    @classmethod
    async def run(
        cls, hass: HomeAssistant, request: RequestT, targets: list[Target], dispatcher: Dispatcher
    ) -> list[EntityResult]:
        """Run this action's adapters; a action that routes targets elsewhere overrides this."""
        return await dispatcher.run_adapters(cls.key, request, targets)
