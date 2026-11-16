from collections.abc import Awaitable, Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .errors import Reason
from .fields import LACKABLE
from .models import EntityResult, Request, Target

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .adapter import Adapter
    from .ha_watch import CallResolver


@dataclass(frozen=True, slots=True)
class DurationLimits:
    """The durations a call can carry, in seconds (core/duration.py fits a request to them). `step_s` is the call's
    resolution where it is coarser than the request's (whole seconds: 1), which a duration is rounded to; None leaves
    it as asked."""

    min_s: float
    max_s: float
    step_s: float | None = None


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


@dataclass(frozen=True, slots=True)
class OnDomains:
    """A class's level on some of the adapter's domains alone (docs/evidence.md, Device classes): on any other its
    class has no entry, so counts as Experimental, as a class outside the scope does. A record on the class in one
    domain proves nothing about it in another: a Hue bulb's `turn_on_for` isn't a Hue plug's."""

    level: Level
    domains: frozenset[str]


type ClassLevel = Level | OnDomains


def _levels(items: tuple[str, ...], level: Level, domains: Collection[str] | None) -> dict[str, ClassLevel]:
    # Typed for a class's levels, which domains and fields share as plain Levels: their scope refuses OnDomains.
    entry = level if domains is None else OnDomains(level, frozenset(domains))
    return dict.fromkeys(items, entry)


def verified(*items: str, domains: Collection[str] | None = None) -> dict[str, ClassLevel]:
    """Each item Verified; a class's on `domains` alone when given (OnDomains)."""
    return _levels(items, Level.VERIFIED, domains)


def documented(*items: str, domains: Collection[str] | None = None) -> dict[str, ClassLevel]:
    """Each item Documented; a class's on `domains` alone when given (OnDomains)."""
    return _levels(items, Level.DOCUMENTED, domains)


def experimental(*items: str, domains: Collection[str] | None = None) -> dict[str, ClassLevel]:
    """Each item Experimental; a class's on `domains` alone when given (OnDomains)."""
    return _levels(items, Level.EXPERIMENTAL, domains)


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
class NoKnownMethod:
    """A class with no known method, a device limit as far as anyone knows (docs/evidence.md, No known method): no
    known call works on it, or the only one known is unsafe, and the reason says which. What the card names, why, and
    the source, an https URL (scripts/gen_compat.py checks it). The dispatcher refuses it as `no_known_method`,
    raising with the reason; the card lists it under No known method.

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
class NotBuilt:
    """A class not built yet (docs/evidence.md, Not built yet), declared because the adapter's call would harm it: a
    call that would work is known or plausible, and nobody has built it. Why the user can't have it yet, and the
    source, an https URL (scripts/gen_compat.py checks it); the dispatcher refuses it as `not_built` with the reason,
    and the card lists it as not built yet, as it does a class a scope leaves out.

    `harms`, required as NoKnownMethod's is: the adapter's call harms the class (When today's call harms a class), so
    AdapterScope.refusal refuses a target that could still be in it as class_unknown, exactly as for a NoKnownMethod
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
    the plain string, so a scope's levels and no_known_method read it as they would), except where an adapter's call
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


# eq=False: compared and hashed by identity, so the dispatcher runs together only the targets one call object serves.
@dataclass(frozen=True, slots=True, eq=False)
class OwnCall:
    """A class's own call (docs/evidence.md, The split rule): what an adapter sends a class in place of its `execute`,
    held in AdapterScope.own_calls. `send` makes the call for one target and gives its result, as the `send` an adapter
    hands `gather` does (Adapter.execute_own runs it); `limits` are the durations it can carry, None for the scope's
    `duration`.

    Why a value, not a branch in execute: the dispatcher plans a run on the class it found and hands the adapter that
    class's call, so the adapter never classes a target again, where a report in between could have moved it. Classes
    that share one OwnCall object share a run."""

    send: Callable[[Adapter, HomeAssistant, Request, Target], Awaitable[EntityResult]]
    limits: DurationLimits | None = None


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
    # A class the integration names in neither this nor no_known_method is not built yet, and refused. A class's
    # level holds on every domain unless its entry names some (OnDomains): elsewhere it counts as Experimental.
    capabilities: Mapping[str, ClassLevel] | None = None
    # Classes with no known method, refused with why; never in capabilities. Per adapter, as one class can fail one
    # action's call and answer another's.
    no_known_method: Mapping[str, NoKnownMethod] = field(default_factory=dict)
    # Classes not built yet that the adapter's call would harm, refused with why (each entry's harms is True); in
    # neither of the above. Any other class not built yet is simply left out.
    not_built: Mapping[str, NotBuilt] = field(default_factory=dict)
    # Classes the adapter sends a call of their own (OwnCall), each with that call. Each is in capabilities. A native
    # group's call isn't theirs, so a group with a member of one falls back to its members (Reason.OWN_CALL), and the
    # member gets its own call.
    own_calls: Mapping[str, OwnCall] = field(default_factory=dict)
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
        if both := self.no_known_method.keys() & (self.capabilities or {}).keys():
            raise ValueError(f"no_known_method names classes the scope serves: {sorted(both)}")
        if both := self.not_built.keys() & ((self.capabilities or {}).keys() | self.no_known_method.keys()):
            raise ValueError(f"not_built names classes the scope serves or lists under no_known_method: {sorted(both)}")
        if unharmed := sorted(name for name, entry in self.not_built.items() if not entry.harms):
            raise ValueError(f"not_built entries {unharmed} don't harm: an unharmed class not built yet needs no entry")
        if unserved := sorted(self.own_calls.keys() - (self.capabilities or {}).keys()):
            raise ValueError(f"own_calls names classes the scope doesn't serve: {unserved}")
        self._check_on_domains()
        # Read-only copies: adapters share mappings such as Shelly's CAPABILITIES, and a frozen scope stays frozen.
        for name in ("domains", "fields", "capabilities", "no_known_method", "not_built", "own_calls"):
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
            levels += [self.class_level(name, domain) for name in classes]
        return min(levels)

    def class_level(self, name: str | None, domain: str) -> Level:
        """A class's level in a domain: its entry's, where that holds the domain (an OnDomains entry names some alone),
        else Experimental, as for a class outside the scope or None."""
        entry = (self.capabilities or {}).get(name)
        if isinstance(entry, OnDomains):
            return entry.level if domain in entry.domains else Level.EXPERIMENTAL
        return Level.EXPERIMENTAL if entry is None else entry

    def class_entries(self) -> list[tuple[str, Level, frozenset[str] | None]]:
        """Each class the scope serves, with its level and the domains it holds it on, None for every domain."""
        return [
            (name, entry.level, entry.domains) if isinstance(entry, OnDomains) else (name, entry, None)
            for name, entry in (self.capabilities or {}).items()
        ]

    @property
    def harms(self) -> bool:
        """Whether the adapter's call harms a class it could reach: a no_known_method or not_built entry with harms."""
        return any(entry.harms for entry in (*self.no_known_method.values(), *self.not_built.values()))

    def refusal(self, classes: Collection[str | None], group: bool = False) -> tuple[str, str | None] | None:
        """Why the scope refuses a target of these classes (a native group's: its members'), with the reason the user
        reads, or None. Where the call harms a class (`harms`), first `class_unknown` when one is Unplaced, or None
        (the integration couldn't name it, or a group's membership is unknown), as it could be the harmed class, with
        Experimental features on or off. Then `no_known_method` and its NoKnownMethod.reason when one is listed as
        having none, else `not_built` when one is named but not served, with its NotBuilt.reason when it has an entry.
        Elsewhere None is no refusal: the gate weighs it as Experimental, and an Unplaced class as the class it
        names. Last, for a native group whose members are listed (`group`), `own_call` when a member's class takes a
        call of its own (own_calls), so the group falls back to its members."""
        if self.capabilities is None:
            return None
        if self.harms and any(name is None or isinstance(name, Unplaced) for name in classes):
            return Reason.CLASS_UNKNOWN, None
        if entry := next((self.no_known_method[name] for name in classes if name in self.no_known_method), None):
            return Reason.NO_KNOWN_METHOD, entry.reason
        if entry := next((self.not_built[name] for name in classes if name in self.not_built), None):
            return Reason.NOT_BUILT, entry.reason
        if any(name is not None and name not in self.capabilities for name in classes):
            return Reason.NOT_BUILT, None
        if group and self.own_call(classes) is not None:
            return Reason.OWN_CALL, None
        return None

    def own_call(self, classes: Collection[str | None]) -> OwnCall | None:
        """The call of its own a target of these classes gets, None for the adapter's `execute`. A native group with
        such a member is refused (refusal), so never runs."""
        return next((self.own_calls[name] for name in classes if name in self.own_calls), None)

    def call_limits(self, call: OwnCall | None) -> DurationLimits | None:
        """The duration limits of a run on `call` (own_call): its own, where it has them, else the scope's."""
        return self.duration if call is None or call.limits is None else call.limits

    def _check_on_domains(self) -> None:
        for axis in ("domains", "fields"):
            if any(isinstance(level, OnDomains) for level in getattr(self, axis).values()):
                raise ValueError(f"{axis} take no domains: only a class's level is held on some domains")
        for name, entry in (self.capabilities or {}).items():
            if isinstance(entry, OnDomains) and not entry.domains <= self.domains.keys():
                raise ValueError(f"class {name!r} is held on domains the scope doesn't serve: {sorted(entry.domains)}")

    def _check_unlisted(self) -> None:
        if unknown := self.unlisted - LACKABLE:
            raise ValueError(f"unlisted names fields a light's state never lacks: {sorted(unknown)}")
        if untested := self.unlisted - self.fields.keys():
            raise ValueError(f"unlisted names fields outside the scope's fields: {sorted(untested)}")
        if dropped := self.unlisted & self.drops:
            raise ValueError(f"unlisted names fields the scope drops: {sorted(dropped)}")


@dataclass(frozen=True, slots=True)
class FamilyScope:
    """A family's part of one adapter's scope: its classes' levels and own calls, for AdapterScope's fields of the same
    names, each by class. A class it leaves out is left out of the adapter's scope, so refused as not built yet.

    It holds no refusal entry (NoKnownMethod, NotBuilt): those are the integration's, in its `refusals.py`, which
    `class_scope` merges in. A family's maintainers may merge a change to its files alone, and an entry with `harms`
    protects users of every family's devices, so it lives on a path a family maintainer doesn't own."""

    capabilities: Mapping[str, ClassLevel] = field(default_factory=dict)
    own_calls: Mapping[str, OwnCall] = field(default_factory=dict)


@dataclass(frozen=True, slots=True, kw_only=True)
class Family:
    """A vendor's firmware family inside one integration (docs/design.md, Family): the classes it owns
    and, per action key, the levels and own calls each adapter's scope holds for them (`scopes`; an action with none
    leaves its classes out of that adapter's scope). Where an action refuses one of its classes with a reason is the
    integration's to say (FamilyScope). It exists so a vendor is one path with its own maintainers: GitHub handles,
    which may be empty, as the integration's maintainers own every family of it too. The registry checks it
    (core/registry.py, check_families)."""

    key: str
    maintainers: tuple[str, ...] = ()
    classes: frozenset[str]
    scopes: Mapping[str, FamilyScope] = field(default_factory=dict)


def family_scope(families: Iterable[Family], action: str) -> FamilyScope:
    """The families' parts of one action's scope, merged in the families' order. The registry has checked that no two
    families hold one class (core/registry.py, check_families), so no part replaces another's."""
    parts = [family.scopes[action] for family in families if action in family.scopes]
    return FamilyScope(
        capabilities={name: level for part in parts for name, level in part.capabilities.items()},
        own_calls={name: call for part in parts for name, call in part.own_calls.items()},
    )


def class_scope(
    action: str,
    *,
    families: Iterable[Family],
    default_levels: Mapping[str, Mapping[str, ClassLevel]],
    refusals: Mapping[str, Mapping[str, NoKnownMethod | NotBuilt]],
) -> dict[str, Any]:
    """The class entries of an action's AdapterScope, as its keyword arguments, for an integration with families:
    the default class at the integration's level (`default_levels`, by action), then the families' classes and own
    calls (family_scope), and the integration's refusal entries (`refusals`, by action then class: its `refusals.py`),
    each under the AdapterScope field its type names. The default class goes first, as the cards list an adapter's
    classes in the scope's order (scripts/gen_compat.py). AdapterScope raises for a class a family serves that the
    integration refuses."""
    parts = family_scope(families, action)
    refused = refusals.get(action, {})
    return {
        "capabilities": {**default_levels[action], **parts.capabilities},
        "no_known_method": {name: entry for name, entry in refused.items() if isinstance(entry, NoKnownMethod)},
        "not_built": {name: entry for name, entry in refused.items() if isinstance(entry, NotBuilt)},
        "own_calls": parts.own_calls,
    }


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
    # The device's own Zigbee manufacturer string (`_TZ3000_…`), for the report form, where HA's registry holds another
    # (Z2M's definition vendor, a ZHA quirk's friendly name); sync, no I/O. None when it isn't held: the form then
    # takes the registry's (config_flow._device_facts).
    zigbee_manufacturer: Callable[[HomeAssistant, dr.DeviceEntry], str | None] | None = None
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
    # adapter serves in neither its capabilities nor its no_known_method as not built yet.
    classes: frozenset[str] = frozenset()
    # The class capability() gives a device no rule matches, one of `classes`; the registry refuses any scope holding it
    # as Verified (docs/evidence.md, Device classes). None for an integration whose classes name every target (Shelly).
    default_class: str | None = None
    # The vendor families that hold its classes, each with its own maintainers; between them every class but the
    # default one, each once (core/registry.py, check_families). Empty for an integration that has none.
    families: tuple[Family, ...] = ()
    # Drops what a light or scene call from HA leaves stale (core/ha_watch.py); None holds nothing it could.
    call_resolver: CallResolver | None = None
    # Starts what the integration keeps running while the entry is loaded (Z2M's bridge cache). Core runs it as the
    # entry's background task, so it never holds setup back and an unload cancels it mid-way; it registers its own
    # teardown with entry.async_on_unload. None for an integration with nothing to start.
    setup: Callable[[HomeAssistant, ConfigEntry], Awaitable[None]] | None = None
    # Undoes what the integration changed outside HA as DeviceSide is deleted (Z2M's color modes); awaited from
    # async_remove_entry. None for an integration that changed nothing.
    remove: Callable[[HomeAssistant, ConfigEntry], Awaitable[None]] | None = None
    max_concurrency: int = 4
    available: bool = True
    unavailable_reason: str | None = None
    # Why DeviceSide never supports this integration's targets, for one declared only to refuse them: a different
    # gateway or API on a sibling's ha_domain (docs/evidence.md, The split rule), whose `detect` hook claims its
    # entities, as the Hue v1 bridge's beside Hue. The sibling's module lists it in UNSUPPORTED (core/registry.py); it
    # has no adapters, and the dispatcher refuses every target it claims as integration_not_supported, with this as the
    # reason a named one raises with. None for every integration that has adapters.
    unsupported: str | None = None
