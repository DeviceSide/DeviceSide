"""Z-Wave over the core zwave_js integration's connection to Z-Wave JS."""

from .classes import CLASSES, OTHER, capability
from .get_attributes import ZwaveGetAttributes
from ...core.scope import IntegrationInfo

INTEGRATION = IntegrationInfo(
    key="zwave_js",
    title="Z-Wave",
    ha_domain="zwave_js",
    maintainers=("jasonmx",),
    capability=capability,
    classes=CLASSES,
    default_class=OTHER,
)

ADAPTERS = [
    ZwaveGetAttributes,
]
