"""Matter over the core matter integration's connection to python-matter-server."""

from .classes import CLASSES, OTHER, capability
from .fade import MatterCallResolver
from .get_attributes import MatterGetAttributes
from .lower_brightness import MatterLowerBrightness
from .lower_hue import MatterLowerHue
from .lower_saturation import MatterLowerSaturation
from .raise_brightness import MatterRaiseBrightness
from .raise_hue import MatterRaiseHue
from .raise_saturation import MatterRaiseSaturation
from .set_attributes import MatterSetAttributes
from .stop import MatterStop
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
    call_resolver=MatterCallResolver(),
)

ADAPTERS = [
    MatterGetAttributes,
    MatterLowerBrightness,
    MatterLowerHue,
    MatterLowerSaturation,
    MatterRaiseBrightness,
    MatterRaiseHue,
    MatterRaiseSaturation,
    MatterSetAttributes,
    MatterStop,
    MatterTurnOnFor,
]
