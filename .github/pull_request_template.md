<!-- CONTRIBUTING.md's "Fast track" explains each section. Delete the ones that don't apply. -->

## Summary

<!-- What this changes and why, in a few lines. -->

## Scope

- Integration:
- Actions:
- Level of each new or changed item:

## Changes to shared code

<!-- "None", or "Depends on #N" for the pull request that carries the change outside your package. -->

## Testing evidence

<!-- For each device: model, firmware, HA version, library version, the commit you tested, the date, and what you saw. -->

## Records staled

<!-- Adapters that `scripts/check_release.py --records` now lists, or "None". -->

## Checks

- [ ] `.venv/bin/pytest`
- [ ] `pre-commit run --all-files`
- [ ] `scripts/gen_compat.py`, `scripts/gen_features.py` and `scripts/gen_codeowners.py` regenerated

## Audit

<!-- How the code quality was audited, and every finding left open, with its severity. -->

## New integration only

- [ ] The shared touch points CONTRIBUTING's Fast track step 3 lists, `manifest.json`'s dependencies and the README's Requirements list included
- [ ] `IntegrationInfo.maintainers` names me
