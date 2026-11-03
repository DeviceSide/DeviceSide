# Rig: share it between sessions, with HA and per-integration locks

## Context

One lock covers the whole rig today (`lock_rig`, `scripts/rig.py`). A session probing only Z2M waits behind a
session testing only Hue, even though they share no devices. A run needs exclusive use of HA for only three
things:

- a deploy, which restarts HA;
- saving device_side's `predicted_state` option, which reloads the entry;
- `--recover`.

Everything else divides by integration. Roaming divides by the networks it visits.

**Goal:** a shared/exclusive lock on HA plus one lock per integration. Sessions on different integrations then run
together, as long as none of them deploys.

**Depends on #171** (parallel lanes), which reworks `run_phases`, the journal (`Journal.put`/`drop`) and
`replay`. Start once it has merged.

- Worktree: `wt/rig-shared-locks` off `release/v0.0.2`.
- First step: copy this plan to `docs/plans/2026-11-03-rig-shared-locks.md`.
- Ship it as **two PRs**: (1) locks, claims, journals and `--hold`; (2) the pause ledger and roam `networks`/`home`.

Decisions taken:
- Roaming locks only the networks the profile declares for its bulbs, and each bulb declares its home.
- Pausing is per integration, coordinated through a shared ledger.
- Probes take their locks through a command wrapper.

## 1. Locks (new `tests/rig/locks.py`)

Move `lock_entry`, `lock_holder`, `wait_for_lock`, `lock_rig`, `wait_free` and `held_by` there from
`scripts/rig.py`.

**Lock files.** All live in the git common dir (`common_dir()`).
- `device_side-rig.lock`: **the HA lock.** It keeps today's path, so a run from an older checkout (which takes it
  exclusively) still excludes new runs.
- `device_side-rig.turnstile.lock`: gives a waiting deploy priority over new shared holders. Without it, flock
  would let a stream of shared holders starve the deploy.
- `device_side-rig.<integration>.lock`: one per key in `TOLERANCE_S`.

**`Claim` dataclass:** `ha: Literal["shared", "exclusive"]` and `integrations: frozenset[str]`.

**`hold(claim, holder)`** takes the locks in a fixed order, which rules out deadlock:
1. Integration locks, exclusive, in sorted order. Each one gets the holder entry written into it.
2. The HA lock:
   - **shared:** take the turnstile exclusively, take the HA lock shared, release the turnstile;
   - **exclusive:** take the turnstile exclusively, take the HA lock exclusively (this waits out the shared
     holders), write the holder entry into the HA lock, release the turnstile.

**Waiting messages** name the holders, as `lock_holder` does today. A shared HA lock has no single owner, so while
waiting on it, list whoever holds the integration locks.

**Workspace colors:** green once everything is held, amber while waiting, as today.

## 2. What a run claims (`scripts/rig.py`)

`claim(args, suites, profile, roaming, deploy)` works out:

- **Integrations:**
  - every integration that has a selected suite with an adapter;
  - plus, when roaming, the networks the bulbs visit (section 5).
- **HA exclusive** for any of these:
  - a deploy is needed and `--no-deploy` isn't set;
  - any suite whose step file has `options`;
  - `--recover`.

  Everything else takes HA shared. Records stay valid under a shared claim: `tested_commit` already names the
  commit only when HA has loaded this tree.

**`run_held` flow:**
1. Read the profile, suites and deploy state. These are read-only and need no locks.
2. Take the claim.
3. Read the deploy state again, since another run may have deployed while this one waited.
4. If the claim now needs HA exclusive, release everything and take the stronger claim, at most once.
5. Then replay, the plan, the gate and the run, as today.

**Unchanged:** `--dry-run` and `--check` take no locks. `--check` names the holders of the locks the run would
claim.

`--wait-free` gains an optional `--integration` filter: it waits until those integrations are free and no one
holds HA exclusively. With no filter it waits until everything is free, which is today's meaning.

## 3. Journals, one per run

- **Files.** Each run writes `device_side-rig.journal.<pid>.json` in the common dir, holds an exclusive flock on that
  file for its whole life, and records its claim in a `claim` section.
- **Orphans.** A journal file nobody holds a lock on is an orphan.
- **Replay before the gate.** A run replays an orphan when the orphan's integrations are a subset of its own claim.
  An orphan with an `options` or `roam` section also needs HA exclusive, or the orphan's networks. Any orphan it
  can't take is reported, with the claim needed (or `--recover`) to replay it.
- **`--recover`** claims everything exclusively and replays every orphan.
- **Legacy journal.** A `device_side-rig.journal.json` from an older run counts as an orphan that claims
  everything.

## 4. `--hold` for probes

```
scripts/rig.py [--profile NAME] --hold INTEGRATION [--hold ...] [--exclusive] -- CMD [ARGS...]
```

- Takes HA shared, or exclusive with `--exclusive`, plus the named integration locks.
- Pauses those integrations' pause entries through the ledger (section 6).
- Runs the command and passes signals through to it. On exit it resumes the paused entries, releases the locks
  and returns the command's exit code.
- Writes no case journal: the probe puts back what it changes itself.
- No gate. Rig authorization stays a rule for the agent, not something the tool enforces.

## 5. Roam profile: declared `networks` and each bulb's `home` (`tests/rig/profile.py`, `tests/rig/roam.py`)

```yaml
roam:
  networks: [hue, zha, zigbee2mqtt]   # where these bulbs may go; must include every bulb's home
  bulbs:
    - ieee: "..."
      entity_id: light.lab_color
      home: hue                       # required; only hue is accepted for now
```

- **Validation in `roam_section` and `roam_bulb`:** `networks` and `home` are required, `networks` must be a subset
  of `CYCLE`, and each `home` must be in `networks`. A `home` other than `hue` fails, with a message saying only Hue
  homes are supported so far. Hue is where `roam.py` saves and restores rooms and scenes.
- **`add_roaming`** lists the bulbs and rig-made groups only under the declared networks. On an undeclared network,
  the cases for the bulbs' roles find no entity and skip.
- **`roams()` and `phases()`:** a run visits the declared networks that have suites, in `CYCLE` order. It starts
  from wherever the bulbs are and always ends at their home, even if they didn't start there. `check_devices`
  already reports a bulb that is away from home.
- **Claim:** the networks visited plus the bulbs' home. An undeclared network is never locked by roaming.
  `--roam-check` visits and locks every declared network.
- **Code that becomes per bulb:** wherever `HOME` means "this bulb's home", use `bulb.home`. Code that is about Hue
  specifically (rooms, scenes, the bridge) keeps `"hue"`.
- **Example profile:** update `tests/rig/profile.example.yaml`.
- **Local profiles:** the gitignored ones in the main checkout (`lab`, `house`, `a60_roam`) need `networks:` and
  `home:` added. They live outside the PR, so tell Jason the exact lines to add, or ask before editing them.

## 6. The pause ledger (replaces the journal's `paused` section)

**Profile.** `pause:` accepts either form:
- a list, meaning every integration (today's form);
- a mapping `{all: [...], hue: [...], zha: [...]}`.

A claim pauses `all` plus the lists for the integrations it holds.

**Ledger.** `device_side-rig.paused.json`, edited only under a short-held `device_side-rig.paused.lock`. It holds
`{entity: {"was_on": bool, "holders": [journal file names]}}`.

- **Pause:** if the entity is already in the ledger, add self to its holders. Otherwise read its state, turn it off
  if it is on, and record `was_on`.
- **Resume:** remove self from the holders. Once none are left, turn the entity back on if `was_on`, and drop the
  entry.
- **Dead holders:** a holder whose journal file isn't locked is dead. It is pruned every time the ledger is opened,
  so a crashed run's pauses get resumed by the last live holder, or by `--recover`.

This replaces `pause` and `resume` (`scripts/rig.py`) and the `paused` part of the journal replay.

## Tests

- **New `tests/scripts/test_rig_locks.py`.** flock locks belong to the open file handle, so two handles in one
  process conflict, which is enough to test with. Cover:
  - shared holders on different integrations both proceed;
  - two holders of the same integration block each other;
  - an exclusive claim waits out the shared holders;
  - a waiting exclusive claim blocks new shared ones (turnstile);
  - the fixed order never deadlocks;
  - a run upgrades to exclusive when it finds a deploy is needed;
  - the legacy lock path still excludes new runs.
- **Claims:**
  - an option suite takes HA exclusive;
  - a ZHA-only roam on a profile declaring hue and zha claims hue and zha, not Z2M;
  - `--no-deploy` takes HA shared.
- **Journals:**
  - an orphan is replayed only when it is a subset of the claim;
  - an orphan with options needs HA exclusive;
  - the legacy journal is replayed only by `--recover`.
- **Pause ledger:**
  - with two holders, the last one out resumes;
  - an entry another holder paused is resumed by the last live holder;
  - a dead holder is pruned;
  - both `pause:` forms work.
- **Profile validation:** `networks` and `home` are required, `home` must be in `networks`, and a non-Hue home is
  refused.
- **`--hold`:** runs the command, returns its exit code, and releases on a signal.
- **Existing tests:** update `test_rig_roam_run.py` and `test_rig.py` for declared networks and `bulb.home`.

## Verification

1. `.venv/bin/pytest`, `pre-commit run --all-files`, and coverage at or above 95%.
2. **Two terminals, no devices touched:**
   - `scripts/rig.py --hold hue -- sleep 30` in one;
   - `--hold zigbee2mqtt -- true` in the other returns at once;
   - `--hold hue -- true` waits, naming the holder;
   - `--hold hue --exclusive -- true` waits for both.
3. `--dry-run` on each profile prints the claim. A ZHA-only run on `a60_roam` shows hue and zha only.
4. **On the rig, after Jason's go-ahead:** two filtered runs at once with `--no-deploy`, on disjoint integrations
   (e.g. `--integration shelly` and `--integration zha`). Both pass, and the paused automations come back on only
   after the second run ends.
5. **Afterwards:**
   - CLAUDE.local.md's "One rig run at a time" line becomes "one holder per integration; deploys and option suites
     take HA exclusively";
   - update the rig-sharing memory note (`rig-shared-with-other-sessions.md`), which says probes are unlocked;
   - update `docs/contributing/testing.md` and the `rig.py` docstring.
6. `/audit-code` on each PR's diff, then a PR into `release/v0.0.2`.
