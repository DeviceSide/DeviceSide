"""Shelly Gen2+ over the core shelly integration's RPC connection. Gen1 (CoIoT) devices are unsupported."""

from .clear_auto_off import ShellyClearAutoOff
from .clear_auto_on import ShellyClearAutoOn
from .get_attributes import ShellyGetAttributes
from .lower_brightness import ShellyLowerBrightness
from .raise_brightness import ShellyRaiseBrightness
from .set_attributes import ShellySetAttributes
from .set_auto_off import ShellySetAutoOff
from .set_auto_on import ShellySetAutoOn
from .stop import ShellyStop
from .turn_off_for import ShellyTurnOffFor
from .turn_on_for import ShellyTurnOnFor
from ...core.scope import IntegrationInfo

INTEGRATION = IntegrationInfo(
    key="shelly", title="Shelly", ha_domain="shelly", maintainers=("jasonmx",), max_concurrency=4
)

ADAPTERS = [
    ShellyClearAutoOff,
    ShellyClearAutoOn,
    ShellyGetAttributes,
    ShellyLowerBrightness,
    ShellyRaiseBrightness,
    ShellySetAttributes,
    ShellySetAutoOff,
    ShellySetAutoOn,
    ShellyStop,
    ShellyTurnOffFor,
    ShellyTurnOnFor,
]
