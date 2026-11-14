"""A Z2M group's member lights, as targets: only Z2M's bridge/groups knows who they are."""

from collections.abc import Iterable

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import bridge_cache
from .addressing import group_id, state_topic, z2m_device
from .bridge import group_members, members_of
from ...core.models import Target
from ...core.resolver import resolve_members
from ...core.runtime import get_runtime


def expand_group(hass: HomeAssistant, target: Target) -> list[Target] | None:
    """Zigbee2MQTT's IntegrationInfo.expand_group: the group's members that have an entity in its domain, from the
    bridge cache's bridge/groups, so sync and with no I/O. The dispatcher classes a group by them, and falls back to
    them when one's class is refused (docs/design.md, Groups).

    None, membership unknowable, while the cache holds no bridge/groups (before Z2M's first publish after a connect),
    or for a group on another base topic; the group then counts as Experimental.
    """
    if (gid := group_id(target)) is None or (cache := bridge_cache.get(hass)) is None:
        return None
    if (groups := cache.parsed("groups")) is None:
        return None
    return _members(hass, target, members_of(groups, gid))


async def member_lights(hass: HomeAssistant, group: Target) -> list[Target]:
    """The group's member lights that HA has and that are available, one per device.

    An unavailable member is left out, as the dispatcher leaves one out when it expands a group, and so is one HA
    has no light for.
    """
    members = _members(hass, group, await group_members(hass, group_id(group)))
    return [
        member
        for member in members
        if member.state is not None and member.state.state != STATE_UNAVAILABLE and state_topic(member) is not None
    ]


def _members(hass: HomeAssistant, group: Target, addresses: Iterable[str]) -> list[Target]:
    """The member at each address that HA has an entity for in the group's domain, one per device."""
    entities = er.async_get(hass)
    unique_ids = []
    for address in addresses:
        if (device := z2m_device(hass, group, address)) is None:
            continue
        lights = [e for e in er.async_entries_for_device(entities, device.id) if e.domain == group.domain]
        unique_ids += [lights[0].unique_id] if lights else []
    return resolve_members(hass, get_runtime(hass).registry, group, "mqtt", unique_ids)
