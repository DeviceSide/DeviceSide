---
name: release
description: Cut a DeviceSide release candidate or release, or fix one on a release/vX.Y.Z branch. Use when the user asks to cut, tag, ship or hotfix an RC or a release, or asks what the cut workflows check.
---

Work lands on `main`. RCs are cut from it, and `cut-release` tags the version's latest RC, so what ships is what
soaked while `main` moves on. The cut workflows enforce the tag rules, green CI, the RC audit (its record comes from
`/rc-audit`) and, in `cut-release`, the release gate (`check_release.py --signoffs`; `docs/evidence.md` says when
sign-offs must land); see their headers. The steps they don't check:

1. **Each RC from `main`, before `/rc-audit`:** bump the standard lights table to ZHC's latest release
   (`gh release list -R Koenkk/zigbee-herdsman-converters -L 1`): `.venv/bin/python scripts/zhc_table.py --pin <it>`,
   open the bump PR with the proposal it prints as the body, review its departures there (`docs/evidence.md`,
   Documented), and merge. No newer release, or a bump you hold back: write `ZHC bump skipped: <reason>` in the audit
   record instead; `check_audit.py` refuses an RC with neither. No bump lands between an RC and its release.
2. **Each RC:** install it through HACS (the rig deploys a checkout, not the release); it loads and the log is clean.
   Then review `docs/deferred.md`: list the entries whose Revisit when condition has been met, and delete, by PR,
   those nobody defends.
3. Dispatch `cut-release` from `main` with `vX.Y.Z`.
4. Set `manifest.json` on `main` to the next version.

To fix an RC or a release without what `main` has gained since, cut `release/vX.Y.Z` from its tag, land the fix
there, cut the next RC from it, and merge the branch back into `main`.
