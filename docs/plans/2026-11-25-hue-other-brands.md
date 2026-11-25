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

1. **Documented on Hue's `other` lights:** `set_attributes`, `set_scene` and `get_attributes`, with the Labs option
   off. A scene that writes an `other` light, and a room or zone holding one, run on these three actions.
2. **Labs on `other`:** `raise_brightness`, `lower_brightness`, `raise_saturation`, `lower_saturation` and `stop`,
   admitted on the sourced call: the request is the one Hue Smooth Dimming sent every brand. They stay out of
   Documented because the bridge runs the fade, and other brands are known to fade differently (index.md, Other
   brands).
3. **The route, an amendment to `docs/evidence.md`** (Unknown is flagged, and Levels), beside #615's standard
   converter's call: *a bridge's one request*. Where the integration sends the bridge the same request for every light
   and the bridge picks the Zigbee call (Hue's CLIP v2), an action whose failure doesn't harm
   (`Action.failure_harms`) and whose known failures show at once is Documented on the default class on the request's
   usage: Hue Smooth Dimming sent the identical `set_state` to every brand, with this report's pass and no reported
   departure. A read that sends nothing (`get_attributes` reads the event stream) qualifies outright. Split-offs follow
   the contrary-evidence rules unchanged: a failing report splits off the identity (manufacturer and model), citing
   it. A light that comes on when written while off is that kind of failure: visible at once, one tap fixes it. The
   implementer words the amendment; Jason reviews it in the PR. It is binding-rule text: Opus auditor.
4. **Rides v0.2.0rc1.** Levels and classes change, calls don't, so no Hue rig rerun (tenet 9);
   `--transcripts=check` proves no call changed.
5. **The Hue Smooth Dimming migration repair is unchanged.** The coverage view (#611) shows what stays behind Labs.
6. **The reply on #617** is posted once Jason approves its text. It asks for the lights' Manufacturer and Model;
   if he answers, they go in a `_manual.json` row crediting his report (`docs/evidence.md`, the Labs flag), as a
   follow-up, not a gate.

## Steps

1. **Build** (opus implementer: binding-rule text and public docs; Opus `plan-reviewer`). `hue/classes.py`: `LEVELS`
   per action, or one per group of actions, keeping one home for the levels; the docstrings and comments that say
   `other` gets nothing. Each adapter's scope (`set_attributes.py`, `set_scene.py`, `get_attributes.py`,
   `raise_*`/`lower_*`, `stop.py`, `fade.py` where it holds levels). `docs/evidence.md` per Decision 3, with a Hue
   example beside #615's Z2M one. `docs/integrations/hue/index.md` `### Other brands`: what they get now and why, in
   Hue's page shape, no level stated. `internals.md`, Device classes: the hue_dimmer call comparison, with links to
   its source at a pinned commit. `devices.yaml` card phrase if needed; regenerate with `scripts/gen_compat.py`
   (README, `docs/device-compatibility.md`). The refusal text for a fade on `other` with Labs off then names Labs.
   Tests (`tests/integrations/hue/`): `other` at Documented on the three actions and Labs on the five, Labs off and
   on; a scene with an `other` light runs `set_scene`; a room mixing `hue` and `other` lights runs
   `set_attributes` as a room, and falls back on a fade with Labs off.
   Check: `.venv/bin/pytest -n auto --transcripts=check`, `scripts/gen_compat.py --check`.
2. **Audit and ready:** `audit-gate` on the PR diff (Opus auditor: `docs/evidence.md`, `Level.DOCUMENTED`),
   `owner-findings`, then `gh pr ready`, merged with `merge-green <n> --squash --delete-branch`. The PR body says
   "Refs #617", carries the rule evidence (Decision 3's sources), and the issue closes once the reporter confirms or
   the release ships.

## Verification

- Unit: the tests above; `--transcripts=check` unchanged for every Hue action.
- Card: the Hue card shows other brands' lights with set without turning on and get attributes outside Labs, and
  smooth dimming and saturation under Labs.
- User: on v0.2.0rc1, #617's `set_attributes` and `set_scene` run with Labs off.

## Coordination

Intent: Hue's other brands' lights get set_attributes, set_scene and get_attributes outside Labs, and dimming, saturation
and stop in Labs, on a bridge's-one-request route to Documented; fixes #617 for v0.2.0rc1.
Touches: custom_components/deviceside/integrations/hue/**, tests/integrations/hue/**, docs/evidence.md, docs/integrations/hue/**, docs/device-compatibility.md, README.md, docs/plans/2026-11-25-hue-other-brands.md
