"""scripts/check_private.py: terms from the gitignored files, matched in staged files and messages."""

import importlib.util
from pathlib import Path

REPO = Path(__file__).parents[2]
_spec = importlib.util.spec_from_file_location("check_private", REPO / "scripts" / "check_private.py")
check_private = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_private)


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def terms(tmp_path: Path, profile: str = "", env: str = "", extra: str = "") -> dict[str, str]:
    return check_private.private_terms(
        [write(tmp_path, "house.yaml", profile) if profile else tmp_path / "missing.yaml"],
        write(tmp_path, ".env.rig", env) if env else tmp_path / "missing.env",
        write(tmp_path, ".private-terms", extra) if extra else tmp_path / "missing.terms",
    )


def test_no_private_files_means_no_terms(tmp_path):
    assert terms(tmp_path) == {}


def test_terms_come_from_each_private_file(tmp_path):
    found = terms(
        tmp_path,
        profile="shelly:\n  - entity_id: light.Kitchen_Relay\n    roles: [light_onoff]\n",
        env="HA_URL=http://ha.example.lan:8123\nHA_TOKEN=abc.def\n",
        extra="# names\nAcme Street\n\n",
    )
    assert found == {
        "light.kitchen_relay": "light.Kitchen_Relay",
        "ha.example.lan": "ha.example.lan",
        "abc.def": "HA_TOKEN from .env.rig",
        "acme street": "Acme Street",
    }


def test_terms_come_from_every_entity_a_profile_names(tmp_path):
    house = write(tmp_path, "house.yaml", "pause: [automation.Hall_Motion]\n")
    lab = write(
        tmp_path,
        "lab.yaml",
        "zigbee2mqtt:\n  - entity_id: light.desk_group\n    roles: [group]\n    members: [light.desk_a]\n"
        "  - entity_id: light.desk_b\n    roles: [light_ct]\n    powered_by: switch.desk_plug\n"
        "  - entity_id: switch.desk_plug\n    roles: [switch_plug]\n",
    )
    found = check_private.private_terms([house, lab], tmp_path / "missing.env", tmp_path / "missing.terms")
    assert found == {
        "automation.hall_motion": "automation.Hall_Motion",
        **{name: name for name in ("light.desk_group", "light.desk_a", "light.desk_b", "switch.desk_plug")},
    }


def test_generic_host_is_not_a_term(tmp_path):
    assert terms(tmp_path, env="HA_URL=http://homeassistant.local:8123\n") == {}


def test_find_reports_matches_case_insensitively_by_label(tmp_path):
    staged = write(tmp_path, "doc.md", "fine\nToken ABC.DEF here\n")
    binary = tmp_path / "blob.bin"
    binary.write_bytes(b"\xff\xfe")
    hits = check_private.find([staged, binary], {"abc.def": "HA_TOKEN from .env.rig"})
    assert hits == [f"{staged}:2: HA_TOKEN from .env.rig"]


def test_main_passes_without_terms(tmp_path, monkeypatch):
    monkeypatch.setattr(check_private, "private_terms", dict)
    assert check_private.main([str(write(tmp_path, "doc.md", "anything"))]) == 0


def test_main_fails_when_a_profile_cannot_be_read(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(check_private, "profile_paths", lambda: [write(tmp_path, "house.yaml", "pause: [a]1\n")])
    assert check_private.main([str(write(tmp_path, "msg", "anything"))]) == 1
    assert "house.yaml: not valid YAML" in capsys.readouterr().out


def test_main_fails_on_a_hit(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(check_private, "private_terms", lambda: {"acme street": "Acme Street"})
    assert check_private.main([str(write(tmp_path, "msg", "Fix lamp on acme street"))]) == 1
    assert "Acme Street" in capsys.readouterr().out


def test_terms_default_to_every_profile_and_the_old_inventory(tmp_path, monkeypatch):
    lab = write(tmp_path, "lab.yaml", "pause: [switch.lab_al]\n")
    legacy = write(tmp_path, "inventory.yaml", "pause: [switch.old_al]\n")
    monkeypatch.setattr(check_private, "profile_paths", lambda: [lab])
    monkeypatch.setattr(check_private, "LEGACY_INVENTORY", legacy)
    found = check_private.private_terms(env_file=tmp_path / "missing.env", terms_file=tmp_path / "missing.terms")
    assert found == {"switch.lab_al": "switch.lab_al", "switch.old_al": "switch.old_al"}
