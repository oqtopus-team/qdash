"""Tests for runtime path resolution helpers."""

from pathlib import Path

from qdash.common.config.path_resolver import resolve_calib_data_path


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
