"""Tests for runtime path resolution helpers."""

from pathlib import Path

import pytest

from qdash.common.config.path_resolver import (
    execution_calib_data_dir,
    resolve_calib_data_path,
    resolve_workflow_path,
)
from qdash.common.config.paths import CALIB_DATA_BASE


def test_execution_calib_data_dir_returns_expected_path() -> None:
    """Build the execution directory from username, date, and index."""
    resolved = execution_calib_data_dir("tester", "20250101-001")

    assert resolved == CALIB_DATA_BASE / "tester" / "20250101" / "001"


def test_execution_calib_data_dir_raises_for_missing_separator() -> None:
    """Reject execution ids that lack the required 'YYYYMMDD-NNN' separator."""
    with pytest.raises(ValueError, match="YYYYMMDD-NNN"):
        execution_calib_data_dir("tester", "20250101")


def test_resolve_calib_data_path_returns_existing_path(tmp_path: Path) -> None:
    """A path that already exists is returned unchanged."""
    figure = tmp_path / "figure.png"
    figure.write_bytes(b"png")

    assert resolve_calib_data_path(figure) == figure


def test_resolve_calib_data_path_maps_container_calib_data_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A container calib_data path is remapped onto the host CALIB_DATA_PATH."""
    local_base = tmp_path / "calib_data"
    figure = local_base / "proj-1" / "figure.png"
    figure.parent.mkdir(parents=True)
    figure.write_bytes(b"png")
    monkeypatch.setenv("CALIB_DATA_PATH", str(local_base))

    resolved = resolve_calib_data_path("/app/calib_data/proj-1/figure.png")

    assert resolved == figure


def test_resolve_calib_data_path_leaves_unmapped_missing_path(monkeypatch) -> None:
    """A missing path outside the container calib_data tree is returned unchanged."""
    monkeypatch.delenv("CALIB_DATA_PATH", raising=False)

    resolved = resolve_calib_data_path("/tmp/missing/figure.png")

    assert resolved == Path("/tmp/missing/figure.png")


def test_resolve_workflow_path_uses_container_path_when_available(tmp_path: Path) -> None:
    """resolve_workflow_path returns the container path when it exists."""
    container_path = tmp_path / "templates"
    container_path.mkdir()

    assert resolve_workflow_path(container_path, "templates") == container_path


def test_resolve_workflow_path_falls_back_to_repo_local_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """resolve_workflow_path falls back to the repo-local templates directory."""
    repo_root = Path(__file__).resolve().parents[4]
    monkeypatch.chdir(repo_root)

    resolved = resolve_workflow_path(Path("/missing/templates"), "templates")

    assert resolved == repo_root / "src/qdash/workflow/templates"
