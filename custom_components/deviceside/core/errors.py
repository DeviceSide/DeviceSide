from enum import StrEnum

from homeassistant.exceptions import ServiceNotSupported, ServiceValidationError

from ..const import DOMAIN

# The call touches an Experimental scope item and the Experimental features option is off.
EXPERIMENTAL_OFF = "experimental_off"


class Reason(StrEnum):
    """Reason keys that core and adapters both return or test for, defined once: the dispatcher's skip-vs-raise
    turns on the first two (docs/action-behavior.md), so a copy that drifted would change it. The class refusals
    (docs/evidence.md, Device classes) are defined here too, raised if named and skipped if not, as any other."""

    # The config entry behind the target isn't loaded: unavailable, as core treats an entity whose integration isn't up.
    INTEGRATION_NOT_LOADED = "integration_not_loaded"
    # A group with no members holds nothing to act on, which is not a reason it can't: it is skipped, never raised.
    EMPTY_GROUP = "empty_group"
    # The integration can't address the target (no device address, a nested wrapper, a group member it can't address
    # on its own: Target.addressable): raised if named, else skipped.
    NOT_ADDRESSABLE = "not_addressable"
    # The target's class (a native group: a member's) has no known call that works: AdapterScope.doesnt_work.
    DOESNT_WORK = "doesnt_work"
    # The target's class (a native group: a member's) needs a call that isn't built: the integration names it, and the
    # adapter's scope holds it in neither capabilities nor doesnt_work (AdapterScope.not_supported, where it says why).
    NOT_SUPPORTED = "not_supported"
    # The target's class rests on what DeviceSide doesn't know yet (a device not yet placed, a native group's
    # membership), or can't be named at all (None), on an adapter whose call harms a class it could be: refused even
    # with Experimental features on (docs/evidence.md, Device classes). Usually transient: a device not yet placed
    # clears once the integration has reported it, and a group whose membership isn't listed yet once it is; a target
    # that can't be classed at all (an entity with no device, a classifier that raised) stays refused.
    CLASS_UNKNOWN = "class_unknown"
    # A native group with a member whose class takes a call of its own (AdapterScope.own_calls): the group's call isn't
    # the member's, so the group falls back to its members; raised for the group only when none of them runs.
    OWN_CALL = "own_call"


class TargetNotSupported(ServiceNotSupported):
    """A target the caller named can't take the action: core's ServiceNotSupported, with our reason in it. A target
    refused for experimental_off gets a message of its own, saying how to let it through, and one whose class doesn't
    work, or isn't supported yet and has an entry, a message carrying why (`why`, the entry's reason), each under its
    reason's own key (`doesnt_work`, `not_supported`; any other reason with a why reads as doesn't work). One refused as
    class_unknown gets one saying it clears once the integration (`integration`, its title, which the dispatcher always
    passes) has reported the device; without the title it gets the plain refusal, never an untranslated name."""

    def __init__(self, entity_id: str, reason: str, why: str | None = None, integration: str | None = None) -> None:
        placeholders = {"entity_id": entity_id, "reason": reason}
        if reason == EXPERIMENTAL_OFF:
            key = EXPERIMENTAL_OFF
        elif reason == Reason.CLASS_UNKNOWN and integration is not None:
            key, placeholders["integration"] = Reason.CLASS_UNKNOWN.value, integration
        elif why is not None:
            # A not yet supported class reads "yet"; a doesn't-work one doesn't, as no known call works on it.
            key = Reason.NOT_SUPPORTED.value if reason == Reason.NOT_SUPPORTED else Reason.DOESNT_WORK.value
            placeholders["why"] = why
        else:
            key = "target_not_supported"
        # Skips ServiceNotSupported.__init__, which would set core's own translation key.
        ServiceValidationError.__init__(
            self, translation_domain=DOMAIN, translation_key=key, translation_placeholders=placeholders
        )
        self.reason = reason
