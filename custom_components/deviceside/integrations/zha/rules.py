"""ZHA's rule fields: what a family's rule (core/rules.py) may test on ZHA, and how each is read off a device. Which
strings name which class is each family's (families/<family>/); the order between their rule groups is the
integration's (families/__init__.py)."""

# The fields a rule may test: `manufacturer` and `model`, zigpy's raw Zigbee strings, and `quirk`, the module that
# defines the On/Off cluster's `command` (classes.py says why each, and where it is read).
FIELDS = frozenset({"manufacturer", "model", "quirk"})


def read(manufacturer: str, model: str, quirk: str | None = None) -> dict[str, str | None]:
    """A device's rule fields, from its Zigbee strings and its On/Off `quirk` module, None without one."""
    return {"manufacturer": manufacturer, "model": model, "quirk": quirk}
