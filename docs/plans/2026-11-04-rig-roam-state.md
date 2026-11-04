# Rig: one bulb on one network, Z2M coordinator crashes, and state saved before every change

Save as `docs/plans/2026-11-04-rig-roam-state.md` in the worktree before step 1. Three PRs into `release/v0.0.2`, each
from its own `wt/` branch, in order.

## Context

The A60's moves kept failing (3–4 Nov). The kept Z2M debug logs show two causes, neither of them the bulb:

1. **Z2M's coordinator crashes.** EmberZNet 7.4.5 over USB hit `ASH_NCP_FATAL_ERROR` (`ERROR_EXCEEDED_MAXIMUM_ACK_TIMEOUT_COUNT`)
   three times on 3 Nov (16:47, 18:41, 23:08). At 23:08:46 it died sending the A60's Leave, so the Leave never went out and
   Z2M restarted. The rig said "it didn't take the Leave. Switch its lamp off and on", blaming the bulb.
2. **A stale Z2M record.** Z2M keeps a device whose remove fails. The A60 later reached Hue, then ZHA, while Z2M still listed
   it at its old address. `RoamSession.locate()` (`tests/rig/roam.py:240`) asks Z2M before ZHA, so on 4 Nov 09:29 the rig
   thought it was already on Z2M, left it out of the ZHA → Z2M move, failed the group add, and sent every `--recover`'s
   Leave to a dead address. `joined("zigbee2mqtt")` (`roam.py:231`) would also count a stale entry as arrived at once.
   Cleared by hand on 4 Nov (a Z2M force remove, then `--recover`).

A Leave reported as `Delivery failed` is usually harmless: the bulb leaves 0.1 s later and Z2M drops it itself.

The state inventory (4 Nov) found that state is already saved beside the locks (per-run journals and the pause ledger),
but with gaps: nothing records the bulbs' own state before a run; `z2m_option` steps (`engine.py:1155`) are never
journaled, so a failed case leaves `hue_native_control` off; HA and Z2M log levels are global with no owner, so a level
left at debug is read as the original and never lowered (Z2M is at debug now); a probe's pauses are invisible to
`--recover` (`hold_command`, `rig.py:849`, never writes its journal); `save_home` (`roam.py:862`) keeps an earlier home
only from its own journal, so two crashes can save a half-restored Hue home; a failed light restore still drops its
journal entry (`engine.py:788`); `roam.made`'s `renamed` flag is written after the rename (`roam.py:720`); orphans replay
in lock-name order, not start order.

Decided with Jason (4 Nov): resolve duplicate listings by liveness and purge the dead ones; retry a Z2M remove after Z2M
restarts; flag coordinator crashes in every run's summary; Z2M at `info` unless `--debug-logs`; per-run journals plus one
shared, holder-counted baseline; a per-bulb home record that outlives runs; roaming bulbs end in their pre-run state.

## PR 1: one bulb, one network; Z2M crashes

**Now (ops, under `scripts/rig.py --profile lab --hold zigbee2mqtt -- …`):** set Z2M's log level to `info`
(`HAClient.z2m_set_log_level`).

**Duplicates, by liveness** (`tests/rig/roam.py`):
- `listings(bulb)`: every network that lists it: the Hue bridge (`device_id_by_ieee`), Z2M (`ha.z2m_device`), and ZHA
  (`ha.device_by_ieee`).
- `live(network, bulb)`:
  - **Hue:** its `zigbee_connectivity` `status` is `connected` (CLIP v2).
  - **ZHA:** its HA light isn't `unavailable`.
  - **Z2M:** the retained `zigbee2mqtt/<friendly_name>/availability` is `online`. A new `HAClient.z2m_availability(name)`
    reads it through `_mqtt_messages`; when availability is off in `bridge/info`, fall back to the HA entity's state.
  - **Two networks live:** a Z2M availability record can lag up to 10 min, so an active check on the Z2M listing decides
    it. Read `genOnOff` through Z2M; no reply in 10 s means dead.
- `locate()` returns the one live listing. It force-removes each dead Z2M or ZHA listing and names it:
  - Z2M: a new `HAClient.z2m_force_remove(ieee)` sends `device/remove` `{"id", "force": true}`, a database delete with no
    Leave.
  - ZHA: `zha.remove`.
- `locate()` stops with a `RoamError` naming both networks in three cases: two listings are live, a dead listing is on Hue
  (never purged: it holds the home), or nothing is live.
- `move()`: after the releases and before `join`, purge any listing the target still holds for a leaving bulb. It can only
  be stale, so a Z2M window can't count it as arrived.

**Z2M remove across a coordinator crash** (`client.py` `z2m_remove_device`, `roam.py` `release`):
- While waiting, read `bridge/response/device/remove` for Z2M's error, and the retained `bridge/state`.
- If the remove fails and Z2M went offline (or goes offline within 30 s), wait up to 120 s for `online`, then retry the
  remove once.
- The `RoamError` says what happened:
  - Z2M restarted mid-remove: "Z2M's coordinator crashed mid-remove; see the run's Z2M log".
  - Z2M stayed up and the bulb is live elsewhere: the stale entry is force-removed, and the move goes on.
  - Z2M stayed up and the bulb is live only on Z2M: the current lamp advice stays.

**Crash flag** (`tests/rig/runlogs.py`):
- Count `ASH_NCP_FATAL_ERROR` / `Adapter disconnected` (error level, captured at any Z2M level) and `Timer expired waiting
  for ACK` (debug only) in the captured Z2M log.
- `settle()` prints "Z2M's coordinator crashed N times (HH:MM:SS, …)" and keeps the log whenever N > 0, even on a clean
  run.

**Tests** (`tests/scripts/test_rig_roam.py`, `rig_fakes.py`):
- Teach `Lab` a `stale_z2m` bulb and `FakeHA` a Z2M `availability` topic, a `force` remove, a `bridge/state` that drops
  and returns, and a remove that errors once.
- Cases:
  - the 09:29 run (live on ZHA, stale on Z2M): located on ZHA, stale entry purged, joins Z2M;
  - a stale target entry is purged before the window;
  - two live listings stop the move;
  - a crash mid-remove is retried, and passes;
  - a remove error without a restart names the bulb;
  - the crash count prints, and keeps the log.

## PR 2: the shared baseline

Replace the pause ledger (`tests/rig/ledger.py`) with a baseline: `device_side-rig.baseline.json` and its lock in the
git common dir.

**Format:** keyed `kind:key`, each `{original, holders}`.
- `kind` is one of `automation` and `switch` (today's `was_on`), `ha_log_level:<domain>`, `z2m_log_level`, and
  `z2m_option:<ieee>:<name>`.
- On first use the existing `paused.json` is read in once, keeping its semantics.

**API:** `Baseline.hold(kind, key, read, apply)` and `Baseline.release(holder)`.
- The first holder reads and records the original before applying.
- The last holder out, or the next prune after a holder dies, puts it back.
- Dead holders are pruned as today: a holder whose journal lock is free.

**Callers:**
- `Ledger.pause`/`resume` become `automation`/`switch` holds.
- `DebugLevels.raise_levels`/`restore` (`runlogs.py:156`) and `RoamSession.z2m_logging` (`roam.py:502`) become log-level
  holds. Their journal sections go.
- `engine._z2m_option` holds `z2m_option` for the case and releases at case end, so a failed case still puts
  `hue_native_control` back.

**A raised level nobody holds:** a Z2M level read as `debug` (or `trace`) with no holder is recorded as `info`, and the run
says so. Debug is never a resting level.

**Probes and `--recover`:**
- `hold_command` holds through the baseline, so a crashed probe's pauses are pruned like a run's.
- `recover_all` always prunes the baseline, even with no orphan journals (`rig.py:901`).

**Tests:** for each kind:
- two runs overlapping, then one crashing, then the other ending;
- a probe crashing;
- the old ledger read in;
- a leftover debug level lowered.

## PR 3: the home record and the smaller gaps

**Home record:** `device_side-rig.home.json` (git common dir), one entry per roaming bulb's IEEE. It holds:
- the home network;
- the Hue home (rooms, zones, scene actions, name), as `save_home` saves it now;
- the pre-run state: on/off, brightness, and xy or color temperature, read from HA before the first move.

It is written only when no entry exists, never overwritten while one does, and cleared only after the bulb is home,
`restore_home` succeeded and its state was put back. `save_home` and `restore_home` (`roam.py:862`, `886`) use it in
place of `roam.home`.

**Ending state:** `RoamSession.go("hue")` turns each bulb back to its recorded state through its fixed entity (or off),
on a clean run and on `--recover`.

**Smaller gaps:**
- `Snapshot.restore` (`engine.py:769`) keeps the journal entry when a restore failed, so `--recover` tries again.
- Before the rename, `make` (`roam.py:705`) journals `renaming`, and `unmake` drops the entity under either flag.
- Each journal records `started` at its first save, and `orphans()` replays oldest first.

**Tests:**
- two crashes in a row keep the first home;
- the pre-run state comes back after `--recover`;
- a failed light restore stays journaled;
- a crash between rename and flag;
- orphans replayed in start order.

## Docs and finish

- `docs/contributing/testing.md`:
  - the baseline and the home record (where they live, what clears them);
  - the crash line in a run's summary.
- Lab plan (`docs/plans/2026-11-01-lab.md`): a findings paragraph on the coordinator crashes and the stale record. It
  replaces the 3 Nov reading that the bulb ignored the Leave, and the matching sentence in `TODO.md`'s sideboard note.
- `TODO.md`: a Done row per PR.
- Each PR: `/audit-code`, then fix its findings. Each PR body cites `docs/plans/2026-11-04-rig-roam-state.md`.
- **After PR 3 merges (Jason, 4 Nov):** put every logging level back to its default, under
  `scripts/rig.py --profile lab --hold zigbee2mqtt --exclusive -- …`:
  - HA: `device_side`, `hue`, `zha`, `mqtt`, `shelly`, `matter` back to the level they had before any rig run. They were
    raised with `persistence: "none"`, so an HA restart does it, or `logger.set_level` to the configured default.
  - Z2M: `warning` (its level before the rig; the lab plan records Z2M logging at `warning`), and
    `advanced.log_debug_to_mqtt_frontend` back to `false` (set on 3 Nov; takes effect after a Z2M restart).
  - Then confirm through `logger/log_info` and Z2M's `bridge/info`.

## Verification

- Each PR: `.venv/bin/pytest`, `pre-commit run --all-files`.
- PR 1: `scripts/rig.py --profile lab --roam-check --debug-logs` twice in the background. Both clean; the summary shows the
  crash count (0 or more), with each crash's time.
- PR 2: a lab run killed mid-Z2M phase, then `--recover`. Automations back on, Z2M back at `info`, `hue_native_control`
  as the profile has it; the baseline file empty or gone.
- PR 3: record the lab bulbs' states, run `--roam-check`, and compare. Then a run killed after the first move and
  `--recover`. The Hue rooms, scenes and states match the starting record.
