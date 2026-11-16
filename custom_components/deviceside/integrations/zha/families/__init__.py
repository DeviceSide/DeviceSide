"""ZHA's vendor families, and the order their rule groups run in (docs/design.md, Family). A family
holds its classes, the rules that place a device in them, and their levels; the order inside a rule group is the
family's. The order between groups is the integration's, here, as one family's rule can take another's device.

RULES is ordered, the first match winning; a device none places gets the integration's default class
(classes.device_class). tests/integrations/zha/test_classification.py pins the devices each constraint below is
about."""

from . import hue, sengled, sonoff, tuya
from ..rules import FIELDS
from ....core.rules import Rule, compose
from ....core.scope import Family

FAMILIES: tuple[Family, ...] = (hue.FAMILY, tuya.FAMILY, sengled.FAMILY, sonoff.FAMILY)

RULES: tuple[Rule, ...] = compose(
    FIELDS,
    # Reads a manufacturer no Tuya device carries, so it could go anywhere.
    (hue.FAMILY, hue.RULES),
    # Before Tuya's ZCL rules: a TS0601's model matches their `TS` and four digits, and some datapoint devices carry a
    # `_TZ3000_…` or `_TZ3210_…` manufacturer, which the quirk rule catches.
    (tuya.FAMILY, tuya.DATAPOINT_RULES),
    (tuya.FAMILY, tuya.ZCL_RULES),
    # After every Tuya rule, so a Tuya device sold under Sengled's name keeps its Tuya class.
    (sengled.FAMILY, sengled.RULES),
    (sonoff.FAMILY, sonoff.RULES),
)
