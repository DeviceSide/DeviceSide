# Hue: other brands' lights take set_attributes, set_scene and get_attributes (#617)

2026-11-25. Triage of #617, agreed with Jason; branch `wt/hue-other-brands`. Rides v0.2.0rc1 as step 5b of
[the v0.2.0 plan](2026-11-25-v0.2.0-backlog.md).

## Context

#617 (nlvmark, v0.1.0, Labs off): ZLL dimmers of another brand (ROBB smarrt) on a Hue bridge are refused
`not_built` on `set_attributes` and `set_scene`. They worked under Hue Smooth Dimming, DeviceSide's predecessor:
the same reporter asked for set_scene in jasonmx/hue-smooth-dimming#22, and it worked on these lights.

**Root cause: scope, not code.** `integrations/hue/classes.py` classes every light whose manufacturer isn't
`Signify Netherlands B.V.` as `other`, the default class, and `LEVELS = verified(HUE)` gives `other` nothing on any
action, even with Labs on (`docs/integrations/hue/index.md`, Other brands). Hue Smooth Dimming sent every brand the
same aiohue `lights.set_state` call with no branch on the manufacturer (`hue_dimmer/bridge.py`, `scenes.py`), and
DeviceSide's request is the same for every light too (`docs/integrations/hue/internals.md`, Device classes). So a
user moving from Hue Smooth Dimming, as its migration repair invites, loses features on every non-Signify light:
`docs/action-behavior.md`, Replacing hue_dimmer, asks that such a break be named, and it wasn't. The refusal
(`not_built`) and the Labs option give the user no way forward.

## Decisions (interview, 2026-11-25)

Two principles Jason drew from #617, which this PR writes into the rules (step 1, part B):

- **P1. Include unless harmful.** Users want broad coverage of devices we can't test: a device gets an action unless
  it is likely to cause harm there.
- **P2. Never withdraw a released feature silently.** Users rely on what shipped, and breaking their setup is a material
  harm: keep it, and act only on a report.

1. **Documented on every light action on Hue's `other`, with the Labs option off:** `raise_brightness`,
   `lower_brightness` and `stop` (Hue Smooth Dimming ran them on every brand: `transitions.py` sends
   `set_state(on, brightness, transition_time)`, stop `set_dimming_delta`, the same aiohue calls DeviceSide's
   `hue/fade.py` and `hue/bridge.py` send, so dropping them would regress its users, P2); `set_attributes`,
   `set_scene` and `get_attributes` (hue_dimmer ran these on every brand too); `raise_saturation` and
   `lower_saturation` (new, not in hue_dimmer; included on P1: the same `set_state` with xy and a transition, low harm,
   visible at once). A scene writing an `other` light, and a room or zone holding one, run on all of them. Nothing on
   `other` stays in Labs; smart scenes keep their no known method entry.
2. *(merged into 1)*
3. **The route, an amendment to `docs/evidence.md`** (Levels, and Unknown is flagged), beside #615's standard
   converter's call: *a bridge's one request*. Where the integration sends the bridge the same request for every light
   and the bridge picks the Zigbee call (Hue's CLIP v2), an action whose failure doesn't harm (`Action.failure_harms`)
   is Documented on the default class on the request's usage: Hue Smooth Dimming sent the identical request to every
   brand (cite its source at a pinned commit), with #617's pass and no reported departure. A read that sends nothing
   (`get_attributes` reads the event stream) qualifies outright. Split-offs follow the contrary-evidence rules: a
   failing report splits off the identity (manufacturer and model), citing it. The known departures (index.md's: a
   light that fades only one of brightness and color, or comes on when written while off) stay in `internals.md` as
   what such a report would split off. The implementer words it; Jason reviews it in the PR; Opus auditor.
4. **Rides v0.2.0rc1.** Levels and classes change, calls don't, so no Hue rig rerun (tenet 9);
   `--transcripts=check` proves no call changed.
5. **The Hue Smooth Dimming migration repair is unchanged.**
6. **The reply on #617** is posted once Jason approves its text. If the reporter gives his lights' Manufacturer and
   Model, they go in a `_manual.json` row crediting his report, as a follow-up, not a gate.
7. **(2026-11-25, after step 1's review) `get_attributes` on a light whose `mirek_valid` is known wrong is split
   off, not worked around:** `get_attributes` promises the light's actual value, never a cache of DeviceSide's or HA's
   last write, so core's fix (PR #97263: track the last command on uncertified lights) is out. The Gledopto GL-C-008P
   (core #93459) gets a class of its own that `get_attributes` doesn't serve; every other `other` light keeps it. A
   user of that model reads HA's own light attributes.
8. **(2026-11-25) Tenet 11 covers full releases, not RCs.**

9. **(2026-11-25, after the PR audit) Decision 7 widens to the makers core #62497 reports, and the route narrows.**
   [core #62497](https://github.com/home-assistant/core/issues/62497) reports the same color temperature mode misread
   through the bridge on other Gledopto models (GL-S-004P, GL-B-007P, non-Pro strip controllers), a Müller Licht tint
   and a LivarnoLux strip; the bridge itself reports it, and a Gledopto Pro controller didn't. So the split-off keys on
   the maker, at the narrowest key a class rule can use: Gledopto (`GLEDOPTO`, any model) and Müller Licht (its Zigbee
   manufacturer string, cited), each a class of its own that `get_attributes` doesn't serve; every other `other` light
   keeps it. Livarno is Tuya inside, with a `_TZ…` string per model and none in the report, so it has no key yet: it
   is recorded in `internals.md` as reported, to split off when a report gives its strings. Not `product_data.certified`:
   it would drop a read that works on most uncertified lights, and whether Friends of Hue lights report it is unverified.
   In `docs/evidence.md`'s route: the bridge picks the call (not "or the device's driver", which a Zigbee2MQTT
   converter could claim), and a read that sends nothing needs no usage evidence but splits off on a reported misread
   like a failing request.

## Steps

1. **Build** (opus implementer: binding-rule text and public docs; Opus `plan-reviewer`).
   - **A. Hue.** `hue/classes.py`: `LEVELS` Documented on `other` beside Verified on `hue`, one home for the levels;
     the docstrings and comments that say `other` gets nothing. Each adapter's scope where it holds levels.
     `docs/integrations/hue/index.md` `### Other brands`: they get every feature, why, and how to report one that
     misbehaves, in Hue's page shape, no level stated. `internals.md`, Device classes: the hue_dimmer call comparison,
     linked at a pinned commit; the known departures as split-off candidates. `devices.yaml` card phrase if needed;
     regenerate with `scripts/gen_compat.py`. Tests (`tests/integrations/hue/`): `other` at Documented on all eight
     actions, Labs off; a scene with an `other` light runs `set_scene`; a room mixing `hue` and `other` lights runs
     as a room on every action.
   - **B. The principles in the rules** (terse; a deletion pass on each section touched; the evidence is this PR's
     body, never provenance in the rule):
     - `CLAUDE.md` tenets: tenet 2's "build from a cited source to Labs" and tenet 8's "A new item is flagged until its
       pass is on record" become P1: an item ships outside Labs unless it is likely to harm or no route in
       `docs/evidence.md` (Levels) admits it. A tenet for P2: a feature shipped outside Labs in a tagged release is
       withdrawn only on a report or a root-caused finding, and its release notes name the withdrawal.
     - `CONTRIBUTING.md`: Development principles, "Tested on real devices", restated for P1 and P2; step 4, Set the
       level, points to `docs/evidence.md` Levels instead of listing the Documented routes (it already misses #615's).
     - `docs/evidence.md`: the Labs flag's "An item is in Labs until a real device has passed it" and the default
       class's "Nothing lifts it" reconciled with the routes; contrary evidence's "the demotion lands with the finding"
       and the deprecation note extended so any withdrawal of a shipped feature gets a release-notes line. #615's
       Decision 11 becomes one case of it: point to it, don't restate it.
   Check: `.venv/bin/pytest -n auto --transcripts=check`, `scripts/gen_compat.py --check`.
2. **Audit and ready:** `audit-gate` on the PR diff (Opus auditor: `docs/evidence.md`, `Level.DOCUMENTED`),
   `owner-findings`, then `gh pr ready`, merged with `merge-green <n> --squash --delete-branch`. The PR body says
   "Refs #617", carries the rule evidence (Decision 3's sources), and the issue closes once the reporter confirms or
   the release ships.

## Verification

- Unit: the tests above; `--transcripts=check` unchanged for every Hue action.
- Card: the Hue card shows other brands' lights with every feature, none under Labs.
- User: on v0.2.0rc1, #617's `set_attributes` and `set_scene` run with Labs off.

## Coordination

Intent: Hue's other brands' lights get every light action outside Labs, on a bridge's-one-request route to Documented
(fixes #617 for v0.2.0rc1); the rules gain "include unless harmful" and "never withdraw a released feature silently".
Touches: custom_components/deviceside/integrations/hue/**, tests/integrations/hue/**, docs/evidence.md, docs/integrations/hue/**, docs/device-compatibility.md, README.md, CLAUDE.md, CONTRIBUTING.md, docs/plans/2026-11-25-hue-other-brands.md

## Handoff

2026-11-25, step 1 done (the implementing session crashed after plan review 2; a successor finished it).

- **Done:** step 1 (A and B), three plan reviews; the last raised no must-fix.
- **Next:** Decision 9 (step 1 rework), its plan review, a re-audit, then ready again. Post nothing on #617: its reply waits for Jason's yes. The reply should also ask for a GL-C-008P's
  `product_data` on a Hue bridge, if anyone has one, as the split-off's strings are inferred (`internals.md`, Split off).
- **Open decisions:** none.
- **Branch / worktree / PR:** `wt/hue-other-brands`, `deviceside-wt/hue-other-brands`, #619 (draft).
