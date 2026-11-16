import errno
from enum import StrEnum

import aiohttp
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
    # No integration DeviceSide has takes the entity's platform, or one declared only to refuse a gateway or API claims
    # it (IntegrationInfo.unsupported, whose reason a named target raises with).
    INTEGRATION_NOT_SUPPORTED = "integration_not_supported"
    # The integration can't address the target (no device address, a nested wrapper, a group member it can't address
    # on its own: Target.addressable): raised if named, else skipped.
    NOT_ADDRESSABLE = "not_addressable"
    # The target's class (a native group: a member's) has no known method: no known call works on it, or the only one
    # known is unsafe (AdapterScope.no_known_method, where it says which).
    NO_KNOWN_METHOD = "no_known_method"
    # The target's class (a native group: a member's) is not built yet: it needs a call nobody has built, known or
    # plausible. The integration names it, and the adapter's scope holds it in neither capabilities nor
    # no_known_method (AdapterScope.not_built, where it says why).
    NOT_BUILT = "not_built"
    # The target's class rests on what DeviceSide doesn't know yet (a device not yet placed, a native group's
    # membership), or can't be named at all (None), on an adapter whose call harms a class it could be: refused even
    # with Experimental features on (docs/evidence.md, Device classes). Usually transient: a device not yet placed
    # clears once the integration has reported it, and a group whose membership isn't listed yet once it is; a target
    # that can't be classed at all (an entity with no device, a classifier that raised) stays refused.
    CLASS_UNKNOWN = "class_unknown"
    # A native group with a member whose class takes a call of its own (AdapterScope.own_calls): the group's call isn't
    # the member's, so the group falls back to its members; raised for the group only when none of them runs, and then
    # with a member's reason where one was skipped (dispatcher._unanswered), so this only when each is unavailable.
    OWN_CALL = "own_call"


class TargetNotSupported(ServiceNotSupported):
    """A target the caller named can't take the action: core's ServiceNotSupported, with our reason in it. A target
    refused for experimental_off gets a message of its own, saying how to let it through, and one whose class has no
    known method, or is not built yet and has an entry, a message carrying why (`why`, the entry's reason), each under
    its reason's own key (`no_known_method`, `not_built`; any other reason with a why reads as no known method). One
    refused as
    class_unknown gets one saying it clears once the integration (`integration`, its title, which the dispatcher always
    passes) has reported the device; without the title it gets the plain refusal, never an untranslated name."""

    def __init__(self, entity_id: str, reason: str, why: str | None = None, integration: str | None = None) -> None:
        placeholders = {"entity_id": entity_id, "reason": reason}
        if reason in (EXPERIMENTAL_OFF, Reason.OWN_CALL):
            key = str(reason)
        elif reason == Reason.CLASS_UNKNOWN and integration is not None:
            key, placeholders["integration"] = Reason.CLASS_UNKNOWN.value, integration
        elif why is not None:
            # A class not built yet reads "yet"; one with no known method doesn't, as no known call works on it.
            key = Reason.NOT_BUILT.value if reason == Reason.NOT_BUILT else Reason.NO_KNOWN_METHOD.value
            placeholders["why"] = why
        else:
            key = "target_not_supported"
        # Skips ServiceNotSupported.__init__, which would set core's own translation key.
        ServiceValidationError.__init__(
            self, translation_domain=DOMAIN, translation_key=key, translation_placeholders=placeholders
        )
        self.reason = reason


def describe(err: BaseException) -> str:
    """An upstream error for a log line (docs/logging.md): its repr, as its text is often the diagnosis.

    Not an aiohttp error's, nor one wrapping it (as its args, cause, context, or in an exception group): its repr holds
    the request's URL and headers (a Hue bridge's address, a resource id, the hue-application-key), and its text the URL
    or, where a connect failed, the address asyncio writes into the OS error. It gives the type, a response error its
    status and reason, an SSL error its reason (CERTIFICATE_VERIFY_FAILED), and another connection error the OS error's
    errno name; a wrapper's type wraps that.
    """
    if (client := _client_error(err)) is None:
        return repr(err)
    if isinstance(client, aiohttp.ClientResponseError):
        text = f"{type(client).__name__}(status={client.status}, message={client.message!r})"
    elif isinstance(client, aiohttp.ClientSSLError):
        # Its errno is OpenSSL's code, not the OS's; its reason (CERTIFICATE_VERIFY_FAILED) names no address.
        reason = getattr(client.os_error, "reason", None)
        text = f"{type(client).__name__}({reason})" if reason else f"{type(client).__name__}()"
    elif isinstance(client, aiohttp.ClientConnectorError) and client.os_error.errno:
        text = f"{type(client).__name__}({errno.errorcode.get(client.os_error.errno, client.os_error.errno)})"
    else:
        text = f"{type(client).__name__}()"
    return text if client is err else f"{type(err).__name__}({text})"


def traceback_is_safe(err: BaseException) -> bool:
    """Whether a log line may carry err's traceback, which prints each chained error's text: not where describe hides
    an aiohttp error."""
    return _client_error(err) is None


def _client_error(err: BaseException) -> aiohttp.ClientError | None:
    """The aiohttp error err is or wraps, through its args, cause, context and a group's exceptions; None if none."""
    seen: set[int] = set()
    pending: list[BaseException] = [err]
    while pending:
        if id(current := pending.pop()) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, aiohttp.ClientError):
            return current
        pending += [arg for arg in current.args if isinstance(arg, BaseException)]
        if isinstance(current, BaseExceptionGroup):
            pending += current.exceptions
        pending += [chained for chained in (current.__cause__, current.__context__) if chained is not None]
    return None
