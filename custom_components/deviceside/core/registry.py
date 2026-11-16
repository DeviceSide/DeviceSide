import importlib
import logging
import re
from collections.abc import Iterable, Iterator
from types import ModuleType

from .action import Action
from .adapter import Adapter
from .ha_watch import CallResolver
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
    declares in exactly one family, but the default class, which stays the integration's. A family's scopes name only
    its own classes, so no family sets another's level or refusal."""
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
        if both := sorted(family.classes & owners.keys()):
            raise ValueError(f"{name} holds classes family {owners[both[0]]!r} holds: {both}")
        owners |= dict.fromkeys(family.classes, family.key)
        if unknown := sorted(family.classes - info.classes):
            raise ValueError(f"{name} holds classes {info.key} doesn't declare (IntegrationInfo.classes): {unknown}")
        if info.default_class in family.classes:
            raise ValueError(f"{name} holds the default class {info.default_class!r}, which is the integration's")
        if foreign := sorted(_scoped(family) - family.classes):
            raise ValueError(f"{name}: its scopes name classes that aren't its own: {foreign}")
    if unowned := sorted(info.classes - owners.keys() - {info.default_class}):
        raise ValueError(f"{info.key}: classes {unowned} are in no family")


def _scoped(family: Family) -> set[str]:
    """Every class a family's scopes name, across its actions."""
    return {
        name
        for scope in family.scopes.values()
        for part in (scope.capabilities, scope.doesnt_work, scope.not_supported, scope.own_calls)
        for name in part
    }


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
    if info.families:
        check_families(info)


def check_classes(cls: type[Adapter], info: IntegrationInfo) -> None:
    """One class axis per integration (docs/evidence.md, Device classes): an integration that names classes holds
    them in every adapter's scope, and one that names none in none. Otherwise an adapter that skipped the axis would
    let every class through at its domain's level, and one an integration can't name would refuse every call as
    Experimental. Each class a scope holds is one the integration declares, so a typo fails here. The default class,
    which holds every device not yet placed, is never Verified: one maker's record proves nothing about the rest."""
    held = cls.scope.capabilities
    if info.capability is None:
        if held is not None or cls.scope.doesnt_work or cls.scope.not_supported:
            raise ValueError(f"{cls.__name__} holds classes, but {info.key} names none (IntegrationInfo.capability)")
        return
    if held is None:
        raise ValueError(f"{cls.__name__}: {info.key} names classes, but its scope holds none (capabilities)")
    if unknown := sorted((held.keys() | cls.scope.doesnt_work.keys() | cls.scope.not_supported.keys()) - info.classes):
        raise ValueError(
            f"{cls.__name__} holds classes {info.key} doesn't declare (IntegrationInfo.classes): {unknown}"
        )
    if any(name == info.default_class and level is Level.VERIFIED for name, level, _ in cls.scope.class_entries()):
        raise ValueError(f"{cls.__name__} holds {info.key}'s default class {info.default_class!r} as Verified")


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
                (_LOGGER.warning if ours else _LOGGER.debug)("Integration %s unavailable: %r", key, err)
                self._add_unavailable(key, str(err))
                return
            except Exception as err:  # noqa: BLE001 - one integration's broken import must not take the rest down
                _LOGGER.warning("Integration %s unavailable: %r", key, err, exc_info=True)
                self._add_unavailable(key, repr(err))
                return
        info: IntegrationInfo = module.INTEGRATION
        check_integration(info)
        self.integrations[info.key] = info
        for family in info.families:
            # A typo would leave the family's classes out of that adapter's scope, refused with nothing saying why.
            if unknown := sorted(family.scopes.keys() - self.actions.keys()):
                raise ValueError(f"{info.key}: family {family.key!r} holds scopes for unknown actions {unknown}")
        for cls in module.ADAPTERS:
            if cls.integration != info.key:
                raise ValueError(f"{cls.__name__} declares integration {cls.integration}, module is {info.key}")
            if cls.action not in self.actions:
                raise ValueError(f"{cls.__name__} serves unknown action {cls.action}")
            check_classes(cls, info)
            self._adapters[(cls.action, info.key)] = cls()
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
