"""Exercise local scan boundaries with real Git repositories and Betterleaks."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/scan_local_leaks.sh"
pytestmark = pytest.mark.skipif(shutil.which("betterleaks") is None, reason="requires betterleaks")
SECRET = "qdash_fixture_" + "x" * 24
GIT = shutil.which("git") or "/usr/bin/git"
BASH = shutil.which("bash") or "/bin/bash"


def git(repo: Path, *args: str) -> str:
    # Arguments are controlled by these tests and repositories live in tmp_path.
    return subprocess.check_output([GIT, "-C", str(repo), *args], text=True).strip()  # noqa: S603


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-b", "develop")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "core.hooksPath", "/dev/null")
    (tmp_path / ".betterleaks.toml").write_text(
        '[[rules]]\nid = "fixture"\ndescription = "Test marker"\nregex = "qdash_fixture_[x]{24}"\n'
    )
    (tmp_path / "source.txt").write_text("clean\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "base")
    git(tmp_path, "update-ref", "refs/remotes/origin/develop", "HEAD")
    return tmp_path


def scan(repo: Path, base: str = "origin/develop") -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - execute the repository helper in a test fixture
        [BASH, str(SCRIPT)],
        cwd=repo,
        env={**os.environ, "LEAKS_BASE": base},
        capture_output=True,
        text=True,
        check=False,
    )


def test_excludes_other_branches_and_untracked_files(repo: Path) -> None:
    git(repo, "checkout", "-b", "unrelated")
    (repo / "other.txt").write_text(SECRET)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "unrelated fixture")
    git(repo, "checkout", "develop")
    (repo / "untracked.txt").write_text(SECRET)
    (repo / "link.txt").symlink_to(repo / "untracked.txt")
    git(repo, "add", "link.txt")
    result = scan(repo)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("path", ["source.txt", "new file.txt"])
def test_detects_working_content_and_staged_new_files(repo: Path, path: str) -> None:
    (repo / path).write_text(SECRET)
    if path != "source.txt":
        git(repo, "add", path)
    result = scan(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert SECRET not in result.stdout + result.stderr


def test_detects_secret_removed_in_later_commit(repo: Path) -> None:
    (repo / "source.txt").write_text(SECRET)
    git(repo, "commit", "-am", "add fixture")
    (repo / "source.txt").write_text("clean\n")
    git(repo, "commit", "-am", "remove fixture")
    result = scan(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    # Once these commits are in the chosen target, they are outside the scan range.
    result = scan(repo, "HEAD")
    assert result.returncode == 0, result.stdout + result.stderr


def test_missing_base_fails_closed(repo: Path) -> None:
    result = scan(repo, "missing-target")
    assert result.returncode != 0
    assert "Cannot resolve LEAKS_BASE" in result.stderr
