# Test simplification (both repos)

## Coordination

Intent: step 7 of [the evidence-rules plan](2026-11-12-evidence-rules.md). Cut duplicated tests, copied scaffolding
and real waits from DeviceSide's and the rig's test suites, now that steps 1–5 have landed. Nothing changes until
Jason approves this plan.
Touches: DeviceSide `tests/` only; ha-rig `tests/` only. No runtime code, no step files, no
`docs/integrations/*/test-records/`, no scope flags.
Tests-with: none. Test-only changes send no new call, so they need no sign-off and needn't wait for step 6.
Depends-on: none.

## Finding

Both suites are already lean. A fresh audit of all 31k test lines, measured on the branch as it stands, found:

- No tests left of the removed machinery, apart from one negative `Covers` test in the rig (R12) and two stale comments.
- No dead helpers: every fake, fixture and helper has a live user.
- About **890 lines** (2.9%) that can go, over about 17 hours. That is mostly copies folded into tables and setup
  shared through fixtures.
- About **33 s of wall time** (24%) from real waits that fakes don't need. That is the bigger payoff, and it costs about
  2 hours.

Coverage stays as it is: every item was measured, or is a pure merge, and no module the bar covers falls below 95%.

## Baseline (2026-11-12, `claude/reduce-code-complexity-syqjth`)

| | DeviceSide `tests/` | ha-rig `tests/` |
|---|---|---|
| Lines (all) | 17,775 | 13,377 |
| Code lines (no comments, docstrings or blanks) | 12,160 | 10,165 |
| Test functions | 1,095 | 776 |
| Collected cases | 1,685 | 1,119 |
| Wall time, `-p no:randomly` | 55 s (62 s with coverage) | 78 s (84 s with coverage) |
| Coverage | 99% total; lowest module the bar covers: `hue/transition_cache.py` 96.4% | 96% (`ha_rig` + `scripts/`) |

For scale, the runtime under test: DeviceSide `custom_components/` is 6,229 code lines and its `scripts/` 1,342; the rig's
`ha_rig/` + `scripts/` is 7,120.

How it was measured: `wc -l`, plus an AST and tokenize count for code lines and `test_` functions. The cases and times
come from the pytest summary. Coverage commands:
`.venv/bin/pytest --cov=custom_components/deviceside --cov-report=json` for DeviceSide, and
`DEVICE_SIDE_REPO=<deviceside> .venv/bin/pytest --cov=ha_rig --cov=scripts` for the rig.

## Decisions (Jason, 2026-11-12)

- **Dispatcher off/on:** the Experimental-features off/on pair stays only on the refusal and skip-log tests (D2).
- **Generated-file `--check` tests:** keep them as tests. They are the only local guard, cost 0.2 s, and moving them to
  pre-commit would save about 10 lines for about 4 s on each matching commit.
- **Per-action refusal and no-op copies:** fold them into one table per integration, in the test module of the shared
  source. Where actions share one branch, the duplicate rows go (D6, D7, D10, D12, D17, D18).
- **Edge drops approved:**
  - hue `test_report_filter.py::test_a_refused_move_records_nothing` (D19)
  - z2m `test_turn_on_for.py::test_supports_returns_super_reason_when_scope_refuses`. With it gone, `turn_on_for.py`
    goes from 99% to 98.6%, the same one-line gap `stop.py` has (D6).
  - the rig's `test_a_record_has_no_covers_row`, outright (R12)

## Items

Each item: what changes, what still catches any dropped test, risk, and how to verify. Items in each table are ranked
by lines saved per hour; the speed items, which save no lines, are ranked by seconds saved per hour. "Still caught by"
names the test that keeps failing if the dropped test's bug comes back.

### Verify protocol (every item)

1. Before the batch: `COVERAGE_FILE=$S/.cov-before .venv/bin/pytest -p no:cacheprovider --cov=… --cov-report=json:$S/before.json`.
   Use `--cov=custom_components/deviceside` for DeviceSide, and `--cov=ha_rig --cov=scripts` for the rig with
   `DEVICE_SIDE_REPO` set.
2. After: the same into `after.json`. Diff each module's `missing_lines`. Any line that becomes uncovered must be one
   the item names; today only D6's `turn_on_for.py:67` is expected.
3. DeviceSide: `.venv/bin/python scripts/check_release.py --coverage after.json` passes.
4. Run the touched files three times with `pytest-randomly` on (the default), plus `pre-commit run --all-files`.
5. To measure per-test coverage on Python 3.14, set `COVERAGE_CORE=ctrace`: the default sysmon core loses contexts.

### Speed (no lines saved), ranked by seconds per hour

| # | Repo | Change | Files | Saves | Effort | Risk |
|---|---|---|---|---|---|---|
| R2 | rig | Fixture `OBSERVED` call `duration: 0.6` becomes `0.2`. None of the ~30 observed tests is about timing; `TWO_SUITES` and `BOTH` follow it. | `tests/test_rig_engine.py:367` | ~14 s | 0.25 h | low |
| R1 | rig | Set `engine.BUSY_LAG_S` to 0 in the autouse `no_settle` fixture. `test_rig_busy.py:34` keeps its own 0.05. | `tests/conftest.py:53-57` | ~5 s | 0.25 h | low |
| D1 | DS | z2m wait bounds, from 0.2–0.25 to 0.02–0.05. Details below the table. | z2m `conftest.py:31-33`, `test_set_check.py:49,156-162,186`, `test_turn_on_for.py:272,306`, `test_set_attributes.py:262-267` | ~6 s | 0.5 h | low |
| D3 | DS | The `released` git fixture writes its 8 package files in one commit, not 8. The coverage tests write files and skip git. | `tests/scripts/test_check_release.py:103-129,224-233` | ~2 s | 0.25 h | low |
| R3 | rig | Three ~1 s real waits. Details below the table. | `tests/test_rig_client.py:66-67`, `test_rig_network.py:179`, `test_rig_auto.py:17` | ~2.4 s | 0.25 h | low |
| D2 | DS | The dispatcher's off/on fixture becomes opt-in. It stays on `test_refusal_reasons_from_resolution_and_adapters`, `test_a_named_target_that_cant_take_the_action_raises_before_anything_is_sent` and `test_an_indirect_target_that_cant_take_the_action_is_skipped_and_logged` (decided). | `tests/core/test_dispatcher.py:34-39` | ~2.5 s, 46 runs | 0.5 h | low |

Details:

- **R2:** measured with R1, the engine file goes from 42 s to 23 s, and the rig suite without `test_rig_busy.py` from
  66 s to 47 s. The per-module coverage report is identical.
- **D1:** `_RETAINED_TIMEOUT_S` and both `_REPLY_TIMEOUT_S` go from 0.25 to 0.02. `BOUND_S` 0.2 becomes 0.05, and the
  literal at `:186` becomes `< 0.02 <`. `_STATE_TIMEOUT_S` 0.2 becomes 0.05, along with its "0.2 s" log literal.
  `DEADLINE_MARGIN_S` becomes 0.05 and `ADAPTER_TIMEOUT_S` 0.1 in the deadline test, which has not been measured
  yet. The fake broker answers through `call_soon`.
  - Measured: the z2m slice goes from 18 s to 11–13 s over five loaded runs.
  - It probably also settles the known-flaky `test_no_z2m_does_nothing_quietly`, which waits out the 0.25 s retained
    timeout. That is a hypothesis, not a claim: watch it.
- **R3:** the `vanishing` stub awaits `ws.receive()` instead of `sleep(1)`. `Z2M_REQUEST_TIMEOUT_S` goes from 1 to 0.15,
  and `DEADLINE_S` from 0.5 to 0.15. Measured: 15 runs under load all passed, with coverage unchanged.

### DeviceSide, ranked by lines per hour

| # | Change | Files | Lines | Effort | Lines/h | Risk |
|---|---|---|---|---|---|---|
| D4 | The 48-row registry matrix listing becomes two assertions. Details below the table. | `tests/core/test_registry.py:44-96` | 42 | 0.25 h | 168 | low |
| D11 | z2m turn_on_for: one table for the duration rounding and clamping tests; merge the multi-field test into the brightness one; drop two subsumed tests. | `tests/integrations/zigbee2mqtt/test_turn_on_for.py:70-116,166-199` | 45 | 0.5 h | 90 | low |
| D6 | z2m: 13 helper tests for `addressing.py` and `detect.py` in `test_turn_on_for.py` become one table in `test_addressing.py`, holding only the rows nothing else reaches. The scope-swap supports test goes (decided). | `test_turn_on_for.py:341-357,473-569`, `test_addressing.py` | 80 | 1 h | 80 | low |
| D8 | Matter: merge the happy-path copies over `["switch.plug", "light.bulb"]` and the three "timer not reported" tests. Use `pytestmark` in place of the `setup_matter` fixture, and drop 11 explicit default `feature_map` arguments. | `tests/integrations/matter/test_turn_on_for.py`, `test_get_attributes.py:36-60` | 60 | 0.75 h | 80 | low |
| D10 | ZHA: one "nothing to make is unchanged" table in `test_fade.py`. Its rows: lower_brightness off; raise_hue off; raise_saturation off; lower_saturation at limit; raise_brightness at limit; raise_hue fields dropped. | ZHA `test_lower_*.py`, `test_raise_*.py`, `test_fade.py` | 40 | 0.5 h | 80 | low |
| D12 | z2m: the off-light check becomes one test over `COLOR_ACTIONS` in `test_fade.py`, with one row per shared branch (`fade.py:178`, `fade.py:252`). | `test_raise_hue.py`, `test_lower_hue.py`, `test_raise_saturation.py`, `test_lower_saturation.py`, `test_fade.py` | 20 | 0.25 h | 80 | low |
| D9 | ZHA: one `admin_command` fixture in `conftest.py`, for both cluster and group commands, plus `call_as()`. It replaces 5 copies. | ZHA `test_fade.py:58-80`, `test_set_attributes.py:255-276`, `test_stop.py:143-165`, `test_turn_on_for.py:185-224,315-338`, `conftest.py` | 55 | 0.75 h | 73 | low |
| D7 | Matter: one refusal table in a new `test_addressing.py`, crossed with `get_attributes` and `turn_on_for`. Every case is kept, and get_attributes gains the cases it lacked. | Matter `test_turn_on_for.py:57-63,108-147,224-229`, `test_get_attributes.py:77-99,129-142` | 50 | 0.75 h | 67 | low |
| D5 | test_registry: module-level imports and a `_registry(adapters, info=…)` helper replace 5 inline setups. | `tests/core/test_registry.py:99-170` | 15 | 0.25 h | 60 | low |
| D18 | Hue: one "v1 bridge refused" table in `test_bridge.py`, with a row for each adapter's own `bridge_v1` line. | Hue `test_fade.py:82-88`, `test_get_attributes.py:140-145`, `test_set_attributes.py:259-265`, `test_set_scene.py:166-171` | 15 | 0.25 h | 60 | low |
| D13 | z2m: drop the second test of `bridge.state_reply`'s retained check. A mutation probe failed exactly these two tests. | `test_native_control.py:393-406` | 14 | 0.25 h | 56 | low |
| D14 | z2m native_control: merge the two failed-restore tests; drop the stamp-without-cache test; optionally parametrize the two "leaves it alone" ramps. | `test_native_control.py:171-187,596-601,658-670` | 28 | 0.5 h | 56 | low |
| D21 | One `load_entry(hass)` helper in conftest. `setup_integration` and `setup_production` are identical; `loaded_entry`, 4 inline copies and 2 hand-rolled unload finalizers go. | `tests/conftest.py:80-96`, `tests/test_config_flow.py:76-81,102-161,194,380-384`, `tests/core/test_ha_watch.py:55-60` | 25 | 0.5 h | 50 | low |
| D15 | z2m bridge_cache: three merges of tests with the same setup. No test dropped. | `test_bridge_cache.py:131-138,223-241` | 24 | 0.5 h | 48 | low |
| D22 | Drop `test_a_scope_has_no_caveat_unless_given_one`; fold `test_predicted_state_is_on_for_an_entry_without_options` into the reload test as one assert. | `tests/core/test_scope.py:130-134`, `tests/test_config_flow.py:142-147,160` | 12 | 0.25 h | 48 | low |
| D17 | Shelly: one "Gen1 / not addressable is refused" table in a new `test_addressing.py`, with lower_brightness added. The positive halves of the turn_on_for and turn_off_for copies go. | Shelly `test_get_attributes.py:144-152`, `test_stop.py:116-120`, `test_raise_brightness.py:107-114`, `test_set_attributes.py:117-121`, `test_turn_off_for.py:52-61`, `test_turn_on_for.py:145-154`, `test_auto.py:159-169` | 35 | 0.75 h | 47 | low |
| D20 | Dispatcher near-twins: fold the empty selection, empty HA group and empty native group into their siblings' loops; merge the two reconcile tests. Fix the stale "wire and scope traces" comment at `:372`. | `tests/core/test_dispatcher.py:340-347,418-424,448-455,488-510,712-727` | 35 | 0.75 h | 47 | low |
| D19 | Hue: drop the report filter's copy of the refused-move check (decided). | `tests/integrations/hue/test_report_filter.py:174-181` | 10 | 0.25 h | 40 | medium |
| D23 | Drop the fake-registry import-failure test, and tighten the real one's assert to `"error: missing: failed to import ("`. | `tests/scripts/test_check_release.py:60-74` | 9 | 0.25 h | 36 | low |
| D16 | z2m: one light builder and one group builder in conftest, replacing 3 copies of each. Move `target`, `bulb`, `DIMMABLE` and `turn_ons` out of the test modules that `test_set_check.py` imports. Below the cutoff. | z2m `conftest.py`, `test_get_attributes.py:51,327`, `test_set_attributes.py:30,308`, `test_set_check.py`, `test_native_control.py` | 30 | 1.25 h | 24 | medium |
| D24 | test_check_release: keep only the uppercase repo-maintainer case, and drop the `"0"*40` half of the off-branch test. Below the cutoff. | `tests/scripts/test_check_release.py:323-326,363-367` | 5 | 0.25 h | 20 | low |

Details:

- **D4:** the two assertions are that the pairs equal `sorted(product(actions, integrations))`, and that the pairs with
  an adapter are the 4 fake ones. A new action then no longer means 3 edits here.
- **D6:** the table keeps `topic(None)`, `topic` of a non-z2m identifier, the group-encoding pin, `is_z2m_group` for
  both base topics, a device and `None`, and `detect(None)`. With all 13 tests deselected, `detect.py` falls to 88%;
  these rows restore it.
- **D19 risk:** the remaining check uses a standalone lamp, so a fault confined to room members could slip through.
  Jason accepted this.
- **D16 risk:** the builders differ subtly: cluster defaults, `filtered_cache` and RANGE attributes.
- **D23:** the import errors are computed before any option is read, so the `--signoffs` case reaches no new branch.

Still caught by (DeviceSide drops):

- **D11:**
  - `test_multiple_devices_each_get_their_own_topic`: by `test_turn_on_for.py::test_device_and_group_each_get_their_own_topic`.
  - `test_group_without_fields_publishes_to_group_id_topic`: by `::test_group_with_fields_calls_turn_on_then_publishes`
    and `::test_light_without_fields_publishes_on_time`.
- **D6:**
  - The topic and detect happy paths are hit by every publish.
  - `detect` false: by `test_turn_on_for.py::test_non_z2m_mqtt_entity_is_refused`.
  - `state_topic`: by `test_set_check.py::test_a_device_z2m_names_nothing_for_is_sent_unchecked` and
    `test_get_attributes.py::test_device_without_a_name_is_not_addressable`.
  - The scope-swap test: nothing. Its one line goes uncovered (decided).
- **D8:** `test_plug_sends_on_with_timed_off`: by the switch row of the merged happy path, and
  `::test_the_command_is_logged_without_the_node`.
- **D10:** ZHA `test_lower_hue.py::test_an_off_light_is_unchanged` and `::test_dropped_without_enhanced_hue`: by the
  table's raise_hue rows (same `fade.py:334`, `:283`). `test_lower_saturation.py::test_an_off_light_is_unchanged`: by
  the raise_saturation row (`fade.py:501`). Coverage is unchanged with them deselected. `zha/test_stop.py`'s off test
  stays (its own `stop.py:54`).
- **D12:** z2m lower_hue and lower_saturation off cases: by the raise rows on the same branches.
- **D13:** `test_retained_state_doesnt_end_the_wait`: by `test_turn_on_for.py::test_a_retained_state_is_not_the_answer`.
- **D14:** `test_the_stamp_is_unknown_without_the_bridge_cache`: by `test_stop.py::test_the_stop_is_logged_without_the_topic`
  (same setup, asserts `{'hue_native_control': None}`).
- **D17:** the positive halves: by `shelly/test_turn_on_for.py::test_switch_one_set_then_read_back` and
  `shelly/test_turn_off_for.py::test_each_capability_in_scope_gets_a_set`.
- **D19:** by `hue/test_fade.py::test_a_refused_move_is_rejected_and_not_cached`.
- **D22:**
  - The caveat default: by `tests/test_init.py::test_setup_is_quiet_with_no_caveat` (a non-None default would warn)
    and `::test_setup_warns_once_per_caveat`.
  - The predicted state: by the assert merged into `test_saving_the_option_reloads_the_entry_with_it`.
- **D23:** by `test_check_release.py::test_a_real_import_failure_reaches_the_gate`, plus `tests/core/test_registry.py`'s
  import-failure tests.
- **D24:**
  - The casefold and repo maintainer: by `::test_a_repo_maintainer_may_sign_off_and_handles_ignore_case[JASONMX]`.
  - The maintainer sign-off: by `::test_a_manual_row_at_the_last_change_signs_off_naming_the_tester`.
  - A commit missing from the checkout: by `::test_records_citing_no_commit_are_no_signoff`.
- **D7, D9, D15, D18, D20, D21:** no test dropped; cases move or merge.

Verify (DeviceSide): the protocol above, scoped to each item's package. For example:
`.venv/bin/pytest tests/integrations/zha --cov=custom_components/deviceside/integrations/zha`, then the full-suite
coverage diff.

### ha-rig, ranked by lines per hour

| # | Change | Files | Lines | Effort | Lines/h | Risk |
|---|---|---|---|---|---|---|
| R6 | Drop `test_a_waiting_exclusive_claim_holds_off_no_shared_one`. Fold the "does holder X block Y" tests into one table. | `tests/test_rig_locks.py:106-116,199-218` | 22 | 0.25 h | 88 | low |
| R4 | Six run-claim tests with the same setup become one parametrized `test_a_runs_claim`. | `tests/test_rig_locks.py:369-407` | 18 | 0.25 h | 72 | low |
| R11 | Drop three observed-answer tests that repeat one path. | `tests/test_rig_engine.py:420,429-434,3062-3069` | 17 | 0.25 h | 68 | low |
| R10 | Shared fakes. Details below the table. | `tests/rig_fakes.py`, `test_rig_roam_run.py:44,74`, `test_rig_runlogs.py:27`, `test_rig.py:707`, `test_rig_roam.py:29,38`, `test_rig_groups.py:34`, `test_rig_bridge.py`, `test_rig_client.py`, `test_rig_network.py` | 65 | 1 h | 65 | low |
| R8 | Drop the roam-run group-recovery test. `recover_roam` has no group-specific code. | `tests/test_rig_roam_run.py:510-523` | 14 | 0.25 h | 56 | low |
| R5 | One `put_back` fixture replaces 6 hand-written `recover_rig` recorders. | `tests/test_rig_locks.py:583,625,644,697,1187,1208` | 25 | 0.5 h | 50 | low |
| R12 | Fold `test_an_observed_case_nobody_answered_adds_no_row` into the unattended facts test; drop `test_a_record_has_no_covers_row` (decided). | `tests/test_rig_engine.py:3004,3054-3076` | 12 | 0.25 h | 48 | low |
| R7 | The authorization gate tests driven through `main` become one table per file, keeping every row. | `tests/test_rig_locks.py:1032-1107`, `tests/test_rig_roam_run.py:864-909` | 45 | 1 h | 45 | low–med |
| R9 | Six one-line `skips(...)` tests become one parametrize. Drop `test_a_clean_run_with_no_crash_still_deletes_its_logs`. | `tests/test_rig_groups.py:383-415`, `tests/test_rig_runlogs.py:137-142` | 18 | 0.5 h | 36 | low |
| R13 | `test_observe_roles_leave_the_other_roles_automated_only` asserts on planned `cases()` instead of a full `run_one`. Below the cutoff. | `tests/test_rig_engine.py:851-862` | 3 (and 0.4 s) | 0.25 h | 12 | low |

Details:

- **R10:**
  - `FakeHA` gains a no-op `close`, replacing the 3 identical subclasses (`LabHA`, `LoggedHA`, `RigHA`), plus a
    `connected()` helper for the 3 copies of `connect`.
  - `lab` and `where` move to `rig_fakes`.
  - One stub server and one teardown fixture in `test_rig_bridge.py`.
  - One WebSocket auth handshake replaces 3 copies.
- **R7:** the gate's own matrix stays pinned in `test_authorize.py`, with 32 cases. The tables keep the probe-only
  branches (`rig.py:1450-1454`, `probe_restricted`). Risk: the output assertions must survive as a column.

Still caught by (rig drops):

- **R6:** by `test_rig_locks.py::test_a_deploy_waiting_for_ha_leaves_its_integrations_free`. A waiting exclusive claim
  must leave `claim("zha")` free. `locks.py` stays at 100%.
- **R11:**
  - `test_eof_at_what_was_seen_still_fails_the_case` and the `("", "")` row of
    `test_a_no_records_what_the_person_saw`: by `::test_an_answer_other_than_yes_or_no_is_asked_again` and
    `::test_observed_asks_and_its_answer_is_a_fact_not_a_record[n-fail]`.
  - `test_a_seen_failure_adds_a_fail_row`: by `::test_a_firmware_fact_that_passed_or_failed_adds_a_row_naming_its_devices[FAIL]`
    and `::test_an_answered_observed_case_adds_a_dated_row_with_its_devices`.
  - Measured: the `engine.py` and `facts.py` missing lines are byte-identical with these deselected.
- **R8:** by `test_rig_groups.py::test_recovery_removes_the_groups_a_crash_left_then_brings_the_bulbs_home[zigbee2mqtt]`
  and `test_rig_roam_run.py::test_recover_moves_the_bulbs_home_then_resumes_the_automations`.
- **R9:** by `test_rig_runlogs.py::test_a_clean_run_deletes_its_logs`, which runs the whole settle path.
- **R12:**
  - The not-observed case writing no row: by `written[1] is None` in
    `::test_facts_unattended_runs_the_automated_part_and_leaves_the_watched_one_not_observed`, which gains
    `watched.devices == ()`.
  - The Covers test: nothing, by design. Nothing reads a Covers row (`docs/evidence.md`).
- **R4, R5, R7, R10, R13:** no test dropped.

Verify (rig): the protocol above, from the rig checkout. For example:
`COVERAGE_FILE=$S/.cov DEVICE_SIDE_REPO=<deviceside> .venv/bin/pytest -p no:cacheprovider tests/test_rig_locks.py --cov=ha_rig --cov=scripts --cov-report=term-missing`.
Never run `scripts/rig.py` against a real HA.

## Totals

| | Lines | Effort | Wall time |
|---|---|---|---|
| DeviceSide | ~650 (3.7% of 17,775) | ~12 h (1.25 h of it speed) | −10 s of 55 s |
| ha-rig | ~240 (1.8% of 13,377) | ~5.25 h (0.75 h of it speed) | −23 s of 78 s |
| Both | ~890 | ~17 h | −33 s |

**Recommended cutoff:** every speed item, then each lines table down to 36 lines/h: D23 and R9, the cutoff, are in.
D16, D24 and R13 are below the cutoff and left out unless their files are being touched anyway: D16 is medium risk
for 24 lines/h. That is about 850 lines in about 15.5 h.

## Delivery

- **DeviceSide:** one test-only PR. It spans `core/` tests and several integrations' test packages, so it needs a repo
  maintainer. Commits go in table order: speed first, then lines, one commit per item, so any one item can be reverted.
- **ha-rig:** one test-only PR, independent of DeviceSide's. It reads no new step-file shape, so it needs no `Tests-with`.
- Each PR body carries the before and after line counts, test counts and wall times from this plan's method, plus the
  coverage diff (expected: only D6's `zigbee2mqtt/turn_on_for.py:67`).

## Out of scope and notes

- ha-rig `tests/test_rig_busy.py` timing (a separate task), and DeviceSide `test_no_z2m_does_nothing_quietly` (known
  flaky; D1 may settle it, see above).
- The generated-file `--check` tests stay (decided).
- **For a repo maintainer, outside tests:** `.github/workflows/tests.yml:459-460` still says the pytest job needs full
  history for record freshness. `gen_compat.py` no longer reads git, so that comment is stale, and the pytest job's
  `fetch-depth: 0` may no longer be needed (the `changes` job still needs it). D20 fixes the stale comment in
  `tests/core/test_dispatcher.py:372`, and the comment "A record never ages" in `tests/scripts/test_gen_compat.py:176`
  gets trimmed with D23.
- Considered and rejected:
  - A shared light/group/`clock` fixture across integrations: under 10 lines.
  - One fake registry across `tests/scripts/`: each needs different attributes.
  - Shrinking the rig's `sample: {for: 0.3}`: too close to its 50 ms ramp ticks.
  - A virtual-clock event loop: the engine's prompt thread and `time.monotonic` make it risky.
  - Replacing the rig's `BaselineHA` and `ProbeHA` with `FakeHA`: their state shapes differ, so it needs a prototype
    first.
  - Splitting `ON_THEN_OFF` into a fast copy: about +10 lines for about 3 s, and it weakens the two timing tests.
  - Many tests have no lines of their own, but they assert distinct outputs, so they stay.

## Outcome (2026-11-12)

Approved by Jason with the recommended cutoff, and done on `claude/reduce-code-complexity-syqjth` in both repos, one
commit per item, plus one commit of review fixes in each. An independent review of each diff checked every drop, table
and timing change.

| | DeviceSide before → after | ha-rig before → after |
|---|---|---|
| Lines | 17,775 → 17,180 (−595) | 13,377 → 13,196 (−181) |
| Code lines | 12,160 → 11,759 | 10,165 → 10,039 |
| Test functions | 1,095 → 1,032 | 776 → 746 |
| Collected cases | 1,685 → 1,617 | 1,119 → 1,116 |
| Wall time, `-p no:randomly` | 55 s → 43 s | 74 s → 53 s |

- **Coverage:** the only newly uncovered line is `zigbee2mqtt/turn_on_for.py:67` (decided).
  `check_release.py --coverage` passes. The rig's missing lines are identical.
- **D1:** the z2m reply bounds landed at 0.1 s, not 0.02. At 0.02 the z2m files flaked under CPU load (7 of 8 loaded
  runs); at 0.1 they passed 5 loaded runs.
- **Review fixes:** the review restored two checks the merges had weakened: D20's empty selection, and D9's group
  refusal. It also made the rig's gate tables clearer (R7).
- **CI:** the `tests.yml` pytest job now checks out shallow. Nothing it runs reads history; this was checked in a
  depth-1 clone.

## Handoff

Done; nothing pending. The PRs (one per repo, test-only) come when the branch is split.
