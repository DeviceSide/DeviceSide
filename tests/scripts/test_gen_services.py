"""scripts/gen_services.py: each action's services.yaml `target:` block, from the registry."""

from types import SimpleNamespace

import pytest

from scripts import gen_services as gs

SOURCE = """\
turn_on:
  target: &shared
    entity:
      - domain: light
        integration: old
  fields:
    duration: &duration
      required: true

turn_off:
  target: *shared
  fields:
    duration: *duration

stop:
  # a comment
  target:
    entity:
      - domain: light
        integration: stale
  fields: {}
"""


def registry(served, actions=("turn_on", "turn_off", "stop")):
    """Each integration key is its HA domain here; `served` maps it to the domains it serves."""
    integrations = {key: SimpleNamespace(ha_domain=key, domains=domains) for key, domains in served.items()}
    matrix = [(action, key, key) for action in actions for key in served]
    return SimpleNamespace(integrations=integrations, matrix=lambda: matrix)


@pytest.fixture
def reg(monkeypatch):
    monkeypatch.setattr(gs, "served_domains", lambda adapter, info: set(info.domains))
    return registry({"shelly": {"switch", "light"}, "zha": {"light"}})


def test_an_entry_per_ha_domain_sorted_a_scalar_for_one_domain_and_a_sorted_flow_list_for_several():
    assert gs.block({"zha": {"light"}, "shelly": {"switch", "light"}}) == (
        "  target:\n    entity:\n"
        "      - domain: [light, switch]\n        integration: shelly\n"
        "      - domain: light\n        integration: zha\n"
    )


def test_anchor_and_alias_targets_are_replaced_by_full_blocks(reg):
    text = gs.generate(SOURCE, reg)
    assert "&shared" not in text and "*shared" not in text
    assert text.count("integration: shelly") == 3 and text.count("integration: old") == 0
    assert text.count("integration: stale") == 0


def test_hand_written_field_anchors_and_comments_are_untouched(reg):
    text = gs.generate(SOURCE, reg)
    assert "duration: &duration\n      required: true" in text
    assert "duration: *duration" in text
    assert "  # a comment\n  target:" in text
    assert gs.authored(text) == gs.authored(SOURCE)


def test_authored_drops_only_the_target_blocks():
    assert gs.authored(SOURCE).splitlines()[:3] == ["turn_on:", "  fields:", "    duration: &duration"]
    assert "target" not in gs.authored(SOURCE)


def test_an_action_without_a_target_is_an_error(reg):
    with pytest.raises(SystemExit, match="no `target:` for stop"):
        gs.generate(
            SOURCE.replace("  target:\n    entity:\n      - domain: light\n        integration: stale\n", ""), reg
        )


def test_actions_that_differ_from_the_registrys_are_an_error(reg, monkeypatch):
    with pytest.raises(SystemExit, match="differ from the registry"):
        gs.generate(SOURCE, registry({"zha": {"light"}}, actions=("turn_on", "turn_off")))


def test_check_fails_when_stale_then_passes_once_regenerated(tmp_path, reg, capsys):
    path = tmp_path / "custom_components" / "deviceside" / "services.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(SOURCE)
    assert gs.main(["--check"], reg, tmp_path) == 1
    assert "out of date" in capsys.readouterr().err
    assert path.read_text() == SOURCE
    assert gs.main([], reg, tmp_path) == 0
    assert gs.main(["--check"], reg, tmp_path) == 0


def test_the_checked_in_services_yaml_matches_the_registry():
    assert gs.main(["--check"]) == 0
