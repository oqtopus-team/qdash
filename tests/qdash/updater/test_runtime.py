"""Tests for host updater runtime paths."""

from pathlib import Path

from qdash.updater.runtime import ensure_private_directory, updater_runtime_dir


def test_runtime_dir_uses_explicit_override(monkeypatch) -> None:
    monkeypatch.setenv("QDASH_UPDATER_RUNTIME_DIR", "~/custom-updater")
    monkeypatch.setenv("XDG_STATE_HOME", "/ignored")

    assert updater_runtime_dir() == (Path.home() / "custom-updater").resolve()


def test_runtime_dir_uses_xdg_state_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("QDASH_UPDATER_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    assert updater_runtime_dir() == tmp_path / "qdash" / "updater"


def test_runtime_dir_falls_back_to_user_home(monkeypatch) -> None:
    monkeypatch.delenv("QDASH_UPDATER_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)

    assert updater_runtime_dir() == (Path.home() / ".local" / "state" / "qdash" / "updater")


def test_ensure_private_directory_sets_owner_only_permissions(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"

    ensure_private_directory(runtime_dir)

    assert runtime_dir.stat().st_mode & 0o777 == 0o700
