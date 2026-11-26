"""scripts/check_docs.py: the living docs stay pared (history tags, level words, long items, word budgets)."""

import importlib.util
from pathlib import Path

REPO = Path(__file__).parents[2]
_spec = importlib.util.spec_from_file_location("check_docs", REPO / "scripts" / "check_docs.py")
check_docs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_docs)

SHA = "abc1234def"
LONG = " ".join(["word"] * 81)


def faults(path: str, text: str, budget: int = 1000) -> list[str]:
    return check_docs.check({path: text}, {path: budget})


def test_the_repo_passes():
    docs = {str(p.relative_to(REPO)): p.read_text() for p in check_docs.living_docs()}
    assert check_docs.check(docs, check_docs.read_budgets()) == []


def test_generated_and_dated_files_are_not_living_docs():
    living = {str(p.relative_to(REPO)) for p in check_docs.living_docs()}
    assert "docs/device-compatibility.md" not in living
    assert not {p for p in living if "/research/" in p or p.startswith(("docs/plans/", "docs/audits/"))}
    assert {"CONTRIBUTING.md", "docs/design.md"} <= living


def test_a_decision_tag_is_a_fault():
    (fault,) = faults("docs/a.md", "ok\nSee Decision 12 for why.\n")
    assert fault.startswith("docs/a.md:2:")


def test_a_plan_link_is_a_fault():
    assert len(faults("docs/a.md", "See [the plan](plans/2026-01-01-x.md).\n")) == 1
    assert len(faults("docs/a.md", "See docs/plans/2026-01-01-x.md.\n")) == 1


def test_a_sha_in_prose_or_link_text_is_a_fault():
    assert len(faults("docs/a.md", f"Fixed in {SHA}.\n")) == 1
    assert len(faults("docs/a.md", f"Fixed in [{SHA}](https://example.com/x).\n")) == 1


def test_a_sha_in_a_link_url_passes():
    assert faults("docs/a.md", f"Read at [this commit](https://example.com/tree/{SHA}).\n") == []
    assert faults("docs/a.md", f"Read at https://example.com/commit/{SHA} today.\n") == []


def test_words_that_are_not_shas_pass():
    assert faults("docs/a.md", "decade defaced 1234567 deadbeef\n") == []


def test_generated_blocks_are_skipped():
    text = f"<!-- x:start -->\nDecision 3 {SHA}\n<!-- x:end -->\nDecision 4\n"
    (fault,) = faults("docs/a.md", text)
    assert fault.startswith("docs/a.md:4:")


def test_a_level_word_in_internals_is_a_fault_but_not_elsewhere():
    assert len(faults("docs/x/internals.md", "A Labs thing.\n")) == 1
    assert len(faults("docs/x/internals.md", "Verified and Documented.\n")) == 2
    assert faults("docs/x/other.md", "A Labs thing.\n") == []
    assert faults("docs/x/internals.md", "A labs-free, undocumented thing.\n") == []


def test_a_long_item_in_index_is_a_fault():
    assert len(faults("docs/x/index.md", f"{LONG}\n")) == 1
    assert len(faults("docs/x/index.md", f"- {LONG}\n")) == 1
    assert faults("docs/x/index.md", "- short\n- " + " ".join(["w"] * 79) + "\n") == []
    assert faults("docs/x/other.md", f"{LONG}\n") == []


def test_a_continued_bullet_counts_as_one_item():
    assert len(faults("docs/x/index.md", "- " + " ".join(["w"] * 40) + "\n  " + " ".join(["w"] * 41) + "\n")) == 1


def test_control4_is_skipped_for_length():
    assert faults("docs/integrations/control4/index.md", f"{LONG}\n") == []


def test_a_doc_over_budget_is_a_fault():
    (fault,) = faults("docs/a.md", "one two three\n", budget=2)
    assert "3 words, budget 2" in fault
    assert faults("docs/a.md", "one two\n", budget=2) == []


def test_generated_blocks_dont_count_toward_the_budget():
    text = "one two\n<!-- x:start -->\n" + " ".join(["w"] * 50) + "\n<!-- x:end -->\n"
    assert faults("docs/a.md", text, budget=2) == []


def test_a_doc_without_a_budget_line_is_a_fault():
    (fault,) = check_docs.check({"docs/a.md": "x\n"}, {})
    assert "no line in docs/word-budgets.yaml" in fault


def test_a_budget_for_no_doc_is_a_fault():
    (fault,) = check_docs.check({}, {"docs/gone.md": 5})
    assert "docs/gone.md is no living doc" in fault


def test_control4_budgets_hold_todays_size():
    budgets = check_docs.read_budgets()
    assert budgets["docs/integrations/control4/index.md"] == 681
    assert budgets["docs/integrations/control4/internals.md"] == 3894
