"""Zigbee2MQTT bridge over the core mqtt integration."""

from . import lifecycle
from .addressing import is_z2m_group
from .bridge_cache import capability_ready
from .classes import CLASSES, OTHER, capability, zigbee_manufacturer
from .clear_auto_off import Z2MClearAutoOff
from .detect import detect
from .fade import Z2MCallResolver
from .families import FAMILIES
from .get_attributes import Z2MGetAttributes
from .lower_brightness import Z2MLowerBrightness
from .lower_hue import Z2MLowerHue
from .lower_saturation import Z2MLowerSaturation
from .members import expand_group
from .raise_brightness import Z2MRaiseBrightness
from .raise_hue import Z2MRaiseHue
from .raise_saturation import Z2MRaiseSaturation
from .set_attributes import Z2MSetAttributes
from .set_auto_off import Z2MSetAutoOff
from .stop import Z2MStop
from .turn_off_for import Z2MTurnOffFor
from .turn_on_for import Z2MTurnOnFor
from ...core.scope import IntegrationInfo
from ...zigbee.standard_lights import STANDARD_LIGHT

INTEGRATION = IntegrationInfo(
    key="zigbee2mqtt",
    title="Zigbee2MQTT",
    ha_domain="mqtt",
    maintainers=("jasonmx",),
    detect=detect,
    is_group=is_z2m_group,
    expand_group=expand_group,
    capability=capability,
    capability_ready=capability_ready,
    classes=CLASSES,
    default_class=OTHER,
    families=FAMILIES,
    own_classes=frozenset({STANDARD_LIGHT}),
    zigbee_manufacturer=zigbee_manufacturer,
    call_resolver=Z2MCallResolver(),
    setup=lifecycle.setup,
    remove=lifecycle.remove,
    max_concurrency=4,
)

ADAPTERS = [
    Z2MClearAutoOff,
    Z2MGetAttributes,
    Z2MLowerBrightness,
    Z2MLowerHue,
    Z2MLowerSaturation,
    Z2MRaiseBrightness,
    Z2MRaiseHue,
    Z2MRaiseSaturation,
    Z2MSetAttributes,
    Z2MSetAutoOff,
    Z2MStop,
    Z2MTurnOffFor,
    Z2MTurnOnFor,
]
