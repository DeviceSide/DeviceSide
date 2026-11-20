"""Philips Hue, through aiohue's v2 API on the core hue integration's bridge."""

from .bridge import expand_group, is_hue_group
from .classes import CLASSES, OTHER, capability
from .get_attributes import HueGetAttributes
from .lower_brightness import HueLowerBrightness
from .lower_saturation import HueLowerSaturation
from .raise_brightness import HueRaiseBrightness
from .raise_saturation import HueRaiseSaturation
from .report_filter import HueCallResolver
from .set_attributes import HueSetAttributes
from .set_scene import HueSetScene
from .stop import HueStop
from .v1 import V1_BRIDGE
from ...core.scope import IntegrationInfo

INTEGRATION = IntegrationInfo(
    key="hue",
    title="Hue",
    ha_domain="hue",
    maintainers=("jasonmx",),
    is_group=is_hue_group,
    expand_group=expand_group,
    capability=capability,
    classes=CLASSES,
    default_class=OTHER,
    call_resolver=HueCallResolver(),
    # aiohue allows 3 requests at once per bridge, shared with the core hue integration.
    max_concurrency=2,
)

ADAPTERS = [
    HueGetAttributes,
    HueLowerBrightness,
    HueLowerSaturation,
    HueRaiseBrightness,
    HueRaiseSaturation,
    HueSetAttributes,
    HueSetScene,
    HueStop,
]

# The v1 (round) bridge: a separate integration on the hue domain, which DeviceSide never supports (v1.py).
UNSUPPORTED = [V1_BRIDGE]
