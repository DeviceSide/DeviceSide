import importlib
import logging
import re
from collections.abc import Collection, Iterable, Iterator
from types import ModuleType

from homeassistant.const import Platform

from .action import Action
from .adapter import Adapter, OwnCallsOnly
from .ha_watch import CallResolver
from .models import ActionKind
from .scope import Family, IntegrationInfo, Level
from .. import actions as actions_pkg
from .. import integrations as integrations_pkg

_LOGGER = logging.getLogger(__name__)
# A GitHub handle: alphanumerics and single inner hyphens, at most 39 characters, no leading @.
HANDLE = re.compile(r"[A-Za-z0-9](?:-?[A-Za-z0-9]){0,38}")
# A family's key names its package (integrations/<x>/families/<key>/), so it is shaped like one.
FAMILY_KEY = re.compile(r"[a-z][a-z0-9_]*")


def check_maintainers(info: IntegrationInfo) -> None:
    """An integration names one or more maintainers, each a GitHub handle, each once."""
    if not isinstance(info.maintainers, tuple) or not info.maintainers:
        raise ValueError(f"{info.key}: maintainers must be a non-empty tuple of GitHub handles")
    _check_handles(info.key, info.maintainers)


def _check_handles(owner: str, maintainers: tuple[str, ...]) -> None:
    if bad := [handle for handle in maintainers if not isinstance(handle, str) or not HANDLE.fullmatch(handle)]:
        raise ValueError(f"{owner}: maintainers {bad!r} are not GitHub handles (no leading @)")
    if len(set(maintainers)) != len(maintainers):
        raise ValueError(f"{owner}: maintainers lists a handle twice")


def check_families(info: IntegrationInfo) -> None:
    """An integration's families split its classes between them: each key once and shaped like a package name, each
    maintainer a GitHub handle (none is fine: the integration's own them too), and every class the integration
    declares in exactly one family, with the domains the family gives it, but the default class and `own_classes`,
    which stay the integration's. A family's scopes name only its own classes, so no family sets another's level or own
    call. No family holds a refusal entry: those are the integration's, in its `refusals.py` (core/scope.py,
    FamilyScope)."""
    owners: dict[str, str] = {}
    for family in info.families:
        name = f"{info.key}: family {family.key!r}"
        if not isinstance(family.key, str) or not FAMILY_KEY.fullmatch(family.key):
            raise ValueError(f"{name} is not shaped like a package name")
        if sum(other.key == family.key for other in info.families) > 1:
            raise ValueError(f"{name} is declared twice")
        if not isinstance(family.maintainers, tuple):
            raise ValueError(f"{name}: maintainers must be a tuple of GitHub handles")
        _check_handles(name, family.maintainers)
        if both := sorted(family.classes.keys() & owners.keys()):
            raise ValueError(f"{name} holds classes family {owners[both[0]]!r} holds: {both}")
        owners |= dict.fromkeys(family.classes, family.key)
        _check_declared(info, family, name)
        if info.default_class in family.classes:
            raise ValueError(f"{name} holds the default class {info.default_class!r}, which is the integration's")
        if own := sorted(family.classes.keys() & info.own_classes):
            raise ValueError(f"{name} holds classes the integration holds itself (own_classes): {own}")
        if foreign := sorted(_scoped(family) - family.classes.keys()):
            raise ValueError(f"{name}: its scopes name classes that aren't its own: {foreign}")
    if unowned := sorted(info.classes.keys() - owners.keys() - {info.default_class} - info.own_classes):
        raise ValueError(f"{info.key}: classes {unowned} are in no family")


def _check_declared(info: IntegrationInfo, family: Family, name: str) -> None:
    """The integration declares each of the family's classes, with the family's domains."""
    if unknown := sorted(family.classes.keys() - info.classes.keys()):
        raise ValueError(f"{name} holds classes {info.key} doesn't declare (IntegrationInfo.classes): {unknown}")
    if moved := sorted(cls for cls, domains in family.classes.items() if info.classes[cls] != domains):
        raise ValueError(f"{name}: IntegrationInfo.classes gives {moved} other domains than the family's")


def _scoped(family: Family) -> set[str]:
    """Every class a family's scopes name, across its actions."""
    return {name for scope in family.scopes.values() for part in (scope.capabilities, scope.own_calls) for name in part}


def check_family_actions(info: IntegrationInfo, actions: Collection[str], served: Collection[str]) -> None:
    """Each family's scopes are for actions the integration has an adapter for (`served`), among the known `actions`.
    A typo would leave the family's classes out of that adapter's scope, refused with nothing saying why; a scope for
    an action with no adapter would be read by nothing, as silently."""
    for family in info.families:
        if unknown := sorted(family.scopes.keys() - set(actions)):
            raise ValueError(f"{info.key}: family {family.key!r} holds scopes for unknown actions {unknown}")
        if unserved := sorted(family.scopes.keys() - set(served)):
            raise ValueError(
                f"{info.key}: family {family.key!r} holds scopes for actions {info.key} has no adapter for: {unserved}"
            )


def check_integration(info: IntegrationInfo) -> None:
    """An integration's own fields: its maintainers, its classes with the classifier that names them, its families
    when it has any, and no `unsupported`, which only an integration listed in its sibling's UNSUPPORTED may have."""
    check_maintainers(info)
    if info.unsupported is not None:
        raise ValueError(f"{info.key}: an integration with adapters can't be unsupported; list it in UNSUPPORTED")
    if (info.capability is None) != (not info.classes):
        raise ValueError(f"{info.key}: IntegrationInfo.capability and classes come together")
    if info.default_class is not None and info.default_class not in info.classes:
        raise ValueError(f"{info.key}: default_class {info.default_class!r} is none of its classes")
    if bare := sorted(
        name
        for name, domains in info.classes.items()
        if not isinstance(domains, frozenset) or not domains or not all(isinstance(d, Platform) for d in domains)
    ):
        raise ValueError(f"{info.key}: classes {bare} name no entity domains (a non-empty frozenset of them)")
    if info.own_classes and not info.families:
        raise ValueError(f"{info.key}: own_classes is for an integration with families; one without holds every class")
    if undeclared := sorted(info.own_classes - info.classes.keys()):
        raise ValueError(f"{info.key}: own_classes {undeclared} are none of its classes")
    if info.default_class in info.own_classes:
        raise ValueError(f"{info.key}: own_classes holds the default class {info.default_class!r}")
    if info.families:
        check_families(info)


def check_classes(cls: type[Adapter], info: IntegrationInfo) -> None:
    """One class axis per integration (docs/evidence.md, Device classes): an integration that names classes holds
    them in every adapter's scope, and one that names none in none. Otherwise an adapter that skipped the axis would
    let every class through at its domain's level, and one an integration can't name would refuse every call as
    a Labs item. Each class a scope holds is one the integration declares, so a typo fails here, and on an action
    one of its domains reaches: an action for lights alone never holds a plug, so dispatch refuses it as not built yet
    and the card leaves it off. Per action, not per domain: on an action serving several domains, a plain entry holds
    the class on each, at its level (only the card reads its domains there); a level held on some domains alone
    (OnDomains) names only domains the class can be. The default class,
    which holds every device not yet placed, is never Verified: one maker's record proves nothing about the rest."""
    held = cls.scope.capabilities
    if info.capability is None:
        if held is not None or cls.scope.no_known_method or cls.scope.not_built:
            raise ValueError(f"{cls.__name__} holds classes, but {info.key} names none (IntegrationInfo.capability)")
        return
    if held is None:
        raise ValueError(f"{cls.__name__}: {info.key} names classes, but its scope holds none (capabilities)")
    named = held.keys() | cls.scope.no_known_method.keys() | cls.scope.not_built.keys()
    if unknown := sorted(named - info.classes.keys()):
        raise ValueError(
            f"{cls.__name__} holds classes {info.key} doesn't declare (IntegrationInfo.classes): {unknown}"
        )
    # A class held, or refused with a reason, on an action none of its domains reaches: the card would list a plug's
    # dimming. Leave it out of the scope instead (docs/evidence.md, Device classes).
    if unreached := sorted(name for name in named if not info.classes[name] & cls.scope.domains.keys()):
        raise ValueError(
            f"{cls.__name__} holds classes on none of the domains they can be (IntegrationInfo.classes): {unreached}"
        )
    if beyond := sorted(
        name for name, _, domains in cls.scope.class_entries() if domains is not None and domains - info.classes[name]
    ):
        raise ValueError(f"{cls.__name__} holds classes on domains they can't be (IntegrationInfo.classes): {beyond}")
    if any(name == info.default_class and level is Level.VERIFIED for name, level, _ in cls.scope.class_entries()):
        raise ValueError(f"{cls.__name__} holds {info.key}'s default class {info.default_class!r} as Verified")


def served(cls: type[Adapter] | Adapter, info: IntegrationInfo) -> set[tuple[str | None, str]]:
    """What an adapter serves, as (class, domain): each class its scope serves (AdapterScope.admits) on each of its
    domains the class can be (IntegrationInfo.classes); (None, domain) for each domain where the integration names no
    classes."""
    scope = cls.scope
    if scope.capabilities is None:
        return {(None, domain) for domain in scope.domains}
    return {
        (name, domain)
        for name in scope.capabilities
        for domain in scope.domains
        if domain in info.classes[name] and scope.admits(name, domain)
    }


def served_domains(cls: type[Adapter] | Adapter, info: IntegrationInfo) -> set[str]:
    """The entity domains where an adapter serves at least one class (`served`): the only ones an action's UI picker
    filter (services.yaml), the README's icons and the evidence block's Items show, so no user is offered a domain
    whose every class is refused. The scope keeps such a domain, so a call that skips the picker still reads the
    refusal's reason."""
    return {domain for _, domain in served(cls, info)}


def check_queries(adapters: Iterable[tuple[type[Adapter], Action]], info: IntegrationInfo) -> None:
    """A query (get_attributes) reads state back around DeviceSide's other actions, so it serves only what another of
    the integration's actions serves, class and domain both (docs/evidence.md, "A read serves only"). A class only a
    read would reach (a Tuya plug no other action serves yet) is left out of its scope, or, on some domains, held on the
    rest alone (OnDomains `only`), so it isn't offered and the card doesn't list it. A refusal entry (no_known_method)
    stays: it says why a read that would serve another action can't."""
    adapters = list(adapters)
    others = {item for cls, action in adapters if action.kind is not ActionKind.QUERY for item in served(cls, info)}
    for cls, action in adapters:
        if action.kind is ActionKind.QUERY and (alone := served(cls, info) - others):
            shown = sorted(f"{name or 'any class'} on {domain}" for name, domain in alone)
            raise ValueError(f"{cls.__name__} serves what no other {info.key} action does: {', '.join(shown)}")


class AdapterRegistry:
    """Actions, integrations and the adapters joining them, built from module data with no side effects and no hass.

    That is what lets check_release.py and the rig (outside this repo) import it offline, and tests build one from an
    explicit list.
    """

    def __init__(self, actions: Iterable[type[Action]], integration_modules: Iterable[str | ModuleType]):
        self.actions: dict[str, type[Action]] = {action.key: action for action in actions}
        self.integrations: dict[str, IntegrationInfo] = {}
        # Integrations declared only to refuse a gateway or API (IntegrationInfo.unsupported), by key. Kept apart from
        # `integrations`, which the cards, the release gate and CODEOWNERS read: one lives in its sibling's package,
        # whose bundle and gate cover it, and has nothing to list.
        self.unsupported: dict[str, IntegrationInfo] = {}
        self._adapters: dict[tuple[str, str], Adapter] = {}
        for module in integration_modules:
            self._add_integration(module)

    @classmethod
    def discover(cls) -> AdapterRegistry:
        """The production registry. Imports modules, so run it in the import executor."""
        return cls(actions_pkg.discover(), integrations_pkg.discover())

    def _add_integration(self, module: str | ModuleType) -> None:
        if isinstance(module, str):
            name = module
            key = name.rpartition(".")[2]
            try:
                module = importlib.import_module(module)
            except ImportError as err:
                # The integration's library is absent, which is routine: debug. A missing HA or DeviceSide module is
                # our code out of step with HA (a rename), which would hide every adapter of it: warn.
                ours = (err.name or "").startswith(("homeassistant", "custom_components"))
                (_LOGGER.warning if ours else _LOGGER.debug)(  # log-ok: an import failure is ours (docs/logging.md)
                    "Integration %s unavailable: %r, so its actions are refused", key, err
                )
                self._add_unavailable(key, str(err))
                return
            except Exception as err:  # noqa: BLE001 - one integration's broken import must not take the rest down
                _LOGGER.warning(  # log-ok: an import failure is ours (docs/logging.md)
                    "Integration %s unavailable: %r, so its actions are refused", key, err, exc_info=True
                )
                self._add_unavailable(key, repr(err))
                return
        info: IntegrationInfo = module.INTEGRATION
        check_integration(info)
        self.integrations[info.key] = info
        check_family_actions(info, self.actions.keys(), {cls.action for cls in module.ADAPTERS})
        for cls in module.ADAPTERS:
            if cls.integration != info.key:
                raise ValueError(f"{cls.__name__} declares integration {cls.integration}, module is {info.key}")
            if cls.action not in self.actions:
                raise ValueError(f"{cls.__name__} serves unknown action {cls.action}")
            check_classes(cls, info)
            # The mixin's execute, not one an earlier base gives, is the one the class runs.
            if cls.scope.own_calls_only != (cls.execute is OwnCallsOnly.execute):
                raise ValueError(
                    f"{cls.__name__}: a scope that serves only own calls (own_calls_only) and the OwnCallsOnly base "
                    "come together"
                )
            action = self.actions[cls.action]
            if cls.scope.not_built and not action.failure_harms:
                raise ValueError(
                    f"{cls.__name__} holds not_built entries {sorted(cls.scope.not_built)}, but {cls.action}'s failure "
                    "doesn't harm: a class not built yet that the call leaves unharmed needs no entry"
                )
            adapter = cls()
            adapter.kind = action.kind
            adapter.failure_harms = action.failure_harms
            self._adapters[(cls.action, info.key)] = adapter
        check_queries(((cls, self.actions[cls.action]) for cls in module.ADAPTERS), info)
        for refused in getattr(module, "UNSUPPORTED", ()):
            self._add_unsupported(refused, info)

    def _add_unsupported(self, info: IntegrationInfo, sibling: IntegrationInfo) -> None:
        """An integration its sibling's module declares only to refuse (IntegrationInfo.unsupported): on the sibling's
        ha_domain, claiming its entities by a detect hook, with a reason and nothing else to serve them."""
        check_maintainers(info)
        if not info.unsupported:
            raise ValueError(f"{info.key}: listed in UNSUPPORTED without a reason (IntegrationInfo.unsupported)")
        if info.detect is None or info.ha_domain != sibling.ha_domain:
            raise ValueError(f"{info.key}: an unsupported integration needs a detect hook on {sibling.ha_domain}")
        if info.key in self.integrations or info.key in self.unsupported:
            raise ValueError(f"{info.key}: declared twice")
        self.unsupported[info.key] = info

    def _add_unavailable(self, key: str, reason: str) -> None:
        self.integrations[key] = IntegrationInfo(
            key=key, title=key, ha_domain=key, maintainers=(), available=False, unavailable_reason=reason
        )

    def adapter(self, action: str, integration: str) -> Adapter | None:
        return self._adapters.get((action, integration))

    def available_integrations(self) -> list[IntegrationInfo]:
        return [info for info in self.integrations.values() if info.available]

    def call_resolvers(self) -> dict[str, CallResolver]:
        """Each available integration's call resolver, by its ha_domain."""
        resolvers: dict[str, CallResolver] = {}
        for info in self.available_integrations():
            if info.call_resolver is not None:
                if info.ha_domain in resolvers:
                    raise ValueError(f"Two call resolvers for ha_domain {info.ha_domain}")
                resolvers[info.ha_domain] = info.call_resolver
        return resolvers

    def matrix(self) -> Iterator[tuple[str, str, Adapter | None]]:
        """Every action x integration pair, sorted, with its adapter or None."""
        for action in sorted(self.actions):
            for integration in sorted(self.integrations):
                yield action, integration, self.adapter(action, integration)
