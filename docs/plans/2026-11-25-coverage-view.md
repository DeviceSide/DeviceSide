# Coverage view: show users what DeviceSide supports on their devices

2026-11-25. Step 5 of the v0.2.0 backlog plan (`docs/plans/2026-11-25-v0.2.0-backlog.md`, on `wt/v0.2.0-backlog`),
from step 4's prototype (`spike/coverage-view`: `scripts/prototype_coverage_view.*` and its handoff). Branch
`wt/coverage-view`. Decisions settled with Jason in this session; don't redesign them.

## Coordination

Intent: The Configure Settings form shows, per light and switch entity, which DeviceSide features run now
(Verified, Documented), which need Labs, and which are refused and why, read from the scopes the dispatcher uses.
Touches: custom_components/deviceside/config_flow.py, custom_components/deviceside/coverage.py,
custom_components/deviceside/core/dispatcher.py, custom_components/deviceside/core/scope.py,
custom_components/deviceside/core/registry.py, custom_components/deviceside/features.py, scripts/gen_features.py,
custom_components/deviceside/translations/en.json, custom_components/deviceside/integrations/zigbee2mqtt/**,
tests/**, docs/design.md, docs/plans/2026-11-25-coverage-view.md, README.md

## Decisions

1. **Surface:** a Configure (options-flow) menu item, `coverage`, titled "Device coverage". Not in the install step:
   Z2M's bridge cache starts with the entry, so at install every non-Hue Z2M device would be unplaced. The install
   success text points there: "Success! You can now use DeviceSide actions in your automations. To see what DeviceSide
   supports on your devices, open Configure, then Device coverage."
2. **One source of truth.** The view never re-derives a level. Extract from `Dispatcher` the per-target decision it
   makes today (classes via `_reached`, a group's via its members and `expand_group`; `AdapterScope.refusal`; then
   the Labs gate via `AdapterScope.level`) into one public function both the dispatcher's planning loop and the view
   call, returning ran-at-level / Labs / refused(reason, text) / not built. The dispatcher's behavior must not change:
   `--transcripts=check` proves it. A cell is the action's outcome with no fields (the action itself); fields held in
   Labs aren't shown.
3. **Rows:** one per entity that DeviceSide's resolver accepts, light and switch domains; leave out entities with an
   `entity_category`, disabled or hidden ones, ZHA's groups (on the coordinator device), and any entity whose class is
   Unplaced (`class_unknown`): on Jason's registry the only real one was a stale device Z2M no longer lists. A row with
   no cell (every feature empty) is left out. State-only switches (a breaker status) are listed: DeviceSide would run
   actions on them. The name is the one HA shows; then HA's icon; then a small "Group" label on a native group.
   Integrations in the README device cards' order, from the same ordering the cards use (move it into the package if
   it lives only in `scripts/`), never by parsing the README; names sorted within an integration.
4. **Icon:** the default (not state-dependent) icon HA shows: the entry's `icon`, else `original_icon`, else the
   platform's `entity` icons by `translation_key` (`homeassistant.helpers.icon.async_get_icons`), else the domain's
   `entity_component` icon by device class, else its `_` default. Rendered as `<ha-icon icon="mdi:…">`.
5. **Each entity row shows only its own domain's features,** as the dispatcher resolves per entity.
6. **Columns** (the action→feature map is `scripts/gen_compat.py`'s `FEATURES`; move it into the package if the view
   needs it at runtime): Dim, Saturation, Hue, Preset, Timer on, Timer off, Auto-off. Each heading is an
   `<abbr title="…">` with the full name: Smooth dimming, Smooth saturation, Smooth hue, Set without turning on, Turn on
   with timer, Turn off with timer, Auto-off/on. No Stop column (part of the smooth features), no Read column
   (`get_attributes` is left out of the view and its counts). A feature riding several actions takes its weakest.
7. **Cells:** 🟢 Verified, 🟡 Documented, ⚪ Labs, 🔴 refused; empty where the feature isn't for that entity or isn't
   built. A refused cell is 🔴 with a footnote number (`🔴¹`); the footnotes, one per distinct reason, are listed under
   the table, so they read on a phone. The reason text is the one the dispatcher raises with (the refusal's text, else
   the reason's).
8. **Legend** above the table: the four marks and the seven full feature names against their short headings.
9. **Markdown limits** (HA's flow markdown strips `style` and `class`; keeps tables, `ha-icon`, `abbr`): no sticky
   legend or headings, no rotated headings. The table goes in a description placeholder built in Python.
10. **Intro sentence:** "DeviceSide runs {n} features on {m} of your devices now." n counts 🟢 and 🟡 cells; m the
    distinct devices (a group counts as one) with at least one. Refusals never count.
11. **Labs checkbox** under the matrix, on the same form, defaulting to the current option: label "Labs", description
    "Turn on Labs: adds {k} features on {j} devices." (k: ⚪ cells; j: their distinct devices), then the Settings Labs
    description's warning sentence. Submitting saves the options (the entry reloads only if Labs changed, as
    `OptionsFlowWithReload` does).
12. **Waiting for Z2M:** while any loaded Z2M bridge's cache has no `bridge/devices` yet, the step shows HA's progress
    spinner ("Waiting for Zigbee2MQTT to list its devices.") for at most 10 s, then renders whatever it has. Add a
    generic, optional `IntegrationInfo` hook (sync check or awaitable) that says capability() is ready; Z2M implements
    it from its bridge cache (an `asyncio.Event` set when `bridge/devices` is first parsed). No other integration
    needs one.
13. **`judge()` covers the whole per-target decision** (plan review, step 1): it runs what the dispatcher checks
    before the gate too (`adapter.supports`, the not-addressable branch), on a request the caller passes. The view
    passes each action's minimal request: the action's required fields only, and for `set_attributes` a
    brightness-only one. So an adapter's own refusal (ZHA's `unsupported_reason`, Shelly stop's `not_dimmable`) shows
    as an empty cell (Decision 19), never a 🟢 a call would refuse.
14. **A native group held only by a member's Labs class** shows ⚪, the weakest of its members, though a call runs its
    Verified and Documented members: turning on Labs is what adds the rest.

18. **Columns and legend, after the live check (Jason, 2026-11-25):** headings Smooth dimming, Smooth color (saturation and hue, the weaker), Set while off, Timed on, Timed off, Auto off/on, plain text; the legend's key line is gone and 🔴 reads Unsupported. Replaces Decision 6's headings and abbr, and Decision 8's key.

19. **No refusals in the view (Jason, 2026-11-25):** a refused feature is an empty cell, as a blank is unsupported either way, and a row with no Verified, Documented or Labs cell is left out; the refusals' detail is the compatibility page's. The legend explains each mark, from the README's. Replaces Decision 7's 🔴 and footnotes, and the 🔴 in Decisions 8 and 18.

20. **Coverage in Settings (Jason, 2026-11-25):** one Settings form: its description holds the intro, legend and table; then all three options, Labs last with the "Turn on Labs: adds…" line (Decision 11) as its description. The `coverage` menu item and `coverage_view` step go; the progress wait (Decision 12) runs before Settings. The install success text reads "…open Configure, then Settings." Replaces Decision 1's menu item; its install-flow note stands (HA's `next_flow` takes only `FlowType.CONFIG_FLOW`, so the install can't open Configure).
21. **The "Turn on Labs: adds…" sentence shows only while Labs is off (Jason, 2026-11-25),** closing audit report 2's Medium; with Labs on, the Labs description is the Settings form's own Labs text alone.
22. **Controls first (Jason, 2026-11-25, live check):** the three options head the Settings form; the intro, legend and table follow in Labs's `data_description`, after the Labs text (HA renders a step's description above its fields, a section's description as plain text, and a field's `data_description` as Markdown). The intro drops "now": "DeviceSide runs {n} features on {m} of your devices." The Labs legend line says "above". Headings use `<center>`, as HA's Markdown sanitizer drops `align` from `div`.
23. **Collapsed above the options (Jason, 2026-11-25, live check):** Decision 22's table under Labs still rendered the options last, and HA has no description below a step's fields, so the Settings description is a `<details>` whose summary is the intro sentence, holding the legend and table; Labs's description is its own text again, and the legend says "below". Replaces Decision 22's placement.

## Steps

1. **Shared decision** (Decision 2): extract and route the dispatcher through it. Unit tests pin each outcome on a
   Labs-only, a Documented, a Verified, a refused and a not-built case, and a native group whose member is in Labs.
2. **The view** (`custom_components/deviceside/coverage.py`: rows, cells, counts, the markdown; `config_flow.py`: the
   menu item, the progress step, the form, the Labs field; `en.json`: the strings above). Decisions 1, 3-12.
3. **Docs:** `docs/design.md` gets a short Coverage view section (it reads the dispatcher's decision, never a copy);
   the README's Configure description gets the menu item after the code lands, if it lists the menu.

## Verification

- Every view cell equals the shared function's outcome for a call on that entity with Labs off, and a dispatcher test
  shows a real call on the same fixture entity runs, skips as `labs_off` or refuses where the cell is empty (backlog plan,
  Verification: "the view's per-device level matches what a call on that device does").
- Rows: an `entity_category` entity, a disabled one, a ZHA group and an Unplaced Z2M device are left out; a Z2M group
  shows "Group"; integration order follows the cards.
- Counts and the Labs line on a fixture with known 🟢/🟡/⚪ cells; an entity whose only outcomes are refusals has no row.
- Progress: the step waits while Z2M has no `bridge/devices`, and renders after the 10 s bound.
- Checks: `.venv/bin/pytest -n auto --transcripts=check`, `scripts/gen_compat.py --check`, `scripts/check_ha_literals.py`.
- Before ready: Jason opens Configure → Settings on his HA (a rig run isn't needed: no call changes).

## Handoff

2026-11-25, after the live-check rounds (Decisions 18-19 and the tweaks below).

- **Done:** steps 1-3; plan review of 2-3 (`f152520d`'s note); PR audit report 1's High (a falling-back native group, `18ff1021`); audit report 2 CLEAN at `18ff1021`, now stale. Main merged (`335f6165`: Aqara Verified). Live-check rounds from Jason: Decision 18 (`b397a17d`, `ba53867c`), Decision 19 (`0ba64a32`, legend `d4c6e6c2`), then `4f985a5d`: headings in `<div align="center">` (not yet seen live), the icon before the name, the Labs legend line "not yet passed on a real device. Turn on Labs below to try it", and gen_compat's legend drops "or held back to soak" (README regenerated). HA runs `d4c6e6c2`.
- **Ruling 20 (Jason, 2026-11-25):** merge the coverage view into Settings: one Settings form with the intro, legend and table in its description, then all three options (Labs last, with the "Turn on Labs: adds…" line). The `coverage` menu item and `coverage_view` step go; the progress wait (Decision 12) runs before Settings. The install success text points to "open Configure, then Settings". Decision 1's install-flow note stands: HA's `next_flow` takes only `FlowType.CONFIG_FLOW`, so the install can't open Configure. Device Sentinel's after-setup device list is HA's own success dialog over the devices its entry registers; DeviceSide registers none.
- **Next:** Decisions 20-21 built (`871ac385`, plan-reviewed: design.md typo and plan text fixed after). Check with Jason live (deploy with `/Users/jason/projects/ha/ha-rig/scripts/rig.py --deploy-only` from this worktree, after asking: it restarts HA), including whether the headings centre (else `<center>`). Then the audit gate (`audit-gate brief pr`, opus auditor, `record`, `owner-findings`), `gh pr ready`, `merge-green 611 --squash --delete-branch`.
- **Follow-up PR after #611 merges (Jason agreed, 2026-11-25): README coverage.** (1) "Will it work with my device?" leads with the view: install, open Configure → Settings, see your lights and switches marked Verified, Documented or Labs. (2) gen_compat's collapsed block shrinks to integration plus device class with marks, linking docs/device-compatibility.md for models. (3) README legend shares the view's wording and marks from one source (gen_compat and coverage.legend()); 🔴 leaves the README for the compatibility page (Decision 19). (4) A screenshot of the view: once Jason approves the final Settings form, build a generic mockup (made-up device names, served on a local dev web server) for him to screenshot; never his HA's names.
- **Branch / worktree / PR:** `wt/coverage-view`, `/Users/jason/projects/ha/deviceside-wt/coverage-view`, #611 (draft).
