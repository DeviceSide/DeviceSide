"""scripts/check_audit.py: an RC's audit record covers every commit to its head, with no open Critical or High."""

import pytest
import yaml

from scripts import check_audit

from .conftest import from_template

RC = "v0.0.2rc1"
HINT = "; was the audit PR squashed or rebased? Merge it with a merge commit"


def build_audited(repo):
    base = repo.commit()
    repo.git("tag", "v0.0.1")
    return base, repo.commit()


@pytest.fixture
def audited(repo, tmp_path_factory):
    """v0.0.1 on main, one code commit on top, audited in one pass. Returns (repo, base, audited sha)."""
    return repo, *from_template(repo, build_audited, tmp_path_factory)


def record(repo, rc=RC, base=None, passes=(), findings=(), **extra) -> str:
    """Commit docs/audits/<rc>.md and return the new head."""
    data = {"rc": rc, "base": base, "passes": [{"from": start, "to": end} for start, end in passes], **extra}
    data["findings"] = list(findings)
    return repo.commit(f"docs/audits/{rc}.md", f"---\n{yaml.safe_dump(data)}---\n\n# Audit\n")


def errors(repo, head, rc=RC) -> list[str]:
    return check_audit.errors(repo.path, rc, head)


def test_one_clean_pass_passes(audited):
    repo, base, end = audited
    assert errors(repo, record(repo, base=base[:7], passes=[(base, end)])) == []


def test_a_fix_pass_covers_the_fix(audited):
    repo, base, end = audited
    fix = repo.commit()
    findings = [
        {"id": "H1", "severity": "high", "status": "fixed", "fixed_in": fix[:7]},
        {"id": "C1", "severity": "critical", "status": "waived", "reason": "not reachable from HA"},
    ]
    assert errors(repo, record(repo, base=base, passes=[(base, end), (end, fix)], findings=findings)) == []


def test_an_owner_on_a_finding_changes_nothing(audited):
    """owner-findings writes `owner:`; the status alone still decides, so an owner's open finding still blocks."""
    repo, base, end = audited
    fix = repo.commit()
    findings = [
        {"id": "H1", "severity": "high", "status": "fixed", "fixed_in": fix[:7], "owner": "control4"},
        {"id": "C1", "severity": "critical", "status": "waived", "reason": "unreachable", "owner": "control4"},
        {"id": "H2", "severity": "high", "status": "open", "owner": "zigbee2mqtt/tuya"},
    ]
    head = record(repo, base=base, passes=[(base, end), (end, fix)], findings=findings)
    assert errors(repo, head) == ["finding H2 (high) is open"]


def test_rc2_starts_at_rc1(audited):
    repo, base, end = audited
    repo.git("tag", RC, record(repo, base=base, passes=[(base, end)]))
    rc1 = repo.git("rev-parse", RC)
    later = repo.commit()
    assert errors(repo, record(repo, "v0.0.2rc2", base=rc1, passes=[(rc1, later)]), "v0.0.2rc2") == []
    head = record(repo, "v0.0.2rc2", base=base, passes=[(base, later)])
    assert errors(repo, head, "v0.0.2rc2") == [
        f"base is {base!r}, not {rc1[:7]}",
        f"pass 1 starts at {base!r}, not {rc1[:7]}",
    ]


def test_with_no_release_rc1_starts_at_the_root(repo):
    root = repo.commit()
    end = repo.commit()
    assert errors(repo, record(repo, rc="v0.0.1rc1", base=root, passes=[(root, end)]), "v0.0.1rc1") == []


def test_a_missing_record_is_refused(audited):
    repo, _, end = audited
    assert errors(repo, end) == [f"docs/audits/{RC}.md is missing; run /rc-audit {RC}"]


@pytest.mark.parametrize(
    ("rc", "head", "error"),
    [("v0.0.2", "HEAD", "v0.0.2 is not vX.Y.ZrcN"), (RC, "nope", "the head is not a commit")],
)
def test_bad_arguments(audited, rc, head, error):
    assert check_audit.errors(audited[0].path, rc, head) == [error]


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("# Audit\n", "has no YAML frontmatter"),
        ("---\n- a list\n---\n", "is not a mapping"),
        ("---\nrc: [unclosed\n---\n", "while parsing"),
    ],
)
def test_unreadable_frontmatter(audited, text, error):
    repo = audited[0]
    [problem] = errors(repo, repo.commit(f"docs/audits/{RC}.md", text))
    assert error in problem


def test_an_all_digit_sha_stays_a_string(tmp_path):
    path = tmp_path / "record.md"
    path.write_text("---\nbase: 0123456\npasses: [{from: 0123456, to: 1e10}]\n---\n")
    assert check_audit.frontmatter(path) == {"base": "0123456", "passes": [{"from": "0123456", "to": "1e10"}]}


def test_the_record_must_name_its_rc_and_base(audited):
    repo, base, end = audited
    assert errors(repo, record(repo, base=end, passes=[(base, end)])) == [f"base is {end!r}, not {base[:7]}"]
    head = repo.commit(
        f"docs/audits/{RC}.md", f"---\nrc: v0.0.2rc9\nbase: {base}\npasses: [{{from: {base}, to: {end}}}]\n---\n"
    )
    assert errors(repo, head) == [f"rc is 'v0.0.2rc9', not {RC}"]


def test_no_passes(audited):
    repo, base, _ = audited
    assert errors(repo, record(repo, base=base)) == ["no passes"]


def test_passes_must_chain_and_end_under_the_head(audited):
    repo, base, end = audited
    fix = repo.commit()
    head = record(repo, base=base, passes=[(base, end), (fix, fix)])
    assert errors(repo, head) == [f"pass 2 starts at {fix!r}, not {end[:7]}"]

    repo.git("checkout", "-q", "-b", "other", base)
    elsewhere = repo.commit("other.py")
    repo.git("checkout", "-q", "main")
    head = record(repo, base=base, passes=[(base, elsewhere)])
    assert f"pass 1 ends at {elsewhere!r}, not an ancestor of the head{HINT}" in errors(repo, head)


def test_code_after_the_last_pass_is_refused(audited):
    repo, base, end = audited
    record(repo, base=base, passes=[(base, end)])
    head = repo.commit("code.py")
    assert errors(repo, head) == [f"changed after the last pass: code.py; run /rc-audit {RC} --fix-pass"]


@pytest.mark.parametrize(
    ("finding", "error"),
    [
        ({"id": "H1", "severity": "high", "status": "open"}, "finding H1 (high) is open"),
        ({"id": "H2", "severity": "high", "status": "waived", "reason": " "}, "finding H2 is waived without a reason"),
        ({"id": "M1", "severity": "medium", "status": "open"}, "finding M1: severity 'medium' is not critical or high"),
        ({"id": "H3", "severity": "high", "status": "done"}, "finding H3: status 'done' is not open, fixed or waived"),
        ({"severity": "high", "status": "fixed"}, "finding ?: fixed_in None is not inside a pass after the first"),
    ],
)
def test_findings_that_block(audited, finding, error):
    repo, base, end = audited
    assert errors(repo, record(repo, base=base, passes=[(base, end)], findings=[finding])) == [error]


def test_a_fix_inside_the_first_pass_is_not_a_fix(audited):
    repo, base, end = audited
    fix = repo.commit()
    finding = {"id": "H1", "severity": "high", "status": "fixed", "fixed_in": end}
    head = record(repo, base=base, passes=[(base, end), (end, fix)], findings=[finding])
    assert errors(repo, head) == [f"finding H1: fixed_in {end!r} is not inside a pass after the first"]


def test_a_squashed_audit_pr_is_named_as_the_cause(audited):
    repo, base, end = audited
    repo.git("checkout", "-q", "-b", "audit", end)
    fix = repo.commit("fix.py")
    repo.git("checkout", "-q", "main")
    squashed = repo.commit("fix.py", "squashed\n")  # the squash merge: a new commit, so `fix` is not under main
    finding = {"id": "H1", "severity": "high", "status": "fixed", "fixed_in": fix}
    head = record(repo, base=base, passes=[(base, end), (end, fix)], findings=[finding])
    assert errors(repo, head) == [f"pass 2 ends at {fix!r}, not an ancestor of the head{HINT}"]

    # The pass is re-recorded at the squash commit, but the finding still cites the branch's fix.
    head = record(repo, base=base, passes=[(base, end), (end, squashed)], findings=[finding])
    assert errors(repo, head) == [f"finding H1: fixed_in {fix!r} is not inside a pass after the first{HINT}"]


def test_main(audited, capsys):
    repo, base, end = audited
    assert check_audit.main([RC], repo.path) == 2
    assert check_audit.main(["--base", "v0.0.2"], repo.path) == 2
    assert check_audit.main(["--base", RC], repo.path) == 0
    assert capsys.readouterr().out.strip() == base
    assert check_audit.main([RC, end], repo.path) == 1
    assert "error: docs/audits" in capsys.readouterr().err
    head = record(repo, base=base, passes=[(base, end)])
    assert check_audit.main([RC, head], repo.path) == 0
    assert "no open Critical or High" in capsys.readouterr().out


# The ZHC bump guard: an RC from main bumps the standard lights table's pin since the previous RC tag.


def table(pin: str) -> str:
    return f'"""The table."""\n\nZHC_RELEASE = "{pin}"\nMODELS = {{}}\n'


def build_pinned(repo):
    """v0.0.1, then v0.0.2rc1 with the table at v1, then a commit to audit."""
    repo.commit()
    repo.git("tag", "v0.0.1")
    repo.commit(check_audit.ZHC_TABLE, table("v1"))
    repo.git("tag", "v0.0.2rc1")
    rc1 = repo.git("rev-parse", "v0.0.2rc1")
    return rc1, repo.commit()


@pytest.fixture
def pinned(repo, tmp_path_factory):
    """The previous RC tag holds the table at pin v1. Returns (repo, rc1 sha, audited sha)."""
    return repo, *from_template(repo, build_pinned, tmp_path_factory)


def rc2(repo, start, end, text="") -> str:
    """Commit rc2's record, one pass from rc1 to end, with `text` in its body; return the head."""
    data = {"rc": "v0.0.2rc2", "base": start, "passes": [{"from": start, "to": end}], "findings": []}
    return repo.commit("docs/audits/v0.0.2rc2.md", f"---\n{yaml.safe_dump(data)}---\n\n# Audit\n{text}")


def test_an_rc_whose_zhc_pin_has_not_moved_is_refused(pinned):
    repo, rc1, end = pinned
    [problem] = check_audit.errors(repo.path, "v0.0.2rc2", rc2(repo, rc1, end))
    assert problem.startswith("the ZHC table is pinned to v1, as at v0.0.2rc1: bump it")


def test_an_rc_with_a_bumped_zhc_pin_passes(pinned):
    repo, rc1, _ = pinned
    bumped = repo.commit(check_audit.ZHC_TABLE, table("v2"))
    assert check_audit.errors(repo.path, "v0.0.2rc2", rc2(repo, rc1, bumped)) == []


def test_a_skipped_bump_with_a_reason_passes(pinned):
    repo, rc1, end = pinned
    head = rc2(repo, rc1, end, "\nZHC bump skipped: no ZHC release since rc1\n")
    assert check_audit.errors(repo.path, "v0.0.2rc2", head) == []


def test_a_skip_line_without_a_reason_is_no_skip(pinned):
    repo, rc1, end = pinned
    head = rc2(repo, rc1, end, "\nZHC bump skipped: \n")
    assert len(check_audit.errors(repo.path, "v0.0.2rc2", head)) == 1


def test_a_fix_branch_needs_no_bump(pinned):
    repo, rc1, end = pinned
    assert check_audit.errors(repo.path, "v0.0.2rc2", rc2(repo, rc1, end), "release/v0.0.2") == []


def test_with_no_previous_rc_no_bump_is_asked(repo):
    root = repo.commit(check_audit.ZHC_TABLE, table("v1"))
    end = repo.commit()
    assert errors(repo, record(repo, rc="v0.0.1rc1", base=root, passes=[(root, end)]), "v0.0.1rc1") == []


def test_main_takes_the_branch(pinned, capsys):
    repo, rc1, end = pinned
    head = rc2(repo, rc1, end)
    assert check_audit.main(["v0.0.2rc2", head], repo=repo.path) == 1
    assert check_audit.main(["v0.0.2rc2", head, "release/v0.0.2"], repo=repo.path) == 0


def test_a_table_whose_pin_doesnt_parse_is_refused(pinned):
    repo, rc1, end = pinned
    repo.commit(check_audit.ZHC_TABLE, "ZHC_RELEASE = v1\n")
    with pytest.raises(ValueError, match="has no ZHC_RELEASE"):
        check_audit.errors(repo.path, "v0.0.2rc2", rc2(repo, rc1, end))


def test_a_previous_rc_with_no_table_asks_no_bump(repo):
    repo.commit()
    repo.git("tag", "v0.0.1")
    repo.git("tag", "v0.0.2rc1")
    rc1 = repo.git("rev-parse", "v0.0.2rc1")
    end = repo.commit(check_audit.ZHC_TABLE, table("v1"))
    assert check_audit.errors(repo.path, "v0.0.2rc2", rc2(repo, rc1, end)) == []
