"""Every `docs/...md#anchor` cited under custom_components/ resolves to a heading, so a renamed heading or a moved page
fails here rather than leaving code pointing at nothing."""

import re
from pathlib import Path

import pytest

from scripts.gen_features import REPO, anchors

CITATION = re.compile(r"\b(docs/[\w./-]+\.md)#([\w-]+)")


def citations(root: Path) -> list[tuple[str, str, str]]:
    """(file citing it, page, anchor) for each citation in the code under root."""
    found = []
    for path in sorted(root.rglob("*.py")):
        for page, anchor in CITATION.findall(path.read_text()):
            found.append((str(path.relative_to(REPO)), page, anchor))
    return found


def dead(found: list[tuple[str, str, str]], repo: Path = REPO) -> list[str]:
    """The citations whose page is missing or has no heading for the anchor."""
    errors = []
    for where, page, anchor in found:
        target = repo / page
        if not target.is_file():
            errors.append(f"{where}: {page} doesn't exist")
        elif anchor not in anchors(target.read_text()):
            errors.append(f"{where}: {page} has no heading for #{anchor}")
    return errors


def test_every_doc_anchor_the_code_cites_resolves():
    assert dead(citations(REPO / "custom_components")) == []


@pytest.mark.parametrize(
    ("citation", "error"),
    [
        ("docs/integrations/zha/internals.md#tested-behavior", None),
        ("docs/internals.md#shared", None),
        ("docs/integrations/zha/internals.md#no-such-heading", "has no heading for #no-such-heading"),
        ("docs/integrations/tuya/internals.md#tested-behavior", "doesn't exist"),
    ],
)
def test_a_dead_page_or_anchor_is_named(citation, error):
    page, anchor = CITATION.search(citation).groups()
    errors = dead([("x.py", page, anchor)])
    assert errors == ([] if error is None else [f"x.py: {page} {error}"])
