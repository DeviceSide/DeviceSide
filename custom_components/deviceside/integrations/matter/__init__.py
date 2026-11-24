"""Matter over the core matter integration's connection to python-matter-server."""

from .classes import CLASSES, OTHER, capability
from .get_attributes import MatterGetAttributes
from .set_attributes import MatterSetAttributes
from .turn_on_for import MatterTurnOnFor
from ...core.scope import IntegrationInfo

INTEGRATION = IntegrationInfo(
    key="matter",
    title="Matter",
    ha_domain="matter",
    maintainers=("jasonmx",),
    capability=capability,
    classes=CLASSES,
    default_class=OTHER,
    max_concurrency=2,
)

ADAPTERS = [MatterGetAttributes, MatterSetAttributes, MatterTurnOnFor]
