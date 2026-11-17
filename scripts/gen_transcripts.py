"""Regenerate every call transcript, tests/integrations/<x>/calls/<action>.json, by running the whole suite with
`--transcripts=write` (tests/transcripts.py). Commit the result: CI checks it, and scripts/signoff.py binds to it."""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    """Extra arguments go to pytest (`-q`); the recorder refuses a narrowed run."""
    extra = sys.argv[1:] if argv is None else argv
    command = [sys.executable, "-m", "pytest", "-n", "auto", "--transcripts=write", *extra]
    return subprocess.run(command, cwd=REPO).returncode


if __name__ == "__main__":
    sys.exit(main())
