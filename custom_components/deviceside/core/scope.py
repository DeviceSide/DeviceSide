from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import IntEnum
from types import MappingProxyType
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .models import Target

if TYPE_CHECKING:
    from .ha_watch import CallResolver


@dataclass(frozen=True, slots=True)
class DurationLimits:
    min_s: float
    max_s: float


class Level(IntEnum):
    """How well a scope item is proven. A target's level is the weakest among the in-scope items its call touches."""

    # Sends the same call as a Verified item, differing only in addressing, and documented identically for both.
    DOCUMENTED = 10
    # A passing test record covers it.
    VERIFIED = 30


def verified(*items: str) -> dict[str, Level]:
    return dict.fromkeys(items, Level.VERIFIED)


def documented(*items: str) -> dict[str, Level]:
    return dict.fromkeys(items, Level.DOCUMENTED)


# eq=False: compared and hashed by identity, as the mappings it holds can't be hashed.
@dataclass(frozen=True, slots=True, eq=False)
class AdapterScope:
    """The entity domains, capabilities and fields an adapter is known to work with, each at its Level, plus its
    settings. An item nobody has tested, and that is not Documented, is left out of scope and refused, not gated at
    runtime.
    """

    experimental: bool = False
    domains: Mapping[str, Level] = field(default_factory=lambda: verified("light"))
    duration: DurationLimits | None = None
    # Always Verified: a field changes the call, so it is never Documented.
    fields: Mapping[str, Level] = field(default_factory=dict)
    # Fields the integration can never send; dropped before the scope check, as a field the light lacks is.
    drops: frozenset[str] = frozenset()
    # Device-side capabilities (Shelly: RPC component names); None covers all it can address, as Verified.
    # A record proves only the capability the call reaches, so a sibling's untested one is out of scope unless
    # Documented.
    capabilities: Mapping[str, Level] | None = None
    confirmable: bool = False
    # DeviceSide options that change what the adapter does; tested on hardware with each on and off.
    options: frozenset[str] = frozenset()
    native_groups: bool = False
    max_concurrency: int = 4
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(level is not Level.VERIFIED for level in self.fields.values()):
            raise ValueError("fields are never Documented: a field changes the call")
        # Read-only copies: adapters share mappings such as Shelly's CAPABILITIES, and a frozen scope stays frozen.
        for name in ("domains", "fields", "capabilities"):
            if (items := getattr(self, name)) is not None:
                object.__setattr__(self, name, MappingProxyType(dict(items)))

    def level(self, domain: str, capability: str | None = None) -> Level:
        """The weakest level among the in-scope items a call to this domain and capability touches."""
        levels = [self.domains[domain]]
        if capability is not None and self.capabilities is not None:
            levels.append(self.capabilities[capability])
        return min(levels)


@dataclass(slots=True)
class IntegrationInfo:
    key: str
    title: str
    ha_domain: str
    # Picks this integration over a generic sibling on the same ha_domain (Z2M over plain mqtt).
    detect: Callable[[HomeAssistant, er.RegistryEntry, dr.DeviceEntry | None], bool] | None = None
    # True for an integration-native group (Hue grouped_light, a Z2M or ZHA group entity).
    is_group: Callable[[HomeAssistant, Target], bool] | None = None
    # Members of a native group, for adapters without native_groups; None means membership is unknowable here.
    expand_group: Callable[[HomeAssistant, Target], list[Target]] | None = None
    # Drops what a light or scene call from HA leaves stale (core/ha_watch.py); None holds nothing it could.
    call_resolver: CallResolver | None = None
    max_concurrency: int = 4
    available: bool = True
    unavailable_reason: str | None = None
