"""A ZHA group's members, for the dispatcher to expand a group entity into."""

from collections.abc import Iterable, Iterator

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import zcl
from .addressing import address, group_id
from ...core.models import Target
from ...core.resolver import resolve_members
from ...core.runtime import get_runtime


def expand_group(hass: HomeAssistant, target: Target) -> list[Target]:
    """The group's members that have an entity in the group entity's domain, sorted by entity_id.

    A ZHA group has one entity per domain among its members (a light group, a switch group), so a light group
    expands to its lights only. A member's entity is found by the unique_id the zha library gives it,
    "{ieee}-{endpoint_id}". A group ZHA no longer knows expands to nothing, which the dispatcher skips as an
    empty group: issue_zigbee_group_command would accept the call and send nothing.
    """
    if (gid := group_id(target.entry.unique_id)) is None or (group := zcl.gateway(hass).get_group(gid)) is None:
        return []
    return resolve_members(hass, get_runtime(hass).registry, target, "zha", _member_unique_ids(group))


def light_members(hass: HomeAssistant, gid: int) -> frozenset[str]:
    """The entity IDs of the group's member lights, whether or not a call targets them: a groupcast reaches them all."""
    if (group := zcl.gateway(hass).get_group(gid)) is None:
        return frozenset()
    registry = er.async_get(hass)
    return frozenset(
        entity_id
        for uid in _member_unique_ids(group)
        if (entity_id := registry.async_get_entity_id("light", "zha", uid)) is not None
    )


def covers(hass: HomeAssistant, gid: int, targets: Iterable[Target]) -> bool:
    """Whether the targets are every device endpoint a groupcast to the group reaches, so none gets a command it was
    refused or never asked for. The coordinator, which has nothing to switch, is left out. False for a group ZHA
    doesn't know, or one zigpy holds a member of that ZHA doesn't (zha's Group.members drops it, but the groupcast
    still reaches it).

    A group's light entity reaches only its lights, but a groupcast reaches every member: a Tuya plug in a light group,
    with only a switch entity, would take the light group's OnWithTimedOff (internals.md, `turn_on_for`).
    """
    if (group := zcl.gateway(hass).get_group(gid)) is None:
        return False
    if len(group.members) != len(group.zigpy_group.members):
        return False
    reached = {
        (str(member.device.ieee), member.endpoint_id) for member in group.members if not member.device.is_coordinator
    }
    return reached <= {(addr.ieee, addr.endpoint_id) for target in targets if (addr := address(target.entry.unique_id))}


def _member_unique_ids(group) -> Iterator[str]:
    """The unique_id the zha library gives each member's entity."""
    return (f"{member.device.ieee}-{member.endpoint_id}" for member in group.members)
