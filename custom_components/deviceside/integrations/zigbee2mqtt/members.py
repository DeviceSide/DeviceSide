"""A Z2M group's member lights, as targets: only Z2M's bridge/groups knows who they are."""

import logging
from collections.abc import Iterable
from dataclasses import replace

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from . import bridge_cache
from .addressing import group_id, state_topic, z2m_device
from .bridge import group_members, members_of
from ...core.errors import Reason
from ...core.models import Target
from ...core.resolver import resolve_members
from ...core.runtime import get_runtime

_LOGGER = logging.getLogger(__name__)


def expand_group(hass: HomeAssistant, target: Target) -> list[Target] | None:
    """Zigbee2MQTT's IntegrationInfo.expand_group: the group's members, from the bridge cache's bridge/groups, so sync
    and with no I/O. The dispatcher classes a group by them, and falls back to them when one's class is refused, or
    Experimental with the option off (docs/design.md, Groups).

    A member with a device but no entity in the group's domain that HA resolves (a Tuya plug Z2M exposes as a switch,
    a disabled light) is still classed by its device, through a stand-in no action reaches (`_stand_in`): left out,
    its class would be too, and the plug would get the group's light command at the Hue bulbs' level.

    `[]` only for a group bridge/groups lists with no members, which the dispatcher skips as empty. None, membership
    unknowable, while the cache holds no bridge/groups (before Z2M's publish after a connect), when there is no cache
    (its subscribe failed, which bridge_cache warns of once), when bridge/groups doesn't list the group, or when a
    member it lists has no device in HA; the group then counts as Experimental, and turn_on_for refuses it.
    """
    if (gid := group_id(target)) is None or (cache := bridge_cache.get(hass)) is None:
        return None
    if (groups := cache.parsed("groups")) is None or not any(str(g.get("id")) == gid for g in groups):
        return None
    members, complete = _members(hass, target, members_of(groups, gid))
    return members if complete else None


async def member_lights(hass: HomeAssistant, group: Target) -> list[Target]:
    """The group's member lights that HA has and that are available, one per device, for an action that addresses
    them one by one.

    An unavailable member is left out, as the dispatcher leaves one out when it expands a group, and so is one HA
    has no light for, and one with several lights (`_members`), which the call could reach only on its default
    endpoint, maybe a light the user didn't target.
    """
    members, _complete = _members(hass, group, await group_members(hass, group_id(group)))
    return [
        member
        for member in members
        if member.addressable
        and member.state is not None
        and member.state.state != STATE_UNAVAILABLE
        and state_topic(member) is not None
    ]


def unaddressable(hass: HomeAssistant, target: Target) -> str | None:
    """not_addressable for a group an action reaches through its member lights (member_lights) when every member
    with a light is a device with several (`_members`), so the call has none to address; None for anything else, and
    when the bridge cache can't list the members. A groupcast still reaches such a group: only the actions that
    address members one by one check this, before anything is sent, so a named group raises, as core's rule for a
    group none of whose members runs has it."""
    if not target.is_group or not (listed := expand_group(hass, target)):
        return None
    lights = [member for member in listed if member.state is not None]
    if lights and not any(member.addressable for member in lights):
        return Reason.NOT_ADDRESSABLE
    return None


def _members(hass: HomeAssistant, group: Target, addresses: Iterable[str]) -> tuple[list[Target], bool]:
    """A target per member device HA has, sorted by entity_id: its entity in the group's domain, or a stand-in when
    HA resolves none; and whether every address has a device. A device on two endpoints is listed twice, and counts
    once, keyed by its device.

    A device with more than one entity in the group's domain, disabled ones counted (a two-gang switch, a dual
    Gledopto), is listed by its first, not addressable (Target.addressable): its class counts, but no action addresses
    it on its own. The group holds one endpoint of it, and DeviceSide's set and get topics name the device alone, so
    Z2M would send the call to the device's default endpoint, maybe a gang the user didn't target
    (docs/integrations/zigbee2mqtt/internals.md, Multi-endpoint devices). A groupcast still reaches the right one."""
    entities = er.async_get(hass)
    registry = get_runtime(hass).registry
    members: dict[str, Target] = {}
    complete = True
    for address in addresses:
        if (device := z2m_device(hass, group, address)) is None:
            complete = False
            continue
        own = er.async_entries_for_device(entities, device.id)
        lights = [e for e in own if e.domain == group.domain]
        resolved = resolve_members(hass, registry, group, "mqtt", [lights[0].unique_id]) if lights else []
        if resolved:
            several = [
                e
                for e in er.async_entries_for_device(entities, device.id, include_disabled_entities=True)
                if e.domain == group.domain
            ]
            if len(several) > 1:
                # The first report of "my two-gang's other gang turned on", or "it was skipped", holds why.
                _LOGGER.debug(
                    "%s: a member device (%s) has several %s entities, so it is classed by its device and never"
                    " addressed on its own, which would reach its default endpoint",
                    group.entity_id,
                    ", ".join(e.entity_id for e in several),
                    group.domain,
                )
            members[device.id] = replace(resolved[0], addressable=len(several) == 1)
            continue
        # The first report of "my plug wasn't in the group's fallback" holds why.
        _LOGGER.debug(
            "%s: a member device (%s) has no %s entity, so it is classed by its device and left out of any fallback",
            group.entity_id,
            ", ".join(e.entity_id for e in own) or "no entities",
            group.domain,
        )
        members[device.id] = _stand_in(group, device)
    return sorted(members.values(), key=lambda member: member.entity_id), complete


def _stand_in(group: Target, device: dr.DeviceEntry) -> Target:
    """A member HA has no entity for in the group's domain, for its class alone: the group's own entity with the
    member's device, and no state, so the dispatcher never falls back to it and member_lights leaves it out."""
    return replace(group, device=device, state=None, via_group=group.entity_id, is_group=False)
