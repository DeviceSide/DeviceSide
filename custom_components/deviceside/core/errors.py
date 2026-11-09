from homeassistant.exceptions import ServiceNotSupported, ServiceValidationError

from ..const import DOMAIN

# The call touches an Experimental scope item and the Experimental features option is off.
EXPERIMENTAL_OFF = "experimental_off"


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
