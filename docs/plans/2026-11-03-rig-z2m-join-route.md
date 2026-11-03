# Rig: Z2M joins through the coordinator, and Hue releases that reach every bulb

## Context

On 3 Nov, the lab's Hue → Z2M move failed four times out of five, each time on the third bulb to join:

| When | What happened |
|---|---|
| 09:25 run | Desk bulb joined; interview failed (`Delivery failed`); not interviewed within 120 s |
| 09:47 run | A60 never joined Z2M (no `joined` line) |
| 10:44 scan | A60 never joined (Z2M at `info` via #169: the other two joined in 2 s and 10 s) |
| 10:49 test, A60 released first | A60 joined; interview failed; #169's retry passed; it left the network 15 s later |

Each time the A60 "never joined", a Hue search later picked it up at once, with no reset. So the bridge's Leave
(sent on the CLIP v2 device delete) wasn't reaching it, and it stayed on Hue's network. The rig releases bulbs
last-joined-first, but on Hue the order bulbs joined in doesn't show which bulb routes through which.

Z2M's network map (10:50, with routes) put the desk and corner bulbs on one parent: a mains-powered smart plug
in the same room, an old router model known for small child tables. Their direct links to the coordinator
have LQI 66 to 121. The third bulb through that parent fails.

Not in this repo: the maintainer may move the plug off the Z2M mesh. These fixes don't depend on that.

## Fix 1: Z2M joining through the coordinator only

- `tests/rig/client.py` `z2m_permit_join`: send `{"time": seconds, "device": "Coordinator"}` when opening,
  checked against Z2M 2.14's `bridge/request/permit_join` (the `device` key takes a friendly name or IEEE;
  the coordinator's is `Coordinator`). Closing stays `{"time": 0}`.
- Check what `bridge/info` reports while a coordinator-only permit is open: `done()` reads `permit_join`
  from it.
- Tests: the fake records the payload; a join opens with the coordinator named.
- If the coordinator turns out to be out of range for a lab bulb, the join fails as it does now and the error
  says so. Don't build a fallback until a rig run shows it's needed.

## Fix 2: Hue releases that reach every bulb (design call: interview Jason first)

CLIP v2 has no topology (no parent or neighbor table), so the release order can't be read from the bridge.
Options to put to Jason:

- **a. Detect and retry:** after the target window, a bulb that didn't join and that a Hue search adopts at once
  never got its Leave. Search it back (it keeps its Hue home, already saved), release it alone and first, then
  reopen the target. Bounded: one retry per bulb per move. This handles any topology without reading it.
- **b. One at a time:** release each Hue bulb and wait for it to join the target before releasing the next. Each
  Leave then goes out while the others are still routing. Slower: one window per bulb.
- **c. Reverse the Hue join order plus a:** keep the current order and add a's retry.

Recommendation going in: **a**, as it handles what actually happened with no new assumption about the mesh.
Whichever is chosen: tests in `tests/scripts/test_rig_roam.py` with the Lab fake taught a "missed Leave"
bulb that the next Hue search adopts; journaled, so `--recover` handles a crash mid-retry.

## Rig

Both fixes change only moves. Before merging: a `--roam-check` on the lab (needs Jason's go after 11:30 on
3 Nov, or any other day), and Z2M's log at `info` (#169) for the join. Then the Z2M lab run the 3 Nov
window didn't get: `--profile lab --integration zigbee2mqtt --unattended`.

## Finish

TODO.md: "Done since v0.0.1" row; the lab plan's findings note gets a line on the fix.
