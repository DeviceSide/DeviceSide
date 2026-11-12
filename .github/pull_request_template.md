<!-- CONTRIBUTING.md's "Fast track" explains each section. Delete the ones that don't apply. -->

## Summary

<!-- What this changes and why, in a few lines. -->

## Scope

- Integration:
- Actions:
- Level of each new or changed item (Verified, Documented or untested; flagged `experimental` or not):

## Changes to shared code

<!-- "None", or "Depends on #N" for the pull request that carries the change outside your package. -->

## Testing evidence

<!-- For each device: model, firmware, HA version, library version, the commit you tested, the date, and what you saw. A maintainer's manual sign-off also adds a line to the bundle's `test-records/_manual.md` ([format](https://github.com/DeviceSide/DeviceSide/blob/main/docs/evidence.md#sign-off-format)). -->

## Checks

- [ ] `.venv/bin/pytest`
- [ ] `pre-commit run --all-files`
- [ ] `scripts/gen_compat.py`, `scripts/gen_features.py` and `scripts/gen_codeowners.py` regenerated

## Audit

<!-- How the code quality was audited, and every finding left open, with its severity. -->

## New integration only

- [ ] The shared touch points CONTRIBUTING's Fast track step 3 lists, `manifest.json`'s dependencies and the README's Requirements list included
- [ ] `IntegrationInfo.maintainers` names me
