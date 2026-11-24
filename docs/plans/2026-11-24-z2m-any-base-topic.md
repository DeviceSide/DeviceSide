# Zigbee2MQTT: any base topic, several instances

Saved to the repo as `docs/plans/2026-11-24-z2m-any-base-topic.md` (step 0).

## Coordination

Intent: address Zigbee2MQTT devices and groups on whatever base topic their instance uses, several instances on one
broker at once, so a custom base topic stops being refused (`not_addressable`). Root fix for #575.
Touches: custom_components/deviceside/integrations/zigbee2mqtt/**, tests/integrations/zigbee2mqtt/**,
tests/fixtures/zigbee2mqtt.py, docs/integrations/zigbee2mqtt/**, TODO.md

## Context

#575: a user's Z2M base topic was `'    zigbee2mqtt'` (four hidden leading spaces from an install package), and
every DeviceSide light action refused their lights. `addressing.py` hardcodes `_Z2M_BASE_TOPIC = "zigbee2mqtt"`;
every device, group and bridge topic, and `bridge_cache`'s one set of subscriptions, assume it. A custom base topic
mostly exists to run two Z2M instances (two coordinators) on one broker, so "any base topic" means several at once.
Draft #580 (a log line quoting the base topic, plus a docs note on renaming it) treats the symptom: closed unmerged.

## Decisions

1. **Several instances.** One `BridgeCache` per base topic, not one cache with a configurable topic. (Jason, 2026-11-24)
2. **The base topic comes from the target's bridge.** Z2M's discovery links every device and group to its bridge
   (`payload.via_device = this.bridgeIdentifier`, identifier `zigbee2mqtt_bridge_<coordinator ieee>`) and gives
   each bridge entity unique_id `bridge_<coordinator ieee>_<object_id>_<base topic>`, its object_ids fixed
   (`connection_state`, `restart_required`, `restart`, `log_level`, `version`, `coordinator_version`,
   `network_map`, `permit_join`) (`lib/extension/homeassistant.ts`: `getDevicePayload`, the `Bridge` class, the
   bridge's discovery entries). So base topic = that unique_id with the known prefix stripped: exact, public
   registries only. Not the device's own unique_id tail (#580's guess). (Jason, 2026-11-24)
3. **#580 closes unmerged** (`pr-close 580`); its finding (hidden spaces, HA's UI hides them) goes into the
   research file. (Jason, 2026-11-24)
4. **An address carries its base topic.** Group IDs collide across instances (both can have group 7), so every key
   built from `(kind, z2m_id)` (`restore_journal`, `native_control`'s restore tasks and locks, `BridgeCache.confirmed`
   when the cache is per base) becomes `(base, kind, z2m_id)` or lives in its base's cache. IEEEs don't collide
   (distinct radios), friendly names are scoped by the cache whose log they come from.
5. **No bridge found means refused.** A target whose `via_device` isn't a Z2M bridge with a known bridge entity (a
   discovery race, a stripped registry) is `not_addressable`, with one DEBUG line saying so. No fallback to the
   default topic: a guessed topic reaches nothing silently.
6. **Default-base calls don't change**, so `--transcripts=check` passes untouched and no record reopens (tenet 9).
   A custom base sends the same calls on another prefix: it inherits their evidence (tenet 5); unit tests pin it.

## Steps

### 0. Set up (orchestrator)
`pr-close 580`. Worktree `.claude/worktrees/z2m-any-base-topic`, branch `wt/z2m-any-base-topic` off `main`, `uv sync`.
Save this plan to `docs/plans/2026-11-24-z2m-any-base-topic.md`, `pr-draft` it.

### 1. Probe and research (no code)
Read-only, on the household HA (Jason or the rig session; no restart): dump the Z2M bridge device and its entities'
unique_ids, and check a Z2M light's device has `via_device_id` = that bridge, and a Z2M group's too. Record the
result and Decision 2's upstream citations (pinned to the tag the household runs, 2.14.3) in
`docs/integrations/zigbee2mqtt/research/2026-11-24-base-topics.md`, with #575's report. No household names or IEEEs:
redact to shape. Takes the decision: Decision 2's foundation; if it contradicts, stop and tell Jason.

### 2. Addressing by base topic (implementer: sonnet)
`addressing.py`:
- `bridge_bases(hass) -> dict[str, str]`: bridge device id → base topic, from mqtt-platform entity-registry entries
  (disabled included) matching `^bridge_(0x[0-9a-fA-F]+)_(<known object_ids>)_(.+)$`. A base may hold `/` and spaces.
- `base_topic(hass, target) -> str | None`: the target device's `via_device_id` looked up in `bridge_bases`.
- `topic`, `state_topic`, `bridge_topic(base, suffix)`, `state_unique_id(address, domain, base)`, `group_id`,
  `entity_name`, `options_address`: take the base; groups match their encoded base against the target's own
  base (`getEncodedBaseTopic`, already mirrored by `_ENCODED_BASE_TOPIC`), so a mismatch stays refused.
- `Address` gains the base (Decision 4). `not_addressable`: Decision 5's line; the multi-endpoint rule is
  unchanged, against `state_unique_id(..., base)`.
- Keep `"zigbee2mqtt"` only as the fixtures' default; the code has no default base topic left.
Callers that build topics (`bridge.py`, `read.py`, `fade.py`, `color_refresh.py`, `turn_on_for.py`, `set_check.py`,
`members.py`) pass the target's base. Bridge-cache callers keep `bridge_cache.get(hass)` until step 3.
Tests: `test_addressing.py` cases for a base with spaces, with `/`, two bridges, no bridge (refused), a group on
the other instance's base (refused by its own).

### 3. A bridge cache per base topic (implementer: opus; risky: gets its own `/audit-code` of the range)
`bridge_cache.py`: a registry `{base: BridgeCache}`, each subscribing its own bridge topics with the existing order
and barrier. `get(hass, base)`. `async_setup` creates one per base in `bridge_bases`, and follows
`EVENT_ENTITY_REGISTRY_UPDATED` (create/remove of a bridge entity) to add and stop caches; MQTT reconnect handling
stays per cache. `on_online` passes its base (restore replay per base). `color_modes.async_watch` and
`ensure_color_modes` run per base (their devices and groups lists are per instance). Callers (`classes.py`,
`members.py`, `set_check.py`, `bridge.py`) look up by the target's base.
Tests: two instances in the fixture broker (two bridges, same group ID on both): each group's members, options and
log failures come from its own instance; a bridge added after setup gets a cache; one removed stops its subscriptions.

### 4. Restore journal keys (implementer: opus: stored user data)
`restore_journal.py`: keys carry the base (Decision 4). Store version 1 → 2: every v1 key moves under base
`zigbee2mqtt` (the only base v1 could address), so an owed restore from before the upgrade is still paid.
`native_control.py` restore tasks and locks keyed by the new `Address`.
Tests: a v1 store loads under `zigbee2mqtt` and replays on that base's online; two instances owing the same group
ID are paid separately.

### 5. Docs, issue, TODO (implementer: sonnet)
- `docs/integrations/zigbee2mqtt/internals.md` Addressing: base topic per bridge (link the research), groups'
  encoded base, several instances; drop "Both assume the default base topic".
- `docs/integrations/zigbee2mqtt/index.md` Sharp edges: remove the Custom base topic entry (it no longer limits
  anything a user does).
- Module docstrings: `addressing.py`, `bridge_cache.py` say why, linking internals.
- `TODO.md` if it lists this; `scripts/gen_compat.py --check`, `gen_features.py --check` if their inputs moved.
- Reply on #575 (drafted, Jason approves before posting): support for any base topic is in #<PR>, ask them to test
  the RC on a custom base if they can.

## Verification
- Per push: `.venv/bin/pytest -n auto --transcripts=check` (transcripts unchanged: Decision 6),
  `uvx pre-commit run --all-files`.
- Step 1's probe is the live check. No rig run gates a merge (tenet 8): the next RC's run covers the default base,
  and #575's reporter is asked to test a custom base on the RC.
- PR audit per CLAUDE.md, then `owner-findings`; Jason maintains Zigbee2MQTT, so no owner notice.

## Launch
`cd /Users/jason/projects/ha/deviceside && claude --model opus 'Implement docs/plans/2026-11-24-z2m-any-base-topic.md, starting at step 0.'`
Opus: the orchestrator rules on the bridge-cache concurrency and the stored-data migration, where a wrong call gets
past unit tests.

## Handoff

2026-11-24, from the session that ran steps 0–2.

**Done**
- Step 0: #580 closed; worktree `.claude/worktrees/z2m-any-base-topic`, branch `wt/z2m-any-base-topic`, draft PR #581.
- Step 1: `docs/integrations/zigbee2mqtt/research/2026-11-24-base-topics.md` (47b04d33, review fixes 57ac6736).
  Decision 2 holds upstream (2.14.3) and live (one instance, default base). The probe ran from Jason's shell: the
  sandboxed Python can't reach the LAN HA, and the auto-mode classifier refuses using the rig token from this side.
- Step 2: f2093149, review fixes 17d4a3a3 (its `Plan review:` note). `addressing.py` reads the base from the via
  bridge's entities (a base every bridge entity admits, single survivor, else refused). `Address(base, kind, z2m_id)`.
  Interim guard: `bridge_cache.get(hass, base=None)` returns the one cache only for its own base.
  Suite 3062 passed, `--transcripts=check`, no transcript changed.

**Next: step 3** (opus implementer, its own `/audit-code` of the range), then steps 4 and 5, then the PR audit.

**Carried into step 3**
- No cache when no bridge is registered at setup (`bridge_cache.async_setup` returns early): the registry-update
  handling fixes it.
- `set_check.checked` still calls `bridge_cache.get(hass)` with no base: it listens to one log across several
  targets; move it per base.
- The `base=None` path of `bridge_cache.get` is interim: remove it once every caller passes a base.

**Carried into step 4**
- `restore_journal.request_replay` sets `replays.base` on every call and replays every owed key on that base:
  harmless with one cache, wrong with several ("last online wins"). Keys carrying the base fix it.
- The journal's type alias was renamed `Key` (the new `Address` is addressing's).

**Peers**: #582 (Tuya datapoint countdown, branch `wt/tuya-datapoint-single`) overlaps `integrations/zigbee2mqtt/**`.
Its session was told: `publish_set` keeps its signature; addressing helpers and `bridge_cache.get` gain the base.

**Open decisions**: none.
