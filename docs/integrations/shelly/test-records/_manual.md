# Shelly · manual sign-offs

| Date | Commit | Tester | Devices | Passed |
|---|---|---|---|---|
| 2026-11-13 | `c868be9` | @jasonmx | `S3BL-C010007AEU` | `clear_auto_off`, `clear_auto_on`, `get_attributes`, `lower_brightness`, `raise_brightness`, `set_attributes`, `set_auto_off`, `set_auto_on`, `stop`, `turn_off_for`, `turn_on_for` |

Why manual, on a rig-covered integration: the whole house run's records cite `5aa4aa4`, a commit that isn't an
ancestor of the package's last change on main (`3f41517`), though `git diff 5aa4aa4 c868be9` over the Shelly package
is empty: the package the run exercised is the one released. The gate's ancestor test fails it, not the run. A fix
for that gate behavior is in flight; this row stands in until it lands.
