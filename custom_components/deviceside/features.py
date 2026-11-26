"""The features the feature table, the device cards and the coverage view name, each with the actions it rides, so
the three read one map. A feature is built on an integration only where every one of its actions is
(scripts/gen_features.py); a smooth move rides `stop` too, as it is unusable without it. Keyed by the name a card gives
the feature."""

FEATURE_ACTIONS: dict[str, tuple[str, ...]] = {
    "turn on with timer": ("turn_on_for",),
    "turn off with timer": ("turn_off_for",),
    "auto-off/on": ("set_auto_off", "set_auto_on", "clear_auto_off", "clear_auto_on"),
    "smooth dimming": ("raise_brightness", "lower_brightness", "stop"),
    "smooth saturation": ("raise_saturation", "lower_saturation", "stop"),
    "smooth hue": ("raise_hue", "lower_hue", "stop"),
    "set attributes while off": ("set_attributes",),
    "set scene while off": ("set_scene",),
    "get attributes": ("get_attributes",),
}
