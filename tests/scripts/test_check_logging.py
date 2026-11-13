"""scripts/check_logging.py: a caught exception logged with %s, or a log line naming a device address."""

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).parents[2]
_spec = importlib.util.spec_from_file_location("check_logging", REPO / "scripts" / "check_logging.py")
check_logging = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_logging)


def flagged(tmp_path: Path, body: str) -> list[str]:
    path = tmp_path / "mod.py"
    path.write_text("import logging\n_LOGGER = logging.getLogger(__name__)\n" + body)
    return check_logging.violations(path)


def test_caught_exception_with_percent_s_is_flagged(tmp_path):
    body = "try:\n    pass\nexcept OSError as boom:\n    _LOGGER.warning('failed for %s: %s', 'x', boom)\n"
    assert len(flagged(tmp_path, body)) == 1


def test_percent_r_and_other_arguments_pass(tmp_path):
    body = "try:\n    pass\nexcept OSError as boom:\n    _LOGGER.warning('failed for %s: %r', 'x', boom)\n"
    assert flagged(tmp_path, body) == []


def test_multi_line_call_is_seen_whole(tmp_path):
    body = "def f(err):\n    _LOGGER.debug(\n        'a %s '\n        'b %s',\n        1,\n        err,\n    )\n"
    assert len(flagged(tmp_path, body)) == 1


def test_f_string_exception_needs_repr(tmp_path):
    assert len(flagged(tmp_path, "def f(err):\n    _LOGGER.debug(f'{err}')\n")) == 1
    assert flagged(tmp_path, "def f(err):\n    _LOGGER.debug(f'{err!r}')\n") == []


@pytest.mark.parametrize("name", ["ieee", "mac", "friendly_name", "topic", "light_rid", "node_id", "token"])
def test_address_arguments_are_flagged(tmp_path, name):
    assert len(flagged(tmp_path, f"def f({name}):\n    _LOGGER.debug('x %s', {name})\n")) == 1


def test_entity_lookups_and_entity_ids_pass(tmp_path):
    body = (
        "def f(hass, rid, by_address, a):\n"
        "    _LOGGER.debug('x %s %s', entity_name(hass, rid), by_address[a].entity_id)\n"
    )
    assert flagged(tmp_path, body) == []


def test_exemption_needs_a_reason(tmp_path):
    line = "def f(ieee):\n    _LOGGER.debug('x %s', ieee)  # log-ok: {}\n"
    assert flagged(tmp_path, line.format("a user-supplied value")) == []
    assert len(flagged(tmp_path, line.format(""))) == 1


def test_the_integration_code_is_clean():
    paths = [str(path) for path in (REPO / "custom_components").rglob("*.py")]
    assert check_logging.main(paths) == 0
