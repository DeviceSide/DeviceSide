---
paths:
  - "docs/**"
---

# Editing docs

`scripts/check_docs.py` enforces the mechanical part (no Decision tags, plan links or commit SHAs; no level words in
`internals.md`; no `index.md` item over 80 words; a word budget per doc in `docs/word-budgets.yaml`). The rest:

- Every edit is a deletion pass: before adding a sentence, find one to cut or merge.
- A fact goes under the heading of the thing it is about, not appended where you happened to be reading.
- State the present. History, rationale from a plan and "was X, now Y" go in the PR body or a dated source.
- A class section says only what differs from the matrix; what it inherits is not restated.
- A plan names the doc and heading for each new user-facing fact.
