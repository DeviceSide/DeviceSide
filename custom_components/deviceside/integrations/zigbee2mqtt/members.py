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
    them when one's class is refused, or Experimental with the option off (docs/design.md, Groups).

    `[]` only for a group bridge/groups lists with no members, which the dispatcher skips as empty. None, membership
    unknowable, while the cache holds no bridge/groups (before Z2M's publish after a connect), when there is no cache
    (its subscribe failed, which bridge_cache warns of once), when bridge/groups doesn't list the group, or when any
    member it lists has no device or no entity in the group's domain that HA resolves; the group then counts as
    Experimental. A member left out would leave its class out too: a Tuya plug Z2M exposes as a switch, in a group of
    Hue bulbs, would get the group's light command at the Hue bulbs' level.
    """
    if (gid := group_id(target)) is None or (cache := bridge_cache.get(hass)) is None:
        return None
    if (groups := cache.parsed("groups")) is None or not any(str(g.get("id")) == gid for g in groups):
        return None
    members, complete = _members(hass, target, members_of(groups, gid))
    return members if complete else None


async def member_lights(hass: HomeAssistant, group: Target) -> list[Target]:
    """The group's member lights that HA has and that are available, one per device.

    An unavailable member is left out, as the dispatcher leaves one out when it expands a group, and so is one HA
    has no light for.
    """
    members, _complete = _members(hass, group, await group_members(hass, group_id(group)))
    return [
        member
        for member in members
        if member.state is not None and member.state.state != STATE_UNAVAILABLE and state_topic(member) is not None
    ]


def _members(hass: HomeAssistant, group: Target, addresses: Iterable[str]) -> tuple[list[Target], bool]:
    """The member at each address that HA has an entity for in the group's domain, one per device, and whether every
    address gave one that resolves (a device on two endpoints is listed twice, and counts once)."""
    entities = er.async_get(hass)
    unique_ids: list[str] = []
    complete = True
    for address in addresses:
        device = z2m_device(hass, group, address)
        lights = (
            []
            if device is None
            else [e for e in er.async_entries_for_device(entities, device.id) if e.domain == group.domain]
        )
        if not lights:
            complete = False
        elif lights[0].unique_id not in unique_ids:
            unique_ids.append(lights[0].unique_id)
    members = resolve_members(hass, get_runtime(hass).registry, group, "mqtt", unique_ids)
    return members, complete and len(members) == len(unique_ids)
