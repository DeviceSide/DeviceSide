"""TP-Link (Kasa and Tapo) over the core tplink integration's python-kasa device objects."""

from .addressing import capability
from .classes import CLASSES
from ...core.scope import IntegrationInfo

INTEGRATION = IntegrationInfo(
    key="tplink",
    title="TP-Link",
    ha_domain="tplink",
    maintainers=("jasonmx",),
    capability=capability,
    classes=CLASSES,
    max_concurrency=4,
)

ADAPTERS: list = []
