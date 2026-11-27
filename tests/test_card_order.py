"""The coverage view lists integrations in the README cards' order at runtime, where the bundles aren't shipped, so
registry.CARD_ORDER must stay the order of the bundles' column_order (docs/integrations/<x>/devices.yaml)."""

from pathlib import Path

import yaml

from custom_components.deviceside.core.registry import CARD_ORDER

BUNDLES = Path(__file__).parents[1] / "docs" / "integrations"


def test_the_card_order_is_the_bundles_column_order():
    orders = {
        path.parent.name: yaml.safe_load(path.read_text())["column_order"] for path in BUNDLES.glob("*/devices.yaml")
    }

    assert list(CARD_ORDER) == sorted(orders, key=orders.get)
    assert CARD_ORDER[-1] == "zwave_js"
