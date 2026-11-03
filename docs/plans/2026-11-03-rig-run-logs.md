# Rig: capture HA's and Z2M's logs for every run; debug levels on request

## Context

On 3 Nov two lab failures went undiagnosed because the evidence was gone by the time anyone looked:

- **A Z2M stall.** At 11:18:56 Z2M stopped mid-configure of the A60 for 8 minutes and dropped off MQTT four times,
  so a group add and a Leave went undelivered. The run had already put Z2M back to `warning` (#169's per-join
  raise), so its log held nothing for the gap. A later probe changed Z2M's level twice while idle with no stall, so
  the options call isn't a reliable trigger. The cause is still unknown.
- **The A60's Hue → Z2M move.** It failed again (0 of 1; 3 of 4 earlier on 3 Nov), while Hue → ZHA and ZHA → Z2M
  went 2 of 2. #174's retry spotted it, searched it back and released it alone, and it still didn't join. Z2M's
  frontend keeps only its last 1000 lines, so the log was gone before it was read.

Agreed design (3 Nov, with Jason): capture is always on and cheap; debug levels are opt-in, as they bloat the logs,
cost CPU and could shift timing cases.

## 1. Capture, every run

- **Z2M**: Z2M publishes every log line it emits to `zigbee2mqtt/bridge/logging` as `{message, level, namespace}`
  (not retained; `lib/extension/bridge.ts`). For a run that touches Z2M (a Z2M phase, or roaming), subscribe
  through HA's `mqtt/subscribe` (`HAClient._mqtt_messages`) from before the first phase to the end of the run.
  Append each line to a file as it arrives, so a crash keeps what came before it.
- **HA**: at the end of the run, `GET /api/error_log` (admin token; checked on 3 Nov: it returns the session's log as
  text) and keep the lines from the run's start onwards. A deploy restarts HA, so the session usually starts with
  the run anyway.
- **Where**: next to the run report in `REPORT_DIR`, sharing its stem: `<report>.z2m.log` and `<report>.ha.log`. A
  run that stops before any report still writes them, under the same stem, and prints their paths.
- **Kept only when needed**: deleted after a clean run (exit 0) unless `--debug-logs`; kept and printed after a
  failure, a stopped move, or a crash. A failure to fetch or write a log is printed, never raised: it must not hide
  the run's own error.
- **Z2M's level during a join** stays #169's `info` hold, so the default capture still shows joins and interviews.

## 2. `--debug-logs`

- **What it raises**, after the deploy (a restart would reset it) and before the first phase:
  - HA: `device_side` plus the HA domain of each integration the run touches: `hue`, `zha`, `mqtt` (for Z2M),
    `shelly`, `matter`, and `hue`, `zha` and `mqtt` whenever it roams. Via `logger/integration_log_level`, level
    `debug`, `persistence: "none"`, which also covers each integration's library loggers (aiohue, zigpy, bellows…)
    and never touches the saved settings.
  - Z2M: `debug`, through `HAClient.z2m_set_log_level`. #169's `z2m_logging` already leaves a verbose level alone.
- **Restored** at the end of the run, in the `finally` that resumes automations. Before raising, read each level
  (`logger/log_info` gives each integration's effective level; Z2M's comes from `bridge/info`) and journal it, so
  `--recover` puts it back after a crash. A level HA no longer reports (HA restarted since) is skipped.
- **Z2M's debug lines** reach MQTT only with `advanced.log_debug_to_mqtt_frontend: true`, which needs a Z2M restart.
  It was set on 3 Nov; Z2M had not yet been restarted. The brief warns when `--debug-logs` is given and the setting
  is off (read from `bridge/info`'s `config`); the rig never sets it.
- **The brief** says the run is at debug, and that timing cases may read differently.

## Tests

`tests/scripts`, against the fakes:

- **Z2M capture:** `bridge/logging` lines written in order while the run goes on, and kept after a crash mid-run.
- **HA capture:** the HA log trimmed to the run's start.
- **Keeping or deleting:** files deleted after a clean run, kept after a failed one, and kept by `--debug-logs`.
- **Levels:** raised for exactly the run's integrations, restored after; journaled and restored by `--recover`.
- **Fetch failures:** a failed fetch prints and the run's result stands.

## Rig

1. A `--roam-check` on the lab, with Jason's go, to see both logs captured and deleted on a clean run.
2. Then the diagnostic run the 3 Nov failures need, with `--debug-logs`: the lab's Hue → Z2M move. Z2M's log then
   shows whether the A60 ever reached Z2M:
   - **No trace:** it missed the Leave, or can't hear the coordinator. The lab then routes Hue → Z2M through ZHA.
   - **Turned away:** the fix is in Z2M's join settings.

## Finish

- `docs/contributing/testing.md`: the capture, where the files go, and `--debug-logs`.
- `TODO.md`: a "Done since v0.0.1" row.
- The lab plan's findings note (`2026-11-01-lab.md`): one line on the capture, and the diagnostic run's result.
