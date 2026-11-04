# The rig

The rig runs Device Side's actions against a live Home Assistant and its real devices, and writes the test records
that clear an adapter's `experimental` flag. Its tests are YAML step files in `tests/rig/steps/`, one per action.
`scripts/rig.py` runs each file against every integration in the profile that has an adapter for the action, after a
y/N gate: the devices change state, so nothing moves until you say yes. `--dry-run` prints the plan and stops.

## Before a run

The run first checks every device it will use: each fixed entity must be in HA and available, and each roaming bulb
must be on a network. An unpowered device stops the run there, before anything moves. `--check` runs only this
check, taking no lock and deploying nothing, so you can power devices up until it passes; it names the runs holding
locks it would need.

### Lanes

The run starts with one lane per integration, side by side, each holding that integration's cases on fixed entities.
A case stays out of the lanes when its step file sets device_side options (saving them reloads the integration,
cutting off every lane's fades), or when it uses a roaming bulb, a rig-made group or scene, or a powered entity or
its supply. Those run afterwards, one at a time. `--serial` runs every case one at a time: a case that passes with it
and fails in a lane points at radio or HA contention.

### Profiles

A profile is one test setup on the Home Assistant `.env.rig` connects to: `tests/rig/profiles/<name>.yaml`,
gitignored, copied from `tests/rig/profile.example.yaml`. It lists the entities the rig may move, by integration and
role, and under `pause:` the automations and switches turned off for the run and back on after it (motion lighting,
an Adaptive Lighting switch). `.env.rig` (from `tests/rig/env.example`) holds what belongs to the HA instance: its
address, tokens, deploy commands and Hue bridge.

`--profile <name>` picks one, and can be left out while there is only one. Every test record names its profile, and
records from different profiles of the same suite overwrite each other. A record is public, so name a profile for its
setup (`lab`, `house`), never for a person or place. The household check (`scripts/check_private.py`) keeps every
profile's entity IDs, members, supplies, pause list and IEEEs out of commits.

### Token

Make a Home Assistant user without admin rights and put its long-lived token in `HA_TOKEN`. The rig only calls
actions and reads states and registries, and a non-admin token can't change your configuration if it leaks.

Some suites need an admin token in `HA_ADMIN_TOKEN`: ZHA (its cluster command is admin-only, and the adapter passes
the caller's context through), Zigbee2MQTT (setting device options over MQTT), suites whose adapter has options
(to set them), and roaming. Without it, a run that includes them stops before the gate; `--integration` or
`--action` leaves them out.

### The blocker gate

`RIG_BLOCKER_ENTITY` in `.env.rig` names an HA binary_sensor that is on while someone might see the lights move. A
run approved by `DEVICE_SIDE_RIG_APPROVED=1`, and any probe, starts only while it is off, and aborts, putting the
devices back, once it reads on twice in a row; a yes typed at the prompt overrides it. A profile with
`pre_authorized: true`, for a setup whose lights nobody minds seeing move, skips it. Leave the key unset to gate
nothing.

### Deploys

Each run deploys your committed, pushed checkout and restarts HA whenever HA hasn't loaded that tree, so a run queued
behind another tests its own code. A record cites the commit HA loaded, read before the tests, so committing mid-run
is safe. `--no-deploy` tests whatever HA runs and, unless that is your checkout's tree, writes no record.

## Shared state

- **Roaming.** A profile's `roam:` lists bulbs the run moves between Zigbee networks (Hue, ZHA, Z2M), so one set of
  bulbs serves every Zigbee suite, and `groups:` native groups the run makes on each network. They end home on Hue
  as they were. `--recover`, or the next run, brings them home after a crash; `--roam-check` runs the moves with no
  suites. Roaming also needs `HUE_BRIDGE_HOST` and `HUE_APP_KEY`. How: `tests/rig/roam.py`.
- **Home record.** What a roaming bulb was before its first move is kept until it is back as it was, across crashes
  (`tests/rig/home.py`).
- **Journal.** Each run journals what it changes, so Ctrl-C, a signal, or the next run after a crash puts the devices
  back; `--recover` puts back everything (`tests/rig/journal.py`).
- **Baseline.** Changes beyond the devices (paused automations, log levels, Z2M device options) are shared by runs
  side by side, and the last one out puts them back (`tests/rig/baseline.py`).
- **Locks.** Runs share the rig through one lock per integration and one on HA, so runs on different integrations go
  side by side (`tests/rig/locks.py`). A run takes all its locks at once and holds none while it waits. A deploy holds
  HA exclusively, and a run with no option suites steps down to shared once HA is back. The plan prints a run's
  locks. `--wait-free` waits until the rig is free, or with `--integration`, until those integrations are, without
  taking a lock.

A probe takes the same locks through `--hold`, which runs a command while holding them and returns its exit code:
`scripts/rig.py --hold zha -- <command>`, with `--exclusive` for one that restarts HA or reloads device_side. It
writes no journal, so the probe puts back what it changes.

## Writing a step file

```yaml
action: turn_on_for        # the device_side action every test in the file calls
rig_seconds: 25            # the gate's duration estimate
tests:
  - name: on_then_off
    roles: [switch_plug, light_onoff]   # one run per role the profile names
    steps:
      - set: {state: off}
      - call: {duration: 6}
      - expect_response: {status: expected, integration: self}
      - expect_state: {state: on, within: tol}
      - wait: duration - tol
      - expect_state: {state: off, within: 2 * tol}
```

| Step | Does |
|---|---|
| `set` | Puts the target in a known state with plain HA actions (`state`, plus light attributes). |
| `call` | Calls the file's action with these fields; `duration` is sent in seconds. |
| `expect_response` | Checks the call's response: `status` (`expected` means `confirmed` where the adapter can confirm, else `sent`), `integration` (`self` is the one under test), `detail`, `clamped_to`, `attributes`. |
| `expect_error` | The call before it must fail, with this `key` and/or `summary`. |
| `expect_state` | Checks state and attributes now, or `within` seconds. `unchanged` is the state before the test. A `{min, max}` range fits values that drift. On a `group` it checks every member. |
| `expect_matches_read` | Checks that HA's state of each of `attributes` (dotted: `xy_color.0`) is within `tolerance` of a live `device_side.get_attributes` read, now or `within` seconds. On a `group` it checks every member. |
| `wait` | Sleeps. |
| `sample` | Polls `attribute` (dotted: `hs_color.1`) for `for` seconds and expects it `rising`, `falling` or `steady` (brightness may spread one Zigbee level step, 1/254, as a bulb settles after a stop), optionally within `min`/`max`. `source: device_side` reads `device_side.get_attributes` instead of HA's state, in its units (brightness in percent), for a fade HA shows only the end of. |
| `mark_hue` | Notes each light's hue on its own wheel, for `expect_hue_travel`. On ZHA it is read live off the bulb (EnhancedCurrentHue), since HA works its hue out from the bulb's xy, which departs from the bulb's wheel by 25° and more in the greens; elsewhere it is HA's `hs_color`. On a `group` it marks every member. |
| `expect_hue_travel` | Checks each light has turned `by` degrees round its own wheel since `mark_hue` (negative: down), within `tolerance`, the shorter way round. A hue move's rate is in the bulb's units, so this holds on any gamut. |
| `do` | Prints an instruction for the person and waits for Enter. Only in the `setup` of an observed test. |
| `restore` | Puts back the state from before the test. It also runs after every test, pass or fail. |
| `bridge` | Hue only: writes to the Hue bridge directly, bypassing Home Assistant, as another actor (the Hue app) would. `put: {...}` sends that CLIP v2 body to the target's light (a `group` target's grouped_light); `recall: true` recalls the `scene` target. In an observed run it runs as written. It needs `HUE_BRIDGE_HOST` and `HUE_APP_KEY` in `.env.rig`, and fails in any other integration's suite. |
| `z2m_option` | Sets Zigbee2MQTT device options on the target (`hue_native_control: false`) and waits for Z2M's ok. Does nothing in another integration's suite. |
| `expect_z2m_option` | Expects the target's Zigbee2MQTT device options to hold the given values. Does nothing in another integration's suite. |

Any step takes `target: <role>` to act on another role the test lists; a `group` case that targets a light role is
skipped where the profile lists the group's `members` and that light isn't one. Durations accept numbers, `duration`
(the last call's), `tol` (the integration's timing tolerance) and `+ - *`. `only: [<integration>]` limits a test to
some integrations; when those pile up, split the file.

The roles are listed in `tests/rig/profile.example.yaml`. `group_color` is a native group whose members all take
color: color moves groupcast only to a group like that, so it runs the color cases a `group` can't. Everything this
page says of a `group` holds for it too.

An adapter with options runs each file for its action with them pinned through Device Side's options flow:
`options: [<name>]` at the top of a file turns those on, and every other option in the adapter's scope runs off. Its
record is `<action>-<name>.md`, with an `Options` row. The rig's own options are put back when the run ends.

An integration in `SETTLE_S` (`tests/rig/profile.py`) predicts a light's brightness for a while after a raise, lower
or `stop`, so a later test on that light waits until it reads the device again.

### Observed tests

Some things need eyes, such as a light climbing smoothly without flashing. A test asks for them with an `observe:`
block and puts its start state in `setup:`. Each question costs the person at the rig, so observe only what hardware
has never shown and a check can't measure: once watched on an integration, a behavior stays automated there.

```yaml
  - name: raise
    roles: [light_ct, group]
    setup:
      - set: {state: on, brightness_pct: 20}
    steps:
      - call: {sweep_time: 5}
      - sample: {attribute: brightness, for: 3, expect: rising}
    observe:
      see: The light at 20 %, climbing to full over 5 s.
      watch: Steps or flashes on the way up.
      ask: Did it climb smoothly to full?
```

Such a test runs twice, so you are asked only what a machine can't check:

1. **Automated**, with every other test first: setup and steps, every check applied. It has no automated run if its
   steps check nothing or its setup has a `do`.
2. **Observed** (`<name>[<role>] observed`), after all automated runs. Setup runs and settles for 2 s, then the runner
   prints `see` (in bold) and `watch` and waits for Enter. The steps run with their checks turned into waits, so the
   timing matches. Then you answer `ask`: Enter or `y` if you saw it, `n` if not, which fails the test and asks what
   you saw instead. It is skipped if its automated run failed, and if a step fails after Enter it prints
   `nothing to observe` and the reason.

`roles: [<role>]` in `observe:` limits the observed run to those roles, and `only: [<integration>]` to those
integrations; the rest run automated only. `--unattended` skips the observed runs and reports them `not observed`.
They don't fail, but a test counts toward a test record only when both of its runs pass.

## After a run

### Run reports

Every run, failed, partial or unattended, ends by writing a report to `device_side-rig/` in the system temp folder and
printing its path: each suite's results with the reason for every failure and skip.

### Run logs

Z2M's frontend keeps only its last 1000 lines and HA's log restarts with HA, so a run captures both: Z2M's lines (for
a run that touches Z2M, or roams) to `<report>.z2m.log` as they arrive, and HA's log from the run's start to
`<report>.ha.log` when the run ends. A clean run deletes them; after a failure, a stopped move or a crash they stay
and their paths are printed. When Z2M's coordinator crashed during the run (`ASH_NCP_FATAL_ERROR` or
`Adapter disconnected`), the summary says so with each crash's time, and the logs stay even after a clean run.

`--debug-logs` keeps them whatever the outcome and runs HA's `device_side`, each integration the run touches and Z2M
at debug until the run ends. It costs CPU, so timing cases may read differently. Z2M's debug lines reach the capture
only with `advanced.log_debug_to_mqtt_frontend: true` in its configuration; the brief warns when it is off, and the
rig never sets it.

### Test records

When every test of an adapter passes, the run writes `docs/test-records/<integration>/<action>.md`: the date, the Home
Assistant version, the devices' model and firmware, and each test's result. A failed or partial (`-k`) run writes
nothing. Records are evidence for people, not read by any script: the PR that clears an adapter's `experimental` flag
cites one.
