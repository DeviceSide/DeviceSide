"""Shelly Gen2+ over the core shelly integration's RPC connection. Gen1 (CoIoT) devices are unsupported."""

from .clear_auto_off import ShellyClearAutoOff
from .clear_auto_on import ShellyClearAutoOn
from .get_attributes import ShellyGetAttributes
from .set_attributes import ShellySetAttributes
from .set_auto_off import ShellySetAutoOff
from .set_auto_on import ShellySetAutoOn
from .turn_off_for import ShellyTurnOffFor
from .turn_on_for import ShellyTurnOnFor
from ...core.scope import IntegrationInfo

INTEGRATION = IntegrationInfo(key="shelly", title="Shelly", ha_domain="shelly", max_concurrency=4)

ADAPTERS = [
    ShellyClearAutoOff,
    ShellyClearAutoOn,
    ShellyGetAttributes,
    ShellySetAttributes,
    ShellySetAutoOff,
    ShellySetAutoOn,
    ShellyTurnOffFor,
    ShellyTurnOnFor,
]
