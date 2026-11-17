"""Plans each call's targets by adapter, gates them, and runs the adapters. What an integration declares for groups
(is_group, expand_group, AdapterScope.native_groups) is docs/design.md, Groups; how the dispatcher applies it is here.

Planning. Targets are bucketed by adapter (none: no_adapter). For each, the fields it lacks (fields.lacking: a light's,
minus AdapterScope.unlisted) and the scope's `drops` are dropped, then supports() checks what is left: domain and
fields in scope, then the adapter's own reasons. Then the class, a call left nothing to send first: unchanged with
fields_dropped, never refused. Then AdapterScope.refusal, in order: where the call harms a class (AdapterScope.harms),
an Unplaced or None class as class_unknown; a class in no_known_method as no_known_method, with its reason; one in
not_built, or in neither it nor capabilities, as not_built, with NotBuilt.reason where it has an entry. Then the
Experimental gate (below).

Native groups. One an adapter addresses as one takes its members' classes, from expand_group, and its weakest member's
level for the gate; on an integration that names no classes it runs whole. An empty one (expand_group lists no members)
is skipped silently, named or not, as core skips an empty group; so is one an adapter finds empty (Reason.EMPTY_GROUP).
- Fallback. When a member's class has no known method, is not built yet, or isn't placed where a call harms, or takes a
  call of its own (own_calls: a branch in execute the group's call isn't), or, while Experimental features is off, is
  Experimental (the adapter, domain and fields not flagged), the group falls back to its members: each available one not
  already a target is planned on its own, indirect, so the good ones run and a refused or flagged one is skipped and
  logged; a member also named raises, as its own target. A classifier that raised (logged) leaves the group's class
  unknown, so where a call harms, or while Experimental features is off, it falls back too, and each member is classed
  again. With Experimental features on, a group whose weakest member is Experimental, or whose class is unknown where no
  call harms, runs whole, as one command; a member named beside it then gets its own command as well as the group's.
- Stand-ins and members it can't address. A member expand_group lists for its class that the integration can't address
  on its own (Target.addressable false: a Z2M device with several lights) is skipped with its class's refusal if it has
  one, else not_addressable, named by its device, and answers for nothing. So is a stand-in (Target.stand_in: a member
  device with no entity in the group's domain, listed by the group's own entity with no state, as a plug in a Z2M light
  group), named as a member device of the group, available or not, so the device the group's call would have reached
  gets an entry saying it didn't; unless a target on its device was planned too, which answers for it, the group
  included. Any other member known unavailable is left out quietly. Every member planned is indirect.
- Unknowable membership (no expand_group, or it answered None or raised, logged). Where a call harms, the group is
  refused as class_unknown, with Experimental features on or off; elsewhere it counts as Experimental, refused as
  experimental_off while the option is off. It can't fall back, so it is refused whole. For an adapter without
  native_groups it is refused as group_not_supported, as with no expand_group.
- For an adapter without native_groups, core plans a group whose members are listed as the fallback does (stand-ins
  skipped, the unavailable left out, each indirect, a member also named kept as the caller's target).
- Refusal priority. A group that falls back gets no result of its own: its planned members answer for it, one already a
  target included, so naming a member beside it changes nothing. Only when none of its members is planned or left
  nothing to do (each refused, gated or unavailable) is the group itself refused, raised if named, else skipped and
  logged: with the refusal its members' classes gave it, or experimental_off; for own_call, a skipped member's, ranked
  experimental_off, then a class's refusal, then any other, not_addressable last (_rank), own_call itself only when none
  was skipped (each unavailable).

Experimental gating, the one place the option gates anything (docs/evidence.md, The experimental flag). After supports()
passes and fields are dropped, a call's level is the weakest of its domain, its class in that domain (a native group's:
its weakest member's; one the integration can't name, or whose entry holds other domains alone, counts as Experimental)
and the fields it still carries; an adapter flagged whole has every domain Experimental. An Experimental call is
refused as experimental_off while the option is off, a named target raising its own message. A call left nothing to
send is unchanged, not refused.

Running. A run's durations are clamped to AdapterScope.duration, or its class's own call's limits (own_calls), rounded
to their step_s (core/duration.py). Each adapter runs once per distinct request (its dropped fields and own call),
every run concurrently, under ADAPTER_TIMEOUT_S: Adapter.slot, which gather runs each target in, rejects with timeout
only the targets not done by then, so those that finished keep their results; an execute still busy
ADAPTER_BACKSTOP_S later has all its targets rejected with timeout. An exception from execute rejects its targets
(error); one from a target's send, that target alone (Adapter.gather). A target with no result is rejected
(no_result), a stray result dropped. A named target that can never take the action raises before anything is sent; an
indirect one is skipped and logged; an unavailable one is skipped; a device failure raises once every target has run.
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, replace

from homeassistant.const import ATTR_ENTITY_ID, ENTITY_MATCH_ALL, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, State, split_entity_id
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import target as target_helpers

from . import duration, ha_watch
from .action import Action
from .adapter import Adapter
from .errors import EXPERIMENTAL_OFF, Reason, TargetNotSupported, describe, traceback_is_safe
from .fields import lacking
from .groups import expand_ha_groups
from .models import FAILED, ActionKind, EntityResult, Request, Status, Target, TimedRequest
from .registry import AdapterRegistry
from .resolver import resolve
from .runtime import DEADLINE, get_runtime
from .scope import Level, OwnCall, Unplaced
from ..const import ADAPTER_BACKSTOP_S, ADAPTER_TIMEOUT_S, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _available(state: State | None) -> bool:
    return state is not None and state.state != STATE_UNAVAILABLE


# A target's class, or a native group's members' classes (core/scope.py, AdapterScope.level); None for one the
# integration couldn't name, and an Unplaced one for one it named from partial information. A tuple, one entry per
# member as capability() returned it: an Unplaced class equals its plain class, so a set would drop the flag.
type Classes = tuple[str | None, ...]


@dataclass(frozen=True, slots=True)
class Reached:
    """What a target's call reaches, for planning and its result: its Classes, and for a native group whose members'
    classes are known, `members`, paired by position with `classes`: each member's reported_id, or None for one that
    can't show the call reached it, as core didn't reach it through its own available entity (unavailable, or not
    addressable: a stand-in classed by its device alone, or one of a device's several entities). Availability is
    judged at planning time, from the state the member had then. `members` is empty for any other target, and for a
    group whose classes are unknown, which has `classes` (None,): its membership unlisted, or its classifier
    raised."""

    classes: Classes
    members: tuple[str | None, ...] = ()


# One execute: the adapter, the request its targets get, the targets, the fields dropped, what each reaches, and their
# class's own call (AdapterScope.own_call), None for the adapter's execute.
type Run = tuple[Adapter, Request, list[Target], frozenset[str], dict[str, Reached], OwnCall | None]


def _placed(name: str | None) -> bool:
    return name is not None and not isinstance(name, Unplaced)


def _classed(result: EntityResult, target: Target, reached: Reached) -> EntityResult:
    """The result with the class the call reached (docs/action-behavior.md, What a response looks like): a
    target's, or a native group's members', sorted and each once. None when the integration couldn't name one or
    named it Unplaced, for a group any member's, so a group's list never passes for its whole membership, nor a
    class that could still move for a known one. A native group also gets each member's class (plan Decision 66),
    every member with one that core reached through its own available entity: a member the integration couldn't
    place, and one core didn't reach that way (Reached), is left out, and only they."""
    classes = reached.classes
    if reached.members and (
        by_member := {
            member: name
            for member, name in zip(reached.members, classes, strict=True)
            if member is not None and _placed(name)
        }
    ):
        result = replace(result, member_classes=dict(sorted(by_member.items())))
    if not classes or not all(_placed(name) for name in classes):
        return result
    if target.is_group:
        return replace(result, classes=tuple(sorted(set(classes))))
    return replace(result, classes=classes[0])


def _device_of(member: Target) -> str:
    """What an unaddressable member's skip is named by: its device, as the entity it is listed by may not be the one
    the group holds, and a stand-in's (Target.stand_in) is the group's own."""
    if member.stand_in:
        return f"a member device of {member.reported_id}"
    return f"the device of {member.reported_id}"


# Each device's targets, by the device's id: the targets planned as they came, stand-ins left out, whose entries
# answer for a stand-in of the same device (_fallback, _unanswered).
type ByDevice = dict[str, set[str]]


def _by_device(targets: list[Target]) -> ByDevice:
    by_device: ByDevice = {}
    for target in targets:
        if target.device is not None and not target.stand_in:
            by_device.setdefault(target.device.id, set()).add(target.reported_id)
    return by_device


def _targeted(member: Target, by_device: ByDevice) -> set[str]:
    """The targets on a stand-in's device, which answer for it; none for any other member."""
    return by_device.get(member.device.id, set()) if member.stand_in and member.device is not None else set()


def _rank(reason: str) -> int:
    """Which member's skip a group refused for own_call takes (_unanswered): experimental_off, which says how to let
    the call through; then a class's refusal, which says why it can't; then any other; not_addressable last."""
    if reason == EXPERIMENTAL_OFF:
        return 0
    if reason in (Reason.NO_KNOWN_METHOD, Reason.NOT_BUILT, Reason.CLASS_UNKNOWN):
        return 1
    return 3 if reason == Reason.NOT_ADDRESSABLE else 2


def _skip(
    entity_id: str,
    named: bool,
    reason: str,
    integration: str | None = None,
    why: str | None = None,
    title: str | None = None,
) -> list[EntityResult]:
    """A target that can't take the action: raise if the caller named it (with `why`, a no known method or not built
    yet entry's reason, and `title`, the integration's, which a class_unknown message names), else the result
    that skips it."""
    if reason == Reason.EMPTY_GROUP:
        return []
    if named:
        raise TargetNotSupported(entity_id, reason, why, title)
    return [EntityResult(entity_id, Status.UNSUPPORTED, integration=integration, detail=reason)]


def _unanswered(
    adapter: Adapter,
    fallen: list[tuple[Target, list[Target], str, str | None]],
    answered: set[str],
    by_device: ByDevice,
    title: str,
    skipped: list[EntityResult],
) -> list[EntityResult]:
    """Each group that fell back with no member planned or left nothing to do, refused with its reason: raised if
    named, else skipped. A group a member answers for gets no result of its own, nor one a target on a stand-in's
    device answers for (`by_device`). One that fell back only because a member takes a call of its own (own_call) is
    refused with its members' reason, ranked by _rank (`skipped`: the skips so far); own_call only when none was
    skipped (each unavailable)."""
    results: list[EntityResult] = []
    for group, members, reason, why in fallen:
        # A member left unaddressable answers for nothing, even when its entity ran as a target of its own; a
        # stand-in's device does, through its own target.
        if any(
            (member.addressable and member.reported_id in answered) or bool(_targeted(member, by_device) & answered)
            for member in members
        ):
            continue
        if reason == Reason.OWN_CALL:
            # An unaddressable member's skip names its device (_device_of), so match that form too; a stand-in's
            # reported_id is the group's own, so only that form names it, or its device's own target.
            ids: set[str] = set()
            for member in members:
                ids |= {_device_of(member)} | _targeted(member, by_device)
                if not member.stand_in:
                    ids.add(member.reported_id)
            details = [r.detail for r in skipped if r.entity_id in ids and r.status is Status.UNSUPPORTED and r.detail]
            reason = min(details, key=_rank, default=reason)
        results += _skip(group.reported_id, group.named, reason, adapter.integration, why, title)
    return results


def _members_planned(members: list[Target], seen: set[str], by_device: ByDevice) -> list[Target]:
    """The members a native group is planned as, each indirect (named=False; a stand-in, the group's own entity,
    too): none raises, and only _unanswered refuses a group that fell back. An available one not already a target
    (`seen`), which a target already answers for; and each stand-in (Target.stand_in), which _plan skips, so the
    device the group's call would have reached gets an entry saying it didn't, unless a target on its device
    (`by_device`) answers for it. A stand-in has no state to judge it unavailable by; any other member known
    unavailable, unaddressable or not, is left out quietly, as core skips one in an area."""
    return [
        replace(member, named=False)
        for member in members
        if (member.stand_in and not _targeted(member, by_device))
        or (not member.stand_in and _available(member.state) and member.reported_id not in seen)
    ]


class Dispatcher:
    def __init__(self, hass: HomeAssistant, registry: AdapterRegistry):
        self.hass = hass
        self.registry = registry

    async def handle(self, action: type[Action], call: ServiceCall) -> ServiceResponse:
        """Act on every target that can take the action, as core's entity actions do (docs/action-behavior.md).

        A named target that can never take it raises before anything is sent; an indirect one is skipped and logged.
        Unavailable targets are skipped. A device failure raises once every target has run.
        """
        request = replace(action.parse(self.hass, call), context=call.context)
        if call.data.get(ATTR_ENTITY_ID) == ENTITY_MATCH_ALL:
            # Core passes referenced=None for "all": every entity of the domains is indirect, so none raises or logs.
            selected = target_helpers.SelectedEntities(
                indirectly_referenced=set(self.hass.states.async_entity_ids(action.domains))
            )
        else:
            selection = target_helpers.TargetSelection(call.data)
            if not selection.has_any_target:
                # Core returns here, and raises no_entities_matched only when the caller asked for a response.
                return self._respond(action, call, [])
            # expand_group=False: we expand group.* ourselves so members remember which group they came from.
            selected = target_helpers.async_extract_referenced_entity_ids(self.hass, selection, expand_group=False)
        members, _ = expand_ha_groups(self.hass, sorted(selected.referenced | selected.indirectly_referenced))

        results, targets = self._resolve(action, selected, members)
        if targets:
            # A light call from HA just before this one may still be dropping predictions this one would plan from.
            await ha_watch.settled(self.hass)
            results += await action.run(self.hass, request, targets, self)
        order = {entity_id: index for index, entity_id in enumerate(members)}
        results.sort(key=lambda result: order.get(result.entity_id, len(order)))
        return self._respond(action, call, results)

    def _resolve(
        self, action: type[Action], selected: target_helpers.SelectedEntities, members: dict[str, str | None]
    ) -> tuple[list[EntityResult], list[Target]]:
        """The targets to plan, and a skip for each indirect one that resolution already rules out."""
        results: list[EntityResult] = []
        missing: set[str] = set()
        targets: list[Target] = []
        for entity_id, via_group in members.items():
            named = entity_id in selected.referenced
            if split_entity_id(entity_id)[0] not in action.domains:
                # Core's entity actions never see another domain's entities in an area, so only a named one raises.
                if named:
                    raise TargetNotSupported(entity_id, "domain_not_supported")
                continue
            if not _available(self.hass.states.get(entity_id)):
                missing.add(entity_id)
                continue
            target = resolve(self.hass, self.registry, entity_id, via_group)
            if target == Reason.INTEGRATION_NOT_LOADED:
                missing.add(entity_id)
            elif isinstance(target, str):
                results += _skip(entity_id, named, target)
            elif refused := self.registry.unsupported.get(target.integration):
                # A gateway or API DeviceSide never supports (Hue's v1 bridge): every action, with why.
                why = refused.unsupported
                results += _skip(entity_id, named, Reason.INTEGRATION_NOT_SUPPORTED, target.integration, why)
            elif target.domain not in action.domains:
                results += _skip(entity_id, named, "domain_not_supported", target.integration)
            else:
                targets.append(replace(target, named=named))
        selected.log_missing(missing & selected.referenced, _LOGGER)
        return results, targets

    @staticmethod
    def _respond(action: type[Action], call: ServiceCall, results: list[EntityResult]) -> ServiceResponse:
        """Log the skipped targets, raise on a device failure or an empty response, else answer for those that ran."""
        # An empty group is skipped silently, whether planning found it so or an adapter that reads membership did.
        if skipped := [r for r in results if r.status is Status.UNSUPPORTED and r.detail != Reason.EMPTY_GROUP]:
            _LOGGER.warning(
                "%s skipped targets that can't take it: %s, %s",
                action.key,
                ", ".join(f"{result.entity_id} ({result.detail})" for result in skipped),
                "so they aren't read" if action.kind is ActionKind.QUERY else "so they got no command",
            )
        ran = [result for result in results if result.status is not Status.UNSUPPORTED]
        if failed := [result for result in ran if result.status in FAILED]:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="targets_failed",
                translation_placeholders={
                    "summary": ", ".join(f"{result.entity_id}: {result.detail or result.status}" for result in failed)
                },
            )
        if not call.return_response:
            return None
        if not ran:
            # Core raises here too: the caller asked for data and nothing could give it.
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_entities_matched")
        if action.kind is ActionKind.QUERY:
            # Core's shape for data, as weather.get_forecasts returns it: each target's own data under its entity_id.
            # The class rides the data, as an attribute would (docs/action-behavior.md).
            return {result.entity_id: (result.data or {}) | result.class_keys() for result in ran}
        return {result.entity_id: result.as_response() for result in ran}

    async def run_adapters(self, action_key: str, request: Request, targets: list[Target]) -> list[EntityResult]:
        """Plan every target, then run each adapter once per distinct request, every run concurrently.

        Planning buckets targets by adapter, expands native groups an adapter can't address, drops the fields each
        target lacks and checks supports() on what is left, then the target's class (a native group's: its members'):
        where the adapter's call harms a class, one not yet placed (Unplaced, or None) is refused as class_unknown,
        with Experimental features on or off; one the scope lists in no_known_method, or the integration names but the
        scope doesn't serve, is refused; a native group so refused falls back to its members when the integration can
        list them (the module docstring, Native groups), and an empty one is skipped silently. A flagged call, one
        touching an Experimental scope item, is refused while the Experimental features option is off; a native group
        flagged by a member's class alone falls back to its members instead, as does one with a member whose class
        takes a call of its own (AdapterScope.own_calls), and a target of such a class runs apart, on that call and its
        duration limits. A named target that can't take the action raises then, before anything is sent. Returns a
        result per target that ran or was left nothing to do, each with its class, and an unsupported one per indirect
        target skipped.
        """
        results: list[EntityResult] = []
        buckets: dict[str, tuple[Adapter, list[Target]]] = {}
        for target in targets:
            if (adapter := self.registry.adapter(action_key, target.integration)) is None:
                results += _skip(target.reported_id, target.named, "no_adapter", target.integration)
                continue
            buckets.setdefault(target.integration, (adapter, []))[1].append(target)

        runs: list[Run] = []
        experimental_on = get_runtime(self.hass).experimental_features
        for adapter, bucket in buckets.values():
            runs += self._plan(
                adapter, request, self._expand_native_groups(adapter, bucket, results), results, experimental_on
            )

        for adapter_results in await asyncio.gather(*(self._run_adapter(*run) for run in runs)):
            results.extend(adapter_results)
        return results

    def _plan(
        self,
        adapter: Adapter,
        request: Request,
        targets: list[Target],
        results: list[EntityResult],
        experimental_on: bool,
    ) -> list[Run]:
        """One adapter's runs, one per set of dropped fields and own call so every target in a run gets the same
        request and call; each target skipped or left nothing to do goes in results instead.

        A native group that falls back to its members gets no result of its own: they answer for it. Only when none
        of its members was planned or left nothing to do (each refused, gated or unavailable) is the group itself
        refused, with its reason, raised if named, once every target is judged."""
        by_run: dict[tuple[frozenset[str], OwnCall | None], list[Target]] = {}
        reached: dict[str, Reached] = {}
        pending = deque(targets)
        seen = {target.reported_id for target in pending}
        # Each group that fell back, its members and the reason it would be refused with; the targets that answer.
        fallen: list[tuple[Target, list[Target], str, str | None]] = []
        answered: set[str] = set()
        by_device = _by_device(targets)
        # The integration's title, which a class_unknown message names.
        title = self.registry.integrations[adapter.integration].title
        while pending:
            target = pending.popleft()
            dropped = lacking(target, request, adapter.scope.unlisted) | (
                request.fields_present() & adapter.scope.drops
            )
            reduced = request.without(dropped)
            if not target.addressable:
                # A member a group fell back to that the integration can't address on its own: the call could reach
                # an entity the caller didn't target (Target.addressable). Its class's refusal comes first, so a
                # member whose class harms says so. It stands for its whole device, so the skip names the device
                # (_device_of), with no address.
                reason, why = adapter.scope.refusal(
                    self._reached(adapter, target, None).classes, failure_harms=adapter.failure_harms
                ) or (
                    Reason.NOT_ADDRESSABLE,
                    None,
                )
                results += _skip(_device_of(target), target.named, reason, adapter.integration, why, title)
                continue
            if reason := adapter.supports(self.hass, reduced, target):
                results += _skip(target.reported_id, target.named, reason, adapter.integration, title=title)
                continue
            members = self._listed(adapter, target)
            if members == []:
                # Core's group expansion yields nothing for an empty group, so it is skipped silently.
                results += _skip(target.reported_id, target.named, Reason.EMPTY_GROUP)
                continue
            reached[target.reported_id] = here = self._reached(adapter, target, members)
            found = here.classes
            if reduced.nothing_to_do():
                answered.add(target.reported_id)
                results.append(
                    _classed(adapter.result(target, Status.UNCHANGED, detail="fields_dropped"), target, here)
                )
            elif refused := adapter.scope.refusal(
                found, group=members is not None, failure_harms=adapter.failure_harms
            ):
                # A native group falls back to its members, each judged alone: the good ones run, a refused one is
                # skipped as indirect. So a group with one member not yet placed runs the rest, where the call harms
                # a class, and one with a member that takes a call of its own gives each member its own; one of
                # unknown membership can't fall back, and is refused whole.
                if members is not None:
                    fallen.append((target, members, *refused))
                    pending.extend(self._fallback(adapter, target, members, seen, by_device, refused[0]))
                else:
                    results += _skip(
                        target.reported_id, target.named, refused[0], adapter.integration, refused[1], title
                    )
            elif not experimental_on and self._experimental(adapter, reduced, target, found):
                # A native group flagged only by a member's class falls back the same way: the members of Verified
                # or Documented classes run, the flagged one is skipped (raised only if named on its own).
                if members is not None and self._flagged_by_class_alone(adapter, reduced, target):
                    fallen.append((target, members, EXPERIMENTAL_OFF, None))
                    pending.extend(self._fallback(adapter, target, members, seen, by_device, EXPERIMENTAL_OFF))
                else:
                    results += _skip(target.reported_id, target.named, EXPERIMENTAL_OFF, adapter.integration)
            else:
                answered.add(target.reported_id)
                by_run.setdefault((dropped, adapter.scope.own_call(found)), []).append(target)
        results += _unanswered(adapter, fallen, answered, by_device, title, results)
        return [
            (adapter, request.without(dropped), ready, dropped, reached, own)
            for (dropped, own), ready in by_run.items()
        ]

    def _experimental(self, adapter: Adapter, request: Request, target: Target, classes: Classes) -> bool:
        """Whether the call is flagged experimental: an Experimental item it touches, its domain (an adapter flagged
        whole has every domain Experimental), class (a native group's: its weakest member's) or a field it carries.
        The one place the option gates anything; adapters never read it (docs/evidence.md)."""
        return adapter.scope.level(target.domain, classes, request.fields_present()) is Level.EXPERIMENTAL

    def _flagged_by_class_alone(self, adapter: Adapter, request: Request, target: Target) -> bool:
        """Whether a flagged call would pass but for its classes: neither its domain nor a field it carries is
        Experimental, so a group's members can run one by one."""
        return adapter.scope.level(target.domain, (), request.fields_present()) is not Level.EXPERIMENTAL

    def _listed(self, adapter: Adapter, target: Target) -> list[Target] | None:
        """A native group's members, for an integration that names classes: what its classes come from and what it
        falls back to. `[]` only for a group known to have no members; None when unknown, and for any other
        target."""
        if not target.is_group or self.registry.integrations[adapter.integration].capability is None:
            return None
        return self._members(adapter, target)

    def _reached(self, adapter: Adapter, target: Target, members: list[Target] | None) -> Reached:
        """The target's class, or a native group's members' classes (`members`, as _listed gives them) beside each
        member's reported_id, as IntegrationInfo.capability names them; no classes for an integration that names
        none. A group whose members can't be listed, and a classifier that raised (logged), give (None,), which the
        gate weighs as Experimental, as an unknown device, and which, where the call harms a class, the scope refuses
        (AdapterScope.refusal)."""
        if (capability := self.registry.integrations[adapter.integration].capability) is None:
            return Reached(())
        listed = (members or []) if target.is_group else [target]
        try:
            # Keep each member's class as capability() returned it, in order, never deduplicated: an Unplaced class
            # equals its plain class, so a set would merge it with a placed member's and lose the flag the harm check
            # reads, and the order pairs each class with its member.
            found: Classes = tuple(capability(self.hass, member) for member in listed)
        except Exception:  # noqa: BLE001 - a classifier's bug must not abort the call: the class counts as unknown
            _LOGGER.exception(
                "%s on %s: classing %s failed, so it is treated as an unknown class",
                adapter.action,
                adapter.integration,
                target.reported_id,
            )
            found = ()
        _LOGGER.debug(
            "%s on %s: %s is class %s", adapter.action, adapter.integration, target.reported_id, found or (None,)
        )
        if not found:
            return Reached((None,))
        # A member is credited only through its own entity, with a state to show the call reached it, as _fallback
        # reaches only an available one; a stand-in has neither (zigbee2mqtt/members.py, _stand_in).
        ids = (
            tuple(member.reported_id if member.addressable and _available(member.state) else None for member in listed)
            if target.is_group
            else ()
        )
        return Reached(found, ids)

    def _members(self, adapter: Adapter, target: Target) -> list[Target] | None:
        """A native group's members, as the integration's expand_group lists them; None, membership unknowable, when it
        has no expand_group, or it answered None or raised, which is logged."""
        if (expand := self.registry.integrations[adapter.integration].expand_group) is None:
            return None
        try:
            return expand(self.hass, target)
        except Exception:  # noqa: BLE001 - one group's listing must not abort the call
            _LOGGER.exception(
                "%s on %s: listing %s failed, so its members are unknown",
                adapter.action,
                adapter.integration,
                target.reported_id,
            )
            return None

    @staticmethod
    def _fallback(
        adapter: Adapter, group: Target, members: list[Target], seen: set[str], by_device: ByDevice, reason: str
    ) -> list[Target]:
        """The members a refused or class-flagged native group falls back to (_members_planned), marked seen."""
        fresh = _members_planned(members, seen, by_device)
        _LOGGER.debug("%s: %s falls back to its members (%s)", adapter.action, group.reported_id, reason)
        seen.update(member.reported_id for member in fresh)
        return fresh

    def _expand_native_groups(
        self, adapter: Adapter, bucket: list[Target], results: list[EntityResult]
    ) -> list[Target]:
        if adapter.scope.native_groups or not any(target.is_group for target in bucket):
            return bucket
        expanded: list[Target] = []
        by_device = _by_device(bucket)
        for target in bucket:
            if not target.is_group:
                expanded.append(target)
            elif (members := self._members(adapter, target)) is None:
                # No expand_group, or one that answered None or raised (logged): membership is unknowable here.
                results += _skip(target.reported_id, target.named, "group_not_supported", adapter.integration)
            else:
                expanded += _members_planned(members, set(), by_device)
        # One copy per entity, each stand-in apart, as its reported_id is its group's. A member the caller also named
        # is the caller's own target, whichever copy came first, so it raises rather than skips, as _plan keeps it.
        by_id: dict[str, Target] = {}
        stand_ins: list[Target] = []
        for target in expanded:
            if target.stand_in:
                stand_ins.append(target)
            elif target.named:
                by_id[target.reported_id] = target
            else:
                by_id.setdefault(target.reported_id, target)
        return list(by_id.values()) + stand_ins

    async def _run_adapter(
        self,
        adapter: Adapter,
        request: Request,
        targets: list[Target],
        dropped: frozenset[str],
        reached: dict[str, Reached],
        own: OwnCall | None,
    ) -> list[EntityResult]:
        clamped_to = None
        if isinstance(request, TimedRequest):
            request, clamped_to = duration.clamp(request, adapter.scope.call_limits(own))
        # Each run is its own task (run_adapters gathers them), so the deadline set here is this run's alone.
        deadline = asyncio.get_running_loop().time() + ADAPTER_TIMEOUT_S
        DEADLINE.set(deadline)
        try:
            # Adapter.slot holds each command to the deadline; this catches an execute still busy outside it.
            async with asyncio.timeout_at(deadline + ADAPTER_BACKSTOP_S):
                if own is None:
                    raw = await adapter.execute(self.hass, request, targets)
                else:
                    raw = await adapter.execute_own(self.hass, request, targets, own)
        except TimeoutError:
            _LOGGER.warning(
                "%s on %s timed out after %ss for %s, %s",
                adapter.action,
                adapter.integration,
                ADAPTER_TIMEOUT_S + ADAPTER_BACKSTOP_S,
                ", ".join(target.reported_id for target in targets),
                adapter.consequence,
            )
            return [adapter.result(target, Status.REJECTED, detail="timeout") for target in targets]
        except Exception as err:
            # The catch-all of an adapter's own bug, so the traceback is the diagnosis (docs/logging.md); an HTTP
            # client error's is kept out, as it prints the request's URL and headers.
            _LOGGER.exception(
                "%s on %s failed for %s: %s, %s",
                adapter.action,
                adapter.integration,
                ", ".join(target.reported_id for target in targets),
                describe(err),
                adapter.consequence,
                exc_info=traceback_is_safe(err),
            )
            return [adapter.result(target, Status.REJECTED, detail="error") for target in targets]
        return self._reconcile(adapter, targets, raw, clamped_to, dropped, reached)

    def _reconcile(
        self,
        adapter: Adapter,
        targets: list[Target],
        raw: list[EntityResult],
        clamped_to: float | None,
        dropped: frozenset[str],
        reached: dict[str, Reached],
    ) -> list[EntityResult]:
        """One result per target: stray ones dropped, missing ones rejected. A run the dispatcher dropped fields
        from says so in detail, unless the adapter gave one. Each carries the class the call reached."""
        by_id: dict[str, EntityResult] = {}
        expected = {target.reported_id for target in targets}
        for result in raw:
            if result.entity_id in expected and result.entity_id not in by_id:
                by_id[result.entity_id] = result
            else:
                _LOGGER.debug(
                    "%s on %s: dropping stray result for %s", adapter.action, adapter.integration, result.entity_id
                )
        out = []
        for target in targets:
            result = by_id.get(target.reported_id) or adapter.result(target, Status.REJECTED, detail="no_result")
            if result.status not in FAILED:
                if dropped and result.detail is None:
                    result = replace(result, detail="fields_dropped")
                if clamped_to is not None and result.clamped_to is None:
                    result = replace(result, clamped_to=clamped_to)
                result = _classed(result, target, reached[target.reported_id])
            out.append(result)
        return out
