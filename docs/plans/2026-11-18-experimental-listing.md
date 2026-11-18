# Experimental listing: run on passing kin, fold trials on the cards

Date: 2026-11-18. Status: agreed with the repo maintainer; not started.

## Context

#496 raised the bar for a class to go behind the Experimental flag, which shortened the README, but it also stopped
devices from running at all. Users who own one of the hundreds of other TS011F plug variants can't try Tuya's
countdown even with Experimental features on, although that call passes on four maker strings. The concern behind #496
was the README: when more than half of the card lines were untried classes, readers took DeviceSide to be ready for all
of them.

This plan keeps two bars apart:

- **Run:** a class goes behind the flag on a pass of the same call on its kin.
- **Claim:** the README cards keep Experimental lines to about a quarter of all lines, which a generated fold and a
  check maintain.

Today 8 of the 23 card lines (35%) are Experimental-only.

## Decisions (settled 2026-11-18)

1. **No new level or tier.** Experimental stays the lowest level. A hidden tier (`Level.UNTRIED`, left off the
   cards) is revisited only if the fold below can't hold the cap.
2. **Admission bar, passing kin:** a class goes on trial when the exact call it would get passes on another class of
   the same firmware family. Example: Tuya's countdown passes on four converter-A TS011F maker strings, so the rest of
   `tuya_countdown` is on trial. This adds to the existing bar (a pass on the class, or research predicting most of it
   accepts the call). The listing bar for the cards is unchanged.
3. **Harm:** on an action whose failure harms, the Experimental opt-in is the user's consent. A class on trial there
   runs with the flag on. An identity reported harmed is split off as `NotBuilt`, which "split off the exception"
   already allows once a pass shows the rest works. `class_unknown` still refuses targets that aren't placed yet.
4. **The cap:** Experimental lines are at most 25% of all card lines, counted in aggregate across every README card.
   A line is Experimental when it shows 🔍 and no 🟢 or 🟡 (🔴 may sit beside 🔍). Child lines count. A mixed line
   (🟡 … · 🔍 …) doesn't count, as it makes a real claim. `gen_compat.py` fails when the share is over 25%, in
   `--check` and in a plain run, naming the share and the Experimental lines. The number is directional (the failure
   it prevents is the earlier list of more than 50%), so it is a named constant with that comment.
5. **The fold:** on each card, two or more top-level Experimental lines (Decision 4's definition) fold into one last
   line:
   `🔍 on trial: [IKEA lights] (turn on with timer, smooth dimming); [IKEA LED2005R5 …], [other brands' lights] (smooth dimming)`.
   Lines with the same features share one parenthesis, and a 🔴 part stays inside its parenthesis after ` · `. Child
   lines under a variants parent (the TS011F section) never fold. A single Experimental line stays as it is.
   Expected result: 18 lines, 4 of them Experimental (22%).
6. **Repair notice when a trial first runs:** after v0.1.0. TODO item, and issue DeviceSide/DeviceSide#515.
7. **ZHA is untouched:** Tuya's countdown isn't built on ZHA, so its `tuya_countdown` has no passing kin and keeps
   its `NotBuilt`.

## Steps

### Step 1: the rule (docs only)

- `docs/evidence.md`, On trial: add the passing-kin admission (Decision 2) and the harm consent (Decision 3), in one
  place. Update the examples that now read wrong: Contrary evidence's `_TZ3000_dg7fdg92` ("keeps `tuya_countdown`'s
  level, on trial") and the coverage-check example's "the rest of `tuya_countdown` is not built yet, with an entry"
  ("is on trial").
- `docs/evidence.md`, The experimental flag: one sentence on the cap and the fold (Decision 4), pointing to
  `scripts/gen_compat.py`.
- Check `docs/design.md`'s glossary for "on trial" or "Experimental" wording that contradicts the change.
- Implementer: `opus` (binding rule text). Reviewer: `opus`.

### Step 2: TS011F on trial on Zigbee2MQTT

- `integrations/zigbee2mqtt/families/tuya/__init__.py`, `_TURN_ON_FOR`: `capabilities` becomes
  `verified(*VERIFIED_COUNTDOWNS, domains=(SWITCH,)) | experimental(TUYA_COUNTDOWN, domains=(SWITCH,))`, and
  `own_calls` becomes `dict.fromkeys(COUNTDOWNS, COUNTDOWN)`. Update the comments that say the rest is left out.
- `integrations/zigbee2mqtt/refusals.py`: remove the `TUYA_COUNTDOWN` `NotBuilt` entry from `turn_on_for`, and
  update the block comment. `TUYA_COUNTDOWN_HARMED`, `TUYA_TS011F` and the rest stay, so `class_unknown` still applies.
  `get_attributes`' `NoKnownMethod` on `COUNTDOWNS` stays.
- Tests: `tests/integrations/zigbee2mqtt/families/tuya/test_countdown.py:119` (asserts `tuya_countdown` is absent),
  `tests/integrations/zigbee2mqtt/test_refusals.py`, `test_classes.py:163`. Add one dispatch test: an unrecorded
  string runs the countdown with the flag on, and is refused `experimental_off` with it off. Run the transcripts.
- Docs: `docs/integrations/zigbee2mqtt/index.md` Tuya and TS011F sections. The one-line acknowledgment there: "other
  TS011F plugs with a countdown setting are on trial: turn on Experimental features to try one, and report whether it
  works". Also `docs/device-compatibility.md`, sections "Zigbee plugs and switches" and "Tuya TS011F", and
  `devices.yaml` if the phrase "other makers with a countdown setting" needs to change. Regenerate.
- Implementer: `sonnet` (the code shape is settled and tests catch a wrong placement). Reviewer: `opus` (a harm
  refusal is lifted).

### Step 3: fold and cap in `gen_compat.py`

- In `card()` (`scripts/gen_compat.py:1185`), after `ordered(...)`: take the top-level lines whose `shape` has
  `experimental` and neither `works` nor `should` (and no `note`), and when there are two or more, replace them with
  one folded line as in Decision 5. Reuse `Line.name` and the `OUTCOMES` icons. Group by `shape` so lines with the
  same features share one parenthesis.
- In `cards()`/`main()`: count lines (children included) and Experimental lines across every card. Fail over
  `EXPERIMENTAL_SHARE_MAX = 0.25`, beside `check_sections`.
- Module docstring: a few lines on the fold and the cap, citing `docs/evidence.md`.
- Tests in `tests/scripts/test_gen_compat.py`: fold (two lines fold; one doesn't; a 🔴 part stays inside its
  parenthesis; children don't fold), and the cap (fails at 26%, passes at 25%). Regenerate the README.
- Implementer: `sonnet`. Reviewer: `opus` (README copy).

## Checks

- `.venv/bin/pytest -n auto --transcripts=check`
- `pre-commit run --all-files`
- `python scripts/gen_compat.py --check`, and read the README cards: Zigbee2MQTT, ZHA and Control4 each show one
  "🔍 on trial" line; the TS011F "other makers with a countdown setting" child reads
  "🔍 turn on with timer · 🔴 get attributes"; the totals match Decision 5.
- PR audit: `/audit-code` with an Opus auditor (binding-rule surface: `docs/evidence.md`), then `owner-findings`.

## Coordination

Intent: Experimental admits a class on a pass of the same call on its kin; the README cards fold Experimental-only
lines and cap them at 25%. TS011F countdown plugs without a record go on trial on Zigbee2MQTT.
Touches: docs/evidence.md, docs/design.md, custom_components/deviceside/integrations/zigbee2mqtt/families/tuya/__init__.py,
custom_components/deviceside/integrations/zigbee2mqtt/refusals.py, tests/integrations/zigbee2mqtt/**,
docs/integrations/zigbee2mqtt/**, docs/device-compatibility.md, scripts/gen_compat.py, tests/scripts/test_gen_compat.py,
README.md, TODO.md
