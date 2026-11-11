from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field
from enum import IntEnum
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
    """How well a scope item is proven, weakest first. A call's level is the weakest among the in-scope items it
    touches."""

    # Built and unit-tested, with no proof on hardware: refused unless the Experimental features option is on.
    EXPERIMENTAL = 0
    # Sends the same call as a Verified or Reported item, differing only in addressing, documented identically for both.
    DOCUMENTED = 10
    # An accepted user report says it works; unit tests pin the call.
    REPORTED = 20
    # A passing test record covers it.
    VERIFIED = 30


def verified(*items: str) -> dict[str, Level]:
    return dict.fromkeys(items, Level.VERIFIED)


def reported(*items: str) -> dict[str, Level]:
    return dict.fromkeys(items, Level.REPORTED)


def documented(*items: str) -> dict[str, Level]:
    return dict.fromkeys(items, Level.DOCUMENTED)


def experimental(*items: str) -> dict[str, Level]:
    return dict.fromkeys(items, Level.EXPERIMENTAL)


# eq=False: compared and hashed by identity, as the mappings it holds can't be hashed.
@dataclass(frozen=True, slots=True, eq=False)
class AdapterScope:
    """The entity domains, capabilities and fields an adapter is built for, each at its Level, plus its settings.

    An Experimental item is gated at runtime: the dispatcher refuses a call that touches one unless the Experimental
    features option is on. An item that is not built, or built but not unit-tested, is left out of scope and refused.
    `experimental=True` is the adapter-level flag: it keeps a behavior change to proven code out of a stable release.
    `unmaintained` marks an adapter no one is fixing, and `stale_tests` one that ships changed since its last retest:
    either way it stays live, setup warns and its card says so. None of the three changes a call, so the records check
    ignores them (scripts/check_release.py).
    """

    experimental: bool = False
    # Why no one is fixing it: an issue URL, or a reason. Set by the project owner's call; cleared on a fix or adoption.
    unmaintained: str | None = None
    # Why it ships untested: an issue URL (the call for testers), or a reason. Set by hand on an adapter with no fresh
    # retest at the cut (check_release.py --release); cleared in the PR that adds one.
    stale_tests: str | None = None
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
    # capability() names none (the registry refuses one that does).
    # A record proves only the capability the call reaches, so a sibling's untested one is out of scope unless
    # Documented.
    capabilities: Mapping[str, Level] | None = None
    # Each Documented domain or capability → the Verified or Reported item in the same mapping whose call it rides.
    # Required: a Documented item stands only while its sibling does, so a sibling falling below Reported fails here.
    siblings: Mapping[str, str] = field(default_factory=dict)
    confirmable: bool = False
    # DeviceSide options that change what the adapter does; tested on hardware with each on and off.
    options: frozenset[str] = frozenset()
    native_groups: bool = False
    max_concurrency: int = 4
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if Level.DOCUMENTED in self.fields.values():
            raise ValueError("fields are never Documented: a field changes the call")
        self._check_unlisted()
        self._check_siblings()
        # Read-only copies: adapters share mappings such as Shelly's CAPABILITIES, and a frozen scope stays frozen.
        for name in ("domains", "fields", "capabilities", "siblings"):
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

    def proof(self, item: str) -> Level:
        """The level of the proof behind a domain or capability: its own, or its sibling's when Documented. One outside
        the scope counts as Experimental, as in level()."""
        items = self.domains if item in self.domains else self.capabilities or {}
        level = items.get(item, Level.EXPERIMENTAL)
        return items[self.siblings[item]] if level is Level.DOCUMENTED else level

    def _check_unlisted(self) -> None:
        if unknown := self.unlisted - LACKABLE:
            raise ValueError(f"unlisted names fields a light's state never lacks: {sorted(unknown)}")
        if untested := self.unlisted - self.fields.keys():
            raise ValueError(f"unlisted names fields outside the scope's fields: {sorted(untested)}")
        if dropped := self.unlisted & self.drops:
            raise ValueError(f"unlisted names fields the scope drops: {sorted(dropped)}")

    def _check_siblings(self) -> None:
        if shared := set(self.domains) & set(self.capabilities or {}):
            raise ValueError(f"{sorted(shared)} are both a domain and a capability; siblings can't tell them apart")
        for name in ("domains", "capabilities"):
            items = getattr(self, name) or {}
            for item, level in items.items():
                if level is not Level.DOCUMENTED:
                    continue
                if (sibling := self.siblings.get(item)) is None:
                    raise ValueError(f"Documented {item} names no sibling whose call it rides")
                if items.get(sibling, Level.EXPERIMENTAL) < Level.REPORTED:
                    raise ValueError(f"Documented {item} rides {sibling}, which is neither Verified nor Reported")
        documented = {
            item
            for items in (self.domains, self.capabilities or {})
            for item, lv in items.items()
            if lv is Level.DOCUMENTED
        }
        if stray := set(self.siblings) - documented:
            raise ValueError(f"siblings names items that are not Documented: {sorted(stray)}")


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
