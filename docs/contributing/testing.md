# Testing on your own Home Assistant

The rig runs integration tests against the maintainer's live hardware. If you want to test a
pre-release on your own setup, here is what to do.

## Install

Copy `custom_components/device_side` into your Home Assistant config directory, or add
`https://github.com/jasonmx/device-side` as a custom HACS repository and install Device Side
from there. Restart Home Assistant.

Add the integration: Settings > Devices & services > Add integration > Device Side. Check that
it appears as loaded with no errors in Settings > System > Logs.

## Try the actions

Open Developer tools > Actions and find `device_side.turn_on_for`. Select only a switch entity:
the brightness, color and transition fields should hide. Add a dimmable light: they should show.

Run the action with a short duration (5-8 seconds) and check the device responds.

## Report

[Open an issue](https://github.com/jasonmx/device-side/issues/new?title=Test%20report)
with the Device Side version, the integration (Shelly, ZHA, etc.), the entity type, the fields
you tested, and whether each action worked. Include any error messages from the logs.

An automated runner that connects to your HA, executes the steps and prefills the issue body is
planned for a future release.

## Rig tests

Rig tests are YAML step files in `tests/rig/steps/`, one per action. `scripts/rig.py` runs each file against
every integration in the profile that has an adapter for the action, after a y/N gate: the devices change state, so
nothing moves until you say yes. `--dry-run` prints the plan and stops.

Before the gate, the run checks every device it will use, across all its phases: each fixed entity must be in HA and
available, and each roaming bulb must be on a network. A device left unpowered stops the run there, before anything
moves, rather than part way through. `--check` runs only this check, taking no lock and deploying nothing, so you can
power devices up until it passes; it names the runs holding locks it would need.

The run starts with one lane per integration, the lanes side by side, each holding that integration's cases on fixed
entities. A case stays out of the lanes when its step file sets device_side options (saving them reloads the
integration, cutting off every lane's fades), or when it uses a roaming bulb, a rig-made group or scene, or a powered
entity or its supply. Those run afterwards, one at a time, in the phases below. `--serial` runs every case one at a
time: a case that passes with it and fails in a lane points at radio or HA contention.

### Profiles

A profile is one test setup on the Home Assistant `.env.rig` connects to: `tests/rig/profiles/<name>.yaml`,
gitignored, copied from `tests/rig/profile.example.yaml`. It lists the entities the rig may move, by integration
and role, and under `pause:` the automations and switches turned off for the run and back on after it, for whatever
would fight the tests on those entities (motion lighting, an Adaptive Lighting instance's switch). Only those that
were on are turned back on. `.env.rig` keeps what belongs to the Home Assistant instance: its address, tokens,
deploy commands and Hue bridge.

`--profile <name>` picks one, and can be left out while there is only one. The plan names the profile, and so do
the journal and every test record (a `Profile` row). Records from different profiles of the same suite overwrite
each other; the commit diff shows which one ran last. A record is public, so name a profile for its setup (`lab`,
`house`), never for a person or place.

The household check (`scripts/check_private.py`) reads every profile's entity IDs, members, supplies and pause
list, and each roaming bulb's IEEE, so none of them reach a commit.

### Roaming

A profile's `roam:` lists bulbs the run moves between Zigbee networks, all together, round the fixed cycle Hue →
ZHA → Z2M → Hue (`tests/rig/roam.py`), so one set of bulbs serves every Zigbee suite. Each bulb has its IEEE, the
fixed entity ID it is renamed to after every join, its roles, and the Z2M options set again after each Z2M join.
The suites then run in phases: Hue's with the fixed integrations', then ZHA's, then Z2M's, each after a move and
each with its automated cases before its observed ones. The bulbs move only when a ZHA or Z2M suite runs, and end
home on Hue, with their rooms, zones, scene actions and names put back on their new Hue IDs. A run that stops
part way still moves them home; `--recover`, or the next run before its gate, does it after a crash. A bulb on no
network stops recovery: reset it over Bluetooth in the Hue app, then `--recover` again. A bulb still missing when
the Hue search ends gets one more, and any other device that joins the bridge meanwhile is named, not removed. Z2M
opens joining on its coordinator only. A bulb from Hue that a ZHA or Z2M window still lacks 30 s after the last join,
seen on no network, may have missed the bridge's Leave: the window closes, a Hue search takes it back, and it is
released alone for one more window. A network can list a bulb that left it (Z2M keeps a device whose remove
failed): a bulb is placed where it is live, a dead ZHA or Z2M listing is deleted and named, and a bulb live on two
networks, or listed but live on none, stops the move. A Z2M remove that a coordinator crash cut short is tried once
more when Z2M is back. `--roam-check` runs the cycle with no suites. Roaming needs `HA_ADMIN_TOKEN` and the Hue bridge's `HUE_BRIDGE_HOST` and `HUE_APP_KEY`.

`roam:` can also list `groups:`, native groups of those bulbs that the run makes on each network they visit: a Z2M
group, a ZHA group, or a Hue zone with, if the group names a `scene:`, a Hue scene in it. Each is called
`ds-rig-<object ID>` and renamed to its fixed entity ID, takes the group's roles (`group` or `group_color`, each on
one group; the scene takes `scene`), and is removed before the bulbs move on, or by `--recover` after a crash. A
run of Hue suites alone makes them on Hue without moving the bulbs; that, too, needs the tokens above.

Ctrl-C, SIGTERM or SIGHUP puts the devices back before the run exits; a second one leaves them. Each run journals
what it changes in a file of its own; if a run dies before it can put them back, the next run whose locks cover them
puts them back before its gate, and `--recover`, which takes every lock, puts back everything.

What runs change beyond the devices (the paused automations and switches, HA's and Z2M's log levels, Z2M device
options a test sets) is held in one shared baseline, `device_side-rig.baseline.json` in the git common dir. The first
run to change something records what it was; runs side by side share the change, and the last one out puts it back.
A crashed run's share is put back by the next run's change or by `--recover`, which always clears what no live run
holds. Z2M found at debug or trace with no run holding it goes back to `info`: debug is never its resting level.

Runs share the rig through locks in the git common dir, so every worktree sees them: one per integration, and one on
HA. A run holds each integration it tests, plus those its entities draw power through and the networks its roaming
bulbs visit, so runs on different integrations go side by side, and one on the same integration waits. It holds HA
shared, unless it deploys or runs a suite with device_side options (both restart or reload device_side under every
other run): then it holds HA exclusively, waiting for every other run to end, and new runs queue behind it. The plan
prints the run's locks; a waiting run names who holds what it waits for. `--wait-free` waits until the rig is free,
or with `--integration`, until those integrations are, without taking a lock.

Each run deploys your committed, pushed checkout and restarts Home Assistant whenever HA hasn't loaded that tree, so a
run queued behind another tests its own code. A record cites the commit HA loaded, read before the tests, so
committing mid-run is safe. `--no-deploy` tests whatever HA runs and, unless that is your checkout's tree, writes no
record. A signal during the deploy stops the run only once HA's restart finishes, so the next run never meets HA
mid-restart.

A probe takes the same locks through `--hold`, which runs a command while holding them and returns its exit code:
`scripts/rig.py --hold zha -- <command>`, with `--exclusive` for one that restarts HA or reloads device_side. It
passes signals on to the command, writes no journal and asks nothing unless the rig isn't clear (below): the probe
puts back what it changes.

`RIG_BLOCKER_ENTITY` in `.env.rig` names an HA binary_sensor that is on while someone might see the lights move. A run
approved by `DEVICE_SIDE_RIG_APPROVED=1` and any probe start only while it is off, and abort, putting the devices
back, once it reads on twice in a row; a yes typed at the prompt overrides it. A profile with `pre_authorized: true`,
for a setup whose lights nobody minds seeing move, skips it. Leave the key unset to gate nothing.

### Token

Make a dedicated Home Assistant user without admin rights and create its long-lived token for `HA_TOKEN` in
`.env.rig`. The rig only calls actions and reads states and registries, so admin isn't needed, and a non-admin
token can't change your configuration if it leaks.

ZHA and Zigbee2MQTT are the exceptions. ZHA's cluster command is an admin-only action, and the ZHA adapter passes
the caller's context through to it, so a non-admin token is refused. The Zigbee2MQTT suites set and read Z2M
device options over MQTT, which only an admin may. Put an admin user's token in `HA_ADMIN_TOKEN`: those suites run
on it and every other suite stays on `HA_TOKEN`. Without it, a run that includes either stops before the gate;
`--integration` or `--action` leaves them out. Suites whose adapter has options (Hue `raise_brightness`, `lower_brightness` and `stop`) need it too, to set them
(below).

### Writing a step file

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

Any step takes `target: <role>` to act on another role the test lists; a `group` case that targets a light role
is skipped where the profile lists the group's `members` and that light isn't one. Durations accept numbers, `duration`
(the last call's), `tol` (the integration's timing tolerance) and `+ - *`. `only: [<integration>]` limits a
test to some integrations; when those pile up, split the file.

The roles are listed in `tests/rig/profile.example.yaml`. `group_color` is a native group whose members all take
color: color moves groupcast only to a group like that, so it runs the color cases a `group` can't. Everything this
page says of a `group` holds for it too.

An adapter with options runs each file for its action with them pinned through Device Side's options flow:
`options: [<name>]` at the top of a file turns those on, and every other option in the adapter's scope runs off.
Its record is `<action>-<name>.md`, with an `Options` row. The rig's own options are put back when the run ends.

An integration in `SETTLE_S` (`tests/rig/profile.py`) predicts a light's brightness for a while after a
raise, lower or `stop`, so a later test on that light waits until it reads the device again.

### Observed tests

Some things need eyes, such as a light climbing smoothly without flashing. A test asks for them with an
`observe:` block and puts its start state in `setup:`. Each question costs the person at the rig, so observe
only what hardware has never shown and a check can't measure: once watched on an integration, a behavior stays
automated there.

```yaml
  - name: raise
    roles: [light_ct, group]
    setup:
      - set: {state: on, brightness_pct: 20}
    steps:
      - call: {brightness: brighter, sweep_time: 5}
      - sample: {attribute: brightness, for: 3, expect: rising}
    observe:
      see: The light at 20 %, climbing to full over 5 s.
      watch: Steps or flashes on the way up.
      ask: Did it climb smoothly to full?
```

Such a test runs twice, so you are asked only what a machine can't check:

1. **Automated**, with every other test first: setup and steps, every check applied. It has no automated run if
   its steps check nothing or its setup has a `do`.
2. **Observed** (`<name>[<role>] observed`), after all automated runs. Setup runs and settles for 2 s, then the
   runner prints `see` (in bold) and `watch` and waits for Enter. The steps run with their checks turned
   into waits, so the timing matches. Then you answer `ask`: Enter or `y` if you saw it, `n` if not, which fails
   the test and asks what you saw instead. It is skipped if its automated run failed, and if a step fails after Enter it prints
   `nothing to observe` and the reason.

`roles: [<role>]` in `observe:` limits the observed run to those roles, and `only: [<integration>]` to those
integrations; the rest run automated only.

`--unattended` skips the observed runs and reports them `not observed`. They don't fail, but a test counts toward
a test record only when both of its runs pass.

### Run reports

Every run, failed, partial or unattended, ends by writing a report to `device_side-rig/` in the system temp
folder and printing its path: each suite's results with the reason for every failure and skip. The OS clears it
out in time.

### Run logs

Z2M's frontend keeps only its last 1000 lines and HA's log restarts with HA, so a run captures both for you. Z2M's
lines (for a run that touches Z2M, or roams) are written to `<report>.z2m.log` as they arrive, and HA's log, from the
run's start, to `<report>.ha.log` when the run ends, both beside the report. A clean run deletes them; after a failure,
a stopped move or a crash they stay and their paths are printed. When Z2M's coordinator crashed during the run
(`ASH_NCP_FATAL_ERROR` or `Adapter disconnected` in Z2M's log), the summary says so with each crash's time, and the logs
stay even after a clean run; at debug it also counts the ACK timeouts that lead up to one.

`--debug-logs` keeps them whatever the outcome and runs HA's `device_side`, each integration the run touches (`hue`,
`zha`, `mqtt` for Z2M, `shelly`, `matter`; Hue, ZHA and MQTT when it roams) and Z2M at debug until the run ends. It costs
CPU, so timing cases may read differently. The levels are held in the baseline, so `--recover` puts them back. Z2M's debug
lines reach the capture only with `advanced.log_debug_to_mqtt_frontend: true` in its configuration, which needs a
Z2M restart; the brief warns when it is off, and the rig never sets it.

### Test records

When every test of an adapter passes, the run writes `docs/test-records/<integration>/<action>.md`: the date, the Home
Assistant version, the devices' model and firmware, and each test's result. A failed or partial (`-k`) run writes
nothing. Records are evidence for people, not read by any script: the PR that clears an adapter's `experimental`
flag cites one.

### Tester reports

A passing [Test report](../../.github/ISSUE_TEMPLATE/test-report.yml) issue becomes its own record,
`docs/test-records/<integration>/<action>-issue-<N>.md`, next to the rig's, so a rig run never overwrites it. It uses the
rig record's key/value table: `Source` cites the issue and the RC the tester ran (`tester report, #<N>, <rc>`).
Note the capabilities, fields and device_side options the report shows working. The tests table is optional.
