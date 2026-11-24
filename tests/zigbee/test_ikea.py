"""The catalog's IKEA strings: both Zigbee stacks' rules read them, so a change here that moves a string fails before
either stack's classes do. Which device gets which class is each stack's snapshot
(tests/integrations/<x>/test_classification.py)."""

import ast
from pathlib import Path

from custom_components.deviceside.zigbee import ikea


def test_the_reported_bulbs_models_are_five_distinct_strings():
    """The five Zigbee models zigbee-herdsman-converters lists for LED2005R5/LED2106R3, each once."""
    assert len(set(ikea.TIMER_HARMED_MODELS)) == len(ikea.TIMER_HARMED_MODELS) == 5
    assert all(isinstance(model, str) and model for model in ikea.TIMER_HARMED_MODELS)


def test_the_timer_harmed_reason_reads_as_it_does_to_the_user():
    assert ikea.TIMER_HARMED_REASON == (
        "It is reported to turn on with the timer and never turn off, and DeviceSide's own off, which would "
        "serve it, isn't built"
    )


def test_the_catalog_imports_nothing():
    """Patterns and facts only: a Home Assistant or DeviceSide import would tie both stacks to it."""
    tree = ast.parse(Path(ikea.__file__).read_text())

    assert [node for node in ast.walk(tree) if isinstance(node, ast.Import | ast.ImportFrom)] == []
