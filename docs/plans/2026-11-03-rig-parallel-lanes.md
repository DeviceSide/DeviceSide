# Rig: run fixed-bulb cases in parallel lanes

## Context

A full rig run executes every case one at a time, taking over an hour. Cases on different integrations' fixed
bulbs don't interact, so they can run side by side. Two things in the rig are genuinely shared, and both stay serial:

- **The roaming bulb** (and the rig-made groups and scenes, `Profile.made_entities`) can only be on one network
  at a time.
- **device_side's `predicted_state` option** is global to the integration, and saving it reloads the config
  entry (`EntryOptions.apply`, `tests/rig/engine.py`). That reload would cut off any fade in progress on every
  integration.

This is option A from the discussion. A **parallel head** runs first: one lane per integration, holding every case
that avoids both of the above. Then a **serial tail** runs exactly as today: the roaming phases plus the
`*-predicted_state` suites. On the house profile, `rig_seconds` estimates put the head's longest lane at about
29 min and the tail at about 49 min, so a run drops from about 144 to about 78 min. The lab profile gains nothing,
because every case there roams.

Decisions taken: parallel is the default, and `--serial` keeps today's order. Lane output prints live, with each
line prefixed by its integration and suite.

Work in worktree `wt/rig-parallel-lanes` off `release/v0.0.2`. The PR goes into that branch. First step: copy this
plan to `docs/plans/2026-11-03-rig-parallel-lanes.md` and commit it with the work. The plan holds no household
identifiers.

## Which cases go in the head

Add `engine.in_head(case, profile) -> bool`. A case qualifies when all of these hold:
- its suite's step file has no `options`;
- none of its entities or `members` is in `profile.made_entities`;
- none of them is in `profile.power()`, either as a powered entity or as a supply. Cutting a supply in one lane
  would kill another lane's bulb.

The test applies to the (suite, test, role) and is the same for both twins. An observed case therefore goes with its
automated twin, and runs serially after the lanes finish.

## Engine changes (`tests/rig/engine.py`)

1. **`run(..., only=None, lanes=False)`**
   - `only: Callable[[Case], bool]` filters each suite's cases. Cases it drops aren't run or reported.
   - `lanes=True` groups the planned suites by integration. It runs each group's `_Run.automated` sequence as one
     task in an `asyncio.TaskGroup`, then runs the observed cases serially, as today.
   - If a lane raises anything other than a `StepFailure` (which is already caught per case), the TaskGroup cancels
     the other lanes. Each cancelled case still restores its snapshot in `_CaseRun.run`'s `finally`. Re-raise the
     first exception unwrapped from the `ExceptionGroup`, so callers (RoamError handling, signal cancel) see the
     same types as today.
2. **Options, once.** Before the TaskGroup starts, call `entry_options.apply` with the head's shared wanted options
   (all `predicted_state: False`, or none). After that, every per-case `apply` returns early with no save. Assert
   that all lane suites want the same options, so a future option file can't race into a reload.
3. **Output.** In lanes mode, `_Run.report` prefixes each line with `"{integration} / {suite.name}  "`, and the
   per-suite header lines are dropped. Serial output is unchanged.
4. **Results across head and tail.** Add `merge(parts, ...) -> RunResult`.
   - It joins the SuiteResults for one suite (keyed by integration and suite name) and orders the cases as
     `cases()` lists them.
   - A SuiteResult filtered by `only` gets `complete=False`. `merge` sets `complete=True` only when every planned
     case is present and no `keyword` was given.
   - This keeps a head-only part, left behind when a RoamError cuts the tail short, from writing a test record that
     misses tail cases.
5. **Journal, one entry per lane.** `Snapshot` currently journals `taken`, `stored` and `power` as top-level
   sections, so concurrent cases would overwrite and clear each other's.
   - Add `Journal.put(section, key, value)` and `Journal.drop(section, key)` (`tests/rig/journal.py`).
   - Give `Snapshot` a `journal_key`: the integration in lanes mode, `"serial"` otherwise. It journals under
     `cases[<key>] = {taken, stored, power}`.
   - The `restore(clear=False)` path (the `restore` step) keeps its entry.

`HAClient` is safe for concurrent use: it matches replies to commands by message id (`tests/rig/client.py`). The
`busy` map is keyed per light. `HueBridge` uses one aiohttp session. None of these need changes; confirm that
while implementing.

## Runner changes (`scripts/rig.py`)

1. **`run_phases`.** In phase 0, after `roamer.go(HOME)`/`make_groups` and before the phase's own run, run the
   head over **all** suites:
   - first `wait_for_targets(..., only=in_head)`, then `pause`, then `run(all suites, only=in_head, lanes=True)`;
   - append its suites to `results` straight away, so `report_ran` keeps them after a failed move;
   - every phase run, phase 0's included, then passes `only=not in_head`.

   Running the head here keeps today's conditions: Hue's fixed cases run with the bulbs at home, as the Hue phase
   does now. `--serial` skips the head and passes `only=None` everywhere, which is exactly today's path.
2. **`targets` / `wait_for_targets` / `plan_lines`** take `only`. `check_devices` is unchanged: it already checks
   every phase.
3. **`report` / `report_ran`** call `merge` before writing the report and records.
4. **`replay`** restores every entry in `journal.get("cases")`. It still reads the old top-level
   `taken`/`stored`/`power` sections, for a journal an older run left on disk.
5. **`estimate`.** Prorate each suite's `rig_seconds` by its share of cases. The head counts as the longest lane,
   the tail as a plain sum. `print_phases` lists an "In parallel" block (one line per lane, with its cases) before
   the phases, which now show only the tail cases.
6. **`--serial`** flag in the CLI. Update the module docstring's paragraph on phases, and add a line to
   `docs/contributing/testing.md` (around its "The suites then run in phases" paragraph).

## Tests (`tests/scripts/`, using `rig_fakes.FakeHA`)

- Two integrations' cases overlap in time with lanes, and don't overlap with `--serial`. For example, each case
  waits on an event only the other lane sets.
- `in_head` excludes option files, roaming bulbs and rig-made groups and scenes, and powered entities and their
  supplies.
- Options are saved at most once before the lanes start, with no reload while they run.
- An unexpected error in one lane cancels the other, restores both lanes' snapshots, and re-raises the original
  exception type.
- The journal holds one entry per lane. Replay restores them all, and still restores a legacy top-level `taken`.
- `merge` gives a suite split across head and tail one complete SuiteResult in file order. A head-only part is not
  recordable.
- A roaming run: the head runs once in phase 0, with the bulbs at home, and the phases run only tail cases. Update
  the existing tests in `test_rig_roam_run.py` that assume the old order.
- The dry-run plan shows the parallel block, and `estimate` uses the longest lane.

## Verification

1. `.venv/bin/pytest`, `pre-commit run --all-files`, and 95% coverage still met.
2. `scripts/rig.py --profile house --dry-run`: the plan shows five lanes, and a tail of roaming and
   predicted_state cases. The estimate should be about 78 min against about 144 with `--serial --dry-run`.
3. **A full house rig run, after Jason's go-ahead** (rig runs need his authorization). Compare its pass/fail table
   and wall time against the last full serial run. A case that passes serially but fails in parallel is radio or
   HA contention: report it with `--serial` as the evidence. Don't add pacing before then (measure before
   guardrails).
4. `/audit-code` on the diff, then open a PR into `release/v0.0.2`.
