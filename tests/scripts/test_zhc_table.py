"""scripts/zhc_table.py: the membership predicate, the table's rows, its regeneration and check, and the bump's
proposal."""

import shutil
from pathlib import Path

import pytest

from scripts import zhc_table as zt

from .conftest import GitRepo


def light(model="L1", vendor="Acme", *, meta=None, overrides=(), color_hs=False, white_labels=()) -> dict:
    """A resolved light definition, as resolve.mjs prints it."""
    return {
        "model": model,
        "vendor": vendor,
        "zigbee_models": [model],
        "fingerprinted": False,
        "fingerprint_manufacturers": [],
        "fingerprints": [],
        "white_labels": list(white_labels),
        "meta": meta or {},
        "overrides": list(overrides),
        "color_hs": color_hs,
        "exposes": [],
    }


@pytest.mark.parametrize(
    ("row", "why"),
    [
        (light(), []),
        (light(meta={"supportsHueAndSaturation": True}, color_hs=True), []),
        (light(meta={"multiEndpoint": True, "applyRedFix": True}), []),
        (light(meta={"disableDefaultResponse": False}), []),
        (light(meta={"turnsOffAtBrightness1": True}), ["meta turnsOffAtBrightness1"]),
        (light(meta={"omitOptionalLevelAndColorParams": True}), ["meta omitOptionalLevelAndColorParams"]),
        (light(meta={"supportsEnhancedHue": "function"}), ["meta supportsEnhancedHue"]),
        # A flag ZHC adds keeps a definition out until a maintainer has read it.
        (light(meta={"aNewFlag": True}), ["meta aNewFlag"]),
        (light(overrides=["state", "brightness"]), ["state converter overridden", "brightness converter overridden"]),
        (light(color_hs=True), ["color_hs without supportsHueAndSaturation"]),
    ],
)
def test_departures(row, why):
    assert zt.departures(row) == why


def test_table_holds_members_and_their_fingerprinted_white_labels():
    labels = [
        {"model": "W1", "vendor": "Other", "fingerprinted": True, "fingerprints": []},
        {"model": "W2", "vendor": "Other", "fingerprinted": False, "fingerprints": []},
    ]
    resolved = {
        "lights": [light("L1", white_labels=labels, color_hs=True, meta={"supportsHueAndSaturation": True})],
        "other_models": [],
    }

    assert zt.table(resolved).members == {"L1": ("Acme", True, ("L1",), ()), "W1": ("Other", True, (), ())}


def test_a_white_label_and_its_definition_each_hold_their_own_fingerprints():
    """resolve.mjs leaves the white labels' entries out of the definition's; a pair a white label shares with its
    definition (Paulmann's 291.46, told apart by firmware build) stays a member key while both are members."""
    labels = [
        {"model": "W1", "vendor": "Other", "fingerprinted": True, "fingerprints": [["TS0505B", "_TZ_w1"]]},
        {"model": "W2", "vendor": "Other", "fingerprinted": True, "fingerprints": [["TS0505B", "_TZ_l1"]]},
    ]
    row = light("L1", white_labels=labels) | {"zigbee_models": [], "fingerprints": [["TS0505B", "_TZ_l1"]]}

    found = zt.table({"lights": [row], "other_models": []})

    assert found.members == {
        "L1": ("Acme", False, (), (("TS0505B", "_TZ_l1"),)),
        "W1": ("Other", False, (), (("TS0505B", "_TZ_w1"),)),
        "W2": ("Other", False, (), (("TS0505B", "_TZ_l1"),)),
    }
    assert found.pairs == {("TS0505B", "_TZ_l1"): False, ("TS0505B", "_TZ_w1"): False}


PAULMANN = ("RGBW", "Paulmann Licht GmbH")


@pytest.mark.parametrize(
    ("entries", "member", "pairs"),
    [
        # A pair a split-off shares with a member: Paulmann's 924.70 and 948.47/29165.
        ([("924.70", {PAULMANN}), ("948.47/29165", {PAULMANN})], {"948.47/29165": True}, {}),
        # Both members: the key, color_hs only when both expose it.
        ([("A", {PAULMANN}), ("B", {PAULMANN})], {"A": True, "B": False}, {PAULMANN: False}),
        # A Zigbee model (m, "") overlaps any (m, *), and a full pair overlaps (m, "").
        ([("A", {("bulb", "")}), ("B", {("bulb", "Acme")})], {"A": True}, {}),
        (
            [("A", {("bulb", "")}), ("B", {("bulb", "Acme")})],
            {"A": True, "B": True},
            {("bulb", ""): True, ("bulb", "Acme"): True},
        ),
        # A manufacturer-only fingerprint overlaps any (*, mf).
        ([("A", {("", "_TZ_x")}), ("B", {("TS0505B", "_TZ_x")})], {"B": True}, {}),
        # A key no non-member touches; (m, "") isn't checked against ("", mf).
        ([("A", {("bulb", "")}), ("B", {("", "Acme")})], {"A": True}, {("bulb", ""): True}),
    ],
)
def test_a_key_is_a_member_only_when_every_definition_under_it_is(entries, member, pairs):
    assert zt.member_pairs(entries, member) == pairs


def test_table_keeps_out_a_key_a_definition_that_is_no_light_holds():
    resolved = {
        "lights": [light("L1"), light("L2") | {"zigbee_models": ["solo"]}],
        "other_models": ["S1"],
        "other_strings": [
            {"model": "S1", "vendor": "Acme", "zigbee_models": ["L1"], "fingerprints": [], "white_labels": []}
        ],
    }

    assert zt.table(resolved).pairs == {("solo", ""): False}


def test_table_keeps_out_an_excluded_models_keys():
    assert zt.table({"lights": [light("L1"), light("L2")], "other_models": []}, {"L1"}).pairs == {("L2", ""): False}


def test_table_leaves_out_a_model_two_definitions_publish():
    resolved = {
        "lights": [light("L1"), light("L1", vendor="Else"), light("L2"), light("L3", overrides=["color"])],
        "other_models": ["L2", "L3"],
    }

    found = zt.table(resolved)

    assert found.members == {}
    # L3 is no member under either definition, so isn't ambiguous.
    assert found.ambiguous == ["L1", "L2"]


def row(vendor: str, color_hs: bool = False) -> tuple:
    """A MODELS row with no Zigbee strings."""
    return (vendor, color_hs, (), ())


TABLE_TEXT = '''"""A table."""

from dataclasses import dataclass
from typing import NamedTuple


class Light(NamedTuple):
    vendor: str
    color_hs: bool
    zigbee_models: tuple[str, ...]
    fingerprints: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class Excluded:
    model: str
    action: str
    source: str


@dataclass(frozen=True, slots=True)
class Kept:
    model: str
    light: Light
    reason: str


{block}

EXCLUDED: tuple[Excluded, ...] = ({excluded})

KEPT: tuple[Kept, ...] = ({kept})
'''


def write_table(root: Path, models=None, excluded="", kept="", pin="v1.0.0", pairs=None) -> Path:
    models = {"L1": row("Acme", False), "L2": row("Müller", True)} if models is None else models
    path = root / zt.TABLE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TABLE_TEXT.format(block=zt.block(pin, models, pairs), excluded=excluded, kept=kept))
    page = root / zt.PAGE
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(zt.page(zt.load(path.read_text())))
    return path


def test_rewrite_keeps_the_hand_kept_rows(tmp_path):
    excluded = 'Excluded("L1", "stop", "https://example.com/1"),'
    path = write_table(tmp_path, excluded=excluded)

    text = zt.rewrite(path.read_text(), "v2.0.0", {"L3": row("Acme", False)})

    assert excluded in text
    module = zt.load(text)
    assert (module.ZHC_RELEASE, module.MODELS) == ("v2.0.0", {"L3": row("Acme", False)})


def test_members_less_excluded_plus_kept(tmp_path):
    path = write_table(
        tmp_path,
        excluded='Excluded("L1", "stop", "https://example.com/1"),',
        kept='Kept("L9", Light("Acme", False, (), ()), "reviewed"),',
    )

    assert zt.members(zt.load(path.read_text())) == {"L2", "L9"}


def test_the_committed_table_and_page_pass():
    assert zt.check() == []


def test_check_passes_a_current_table(tmp_path):
    write_table(tmp_path, excluded='Excluded("L1", "stop", "https://example.com/1"),')

    assert zt.check(tmp_path) == []


@pytest.mark.parametrize(
    ("excluded", "kept", "problem"),
    [
        ('Excluded("L1", "stop", ""),', "", "EXCLUDED 'L1' has no https source"),
        ('Excluded("L1", "turn_on_for", "https://example.com/1"),', "", "not an action the class serves"),
        ("", 'Kept("L9", Light("Acme", False, (), ()), " "),', "KEPT 'L9' has no reason"),
        ("", 'Kept("L1", Light("Acme", False, (), ()), "reviewed"),', "KEPT 'L1' is a member again"),
        (
            'Excluded("L9", "stop", "https://example.com/1"),',
            'Kept("L9", Light("Acme", False, (), ()), "reviewed"),',
            "both EXCLUDED and KEPT: ['L9']",
        ),
    ],
)
def test_check_fails_a_bad_row(tmp_path, excluded, kept, problem):
    write_table(tmp_path, excluded=excluded, kept=kept)

    assert any(problem in found for found in zt.check(tmp_path))


def test_check_fails_a_split_offs_key_until_write_drops_it(tmp_path):
    models = {"L1": ("Paulmann", True, (), (PAULMANN,)), "L2": ("Acme", False, ("L2",), ())}
    write_table(
        tmp_path, models=models, excluded='Excluded("L1", "stop", "https://example.com/1"),', pairs={PAULMANN: True}
    )

    assert zt.check(tmp_path) == [NOT_ALLOWED.format([PAULMANN])]
    assert zt.main(["--check", "--write"], repo=tmp_path) == 0
    assert zt.load((tmp_path / zt.TABLE).read_text()).PAIRS == {}


def test_check_fails_a_key_overlapping_a_split_offs_until_write_drops_it(tmp_path):
    """L1's split-off holds (bulb, Acme), which a device keyed by L2's (bulb, "") could be."""
    models = {"L1": ("Acme", True, (), (("bulb", "Acme"),)), "L2": ("Acme", True, ("bulb", "lamp"), ())}
    pairs = {("bulb", ""): True, ("lamp", ""): True}
    write_table(tmp_path, models=models, excluded='Excluded("L1", "stop", "https://example.com/1"),', pairs=pairs)

    assert zt.check(tmp_path) == [NOT_ALLOWED.format([("bulb", "")])]
    assert zt.main(["--check", "--write"], repo=tmp_path) == 0
    assert zt.load((tmp_path / zt.TABLE).read_text()).PAIRS == {("lamp", ""): True}


NOT_ALLOWED = (
    "PAIRS holds keys a split-off overlaps or no member row lists: {}; run scripts/zhc_table.py --check --write"
)


@pytest.mark.parametrize(
    ("pairs", "problem"),
    [
        ({("x", "y"): False}, NOT_ALLOWED.format([("x", "y")])),
        ({("L1", ""): True}, "PAIRS gives color_hs to keys of a row without it: [('L1', '')]"),
    ],
)
def test_check_fails_a_hand_edited_key(tmp_path, pairs, problem):
    write_table(tmp_path, models={"L1": ("Acme", False, ("L1",), ())}, pairs=pairs)

    assert zt.check(tmp_path) == [problem]


def test_check_fails_an_excluded_model_models_doesnt_hold(tmp_path):
    write_table(tmp_path, excluded='Excluded("L9", "stop", "https://example.com/1"),')

    assert zt.check(tmp_path) == ["EXCLUDED 'L9' is no MODELS key, so it excludes nothing"]


def test_page_lists_a_member_its_family_keeps_apart(tmp_path):
    models = {"L1": row("Acme"), "E11-G13": ("Sengled", False, ("E11-G13",), ())}
    page = zt.page(zt.load(write_table(tmp_path, models=models).read_text()))

    assert "## Members (1)" in page
    assert "## In a family (1)" in page
    assert "| Sengled | E11-G13 | [Sengled](index.md#sengled) |" in page


def test_check_fails_a_stale_page(tmp_path):
    write_table(tmp_path)
    (tmp_path / zt.PAGE).write_text("old\n")

    assert zt.check(tmp_path) == [f"{zt.PAGE} is stale; run scripts/zhc_table.py --check --write"]


def test_page_lists_members_excluded_and_kept(tmp_path):
    path = write_table(
        tmp_path,
        excluded='Excluded("L1", "stop", "https://example.com/1"),',
        kept='Kept("L9", Light("Acme", True, (), ()), "reviewed"),',
    )

    page = zt.page(zt.load(path.read_text()))

    assert "## Members (2)" in page
    assert "| Müller | L2 | yes |" in page
    assert "| Acme | L9 | yes |" in page
    assert "| Acme | L1 | `stop` | <https://example.com/1> |" in page
    assert "| Acme | L9 | reviewed |" in page
    assert "[v1.0.0](https://github.com/Koenkk/zigbee-herdsman-converters/releases/tag/v1.0.0)" in page


def test_proposal_reviews_a_departure_that_shipped_outside_labs(tmp_path):
    module = zt.load(write_table(tmp_path, kept='Kept("L5", Light("Acme", False, (), ()), "reviewed"),').read_text())
    old = {"L1": row("Acme", False), "L2": row("Acme", False), "L3": row("Acme", False)}
    new = zt.Resolved({"L1": row("Acme", False), "L4": row("Acme", True), "L5": row("Acme", False)}, ["L6"], {})

    body = zt.proposal("v2", "v1", old, new, ("v0.2.0", frozenset({"L1", "L2"})), module, ["- `H1` (hue): x to y"])

    assert "Members: 3 (was 3); 2 added, 2 departing." in body
    assert "- Acme `L4`" in body
    assert "- **review**: Acme `L2`" in body
    assert "- **leaves**: Acme `L3`" in body
    assert "- `H1` (hue): x to y" in body
    assert "### Left out as ambiguous\n\n- `L6`" in body
    assert "drop their KEPT rows)\n\n- `L5`" in body


def test_proposal_before_any_release_holds_the_table(tmp_path):
    module = zt.load(write_table(tmp_path).read_text())

    body = zt.proposal("v2", "v1", {"L1": row("Acme", False)}, zt.Resolved({}, [], {}), (None, frozenset()), module)

    assert "every departure **leaves**" in body
    assert "- **leaves**: Acme `L1`" in body


def test_released_members_reads_the_last_full_release(repo: GitRepo):
    repo.commit()
    repo.git("tag", "v0.1.0")
    write_table(repo.path, models={"L1": row("Acme", False)})
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "table")
    repo.git("tag", "v0.2.0")
    write_table(repo.path, models={"L2": row("Acme", False)})
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "bump")
    repo.git("tag", "v0.3.0rc1")

    assert zt.released_members(repo.path) == ("v0.2.0", frozenset({"L1"}))


def test_released_members_refuses_a_clone_with_no_tags(repo: GitRepo):
    repo.commit()

    with pytest.raises(SystemExit, match="no release tags"):
        zt.released_members(repo.path)


def test_released_members_refuses_a_table_it_cant_read(repo: GitRepo, monkeypatch):
    repo.commit()
    write_table(repo.path)
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "table")
    repo.git("tag", "v0.1.0")
    run = zt.subprocess.run

    def failing_show(args, **kwargs):
        if "show" in args:
            return zt.subprocess.CompletedProcess(args, 128, "", "fatal: bad object")
        return run(args, **kwargs)

    monkeypatch.setattr(zt.subprocess, "run", failing_show)

    with pytest.raises(SystemExit, match="can't read .* at v0.1.0: fatal: bad object"):
        zt.released_members(repo.path)


def test_released_members_before_the_table_existed(repo: GitRepo):
    repo.commit()
    repo.git("tag", "v0.1.0")

    assert zt.released_members(repo.path) == ("v0.1.0", frozenset())


def test_main_check_write_renders_the_page(tmp_path, capsys):
    shutil.copytree(zt.REPO / zt.TABLE.parent, tmp_path / zt.TABLE.parent, dirs_exist_ok=True)

    assert zt.main(["--check", "--write"], repo=tmp_path) == 0
    assert (tmp_path / zt.PAGE).read_text() == (zt.REPO / zt.PAGE).read_text()
