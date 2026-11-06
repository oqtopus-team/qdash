"""Exercise the Betterleaks version guard with a fake scanner on PATH."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "scripts/check_betterleaks_version.sh"
GIT = shutil.which("git") or "/usr/bin/git"
BASH = shutil.which("bash") or "/bin/bash"
WRONG_VERSION = "0.0.1"


def pinned_version() -> str:
    text = (ROOT / ".devcontainer/Dockerfile").read_text()
    match = re.search(r"^ARG BETTERLEAKS_VERSION=v?(\d+\.\d+\.\d+)\s*$", text, re.MULTILINE)
    assert match, "Dockerfile must pin BETTERLEAKS_VERSION"
    return match.group(1)


def path_without_betterleaks() -> str:
    dirs = os.environ.get("PATH", "").split(os.pathsep)
    return os.pathsep.join(d for d in dirs if d and not (Path(d) / "betterleaks").exists())


@pytest.fixture
def fake_bin(tmp_path: Path) -> Path:
    """Install a fake betterleaks that logs each call and prints $FAKE_VERSION_OUTPUT."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "betterleaks"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        'echo "$*" >>"$FAKE_BETTERLEAKS_LOG"\n'
        'printf "%s\\n" "$FAKE_VERSION_OUTPUT"\n'
        'exit "${FAKE_VERSION_STATUS:-0}"\n'
    )
    fake.chmod(0o755)
    return bin_dir


def run(
    script: Path,
    tmp_path: Path,
    bin_dir: Path | None,
    output: str = "",
    status: int = 0,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    path = path_without_betterleaks()
    if bin_dir is not None:
        path = f"{bin_dir}{os.pathsep}{path}"
    env = {
        **os.environ,
        "PATH": path,
        "FAKE_BETTERLEAKS_LOG": str(tmp_path / "calls.log"),
        "FAKE_VERSION_OUTPUT": output,
        "FAKE_VERSION_STATUS": str(status),
        "LEAKS_BASE": "HEAD",
    }
    return subprocess.run(  # noqa: S603 - execute the repository helper in a test fixture
        [BASH, str(script)],
        cwd=cwd or ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


@pytest.mark.parametrize("template", ["{v}", "betterleaks version {v}", "v{v}"])
def test_accepts_pinned_version(tmp_path: Path, fake_bin: Path, template: str) -> None:
    result = run(GUARD, tmp_path, fake_bin, template.format(v=pinned_version()))
    assert result.returncode == 0, result.stderr
    assert calls(tmp_path) == ["version"]


def test_rejects_other_version_with_expected_actual_and_fix(tmp_path: Path, fake_bin: Path) -> None:
    result = run(GUARD, tmp_path, fake_bin, f"betterleaks version {WRONG_VERSION}")
    assert result.returncode == 1
    assert f"expected betterleaks {pinned_version()}" in result.stderr
    assert f"actual: {WRONG_VERSION}" in result.stderr
    assert "nix develop -c task check" in result.stderr


def test_rejects_missing_scanner(tmp_path: Path) -> None:
    result = run(GUARD, tmp_path, None)
    assert result.returncode == 1
    assert "actual: not installed" in result.stderr
    assert "nix develop -c task check" in result.stderr


@pytest.mark.parametrize(("output", "status"), [("dev", 0), (pinned_version(), 2)])
def test_rejects_unreadable_version(
    tmp_path: Path, fake_bin: Path, output: str, status: int
) -> None:
    result = run(GUARD, tmp_path, fake_bin, output, status)
    assert result.returncode == 1
    assert f"expected betterleaks {pinned_version()}" in result.stderr
    assert "nix develop -c task check" in result.stderr


def test_rejects_dockerfile_without_pinned_version(tmp_path: Path, fake_bin: Path) -> None:
    tree = tmp_path / "tree"
    (tree / "scripts").mkdir(parents=True)
    (tree / ".devcontainer").mkdir()
    (tree / ".devcontainer/Dockerfile").write_text("ARG BETTERLEAKS_VERSION=latest\n")
    guard = tree / "scripts/check_betterleaks_version.sh"
    shutil.copy(GUARD, guard)
    result = run(guard, tmp_path, fake_bin, pinned_version())
    assert result.returncode == 1
    assert "cannot read ARG BETTERLEAKS_VERSION" in result.stderr
    assert calls(tmp_path) == []


@pytest.mark.parametrize("name", ["scan_staged_leaks.sh", "scan_local_leaks.sh"])
def test_scans_stop_before_scanning_on_wrong_version(
    tmp_path: Path, fake_bin: Path, name: str
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.check_call([GIT, "init", "-q", str(repo)])  # noqa: S603
    (repo / "staged.txt").write_text("content\n")
    subprocess.check_call([GIT, "-C", str(repo), "add", "staged.txt"])  # noqa: S603
    result = run(ROOT / "scripts" / name, tmp_path, fake_bin, WRONG_VERSION, cwd=repo)
    assert result.returncode == 1
    assert f"actual: {WRONG_VERSION}" in result.stderr
    # Only the version probe ran; no dir or git scan was attempted.
    assert calls(tmp_path) == ["version"]
