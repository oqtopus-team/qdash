"""Exercise local scan boundaries with real Git repositories and Betterleaks.

The snapshot tests replace Betterleaks with a stub that copies the directory it is asked
to scan, so they check exactly which bytes the scanner would see with each tar on PATH.
"""

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/scan_local_leaks.sh"
needs_betterleaks = pytest.mark.skipif(
    shutil.which("betterleaks") is None, reason="requires betterleaks"
)
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


@needs_betterleaks
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


@needs_betterleaks
@pytest.mark.parametrize("path", ["source.txt", "new file.txt"])
def test_detects_working_content_and_staged_new_files(repo: Path, path: str) -> None:
    (repo / path).write_text(SECRET)
    if path != "source.txt":
        git(repo, "add", path)
    result = scan(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert SECRET not in result.stdout + result.stderr


@needs_betterleaks
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


@needs_betterleaks
def test_missing_base_fails_closed(repo: Path) -> None:
    result = scan(repo, "missing-target")
    assert result.returncode != 0
    assert "Cannot resolve LEAKS_BASE" in result.stderr


@needs_betterleaks
def test_scans_working_bytes_rather_than_staged_blobs(repo: Path) -> None:
    (repo / "source.txt").write_text(SECRET)
    git(repo, "add", "source.txt")
    (repo / "source.txt").write_text("clean again\n")
    result = scan(repo)
    assert result.returncode == 0, result.stdout + result.stderr


# Names that a per-path shell or tar invocation could split, glob, or read as options.
AWKWARD_NAMES = [
    "-leading-dash.txt",
    "--null",
    "dir with space/file name.txt",
    "nested/deeper/glob[*]?.txt",
    "back\\slash.txt",
    "new\nline.txt",
    "unicod\u00e9/\u6587\u4ef6.txt",
    " leading space.txt",
]


@needs_betterleaks
@pytest.mark.parametrize("name", AWKWARD_NAMES)
def test_detects_secrets_in_awkward_file_names(repo: Path, name: str) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SECRET)
    git(repo, "add", "--", name)
    result = scan(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert SECRET not in result.stdout + result.stderr


@needs_betterleaks
def test_detects_secrets_in_read_only_files(repo: Path) -> None:
    (repo / "source.txt").write_text(SECRET)
    (repo / "source.txt").chmod(0o400)
    result = scan(repo)
    assert result.returncode == 1, result.stdout + result.stderr


def pinned_version() -> str:
    text = (ROOT / ".devcontainer/Dockerfile").read_text()
    match = re.search(r"^ARG BETTERLEAKS_VERSION=v?(\d+\.\d+\.\d+)\s*$", text, re.MULTILINE)
    assert match, "Dockerfile must pin BETTERLEAKS_VERSION"
    return match.group(1)


def tar_implementations() -> list[str]:
    """Return one tar executable per distinct implementation found on this machine."""
    found: dict[str, str] = {}
    for candidate in [
        shutil.which("tar"),
        "/usr/bin/tar",
        shutil.which("gtar"),
        shutil.which("bsdtar"),
    ]:
        if not candidate or not Path(candidate).exists():
            continue
        version = subprocess.run(  # noqa: S603 - probing a local tar binary
            [candidate, "--version"], capture_output=True, text=True, check=False
        ).stdout
        family = "gnu" if "GNU tar" in version else "bsd" if "bsdtar" in version else version
        found.setdefault(family, candidate)
    return sorted(found.values())


@pytest.fixture(params=tar_implementations())
def stub_bin(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    """Put a chosen tar and a Betterleaks stub that copies the scanned directory on PATH."""
    bin_dir = tmp_path / "stub-bin"
    bin_dir.mkdir()
    (bin_dir / "tar").symlink_to(request.param)
    stub = bin_dir / "betterleaks"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'case "$1" in\n'
        f"  version) echo 'betterleaks {pinned_version()}' ;;\n"
        '  dir) cp -pR . "$SNAPSHOT_OUT" ;;\n'
        '  git) echo "$*" >"$SNAPSHOT_OUT.git-args" ;;\n'
        "  *) exit 2 ;;\n"
        "esac\n"
    )
    stub.chmod(0o755)
    return bin_dir


def snapshot(
    repo: Path, bin_dir: Path, tmp_path: Path
) -> tuple[subprocess.CompletedProcess[str], Path]:
    out = tmp_path / "snapshot"
    result = subprocess.run(  # noqa: S603 - execute the repository helper in a test fixture
        [BASH, str(SCRIPT)],
        cwd=repo,
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "LEAKS_BASE": "origin/develop",
            "SNAPSHOT_OUT": str(out),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    return result, out


def tree(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() or p.is_symlink()
    }


def test_snapshot_holds_exactly_the_tracked_regular_files_as_in_the_working_tree(
    repo: Path, stub_bin: Path, tmp_path: Path
) -> None:
    expected = {".betterleaks.toml": (repo / ".betterleaks.toml").read_bytes()}
    for index, name in enumerate(AWKWARD_NAMES):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        # Binary content with NUL and CR bytes must survive the copy unchanged.
        path.write_bytes(f"staged {index}\n".encode())
        git(repo, "add", "--", name)
        content = bytes(range(256)) + f"working {index}\r\n".encode()
        path.write_bytes(content)
        expected[name] = content
    (repo / "source.txt").write_text("modified, not staged\n")
    expected["source.txt"] = b"modified, not staged\n"
    (repo / "run.sh").write_text("#!/bin/sh\n")
    (repo / "run.sh").chmod(0o755)
    (repo / "private.txt").write_text("owner only\n")
    (repo / "private.txt").chmod(0o400)
    expected["run.sh"] = b"#!/bin/sh\n"
    expected["private.txt"] = b"owner only\n"

    # Tracked but excluded: a deleted file, a symlink, and a submodule directory.
    (repo / "gone.txt").write_text("deleted later\n")
    (repo / "outside.txt").write_text("untracked target\n")
    (repo / "link.txt").symlink_to(repo / "outside.txt")
    git(repo, "add", "gone.txt", "link.txt", "run.sh", "private.txt")
    (repo / "gone.txt").unlink()
    head = git(repo, "rev-parse", "HEAD")
    git(repo, "update-index", "--add", "--cacheinfo", f"160000,{head},sub")
    (repo / "sub").mkdir()
    (repo / "sub/inside.txt").write_text("submodule content\n")
    (repo / "untracked.txt").write_text("untracked\n")

    result, out = snapshot(repo, stub_bin, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert tree(out) == expected
    assert not any(p.is_symlink() for p in out.rglob("*"))
    assert os.access(out / "private.txt", os.R_OK)
    assert stat.S_IMODE((out / "run.sh").stat().st_mode) & 0o100
    # The history scan still runs over the commits outside the target branch.
    git_args = Path(f"{out}.git-args").read_text()
    assert f"--log-opts={head}..HEAD" in git_args


def test_unreadable_tracked_file_fails_the_scan(repo: Path, stub_bin: Path, tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root can read files without read permission")
    (repo / "source.txt").chmod(0)
    try:
        result, out = snapshot(repo, stub_bin, tmp_path)
    finally:
        (repo / "source.txt").chmod(0o644)
    assert result.returncode != 0
    assert not out.exists(), "the scanner must not run on a partial snapshot"
