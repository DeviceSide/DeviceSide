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

    Not an aiohttp error's: its repr holds the request's URL and headers (a Hue bridge's address, a resource id, the
    hue-application-key) and its str the URL or host. It gives its type, a response error its status and reason, and a
    connection error the OS error's text.
    """
    if isinstance(err, aiohttp.ClientResponseError):
        return f"{type(err).__name__}(status={err.status}, message={err.message!r})"
    if isinstance(err, aiohttp.ClientConnectorError) and err.os_error.strerror:
        return f"{type(err).__name__}({err.os_error.strerror!r})"
    if isinstance(err, aiohttp.ClientError):
        return f"{type(err).__name__}()"
    return repr(err)


def traceback_is_safe(err: BaseException) -> bool:
    """Whether a log line may carry err's traceback, whose last line is str(err): not an aiohttp error's (describe)."""
    return not isinstance(err, aiohttp.ClientError)
