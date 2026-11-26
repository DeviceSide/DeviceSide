# Markdown line length: lint at 120

## Coordination

Intent: a pre-commit lint holds Markdown to 120 columns, so long lines are fixed by the session that writes them
instead of being reported by later ones.
Touches: .pre-commit-config.yaml, a rumdl config (`.rumdl.toml` or `pyproject.toml`), `**/*.md` outside the
excluded paths, scripts/gen_*.py (only if a generator emits lines over 120)
Depends-on: #633

## Why

Several sessions have reported over-long Markdown lines, and audits log them as Lows (#322). Nothing checks them:
pre-commit has no Markdown lint, so the global edit hook (which runs pre-commit) can't catch them. Readers see no
difference (GitHub soft-wraps); the cost is session turns and diffs where one word marks a paragraph changed.

## Decisions

1. **Limit 120.** It matches ruff's `line-length` in `pyproject.toml`, and the living docs are already written to it
   (about 760 lines sit at 115 to 120). 100 would rewrap about four times as many lines for nothing a reader sees.
2. **Tool: rumdl**, through its pre-commit repo, rev pinned like the others. It's a Python wheel, so no Node. Only
   MD013 is enabled; every other rule stays off (this PR adds no style rules).
3. **Exempt inside a file:** tables, code blocks, headings, and lines a wrap can't shorten (a bare URL or link).
4. **Excluded paths:** `docs/plans/`, `docs/audits/` and `notes/` (historical records), every `research/` directory
   (dated sources, never edited after), and generated output that a generator owns wholesale (at least
   `docs/device-compatibility.md`). The exclude list lives in one place: the rumdl config, or the hook's `exclude`, not both.
5. **Autofix.** Enable rumdl's MD013 reflow if it leaves lists, blockquotes, HTML comments and generator markers
   intact; then the edit hook fixes long lines silently. If reflow mangles any of those, ship report-only and say so in
   the PR body.
6. **Generated sections** (README cards, generated parts of `docs/integrations.md` and CONTRIBUTING): if their long
   lines come from a generator, the generator wraps them, so `gen_compat.py --check` and the lint agree. A line a
   generator can't wrap (a table row) is already exempt under 3.
7. **One-time cleanup in this PR:** rewrap every existing violation. Whitespace only: no word changes.

## Steps

1. After #633 merges (`wait-pr 633`), merge `origin/main` into this branch.
2. Add the hook and config per Decisions 1 to 5. Check rumdl's current docs for the option names; don't guess.
3. Fix generators per Decision 6, then run `pre-commit run --all-files rumdl` (with reflow, or by hand) for Decision 7.
4. Confirm the diff is whitespace only outside the config and generators: `git diff -w --word-diff origin/main` shows
   no word changes in `*.md`.

## Checks

- `pre-commit run --all-files` passes.
- `.venv/bin/python scripts/gen_compat.py --check` and the other generators' `--check` pass.
- `.venv/bin/pytest -n auto --transcripts=check` passes.
- The edit hook catches a new long line: add a 130-column prose line to a doc, run `pre-commit run --files <doc>`,
  and see it fixed (reflow) or reported; then revert it.

## Owners

The cleanup touches integration bundles, so `owner-notice.yml` will name their maintainers. Per the maintainer
rules, ask Jason how to handle it before `gh pr ready`, and record his answer in the PR body.
