# Coverage view: scenes in the count

The Settings form's coverage view (`custom_components/deviceside/coverage.py`) shows lights and switches. This adds
"and N scenes" to the intro count, N being the scenes that `set_scene` serves with a Verified or Documented mark. A
Scenes table (Mockup B, chosen by Jason on 2026-11-26) was planned, then dropped (Decision 8). Decisions below are settled; don't redesign them.

## Coordination

Intent: show users which of their scenes DeviceSide can set while the lights are off, and why a scene's mark is lower
than its best lights'.
Touches: custom_components/deviceside/coverage.py, tests/test_coverage.py, docs/design.md,
docs/plans/2026-11-26-coverage-scenes.md

## Mockup

```
DeviceSide runs 97 features on 49 devices and 12 scenes.

🟢 Verified: …
🟡 Documented: …
⚪ Labs: …

| (device grid, unchanged) |
```

## Decisions

1. **Which scenes.** Home Assistant scenes (`core/ha_scene.py`'s `is_ha_scene`; a YAML scene with no `id` has no
   registry entry, so enumerate the scene platform's entities, not the entity registry alone) and scenes an
   integration's `set_scene` adapter serves (today Hue bridge scenes). Disabled or hidden registry entries are left out,
   as device rows are. A scene with no mark (refused, e.g. a Hue smart scene; not built; no light served) has no row,
   as an entity with no cell has none.
2. **The mark reads the dispatcher, never a copy** (design.md, Coverage view). A Hue bridge scene: `judge` on its
   `set_scene` adapter, as a device cell does (Hue classes the scene by its weakest light). A Home Assistant scene: each
   light the scene holds on with something to write (`scene_lights`, HA groups expanded as `ha_scene` expands them)
   is judged on `set_attributes` with the scene's own write for that light, Labs off; the scene's mark is the weakest
   of the lights that run (now or in Labs). Lights held off (turned off by core) and lights with nothing to write carry
   no mark and don't count either way.
3. **Part-served scenes show.** A light a call would skip (refused, not built, no adapter, unresolved, or `SKIPPED` for
   a missing color) doesn't lower the mark; it is counted in Notes as "N light(s) not served". This matches the call,
   which writes the lights it can and skips the rest.
4. **Notes column** (superseded by 8; Jason chose it over "Set by", which read as unclear). Plain text, entries joined by "; ":
   - "<light> is Documented" or "<light> is in Labs" only when the scene's lights' marks differ, naming the light
     whose mark is the scene's (first by name on a tie). Blank when all its lights share the mark.
   - "N light(s) not served" when Decision 3 applies.
   - A Hue bridge scene's Notes are blank: its level is its class's, decided by the adapter.
   Light names are the names HA shows (`_name`), escaped with `_plain`.
5. **Count line.** "DeviceSide runs {n} features on {m} devices and {s} scenes." ("of your" dropped, Jason). {s}
   counts scenes marked 🟢 or 🟡; with none, the line ends at "devices.". Singular forms for 1 ("1 device", "1 scene",
   "1 feature"). Scene marks don't add to {n}.
6. **Layout** (superseded by 8). The Scenes table follows the device grid, headed `**Scenes**`, rows by name (casefolded). Icon: the
   scene's `_Icons.of`, as device rows get theirs (scene is added to the icon lookup's domains). No table and no heading
   when there are no rows. If there are scenes but no device rows, the Scenes table still shows.
7. **Waiting.** (The table wording is superseded by 8.) Scene marks obey the same capability wait as device rows (`settle`), and a Hue scene whose class is
   `Unplaced` is left out like a device.

8. **No table (Jason, 2026-11-26).** The Scenes table, its Notes column, the `**Scenes**` heading and the icon are
   dropped; Decisions 4 and 6 and the table wording of 7 are superseded. Only the count line (5) shows scenes. Scene
   marks are still judged as 1-3 say, since the count needs them; `Coverage.scenes` holds just the marks.

## Steps

One step (sonnet; the decisions settle the judgment calls, and tests catch a wrong mark):

1. `coverage.py`: collect scene marks (Decisions 1-3, 7) and the count line (5, 8).
   `tests/test_coverage.py`: an all-Verified HA scene; mixed marks (the weakest decides); a part-served scene; a scene
   with no light served; a Hue bridge scene and a smart scene; a YAML scene with no registry entry; the count line with
   0, 1 and several scenes. `docs/design.md`, Coverage view: one bullet on scenes (what a scene's mark is, counted in the intro),
   cutting a sentence elsewhere (`.claude/rules/docs.md`). The README screenshot is left as is.

Checks: `.venv/bin/pytest -n auto --transcripts=check`, `.venv/bin/python scripts/check_docs.py`, pre-commit. Then deploy to the
maintainer's HA for Jason's live look; that check decides wording, not a release, so no rig run.

## Handoff

- Done: plan settled with Jason (Decisions 1-7); draft PR #640 on `wt/coverage-scenes`, worktree
  `deviceside-wt/coverage-scenes`. The PR also carries a merged-in tweak Jason confirmed live: column headings use
  non-breaking hyphens so "Flash-free turn-on" wraps to two lines (`coverage.py` `table()`, its test).
- Next: step 1, the scene count (one implementer, then a plan-reviewer), then the PR audit and Jason's live look.
- Open decisions: none.
