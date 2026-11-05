"""Drop the predictions a light or scene call made from Home Assistant leaves stale.

A call from a dashboard, an automation or a script can change a light while a fade of ours runs, and the light's next
move or stop would then plan from the wrong value. One listener watches the light and scene calls, resolves each
call's target once, and hands each integration's resolver (IntegrationInfo.call_resolver) the registry entries it
owns. Our own commands go outside the light domain, or over MQTT, so they pass it by.

The listener runs before the call's service does. A resolver that must look something up (a Z2M group's members) runs
in a task instead, and settled() waits for it: the dispatcher awaits it before any adapter plans.
"""

import asyncio
import logging
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, Protocol

from homeassistant.const import (
    ATTR_DOMAIN,
    ATTR_ENTITY_ID,
    ATTR_SERVICE,
    ATTR_SERVICE_DATA,
    ENTITY_MATCH_ALL,
    EVENT_CALL_SERVICE,
)
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.target import TargetSelection, async_extract_referenced_entity_ids

from .runtime import get_runtime

_LOGGER = logging.getLogger(__name__)

SERVICE_DOMAINS = frozenset({"light", "scene"})
# A turn_on with any of these sets a color or an effect, which ends a bulb's hue cycle; so do turn_off and toggle.
_COLOR_FIELDS = frozenset(
    {
        "hs_color",
        "xy_color",
        "rgb_color",
        "rgbw_color",
        "rgbww_color",
        "color_name",
        "color_temp_kelvin",
        "white",
        "effect",
    }
)
_PENDING = "ha_watch_pending"


class _All(Enum):
    ALL = "all"


ALL = _All.ALL
"""Every light: the call targets entity_id: all."""

type Entries = list[er.RegistryEntry] | Literal[_All.ALL]


@dataclass(frozen=True, slots=True)
class Call:
    domain: str
    service: str
    service_data: Mapping[str, Any]

    @property
    def ends_hue_cycle(self) -> bool:
        """Whether the call sets a color or turns the light off, which ends a hue move's cycle on the bulb."""
        if self.domain != "light":
            return False
        if self.service in ("turn_off", "toggle"):
            return True
        return self.service == "turn_on" and not _COLOR_FIELDS.isdisjoint(self.service_data)


class CallResolver(Protocol):
    def busy(self, hass: HomeAssistant) -> bool:
        """Whether the integration holds anything a call could leave stale: predictions, ends to show, hue marks."""
        ...

    def forget(self, hass: HomeAssistant, call: Call, entries: Entries) -> Awaitable[None] | None:
        """Drop what the call leaves stale for these entries of the integration, or for ALL."""
        ...


def attach(hass: HomeAssistant, resolvers: Mapping[str, CallResolver]) -> CALLBACK_TYPE:
    """Listen for light and scene calls; resolvers are keyed by their integration's ha_domain."""

    @callback
    def on_call(event: Event) -> None:
        if not (busy := {ha_domain: r for ha_domain, r in resolvers.items() if _busy(hass, ha_domain, r)}):
            return
        service_data = event.data.get(ATTR_SERVICE_DATA) or {}
        call = Call(event.data[ATTR_DOMAIN], event.data[ATTR_SERVICE], service_data)
        for ha_domain, entries in _entries(hass, service_data, busy).items():
            _forget(hass, ha_domain, busy[ha_domain], call, entries)

    return hass.bus.async_listen(EVENT_CALL_SERVICE, on_call, event_filter=_is_light_call)


async def settled(hass: HomeAssistant) -> None:
    """Wait for the resolvers still running for calls already made."""
    if pending := _pending(hass):
        await asyncio.gather(*pending, return_exceptions=True)


def _entries(
    hass: HomeAssistant, service_data: Mapping[str, Any], resolvers: Mapping[str, CallResolver]
) -> dict[str, Entries]:
    """The call's target, once, split by the ha_domain owning each entry (its registry platform)."""
    if service_data.get(ATTR_ENTITY_ID) == ENTITY_MATCH_ALL:
        return dict.fromkeys(resolvers, ALL)
    selected = async_extract_referenced_entity_ids(hass, TargetSelection(service_data))
    registry = er.async_get(hass)
    by_domain: dict[str, Entries] = {}
    for entity_id in sorted(selected.referenced | selected.indirectly_referenced):
        if (entry := registry.async_get(entity_id)) is not None and entry.platform in resolvers:
            by_domain.setdefault(entry.platform, []).append(entry)
    return by_domain


def _busy(hass: HomeAssistant, ha_domain: str, resolver: CallResolver) -> bool:
    try:
        return resolver.busy(hass)
    except Exception:
        _LOGGER.exception("The %s call resolver failed", ha_domain)
        return False


def _forget(hass: HomeAssistant, ha_domain: str, resolver: CallResolver, call: Call, entries: Entries) -> None:
    """Run the resolver, logging a failure so the others still run; one that returns an awaitable runs in a task."""
    try:
        if (later := resolver.forget(hass, call, entries)) is None:
            return
    except Exception:
        _LOGGER.exception("The %s call resolver failed on %s.%s", ha_domain, call.domain, call.service)
        return

    async def run() -> None:
        try:
            await later
        except Exception:
            _LOGGER.exception("The %s call resolver failed on %s.%s", ha_domain, call.domain, call.service)

    pending = _pending(hass)
    task = hass.async_create_task(run(), f"deviceside {ha_domain} call resolver")
    if not task.done():
        pending.add(task)
        task.add_done_callback(pending.discard)


def _pending(hass: HomeAssistant) -> set[asyncio.Task]:
    return get_runtime(hass).integration_state.setdefault(_PENDING, set())


@callback
def _is_light_call(event_data) -> bool:
    return event_data[ATTR_DOMAIN] in SERVICE_DOMAINS
