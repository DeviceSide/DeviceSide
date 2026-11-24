"""IKEA's Zigbee strings, as both Zigbee stacks' IKEA rules read them off the device's own manufacturer and model.
Which class a match gives, and the order the rules run in, is each integration's. Every constant is a literal string,
the device's own: a rule that tests it wraps it in `re.escape`.

Sources: the manufacturer string, zha-quirks' IKEA package
(https://github.com/zigpy/zha-device-handlers/blob/b07fa76876e081d48744968f9fb806e7f1fee0ee/zhaquirks/ikea/__init__.py#L16);
the models, zigbee-herdsman-converters' `LED2005R5/LED2106R3` definition
(https://github.com/Koenkk/zigbee-herdsman-converters/blob/74553288c1479da1e66f7808289186a68adab3d9/src/devices/ikea.ts#L406-L418).
"""

# IKEA's Zigbee manufacturer string, on its TRÅDFRI bulbs, drivers and outlets.
MANUFACTURER = "IKEA of Sweden"

# The TRÅDFRI GU10 white spectrum bulbs (LED2005R5, LED2106R3) reported turned on by a unicast OnWithTimedOff and never
# off, by two users (https://github.com/Koenkk/zigbee2mqtt/issues/29158): their Zigbee models, all five
# zigbee-herdsman-converters lists for the one definition.
TIMER_HARMED_MODELS = (
    "TRADFRI_bulb_GU10_WS_345lm",
    "TRADFRIbulbGU10WS345lm",
    "TRADFRI bulb GU10 WS 345lm",
    "TRADFRIbulbGU10WS380lm",
    "TRADFRI bulb GU10 WS 380lm",
)

# Why `turn_on_for` refuses them: reported turned on by a unicast timer and never off, while the same call by group
# did turn them off; the cause is unknown. A host-side off would serve them.
TIMER_HARMED_REASON = (
    "It is reported to turn on with the timer and never turn off, and DeviceSide's own off, which would "
    "serve it, isn't built"
)
