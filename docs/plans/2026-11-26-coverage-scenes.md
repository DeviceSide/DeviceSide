# Coverage view: a Scenes table

The Settings form's coverage view (`custom_components/deviceside/coverage.py`) shows lights and switches. This adds a
second, small table under the device grid: one row per scene that `set_scene` serves, with its Flash-free turn-on mark
and a Notes column. Mockup B, chosen by Jason on 2026-11-26. Decisions below are settled; don't redesign them.

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

**Scenes**

|                | Flash-free turn-on | Notes                                         |
|----------------|:------------------:|-----------------------------------------------|
| 🎨 Evening     |         🟢         |                                               |
| 🎨 Movie       |         🟡         | Hall lamp is Documented                       |
| 🎨 Reading     |         🟢         | 2 lights not served                           |
| 🎨 Party       |         ⚪         | Strip light is in Labs; 1 light not served    |
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
4. **Notes column** (Jason chose it over "Set by", which read as unclear). Plain text, entries joined by "; ":
   - "<light> is Documented" or "<light> is in Labs" only when the scene's lights' marks differ, naming the light
     whose mark is the scene's (first by name on a tie). Blank when all its lights share the mark.
   - "N light(s) not served" when Decision 3 applies.
   - A Hue bridge scene's Notes are blank: its level is its class's, decided by the adapter.
   Light names are the names HA shows (`_name`), escaped with `_plain`.
5. **Count line.** "DeviceSide runs {n} features on {m} devices and {s} scenes." ("of your" dropped, Jason). {s}
   counts scenes marked 🟢 or 🟡; with none, the line ends at "devices.". Singular forms for 1 ("1 device", "1 scene",
   "1 feature"). Scene marks don't add to {n}.
6. **Layout.** The Scenes table follows the device grid, headed `**Scenes**`, rows by name (casefolded). Icon: the
   scene's `_Icons.of`, as device rows get theirs (scene is added to the icon lookup's domains). No table and no heading
   when there are no rows. If there are scenes but no device rows, the Scenes table still shows.
7. **Waiting.** Scene rows obey the same capability wait as device rows (`settle`), and a Hue scene whose class is
   `Unplaced` is left out like a device.

## Steps

One step (sonnet; the decisions settle the judgment calls, and tests catch a wrong mark):

1. `coverage.py`: collect scene rows (Decisions 1-3, 6-7), the Notes text (4), the count line (5), and render the table
   in `section()`. `tests/test_coverage.py`: a test per decision: an all-Verified HA scene; mixed marks naming the
   weakest light; a tie by name; a part-served scene's count; a scene with no light served (no row); a Hue bridge scene
   and a smart scene (no row); a YAML scene with no registry entry; the count line with 0, 1 and several scenes; Notes
   escaping. `docs/design.md`, Coverage view: one bullet on scenes (what a scene's mark is and what Notes say),
   cutting a sentence elsewhere (`.claude/rules/docs.md`). The README screenshot is left as is.

Checks: `.venv/bin/pytest -n auto --transcripts=check`, `.venv/bin/python scripts/check_docs.py`, pre-commit. Then deploy to the
maintainer's HA for Jason's live look; that check decides wording, not a release, so no rig run.
