# Docs scrub: pare the living docs, then keep them pared

## Context

Consecutive sessions each appended a caveat to the nearest paragraph instead of restructuring, so the living docs
(about 55k words) file facts by the PR that found them, restate one fact in three or four homes, repeat the generated
matrix in prose, and carry plan and commit history. Trigger: the "A **group**" bullet in the Zigbee2MQTT page. Two
read-only Opus audits plus my own read of the seven user-facing pages produced the findings below. Outcome: about 35k
words with no device fact lost, and checks that make a later addition pay for itself.

Frozen and untouched: `docs/**/research/`, `docs/plans/`, `docs/audits/`, test records, generated blocks.

## Decisions (settled with Jason, 2026-11-26)

1. **Shared Zigbee page:** build it, `docs/integrations/zigbee.md`.
2. **Class headings stay on each integration page** (`gen_compat.py` `check_sections` needs them); no generator change.
3. **Control4's bundle is its owner's: no edit to `docs/integrations/control4/`.** No issue filed. Its budget is set at
   today's size (index 681, internals 3,894 words), so it can't grow; the paragraph cap skips it. The checks stop
   growth and the docs rule makes each edit a deletion pass; neither shrinks an untouched passage.
4. **Word budgets: yes**, one shared file, so a raise is a line a repo maintainer sees.
5. **All three regrowth checks**, landing last, set against the pared docs.
6. **Plans stay in `docs/plans/`**; living docs stop citing them.

## Rules for every step

- One fact, one home (`CLAUDE.md`, Where facts go); elsewhere one sentence and a link.
- No fact is dropped: it stays, moves to its home, or (history only) goes. Each step's PR body lists what moved where
  and what was cut.
- State the present. `Decision N`, plan links, SHAs and write-ups of superseded builds go; a source walk of 400+ words
  becomes a new dated research file, with a 3 to 6 row table left behind.
- No level word in `index.md` headings or anywhere in `internals.md`.
- Target x action -> result, and class -> value, are tables.
- A heading that `devices.yaml` `section:` or a README card links keeps its text. Run `scripts/gen_compat.py --check`
  and the lychee hook after every step.

## Steps (one PR each, in order)

### 1. `docs/evidence.md` (7,260 -> about 3,800) — opus
Binding rule text. Reconcile first: "The Labs flag" still says new items ship flagged and need a pass to lift, which
contradicts tenets 10 and 11. The rewrite changes wording and layout, never what a rule requires (Review, below).
Outline: Tenets (rule + one-line why; drop "This prevents... replaces...") · Levels (route table) · Classes · Refusals
(one table: no known method, not built, `NotBuilt` entry, `class_unknown`; harm points at `Action.failure_harms`) ·
Contrary evidence · The Labs flag (three short paragraphs) · Caveats (unchanged) · Release gate · Sign-off format ·
Coverage check (two sentences + `gen_compat.py`) · Worked examples (about 6). Blob-binding, crediting and format-1/2
mechanics move to the docstrings of `tests/transcripts.py`, `scripts/signoff.py`, `scripts/gen_compat.py` and the
schema description. Cut the three plan links.
Must survive: the harm definition; narrowest identity (model ID + manufacturer string, firmware where it decides); a
class spanning vendors is never Documented by a sibling's pass; a standard-converter departure is a withdrawal; the
bridge route's no-harm restriction; mixed vs all-Labs sign-off; `cut-release` checks the latest RC's commit; a blob git
lacks stands for nothing; formats 1 and 2 sign nothing off; model IDs come from the device.
Then `CONTRIBUTING.md`: the principle and Fast track step 4 shrink to the user-level rule plus a link.

### 2. Zigbee: shared page, Zigbee2MQTT pair, ZHA pair — opus (public text, placement calls)
- **New `docs/integrations/zigbee.md`:** brand facts true on both transports (why classes exist, IKEA GU10s, Sengled,
  Tuya identity, the Zigbee 3.0 dimming argument, the TS011F result). Linked from `docs/integrations.md`.
- **Class-section shape, both pages:** what identifies the class; what differs from the matrix that a user would trip
  on; the source. Delete sentences that only restate built or not built (the reason is in `refusals.py`).
- **Z2M `index.md` (4,627 -> about 2,800):** new `## Groups` (table; Tuya, TS011F and datapoint clauses move under
  Tuya) and `## Right after startup` (the `class_unknown` window and the bridge-subscribe failure, once). Lowest
  brightness becomes a class table.
- **Z2M `internals.md` (8,859 -> about 5,000):** Addressing as Devices / Groups / Base topic plus a multi-endpoint
  table; `fade` lowest level as a five-row table; each measurement once (module states the call, Tested behavior the
  number, Upstream defects the workaround); the stop pin's "fix if it bites" and the Sengled survey move to
  `docs/deferred.md`; the fixed identifier bug moves to `core/identifiers.py`'s docstring.
  Must survive: topic and unique-ID grammars; awaiting the On before 0x42; countdown bounds (1 to 43,200 s; datapoint
  43,200 / 86,400 / 7,210 s); Sonoff mode-ON trap; 16-bit truncation over 32,767.5 s; Tuya gang >= 4 mis-encoding;
  `turnsOffAtBrightness1` and `allEqual`; the standard light's raw level 2 and what reopens it; the 0.25 s vs 2 s
  `set_check` settle; `hue_native_control` lock and write-back; the restore journal's never-replace rule.
- **ZHA (index 1,300, internals 3,009 -> about 3,000 together):** the `classes` quirk walk becomes a research file and
  a six-row table; the parked Tuya recipe moves to `deferred.md`.
  Must survive: `UNSUP_CLUSTER_COMMAND` after the plain On; ZBMINIR2 1.0.1 lacks 0x42; the SWV valve reads seconds;
  strings and quirk fixed before entities exist; group read-back retries 0.5 s x 3.

### 3. The rest — sonnet (moves settled here; the checks catch a miss)
- `docs/internals.md`: add Control4 to the intro list; the Zigbee 3.0 paragraph becomes a two-line rule + link.
- Matter and Hue internals: drop Decision tags; Matter read-back paths as a table; Hue class-admission reasoning
  (about 1,000 words) moves to its `index.md` class sections or a research file. Shelly internals: drop the level line.
- `docs/integrations.md`: rewrite "Zigbee plugs and switches"; point Groups at the dispatcher docstring.
- `docs/design.md`: contract-table cells to 25 words or fewer; Coverage view as bullets. Keep the
  `brightness_pct` rounding fact and the semaphore and `hold` ordering.
- `docs/action-behavior.md`: Refused | Dropped table; response keys table; group fallback one line. Keep "absent
  never means clear", `merge_response` forbids `entity_id`, nothing-to-do before class.
- `docs/deferred.md`: entries to about 80 words; pull each cited Decision's rationale in; fix the entry count.
- Group fallback's one home is `core/dispatcher.py`'s docstring; every other doc links it.
- Light pages (Hue, Shelly, Matter `index.md`): the "report a device test" link once per page.

### 4. Forcing functions — sonnet; has code, so the PR audit runs
- **`scripts/check_docs.py`** (pre-commit hook beside `check-logging`, and a `tests.yml` step beside
  `gen_compat.py --check`), with a unit test:
  1. living docs: no `Decision \d+`, no `plans/` link, no commit SHA (hex with a letter and a digit, 7+ chars, word-bounded);
  2. `*/internals.md`: no `Labs`, `Documented`, `Verified`;
  3. `*/index.md`: no bullet or paragraph over 80 words; skip list: `control4`;
  4. word budget per living doc from `docs/word-budgets.yaml`: measured size + 10%, Control4 at today's size.
- **`.claude/rules/docs.md`**, path-scoped to `docs/**`: every edit is a deletion pass; a fact goes under the heading
  of the thing it is about; state the present; a class section says only what differs from the matrix; a plan names
  the doc and heading for each new user-facing fact.
- **`.claude/skills/audit-code/SKILL.md`:** one readability line: flag a doc fact restated from another home, and a
  caveat appended where a restructure was due.
- **`CLAUDE.md`, Where facts go:** one pointer to `check_docs.py`; `docs/repo-maintainers.md`: who raises a budget.

## Review: Opus reads every diff; Jason hears by exception

Each step's diff goes to a fresh `plan-reviewer` on `opus` (steps 3 and 4 too: a sonnet implementer's prose is what
this plan exists to fix). It gets the plan, the step, the diff range and the pre-change files, never the implementer's
report, and checks: every must-survive fact and every fact on the PR body's moved list is present at its new home
(`rg` for its key term); nothing on the cut list is a device fact or a rule; no rule in `evidence.md`, `design.md`,
`action-behavior.md` or `CONTRIBUTING.md` requires more, less or something else than before; the step's rules hold.
The orchestrator rules on its findings and merges without waiting for Jason.

Escalate to Jason, with `AskUserQuestion`, one question per call, only:
1. a rule whose meaning must change to resolve a contradiction, when the two texts disagree on what ships or what is
   refused and tenets 10 and 11 don't settle which stands;
2. a fact two docs state differently, when no record, research file or code says which is right;
3. a fact the reviewer and implementer disagree on cutting after one round;
4. anything this plan doesn't settle that changes what a user or contributor is told to do.
Each is recorded here as a numbered Decision. Everything else is the orchestrator's call, named in the step's
`Plan review:` commit note.

## Coordination

Intent: pare the living docs to one fact per home and add checks that bound them.
Touches: docs/evidence.md, docs/design.md, docs/deferred.md, docs/action-behavior.md, docs/internals.md,
docs/integrations.md, docs/integrations/zigbee.md, docs/integrations/{zigbee2mqtt,zha,matter,hue,shelly}/*.md,
CONTRIBUTING.md, CLAUDE.md, scripts/check_docs.py, docs/word-budgets.yaml, .claude/rules/docs.md,
.claude/skills/audit-code/SKILL.md, .pre-commit-config.yaml, .github/workflows/tests.yml

## Verification

- Every step: `.venv/bin/python scripts/gen_compat.py --check`; `pre-commit run --all-files` (lychee catches a dead
  anchor); `.venv/bin/pytest -n auto --transcripts=check`.
- Every step: `git diff --stat -- docs/integrations/control4` is empty.
- Every step: the Opus review above, before merge.
- Step 4: `check_docs.py` passes on main after steps 1 to 3, and fails on a fixture with each of the four faults.

## Implementing

A fresh `opus` session orchestrates (steps 1 and 2 are binding rule text and public copy); implementers per step as marked.
