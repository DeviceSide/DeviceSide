# Rig clear gate: run when the house is empty, abort when someone is near

## Context

Agents get rig authorization today from dated memory entries ("authorized 3 Nov until 11:30"). Jason has to issue
each one, they go stale, and they ignore what's actually happening. The risk they guard against is household
members seeing lights flash. A sensor rule matches that risk directly: the rig is **clear** while both household
phones are away and the car is more than 5 minutes from home. When it stops being clear, a running rig run or
probe aborts at once. The existing abort path puts the devices back.

Decisions taken (interview, 2026-11-03):
- On revoke, **abort always**. No "finish if nearly done".
- The car's ETA sensor goes `unknown` when parked. Count that as far away while the car tracker is not `home`.
  Car `home` means not clear.
- The rule covers **unattended runs and `--hold` probes**. A human's interactive "yes" overrides it. Watched
  sessions still need Jason's go.
- The condition lives in **one HA template binary_sensor**. rig.py reads one entity named in `.env.rig`, so no
  household names or entity IDs go into the repo, which is public.

## Steps

0. Worktree `wt/rig-clear-gate` off `release/v0.0.2`. Copy this plan to `docs/plans/2026-11-03-rig-clear-gate.md`
   with entity names replaced by roles ("phone A", "phone B", "car").

1. **HA template sensor** (Jason creates it in Settings → Helpers → Template → Binary sensor, or approves the
   session doing so). Find the real entity IDs through the HA API: phone A's and phone B's `device_tracker`/`person`, the
   car's tracker, and the car's time-to-home sensor. Check the ETA sensor's history to confirm its units and that it
   goes `unknown` when parked. Template shape:
   ```jinja
   {% set away = lambda e: states(e) not in ['home', 'unknown', 'unavailable'] %}
   {% set car = states('<car tracker>') %}
   {% set eta = states('<car eta>') %}
   {{ away('<phone A>') and away('<phone B>')
      and car not in ['home', 'unknown', 'unavailable']
      and (eta in ['unknown', 'unavailable'] or eta | float(0) > 5) }}
   ```
   (Jinja has no lambda, so write `away` out per phone. The shape above just shows the rule.) Phones or car
   unreadable means not clear. Add `delay_on: 2 min` so a run doesn't start just as a flapping ETA crosses the line.
   No `delay_off`.

   As built (3 Nov): the phones are presence binary_sensors (on = home), not trackers. The car's ETA is a navigation
   arrival-time sensor, `unavailable` when not navigating, so the template counts it only while the car's route
   destination is home. Jason made the sensor in the HA UI; its entity ID stays in `.env.rig`.
   The sensor is inverted from the shape above: a blocker, on while someone might see the lights, so the rig is clear
   only while it is off, and `on`, `unknown` and `unavailable` revoke. Steps 2–6 read with on and off swapped.

2. **`.env.rig` key** `RIG_BLOCKER_ENTITY`. Add it to `tests/rig/env.example` with a generic example
   (`binary_sensor.rig_blocker`), and give `docs/contributing/testing.md` one line on what it gates. It's optional:
   unset means today's behavior, so contributors without it are unaffected.

3. **`scripts/rig.py`: reading it.** Add `rig_clear(env) -> tuple[bool, str]` using the existing `_get`
   (`scripts/rig.py:343`) on `/api/states/<entity>`. It's clear only on state `on`. `off`, `unknown`,
   `unavailable`, a missing entity or an unreachable HA all mean not clear, with the state as the reason.

4. **Gate** (`gate()`, `scripts/rig.py:333`). With `RIG_BLOCKER_ENTITY` set and `DEVICE_SIDE_RIG_APPROVED=1`, refuse
   unless clear: "Rig not clear (<reason>); nothing changed." An interactive prompt still asks. If not clear, it says
   so in the prompt ("Rig not clear (<reason>). Proceed anyway? [y/N]"), so Jason's yes overrides it.

5. **Probes** (`hold_command`, `scripts/rig.py:670`). Same check before `locks.hold`, and again once the locks are
   held, since a probe can queue for a long time. Not clear: prompt as in step 4. An agent's call has no stdin, so it
   gets `EOFError` and is refused.

6. **Watcher, for runs and probes approved by the env var or started while clear.** A daemon thread polls
   `rig_clear` every 15 s from the moment approval is given. On **two consecutive** reads of state `off`, `unknown`
   or `unavailable`, it prints "Rig authorization revoked (<reason>); aborting." and does
   `os.kill(os.getpid(), signal.SIGTERM)` once. That sends it down the existing paths:
   - mid-deploy: `finish_first` lets HA's restart finish,
   - tests: `cancel_on_signals` puts devices back,
   - probe: `run_command` forwards it.

   Connection errors don't count, because HA is unreachable during the run's own deploy restart. Not armed when
   Jason answered the prompt interactively and overrode a not-clear state. Stop the thread in the `finally` of
   `run_held` / `hold_command`.

7. **Docstring.** Add one paragraph to the module docstring of `scripts/rig.py` stating the gate and the watcher.

8. **Memory (main session, after merge).** Replace the dated authorization entries (`rig-preauthorized-*`,
   `lab-preauthorized-*`, `a60-probe-authorized-*`) with one feedback memory: agents may run the rig and probes
   without asking whenever rig.py's clear gate passes, and never set `DEVICE_SIDE_RIG_APPROVED=1` to get past a
   refusal. "Watched sessions" and "measure before guardrails" stay as they are.

## Critical files

- `scripts/rig.py`: `gate`, `hold_command`, `run_held`, new `rig_clear` and watcher
- `tests/scripts/test_rig.py`: tests
- `tests/rig/env.example`, `docs/contributing/testing.md`

## Verification

- Unit tests (`tests/scripts/test_rig.py`, stub `_get`): the gate with the env var refuses on `off`, `unknown` and
  unreachable, and passes on `on`. With the key unset, behavior is unchanged. The prompt shows the not-clear reason.
  The watcher sends SIGTERM after two `off` reads, not after one, and not on connection errors. `hold_command`
  refuses when not clear and stdin is at EOF. `.venv/bin/pytest`, `pre-commit run --all-files`, rig.py coverage
  doesn't drop.
- Live, with Jason's go:
  - `scripts/rig.py --dry-run` prints the clear state.
  - Flip the template (temporarily edit it to `{{ false }}`) during a short `--hold <integration> -- sleep 120`
    probe. It aborts within ~30 s and the pause ledger resumes the automations.
  - A run that deploys, approved by `DEVICE_SIDE_RIG_APPROVED=1` while clear, survives HA's restart: the sensor must
    not read `off` twice in a row as HA comes back (the watcher skips failed reads and restored states, not a real
    `off`).
  - Restore the template and confirm the HA sensor history shows sensible on/off over a day of normal comings and
    goings before retiring the dated memories.
