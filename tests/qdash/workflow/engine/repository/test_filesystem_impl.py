"""Tests for FilesystemCalibDataSaver."""

import tempfile
from pathlib import Path

import numpy as np
import plotly.graph_objs as go
import pytest
from qdash.repository.filesystem import FilesystemCalibDataSaver


class TestFilesystemCalibDataSaver:
    """Test FilesystemCalibDataSaver."""

    @pytest.fixture
    def saver(self):
        """Create a temporary saver."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield FilesystemCalibDataSaver(tmpdir)

    def test_save_figures_creates_png_and_json(self, saver):
        """Test save_figures creates both PNG and JSON files."""
        fig = go.Figure(data=[go.Scatter(x=[1, 2, 3], y=[4, 5, 6])])

        png_paths, json_paths = saver.save_figures([fig], "CheckRabi", "qubit", "0")

        assert len(png_paths) == 1
        assert len(json_paths) == 1
        assert Path(png_paths[0]).exists()
        assert Path(json_paths[0]).exists()
        assert "CheckRabi" in png_paths[0]
        assert "0" in png_paths[0]

    def test_save_figures_handles_multiple_figures(self, saver):
        """Test save_figures handles multiple figures."""
        figs = [
            go.Figure(data=[go.Scatter(x=[1, 2], y=[3, 4])]),
            go.Figure(data=[go.Scatter(x=[5, 6], y=[7, 8])]),
        ]

        png_paths, json_paths = saver.save_figures(figs, "CheckT1", "qubit", "1")

        assert len(png_paths) == 2
        assert len(json_paths) == 2

    def test_save_figures_empty_list(self, saver):
        """Test save_figures with empty list returns empty lists."""
        png_paths, json_paths = saver.save_figures([], "Task", "qubit", "0")

        assert png_paths == []
        assert json_paths == []

    def test_save_raw_data_creates_csv(self, saver):
        """Test save_raw_data creates CSV files."""
        data = [np.array([1.0, 2.0, 3.0])]

        paths = saver.save_raw_data(data, "CheckRabi", "qubit", "0")

        assert len(paths) == 1
        assert Path(paths[0]).exists()
        assert paths[0].endswith(".csv")

        # Verify content
        loaded = np.loadtxt(paths[0], delimiter=",")
        np.testing.assert_array_almost_equal(loaded, data[0])

    def test_save_raw_data_handles_complex_arrays(self, saver):
        """Test save_raw_data handles complex arrays correctly."""
        complex_data = [np.array([1 + 2j, 3 + 4j, 5 + 6j])]

        paths = saver.save_raw_data(complex_data, "CheckRabi", "qubit", "0")

        assert len(paths) == 1
        loaded = np.loadtxt(paths[0], delimiter=",")

        # Should have two columns: real, imag
        assert loaded.shape == (3, 2)
        np.testing.assert_array_almost_equal(loaded[:, 0], [1.0, 3.0, 5.0])
        np.testing.assert_array_almost_equal(loaded[:, 1], [2.0, 4.0, 6.0])

    def test_save_raw_data_empty_list(self, saver):
        """Test save_raw_data with empty list returns empty list."""
        paths = saver.save_raw_data([], "Task", "qubit", "0")

        assert paths == []

    def test_save_task_json(self, saver):
        """Test save_task_json creates JSON file."""
        task_data = {
            "name": "CheckRabi",
            "status": "completed",
            "parameters": {"frequency": 5.0},
        }

        path = saver.save_task_json("task-123", task_data)

        assert Path(path).exists()
        assert path.endswith(".json")

        # Verify content
        import json

        with open(path) as f:
            loaded = json.load(f)
        assert loaded["name"] == "CheckRabi"

    def test_resolve_conflict_creates_unique_filename(self):
        """Test _resolve_conflict appends counter for existing files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            saver = FilesystemCalibDataSaver(tmpdir)

            # Create existing files
            existing1 = Path(tmpdir) / "test.png"
            existing1.touch()

            existing2 = Path(tmpdir) / "test_1.png"
            existing2.touch()

            # Should return test_2.png
            result = saver._resolve_conflict(Path(tmpdir) / "test.png")

            assert "test_2.png" in str(result)

    def test_build_filename_qubit_task(self):
        """Test _build_filename for qubit tasks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            saver = FilesystemCalibDataSaver(tmpdir)

            filename = saver._build_filename("CheckRabi", "qubit", "0", "", "png", 0)

            assert filename == "CheckRabi_0_0.png"

    def test_build_filename_global_task(self):
        """Test _build_filename for global tasks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            saver = FilesystemCalibDataSaver(tmpdir)

            filename = saver._build_filename("GlobalInit", "global", "", "", "json", None)

            assert filename == "GlobalInit.json"

    def test_build_filename_with_suffix(self):
        """Test _build_filename with suffix."""
        with tempfile.TemporaryDirectory() as tmpdir:
            saver = FilesystemCalibDataSaver(tmpdir)

            filename = saver._build_filename("CheckRabi", "qubit", "0", "raw", "csv", 0)

            assert filename == "CheckRabi_0_raw_0.csv"
