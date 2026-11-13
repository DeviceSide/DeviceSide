---
name: release
description: Cut a DeviceSide release candidate or release, or fix one on a release/vX.Y.Z branch. Use when the user asks to cut, tag, ship or hotfix an RC or a release, or asks what the cut workflows check.
---

Work lands on `main`. RCs are cut from it, and `cut-release` tags the version's latest RC, so what ships is what
soaked while `main` moves on. The cut workflows enforce the tag rules, green CI, the RC audit (its record comes from
`/rc-audit`) and, in `cut-release`, the release gate (`docs/evidence.md`, which says when sign-offs must land; until
step 4 lands, the old checks its Transition lists); see their headers. The steps they don't check:

1. **Each RC:** install it through HACS (the rig deploys a checkout, not the release); it loads and the log is clean.
2. Dispatch `cut-release` from `main` with `vX.Y.Z`.
3. Set `manifest.json` on `main` to the next version.

To fix an RC or a release without what `main` has gained since, cut `release/vX.Y.Z` from its tag, land the fix
there, cut the next RC from it, and merge the branch back into `main`.
