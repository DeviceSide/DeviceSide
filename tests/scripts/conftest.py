import shutil
import subprocess
from pathlib import Path

import pytest


class GitRepo:
    """A throwaway repository for the tag and audit checks: commits, tags and audit records."""

    def __init__(self, path: Path):
        self.path = path
        self.git("init", "-q", "-b", "main")

    def git(self, *args: str) -> str:
        command = ["git", "-C", str(self.path), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "tag.gpgsign=false"]
        # gc.auto=0: a commit never forks a background `git gc --auto`.
        command += ["-c", "commit.gpgsign=false", "-c", "gc.auto=0", *args]
        return subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()

    def head(self) -> str:
        """HEAD's commit, read from `.git` (the repository never packs refs) instead of spawning `rev-parse`."""
        git_dir = self.path / ".git"
        head = (git_dir / "HEAD").read_text().strip()
        if head.startswith("ref: "):
            return (git_dir / head.removeprefix("ref: ")).read_text().strip()
        return head

    def commit(self, file: str = "code.py", text: str | None = None) -> str:
        path = self.path / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text if text is not None else f"{path.read_text() if path.exists() else ''}x\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", f"change {file}")
        return self.head()


_TEMPLATES: dict = {}


def from_template(repo: GitRepo, build, tmp_path_factory: pytest.TempPathFactory):
    """Fill `repo` with a history `build(GitRepo)` made once in this process, and return what `build` returned.
    A test's repository is a copy of it, instead of dozens of git spawns."""
    if build not in _TEMPLATES:
        template = GitRepo(tmp_path_factory.mktemp("template"))
        _TEMPLATES[build] = (template.path, build(template))
    path, result = _TEMPLATES[build]
    shutil.copytree(path, repo.path, dirs_exist_ok=True)
    return result


@pytest.fixture
def repo(tmp_path: Path) -> GitRepo:
    return GitRepo(tmp_path)
