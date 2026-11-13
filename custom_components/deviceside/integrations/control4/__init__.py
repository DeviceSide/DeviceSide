"""Control4 lights over the core control4 integration's Director connection."""

from .lower_brightness import Control4LowerBrightness
from .raise_brightness import Control4RaiseBrightness
from .stop import Control4Stop
from ...core.scope import IntegrationInfo

INTEGRATION = IntegrationInfo(
    key="control4", title="Control4", ha_domain="control4", maintainers=("skialpine",), max_concurrency=4
)

ADAPTERS = [
    Control4LowerBrightness,
    Control4RaiseBrightness,
    Control4Stop,
]
