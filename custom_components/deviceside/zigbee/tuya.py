"""Tuya's Zigbee strings, as both Zigbee stacks' Tuya rules read them: each pattern is a regex the device's own
manufacturer or model string must fully match. Which class a match gives, and the order the rules run in, is each
integration's."""

# Tuya's Zigbee manufacturer strings (docs/integrations/zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md, §4):
# `_TZE…` for datapoint devices, `_TZ3000_…`, `_TZ3210_…` and `_TYZB01_…` for ZCL ones. Only the TS011F's are measured;
# the rest are Tuya's naming, from the converters and quirks.
DATAPOINT_MANUFACTURER = r"_TZE\d{3}_.*"
ZCL_MANUFACTURER = r"_TZ\d{4}_.*|_TYZB\d{2}_.*"

# A Tuya datapoint device's model: it has no Zigbee On/Off cluster, so no raw ZCL read or write reaches it.
DATAPOINT_MODEL = "TS0601"
# A Tuya device on the Zigbee On/Off cluster (TS000x, TS0505B and white labels): `TS` and four digits, which
# DATAPOINT_MODEL matches too, and a TS011F, with three, doesn't.
ZCL_MODEL = r"TS\d{4}.*"

# The TS011F maker string reported failing Tuya's countdown with harm, its timer restarting at random
# (https://github.com/Koenkk/zigbee2mqtt/issues/30493). The string itself, not a pattern; ZCL_MANUFACTURER matches it.
COUNTDOWN_HARMED_MANUFACTURER = "_TZ3000_gjnozsaz"
COUNTDOWN_HARMED_MODEL = "TS011F"
