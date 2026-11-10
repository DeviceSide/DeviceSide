import importlib
import logging
from collections.abc import Iterable, Iterator
from types import ModuleType

from .action import Action
from .adapter import Adapter
from .ha_watch import CallResolver
from .scope import IntegrationInfo
from .. import actions as actions_pkg
from .. import integrations as integrations_pkg

_LOGGER = logging.getLogger(__name__)


class AdapterRegistry:
    """Actions, integrations and the adapters joining them, built from module data with no side effects and no hass.

    That is what lets check_release.py and the rig (outside this repo) import it offline, and tests build one from an
    explicit list.
    """

    def __init__(self, actions: Iterable[type[Action]], integration_modules: Iterable[str | ModuleType]):
        self.actions: dict[str, type[Action]] = {action.key: action for action in actions}
        self.integrations: dict[str, IntegrationInfo] = {}
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
                (_LOGGER.warning if ours else _LOGGER.debug)("Integration %s unavailable: %s", key, err)
                self._add_unavailable(key, str(err))
                return
            except Exception as err:  # noqa: BLE001 - one integration's broken import must not take the rest down
                _LOGGER.warning("Integration %s unavailable: %r", key, err, exc_info=True)
                self._add_unavailable(key, repr(err))
                return
        info: IntegrationInfo = module.INTEGRATION
        self.integrations[info.key] = info
        for cls in module.ADAPTERS:
            if cls.integration != info.key:
                raise ValueError(f"{cls.__name__} declares integration {cls.integration}, module is {info.key}")
            if cls.action not in self.actions:
                raise ValueError(f"{cls.__name__} serves unknown action {cls.action}")
            self._adapters[(cls.action, info.key)] = cls()

    def _add_unavailable(self, key: str, reason: str) -> None:
        self.integrations[key] = IntegrationInfo(
            key=key, title=key, ha_domain=key, available=False, unavailable_reason=reason
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
