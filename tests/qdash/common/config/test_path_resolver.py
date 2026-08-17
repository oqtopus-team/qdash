"""Tests for runtime path resolution helpers."""

from pathlib import Path

import pytest

from qdash.common.config.path_resolver import execution_calib_data_dir, resolve_calib_data_path
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
    figure = tmp_path / "figure.png"
    figure.write_bytes(b"png")

    assert resolve_calib_data_path(figure) == figure


def test_resolve_calib_data_path_maps_container_calib_data_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    local_base = tmp_path / "calib_data"
    figure = local_base / "proj-1" / "figure.png"
    figure.parent.mkdir(parents=True)
    figure.write_bytes(b"png")
    monkeypatch.setenv("CALIB_DATA_PATH", str(local_base))

    resolved = resolve_calib_data_path("/app/calib_data/proj-1/figure.png")

    assert resolved == figure


def test_resolve_calib_data_path_leaves_unmapped_missing_path(monkeypatch) -> None:
    monkeypatch.delenv("CALIB_DATA_PATH", raising=False)

    resolved = resolve_calib_data_path("/tmp/missing/figure.png")

    assert resolved == Path("/tmp/missing/figure.png")
