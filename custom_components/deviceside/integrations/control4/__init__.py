"""Control4 lights over the core control4 integration's Director connection."""

from . import inventory
from .get_attributes import Control4GetAttributes
from .lower_brightness import Control4LowerBrightness
from .raise_brightness import Control4RaiseBrightness
from .set_attributes import Control4SetAttributes
from .stop import Control4Stop
from ...core.scope import IntegrationInfo

INTEGRATION = IntegrationInfo(
    key="control4",
    title="Control4",
    ha_domain="control4",
    maintainers=("skialpine",),
    is_group=inventory.is_group,
    expand_group=inventory.expand_group,
    setup=inventory.setup,
    max_concurrency=4,
)

ADAPTERS = [
    Control4GetAttributes,
    Control4LowerBrightness,
    Control4RaiseBrightness,
    Control4SetAttributes,
    Control4Stop,
]
