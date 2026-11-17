"""Test-records files for the script tests, as docs/test-records.schema.json shapes them."""

import json
from pathlib import Path


def device(
    model: str = "LTA009", firmware: str | None = "1.2.3", cls: str | None = None, manufacturer: str | None = None
) -> dict:
    """A format 2 test's device."""
    return {"model": model, "manufacturer": manufacturer, "firmware": firmware, "class": cls}


def ran(domain: str, *devices: dict, result: str = "pass", group: bool = False, role: str = "light_ct") -> dict:
    """A format 2 test that ran, on its devices (a native group's: its members)."""
    test = {"id": f"t[{role}]", "domain": domain, "role": role, "result": result}
    return test | ({"group": True} if group else {}) | {"devices": list(devices or [device()])}


def skipped(role: str = "switch_plug") -> dict:
    return {"id": f"t[{role}]", "role": role, "result": "skipped", "reason": "none in the profile"}


def old_test(domain: str | None = "light", result: str = "pass", classes: list[str] | None = None) -> dict:
    """A format 1 test: a markdown Tests row, `classes` its Capability cell (None: no column)."""
    test = {"id": "t[r]", "role": "r", "result": result} | ({"domain": domain} if domain else {})
    if result == "skipped":
        test["reason"] = "none in the profile"
    return test | ({"classes": classes} if classes is not None else {})


def old_device(model: str = "LTA009", firmware: str = "1.2.3") -> dict:
    """A format 1 record's device."""
    return {"model": model, "firmware": firmware}


def old_group(name: str = "Zone", firmware: str | None = None) -> dict:
    return {"name": name, "firmware": firmware, "group": True}


def envelope(integration: str, action: str, result: str, commit: str, options=()) -> dict:
    """A record's fields bar its tests; `options` as its file name gives them (none: absent)."""
    return {
        "integration": integration,
        "action": action,
        **({"options": sorted(options)} if options else {}),
        "result": result,
        "date": "2026-11-14",
        "source": {"kind": "rig", "commit": commit[:7]},
    }


BLOB = "ab" * 20  # a transcript's blob id, for a file no gate reads


def bound(*actions: str, blob: str = BLOB) -> dict[str, str]:
    """A manual row's `calls`: each action bound to the blob."""
    return dict.fromkeys(actions, blob)


def record_v3(
    integration: str,
    action: str,
    tests: list[dict],
    *,
    result: str = "pass",
    commit: str = "1a2b3c4",
    calls: str = BLOB,
    options=(),
) -> dict:
    """A record as the rig writes it: bound to the call transcript it tested."""
    found = {"format": 3, **envelope(integration, action, result, commit, options)}
    return found | {"calls": calls, "home_assistant": "2026.10.4", "tests": tests}


def record_v2(
    integration: str,
    action: str,
    tests: list[dict],
    *,
    result: str = "pass",
    commit: str = "1a2b3c4",
    package=None,
    options=(),
) -> dict:
    """A record bound to its package tree, from before transcripts: it credits, and signs off nothing."""
    found = {"format": 2, **envelope(integration, action, result, commit, options)}
    return found | {"package": package or "0123456789ab", "home_assistant": "2026.10.4", "tests": tests}


def record_v1(
    integration: str,
    action: str,
    *,
    result: str = "pass",
    devices: list[dict] | None = None,
    tests: list[dict] | None = None,
    commit: str = "1a2b3c4",
    options=(),
) -> dict:
    found = {"format": 1, **envelope(integration, action, result, commit, options), "home_assistant": "2026.10.4"}
    return found | {"devices": [old_device()] if devices is None else devices, "tests": tests or [old_test()]}


def signoff(
    commit: str = "1a2b3c4",
    tester: str = "a",
    devices=(("LCA001", None),),
    calls=None,
    group: bool = False,
    passed=None,
) -> dict:
    """A `_manual.json` row: format 3, `calls` each action's transcript blob (default: turn_on_for's, `BLOB`); or, with
    `passed`, format 2's, naming the actions alone. `group` for a native group's members."""
    row = {"date": "2026-11-12", "commit": commit[:7], "tester": tester} | ({"group": True} if group else {})
    row["devices"] = [{"model": m, "manufacturer": None, "class": c} for m, c in devices]
    if passed is not None:
        return row | {"passed": list(passed)}
    return row | {"calls": dict(calls) if calls is not None else {"turn_on_for": BLOB}}


def manual(integration: str, *rows: dict) -> dict:
    """A `_manual.json`, in format 2 when its rows are (`passed`), else 3."""
    format_ = 2 if rows and all("passed" in row for row in rows) else 3
    return {"format": format_, "integration": integration, "signoffs": list(rows)}


def text(data: dict) -> str:
    return json.dumps(data, indent=2) + "\n"


def write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text(data))
    return path
