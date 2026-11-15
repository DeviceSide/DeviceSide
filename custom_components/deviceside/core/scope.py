from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from types import MappingProxyType
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .errors import Reason
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
    # Reaches the same capability as a Verified item, differing only in addressing, or a read a certification tests on
    # every certified device, its class keyed on a marker (docs/evidence.md, Levels); unit tests pin the payload.
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


@dataclass(frozen=True, slots=True)
class DoesntWork:
    """A class no known call works on, a device limit (docs/evidence.md, Doesn't work): what the card names, why it
    fails, and the source, an https URL (scripts/gen_compat.py checks it). The dispatcher refuses it, raising with
    the reason; the card lists it under Doesn't work.

    `harms`, which every entry states: whether the call's failure on the class is deferred and unattended, leaving it
    on or off unasked after the user stopped watching (a plug turned on that stays on), by docs/evidence.md's test,
    When today's call harms a class: the timed and auto on/off actions, never dimming, color or a read. Where an
    adapter's scope holds one such entry, a target that could still be in that class is refused too, even with
    Experimental features on (AdapterScope.refusal). Required, so no entry leaves the question unanswered by default.
    """

    what: str
    reason: str
    source: str
    harms: bool = field(kw_only=True)


@dataclass(frozen=True, slots=True)
class NotSupported:
    """A class not yet supported (docs/evidence.md, Not yet supported), declared because the adapter's call would
    harm it: a call that would work is known or plausible, but isn't built. Why the user can't have it yet, and the
    source, an https URL (scripts/gen_compat.py checks it); the dispatcher refuses it as `not_supported` with the
    reason, and the card lists it as not yet supported, as it does a class a scope leaves out.

    `harms`, required as DoesntWork's is: the adapter's call harms the class (When today's call harms a class), so
    AdapterScope.refusal refuses a target that could still be in it as class_unknown, exactly as for a DoesntWork
    entry with `harms`. It must be True, which AdapterScope checks: a class today's call would leave unharmed needs
    no entry, as leaving it out of the scope refuses it the same way, and an entry saying so would be a second home
    for that refusal.
    """

    reason: str
    source: str
    harms: bool = field(kw_only=True)


class Unplaced(str):
    """A class IntegrationInfo.capability named from partial information (the integration hasn't reported all it
    will about the device), which could still move once it has. It is that class everywhere (it equals and hashes as
    the plain string, so a scope's levels and doesnt_work read it as they would), except where an adapter's call
    harms a class (AdapterScope.harms): there AdapterScope.refusal refuses it as class_unknown, as it may be one.

    Why a flag on the class, not a class of its own or None: None is a permanent "can't class" (a Shelly entity with
    no RPC component, a classifier that raised, a group whose members can't be listed), weighed as Experimental, and
    refused as class_unknown too where the call harms a class, as it could be the harmed one; and a class of its own
    would change what every other adapter does with a device for the seconds until the integration reports it, where
    only the harmful call needs to wait.

    It is equal to its class, so a set or dict built from classes merges it with a placed one of the same class and
    may keep either: whatever holds classes for the harm check (the dispatcher's Classes) keeps each as capability()
    returned it, never deduplicated. A response leaves it out, as it does None (dispatcher._classed)."""

    __slots__ = ()

    def __repr__(self) -> str:
        return f"Unplaced({str.__repr__(self)})"


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
    # The classes the adapter serves (docs/evidence.md, Device classes), as IntegrationInfo.capability names them;
    # None for an integration that names none (the registry refuses a mismatch either way). Proof follows the call and
    # the class, so each stands on its own evidence: a sibling's untested one is Experimental unless it is Documented.
    # A class the integration names in neither this nor doesnt_work is not yet supported, and refused.
    capabilities: Mapping[str, Level] | None = None
    # Classes no known call works on, refused with why; never in capabilities. Per adapter, as one class can fail one
    # action's call and answer another's.
    doesnt_work: Mapping[str, DoesntWork] = field(default_factory=dict)
    # Not yet supported classes the adapter's call would harm, refused with why (each entry's harms is True); in neither
    # of the above. Any other not yet supported class is simply left out.
    not_supported: Mapping[str, NotSupported] = field(default_factory=dict)
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
        if both := self.doesnt_work.keys() & (self.capabilities or {}).keys():
            raise ValueError(f"doesnt_work names classes the scope serves: {sorted(both)}")
        if both := self.not_supported.keys() & ((self.capabilities or {}).keys() | self.doesnt_work.keys()):
            raise ValueError(f"not_supported names classes the scope serves or lists as doesn't work: {sorted(both)}")
        if unharmed := sorted(name for name, entry in self.not_supported.items() if not entry.harms):
            raise ValueError(
                f"not_supported entries {unharmed} don't harm: an unharmed not yet supported class needs no entry"
            )
        # Read-only copies: adapters share mappings such as Shelly's CAPABILITIES, and a frozen scope stays frozen.
        for name in ("domains", "fields", "capabilities", "doesnt_work", "not_supported"):
            if (items := getattr(self, name)) is not None:
                object.__setattr__(self, name, MappingProxyType(dict(items)))

    def level(self, domain: str, classes: Collection[str | None] = (), fields: Collection[str] = ()) -> Level:
        """The weakest level among the in-scope items a call touches: its domain, its classes (when the scope lists
        capabilities: the target's, or a native group's members') and the fields it carries. Domain and fields must
        be in scope, as supports() has checked; a class outside the scope, or None (one the integration couldn't
        name, or a group whose members it can't list), counts as Experimental, so a call let past on another ground
        fails safe instead of raising."""
        levels = [self.domains[domain], *(self.fields[name] for name in fields)]
        if self.capabilities is not None:
            levels += [self.capabilities.get(name, Level.EXPERIMENTAL) for name in classes]
        return min(levels)

    @property
    def harms(self) -> bool:
        """Whether the adapter's call harms a class it could reach: a doesnt_work or not_supported entry with harms."""
        return any(entry.harms for entry in (*self.doesnt_work.values(), *self.not_supported.values()))

    def refusal(self, classes: Collection[str | None]) -> tuple[str, str | None] | None:
        """Why the scope refuses a target of these classes (a native group's: its members'), with the reason the user
        reads, or None. Where the call harms a class (`harms`), first `class_unknown` when one is Unplaced, or None
        (the integration couldn't name it, or a group's membership is unknown), as it could be the harmed class, with
        Experimental features on or off. Then `doesnt_work` and its DoesntWork.reason when one is listed as failing
        the call, else `not_supported` when one is named but not served, with its NotSupported.reason when it has an
        entry. Elsewhere None is no refusal: the gate weighs it as Experimental, and an Unplaced class as the class it
        names."""
        if self.capabilities is None:
            return None
        if self.harms and any(name is None or isinstance(name, Unplaced) for name in classes):
            return Reason.CLASS_UNKNOWN, None
        if broken := next((self.doesnt_work[name] for name in classes if name in self.doesnt_work), None):
            return Reason.DOESNT_WORK, broken.reason
        if entry := next((self.not_supported[name] for name in classes if name in self.not_supported), None):
            return Reason.NOT_SUPPORTED, entry.reason
        if any(name is not None and name not in self.capabilities for name in classes):
            return Reason.NOT_SUPPORTED, None
        return None

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
    # Members of a native group, sync and with no I/O: for adapters without native_groups, the targets they get; for
    # one with, the members whose classes the group takes, and the targets it falls back to when a member's class is
    # refused (docs/design.md, Groups). None, as the hook or its answer, means membership is unknowable here.
    expand_group: Callable[[HomeAssistant, Target], list[Target] | None] | None = None
    # Names a target's class (docs/evidence.md, Device classes): sync and cheap, no I/O, reading only the target's
    # registry entries, config entry or the integration's data. A device no rule matches gets the default class; one
    # it places from partial information, which a later report could move, its class as Unplaced; None only for a
    # target it can't class at all. On an integration with a `harms` entry (AdapterScope.harms), a device no rule
    # matches gets the default class, never None: core refuses None there as class_unknown, as it does Unplaced. None
    # for an integration with one class, whose scopes then hold no capabilities.
    capability: Callable[[HomeAssistant, Target], str | None] | None = None
    # Every class capability() can name, so a scope's typo fails at registration and the cards name the classes an
    # adapter serves in neither its capabilities nor its doesnt_work as not yet supported.
    classes: frozenset[str] = frozenset()
    # The class capability() gives a device no rule matches, one of `classes`; the registry refuses any scope holding it
    # as Verified (docs/evidence.md, Device classes). None for an integration whose classes name every target (Shelly).
    default_class: str | None = None
    # Drops what a light or scene call from HA leaves stale (core/ha_watch.py); None holds nothing it could.
    call_resolver: CallResolver | None = None
    max_concurrency: int = 4
    available: bool = True
    unavailable_reason: str | None = None
