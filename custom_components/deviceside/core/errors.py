import errno
from enum import StrEnum

import aiohttp
from homeassistant.exceptions import ServiceNotSupported, ServiceValidationError

from ..const import DOMAIN

# The call touches an Experimental scope item and the Experimental features option is off.
EXPERIMENTAL_OFF = "experimental_off"


class Reason(StrEnum):
    """Reason keys that core and adapters both return or test for, defined once: the dispatcher's skip-vs-raise
    turns on the first two (docs/action-behavior.md), so a copy that drifted would change it."""

    # The config entry behind the target isn't loaded: unavailable, as core treats an entity whose integration isn't up.
    INTEGRATION_NOT_LOADED = "integration_not_loaded"
    # A group with no members holds nothing to act on, which is not a reason it can't: it is skipped, never raised.
    EMPTY_GROUP = "empty_group"
    # The integration can't address the target (no device address, a nested wrapper): raised if named, else skipped.
    NOT_ADDRESSABLE = "not_addressable"


class TargetNotSupported(ServiceNotSupported):
    """A target the caller named can't take the action: core's ServiceNotSupported, with our reason in it. A target
    refused for experimental_off gets a message of its own, saying how to let it through."""

    def __init__(self, entity_id: str, reason: str) -> None:
        # Skips ServiceNotSupported.__init__, which would set core's own translation key.
        ServiceValidationError.__init__(
            self,
            translation_domain=DOMAIN,
            translation_key=EXPERIMENTAL_OFF if reason == EXPERIMENTAL_OFF else "target_not_supported",
            translation_placeholders={"entity_id": entity_id, "reason": reason},
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
