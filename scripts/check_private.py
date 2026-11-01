#!/usr/bin/env python3
"""Refuse a commit whose files or message name the household's private details.

The repo is public, so the blocklist cannot live in it. Terms come from the gitignored files that already hold them:
every rig profile's entity IDs and roaming bulbs' IEEEs, .env.rig's HA host and token, and .private-terms (one term
per line, for names, hostnames and anything else), all read from the main checkout so a linked worktree is checked
too.
Where none of those exist (CI, a contributor's clone) the check passes.

Usage: scripts/check_private.py FILE ...   (pre-commit passes staged files, or the message file at commit-msg)
"""

import sys
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tests.rig.profile import (  # noqa: E402
    ENV_FILE,
    LEGACY_INVENTORY,
    MAIN_CHECKOUT,
    Profile,
    colon_ieee,
    load_env,
    profile_paths,
)

PRIVATE_TERMS = MAIN_CHECKOUT / ".private-terms"
# Hosts the docs and examples name on purpose.
GENERIC_HOSTS = frozenset({"homeassistant.local", "localhost", "127.0.0.1"})


def private_terms(
    profiles: Iterable[Path] | None = None, env_file: Path = ENV_FILE, terms_file: Path = PRIVATE_TERMS
) -> dict[str, str]:
    """Lowercased term -> label to report. Secrets are reported by label, never echoed. `profiles` defaults to every
    profile, and the inventory.yaml they replaced while it is still there."""
    terms: dict[str, str] = {}
    if profiles is None:
        profiles = [*profile_paths(), LEGACY_INVENTORY]
    for path in profiles:
        if path.exists():
            terms.update((entity_id.lower(), entity_id) for entity_id in profile_entities(Profile.load(path)))
    if env_file.exists():
        env = load_env(env_file)
        if (host := urlparse(env.get("HA_URL", "")).hostname) and host not in GENERIC_HOSTS:
            terms[host.lower()] = host
        if token := env.get("HA_TOKEN"):
            terms[token.lower()] = "HA_TOKEN from .env.rig"
    if terms_file.exists():
        for line in terms_file.read_text().splitlines():
            if (line := line.strip()) and not line.startswith("#"):
                terms[line.lower()] = line
    return terms


def profile_entities(profile: Profile) -> set[str]:
    """Every entity ID a profile names (its entities, their groups' members and supplies, its pause list), and each
    roaming bulb's IEEE: as bare hex, which `0x`-prefixed spellings contain, and with colons."""
    named = set(profile.pause)
    for entities in profile.integrations.values():
        for entity in entities:
            named |= {entity.entity_id, *entity.members, *filter(None, [entity.powered_by])}
    for bulb in profile.roam:
        named |= {bulb.entity_id, bulb.ieee, colon_ieee(bulb.ieee)}
    return named


def find(paths: list[Path], terms: dict[str, str]) -> list[str]:
    hits = []
    for path in paths:
        try:
            lines = path.read_text().splitlines()
        except UnicodeDecodeError, FileNotFoundError:
            continue
        for number, line in enumerate(lines, 1):
            lowered = line.lower()
            hits.extend(f"{path}:{number}: {label}" for term, label in terms.items() if term in lowered)
    return hits


def main(argv: list[str]) -> int:
    try:
        terms = private_terms()
    except ValueError as err:
        print(f"Can't read the household's terms, so nothing is checked: {err}")
        return 1
    if not terms:
        return 0
    if hits := find([Path(arg) for arg in argv], terms):
        print("Private details in a public repo:", *hits, sep="\n  ")
        print("Remove them, or move them to a gitignored file (CLAUDE.local.md, tests/rig/profiles/, .env.rig).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
