from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from types import MappingProxyType
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .fields import LACKABLE
from .models import Target

if TYPE_CHECKING:
    from .ha_watch import CallResolver


@dataclass(frozen=True, slots=True)
class DurationLimits:
    min_s: float
    max_s: float


class Level(IntEnum):
    """How well a scope item is proven, weakest first (docs/evidence.md). A call's level is the weakest among the
    in-scope items it touches."""

    # The experimental flag on one item, not yet judged ready for everyone: refused unless the Experimental features
    # option is on. A maintainer lifts it when they judge it ready (docs/evidence.md, The experimental flag).
    EXPERIMENTAL = 0
    # Reaches the same capability as a Verified item, differing only in addressing; unit tests pin the payload.
    DOCUMENTED = 10
    # A maintainer has verified the call on a real device.
    VERIFIED = 20


def verified(*items: str) -> dict[str, Level]:
    return dict.fromkeys(items, Level.VERIFIED)


def documented(*items: str) -> dict[str, Level]:
    return dict.fromkeys(items, Level.DOCUMENTED)


def experimental(*items: str) -> dict[str, Level]:
    return dict.fromkeys(items, Level.EXPERIMENTAL)


class CaveatKind(Enum):
    """A risk the adapter ships with (docs/evidence.md, Caveats); not a level."""

    # Changed, and nobody could test it before the release.
    UNTESTED_FIX = "Untested fix"
    # Nobody is fixing it.
    UNMAINTAINED = "Unmaintained"


@dataclass(frozen=True, slots=True)
class Caveat:
    """A caveat and why: an issue URL, or a reason. Set and cleared by a repo maintainer; the adapter stays live."""

    kind: CaveatKind
    reason: str


# eq=False: compared and hashed by identity, as the mappings it holds can't be hashed.
@dataclass(frozen=True, slots=True, eq=False)
class AdapterScope:
    """The entity domains, capabilities and fields an adapter is built for, each at its Level, plus its settings.

    An Experimental item is gated at runtime: the dispatcher refuses a call that touches one unless the Experimental
    features option is on. `experimental=True` flags the whole adapter the same way. An item that is not built, or
    built but not unit-tested, is left out of scope and refused. `caveat` changes no call: setup warns and the card
    says so.
    """

    experimental: bool = False
    caveat: Caveat | None = None
    domains: Mapping[str, Level] = field(default_factory=lambda: verified("light"))
    duration: DurationLimits | None = None
    # Never Documented: a field changes the call, so no sibling's proof covers it.
    fields: Mapping[str, Level] = field(default_factory=dict)
    # Fields the integration can never send; dropped before the scope check, as a field the light lacks is.
    drops: frozenset[str] = frozenset()
    # Fields the adapter takes though the light's state says it can't (a design gap between the upstream integration
    # and HA): never dropped as lacked on a light. Each must be in `fields`, whose level gates it like any field's.
    unlisted: frozenset[str] = frozenset()
    # Device-side capabilities (Shelly: RPC component names); None for an adapter with no capability axis, whose
    # capability() names none (the registry refuses a mismatch either way).
    # Proof follows the call, so each capability stands on its own evidence: a sibling's untested one is Experimental
    # unless it is Documented.
    capabilities: Mapping[str, Level] | None = None
    confirmable: bool = False
    # DeviceSide options that change what the adapter does.
    options: frozenset[str] = frozenset()
    native_groups: bool = False
    max_concurrency: int = 4
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if Level.DOCUMENTED in self.fields.values():
            raise ValueError("fields are never Documented: a field changes the call")
        self._check_unlisted()
        # Read-only copies: adapters share mappings such as Shelly's CAPABILITIES, and a frozen scope stays frozen.
        for name in ("domains", "fields", "capabilities"):
            if (items := getattr(self, name)) is not None:
                object.__setattr__(self, name, MappingProxyType(dict(items)))

    def level(self, domain: str, capability: str | None = None, fields: Collection[str] = ()) -> Level:
        """The weakest level among the in-scope items a call touches: its domain, its capability (when the scope
        lists capabilities) and the fields it carries. Domain and fields must be in scope, as supports() has checked;
        a capability outside the scope, or none (one the adapter couldn't name), counts as Experimental, so a call
        supports() let past on another ground (one with nothing to do) fails safe instead of raising."""
        levels = [self.domains[domain], *(self.fields[name] for name in fields)]
        if self.capabilities is not None:
            levels.append(self.capabilities.get(capability, Level.EXPERIMENTAL))
        return min(levels)

    def _check_unlisted(self) -> None:
        if unknown := self.unlisted - LACKABLE:
            raise ValueError(f"unlisted names fields a light's state never lacks: {sorted(unknown)}")
        if untested := self.unlisted - self.fields.keys():
            raise ValueError(f"unlisted names fields outside the scope's fields: {sorted(untested)}")
        if dropped := self.unlisted & self.drops:
            raise ValueError(f"unlisted names fields the scope drops: {sorted(dropped)}")


@dataclass(slots=True)
class IntegrationInfo:
    key: str
    title: str
    ha_domain: str
    # GitHub handles of the people who look after its package and approve changes to it; one or more, checked
    # at registration (core/registry.py). Empty only on the placeholder for an integration that failed to import.
    maintainers: tuple[str, ...]
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
