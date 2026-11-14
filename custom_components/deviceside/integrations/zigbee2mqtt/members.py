"""A Z2M group's member lights, as targets: only Z2M's bridge/groups knows who they are."""

import logging
from collections.abc import Iterable
from dataclasses import replace

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from . import bridge_cache
from .addressing import endpoints, group_id, state_topic, z2m_device
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
    member it lists has no device in HA; the group then counts as Experimental, and the dispatcher refuses it where
    the call harms a class (turn_on_for).
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
    endpoint, maybe a light the user didn't target. Raise, lower, stop and set_attributes refuse a group holding one
    (`unaddressable`), so only get_attributes reads a group without it, averaging the others; each one left out is
    logged at DEBUG.
    """
    members, _complete = _members(hass, group, await group_members(hass, group_id(group)))
    lights = [member for member in members if _available(member) and state_topic(member) is not None]
    if dropped := [member for member in lights if not member.addressable]:
        # The first report of "my group's reading leaves out my two-gang" holds why.
        _LOGGER.debug(
            "%s: leaving out the devices of %s, each with several %s entities, which can't be addressed on their own",
            group.entity_id,
            ", ".join(member.entity_id for member in dropped),
            group.domain,
        )
    return [member for member in lights if member.addressable]


def unaddressable(hass: HomeAssistant, target: Target, *, every: bool) -> str | None:
    """not_addressable for a group an action reaches through its member lights (member_lights) when an available
    member light is a device with several (`_members`), which the call can't address on its own; None for anything
    else, and when the bridge cache can't list the members.

    `every` is for an action that plans from every member's state (raise, lower, stop, set_attributes): one such
    member refuses the group, as the groupcast still reaches its gang while the plan can't see it (a raise from a
    lit gang and an off bulb would dip the gang to the bottom; a lower or stop would answer off while the gang is
    lit). Without it (get_attributes, which averages the members it can read), only a group with no other available
    light is refused. A groupcast-only action never checks this. Checked before anything is sent, so a named group
    raises, as core's rule for a group none of whose members runs has it."""
    if not target.is_group or not (listed := expand_group(hass, target)):
        return None
    lights = [member for member in listed if _available(member)]
    if not lights:
        return None
    fails = any if every else all
    return Reason.NOT_ADDRESSABLE if fails(not member.addressable for member in lights) else None


def _available(member: Target) -> bool:
    """A member with a light HA has and can reach: a stand-in has no state."""
    return member.state is not None and member.state.state != STATE_UNAVAILABLE


def _members(hass: HomeAssistant, group: Target, addresses: Iterable[str]) -> tuple[list[Target], bool]:
    """A target per member device HA has, sorted by entity_id: its entity in the group's domain, or a stand-in when
    HA resolves none; and whether every address has a device. A device on two endpoints is listed twice, and counts
    once, keyed by its device.

    A device with more than one Z2M entity in the group's domain, disabled ones counted (`addressing.endpoints`, the
    count addressing.not_addressable refuses such a device's entities by when targeted themselves), is listed by its
    first, not addressable (Target.addressable): its class counts, but no action addresses it on its own. The group
    holds one endpoint of it, and DeviceSide's set and get topics name the device alone, so Z2M would send the call
    to the device's default endpoint, maybe a gang the user didn't target
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
        # Only Z2M's own entities: a switch_as_x light on the same device is no endpoint of it.
        lights = [e for e in own if e.domain == group.domain and e.platform == "mqtt"]
        resolved = resolve_members(hass, registry, group, "mqtt", [lights[0].unique_id]) if lights else []
        if resolved:
            several = endpoints(hass, device.id, group.domain)
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
