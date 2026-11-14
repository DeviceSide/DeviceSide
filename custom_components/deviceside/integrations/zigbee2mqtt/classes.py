"""Zigbee2MQTT's device classes (docs/evidence.md, Device classes): which firmware family a target's device is.

On Zigbee the call and the firmware family decide the result together, so one call proves nothing across vendors
(research/2026-11-14-timed-on-call-patterns.md). A class is named from the device registry's strings, which Z2M
fills from its definition at discovery, by RULES: an ordered list of (class, conditions), the first match winning, and
`other`, the default class, for a device none places. A lab probe changes the rules' data, never this structure.

The rules read only the registry device, sync and with no I/O, so `capability` takes hass=None on a stand-in target.
A group is no device of its own: the dispatcher classes its members (members.expand_group).
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from ...core.models import Target
from ...core.scope import experimental, verified

# Z2M's vendor string for Hue, which HA's device registry shows as the manufacturer; native_control.py reads it too.
HUE_MANUFACTURER = "Philips"

HUE = "hue"
TUYA_ZCL = "tuya_zcl"  # Tuya firmware speaking ZCL OnOff: TS011F, TS000x and their white labels
TUYA_MCU = "tuya_mcu"  # Tuya MCU firmware behind cluster 0xEF00 datapoints: TS0601
SENGLED = "sengled"
OTHER = "other"  # the default class, never Verified (IntegrationInfo.default_class)
CLASSES = frozenset({HUE, TUYA_ZCL, TUYA_MCU, SENGLED, OTHER})

# The registry fields a rule may test.
_FIELDS = frozenset({"manufacturer", "model", "model_id"})


@dataclass(frozen=True, slots=True)
class Rule:
    """A class and the registry fields that place a device in it, each a regex the field must fully match; every
    condition must hold. A rule with no conditions matches nothing: the placeholder for a class whose strings no
    probe has shown yet."""

    capability: str
    conditions: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.capability not in CLASSES - {OTHER}:
            raise ValueError(f"a rule names {self.capability!r}, no class but the default's")
        if unknown := self.conditions.keys() - _FIELDS:
            raise ValueError(f"a rule tests {sorted(unknown)}, which the device registry doesn't hold")

    def matches(self, device: dr.DeviceEntry) -> bool:
        return bool(self.conditions) and all(
            (value := getattr(device, name)) is not None and re.fullmatch(pattern, value)
            for name, pattern in self.conditions.items()
        )


RULES: tuple[Rule, ...] = (
    Rule(HUE, {"manufacturer": re.escape(HUE_MANUFACTURER)}),
    # Placeholders, matching nothing until step 5 part 2 fills them from the lab probe's registry strings
    # (docs/plans/2026-11-14-device-classes.md, step 3).
    Rule(TUYA_ZCL),
    Rule(TUYA_MCU),
    Rule(SENGLED),
)

# The levels each adapter's scope holds, but turn_on_for's: Verified on Hue, whose bulbs every record ran on, and the
# rest untested (docs/integrations/zigbee2mqtt/index.md, Device classes).
CAPABILITIES = verified(HUE) | experimental(OTHER, TUYA_ZCL, TUYA_MCU, SENGLED)


def device_class(device: dr.DeviceEntry) -> str:
    """The class of a device Z2M registered: the first rule it matches, else the default."""
    return next((rule.capability for rule in RULES if rule.matches(device)), OTHER)


def capability(hass: HomeAssistant | None, target: Target) -> str | None:
    """Zigbee2MQTT's IntegrationInfo.capability: the target's device's class; None for a target with no device,
    which no rule can place and no adapter can address."""
    return device_class(target.device) if target.device is not None else None
