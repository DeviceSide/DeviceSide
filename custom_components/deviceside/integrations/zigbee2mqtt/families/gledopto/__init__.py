"""Gledopto on Zigbee2MQTT: its controllers and bulbs, whose converter departs from the standard calls
(research/2026-11-14-timed-on-call-patterns.md, §3), so they take none of `other`'s levels (plan Decision 24)."""

from homeassistant.const import Platform

from .....core.rules import Rule
from .....core.scope import Family

GLEDOPTO = "gledopto"

RULES = (
    # The registry manufacturer: Z2M's vendor `Gledopto`, in any case, as the devices' own Zigbee string is
    # `GLEDOPTO` (zigbee-herdsman-converters src/devices/gledopto.ts, at the research file's commit).
    Rule(GLEDOPTO, {"manufacturer": "(?i:gledopto)"}),
)

FAMILY = Family(
    key="gledopto",
    maintainers=(),
    classes={GLEDOPTO: frozenset({Platform.LIGHT})},
    # In no scope: not built on every action. Its converter departs from the standard calls (it turns on when its color
    # is set while off, and no converter takes `on_time`), and no pass or research predicts it takes them
    # (docs/evidence.md, On trial).
)
