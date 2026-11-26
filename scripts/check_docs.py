#!/usr/bin/env python3
"""Keep the living docs pared (docs/plans/2026-11-26-docs-scrub.md, step 4).

Living docs are LIVING_GLOBS minus EXCLUDED_GLOBS: docs/**/*.md and CONTRIBUTING.md, less the dated sources
(research, plans, audits, release notes) and the generated pages. Four checks, each reported as file:line and a reason:

- a living doc names no "Decision N", links no docs/plans/ file, and writes no commit SHA in prose. Link targets and
  bare URLs are skipped, so an upstream SHA stays as a permalink pin. Text between generated-block markers is skipped.
- `*/internals.md` never uses the evidence levels' names (Labs, Documented, Verified): levels live in
  docs/device-compatibility.md.
- `*/index.md` has no bullet or paragraph over MAX_ITEM_WORDS words (INDEX_SKIP lists the bundles exempt for now).
- each living doc is within its line in docs/word-budgets.yaml, in whitespace-separated words outside generated blocks;
  a living doc with no line fails, so a new doc adds one. A repo maintainer approves a raise (docs/repo-maintainers.md).

Usage: scripts/check_docs.py   (pre-commit and CI run it on the whole repo)
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).parents[1]
BUDGETS = REPO / "docs" / "word-budgets.yaml"

# The one definition of a living doc. Generated pages are written wholly by scripts/gen_compat.py
# (device-compatibility.md) and scripts/zhc_table.py (standard-lights.md);
# docs/integrations.md and others carry generated blocks only, which every check skips.
LIVING_GLOBS = ("docs/**/*.md", "CONTRIBUTING.md")
EXCLUDED_GLOBS = (
    "docs/**/research/**",
    "docs/plans/**",
    "docs/audits/**",
    "docs/release-notes/**",
    "docs/device-compatibility.md",
    "docs/integrations/zigbee2mqtt/standard-lights.md",
)
MAX_ITEM_WORDS = 80
INDEX_SKIP = ("control4",)
LEVEL_WORDS = ("Labs", "Documented", "Verified")

GENERATED_BLOCK = re.compile(r"(<!-- (\w+):start -->).*?(<!-- \2:end -->)", re.DOTALL)
LINK_TARGET = re.compile(r"\]\([^)]*\)")
BARE_URL = re.compile(r"https?://[^\s)>\]]+")
DECISION = re.compile(r"\bDecision \d+\b")
PLANS_LINK = re.compile(r"\bdocs/plans/|\]\((?:\.\./)*(?:\./)?plans/")
SHA = re.compile(r"\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*[0-9])[0-9a-f]{7,40}\b")
BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")


def living_docs() -> list[Path]:
    found = {p for pattern in LIVING_GLOBS for p in REPO.glob(pattern)}
    excluded = {p for pattern in EXCLUDED_GLOBS for p in REPO.glob(pattern)}
    return sorted(p for p in found - excluded if p.is_file())


def blank_out(text: str, pattern: re.Pattern[str]) -> str:
    """The text with each match replaced by spaces, so line numbers and offsets hold."""
    return pattern.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def prose(text: str) -> str:
    """The text a prose check reads: generated blocks, link targets and bare URLs blanked."""
    return blank_out(blank_out(blank_out(text, GENERATED_BLOCK), LINK_TARGET), BARE_URL)


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def word_count(text: str) -> int:
    """Whitespace-separated words."""
    return len(text.split())


def history_faults(rel: str, text: str) -> list[str]:
    """Decision tags, plan links and commit SHAs."""
    faults = []
    for match in DECISION.finditer(prose(text)):
        faults.append(f"{rel}:{line_of(text, match.start())}: {match.group(0)!r} is a plan's, not a living doc's")
    for match in PLANS_LINK.finditer(blank_out(text, GENERATED_BLOCK)):
        faults.append(f"{rel}:{line_of(text, match.start())}: a living doc links no plan")
    for match in SHA.finditer(prose(text)):
        faults.append(f"{rel}:{line_of(text, match.start())}: commit SHA {match.group(0)!r} in prose")
    return faults


def level_faults(rel: str, text: str) -> list[str]:
    """An internals.md names no evidence level."""
    pattern = re.compile(r"\b(" + "|".join(LEVEL_WORDS) + r")\b")
    return [
        f"{rel}:{line_of(text, m.start())}: {m.group(1)!r}: levels live in docs/device-compatibility.md"
        for m in pattern.finditer(blank_out(text, GENERATED_BLOCK))
    ]


def items(text: str) -> list[tuple[int, str]]:
    """Each bullet and paragraph as (first line, text); headings, tables and fenced code are skipped."""
    found: list[tuple[int, str]] = []
    current: list[str] = []
    start = 0
    fenced = False

    def close() -> None:
        if current:
            found.append((start, " ".join(current)))
            current.clear()

    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            close()
            fenced = not fenced
        elif fenced or not line.strip() or line.lstrip().startswith(("#", "|")):
            close()
        elif BULLET.match(line):
            close()
            start = number
            current.append(line.strip())
        else:
            if not current:
                start = number
            current.append(line.strip())
    close()
    return found


def length_faults(rel: str, text: str) -> list[str]:
    return [
        f"{rel}:{number}: {word_count(item)} words in one item (max {MAX_ITEM_WORDS}): split or cut it"
        for number, item in items(blank_out(text, GENERATED_BLOCK))
        if word_count(item) > MAX_ITEM_WORDS
    ]


def read_budgets(path: Path = BUDGETS) -> dict[str, int]:
    """docs/word-budgets.yaml's `path: words` lines (a flat map; no YAML library needed)."""
    budgets = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([^:\s]+):\s*(\d+)\s*(?:#.*)?", line.strip())
        if not match:
            raise SystemExit(f"{path.name}:{number}: expected 'path: words'")
        budgets[match.group(1)] = int(match.group(2))
    return budgets


def budget_faults(docs: dict[str, str], budgets: dict[str, int]) -> list[str]:
    faults = []
    for rel, text in docs.items():
        if rel not in budgets:
            faults.append(f"{rel}:1: no line in docs/word-budgets.yaml: a new doc adds one")
        elif (words := word_count(blank_out(text, GENERATED_BLOCK))) > budgets[rel]:
            faults.append(f"{rel}:1: {words} words, budget {budgets[rel]}: cut, or a repo maintainer raises the budget")
    faults.extend(f"docs/word-budgets.yaml: {rel} is no living doc" for rel in budgets if rel not in docs)
    return faults


def check(docs: dict[str, str], budgets: dict[str, int]) -> list[str]:
    """Every fault in `docs` (path relative to the repo -> text)."""
    faults = []
    for rel, text in docs.items():
        faults += history_faults(rel, text)
        if rel.endswith("/internals.md"):
            faults += level_faults(rel, text)
        if rel.endswith("/index.md") and not any(f"/{name}/" in rel for name in INDEX_SKIP):
            faults += length_faults(rel, text)
    return faults + budget_faults(docs, budgets)


def main() -> int:
    docs = {str(p.relative_to(REPO)): p.read_text() for p in living_docs()}
    faults = check(docs, read_budgets())
    print("\n".join(faults))
    return 1 if faults else 0


if __name__ == "__main__":
    sys.exit(main())
