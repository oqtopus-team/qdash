"""Tests for qdash.api.lib.metrics_chart module."""

from __future__ import annotations

import math
from unittest.mock import MagicMock

from qdash.api.lib.metrics_chart import (
    ChipGeometry,
    _format_qubit_text,
    build_chip_geometry,
    create_data_matrix,
    create_qubit_heatmap,
    get_qubit_position,
)


class TestChipGeometry:
    """Tests for ChipGeometry dataclass."""

    def test_default_mux_size(self):
        geo = ChipGeometry(n_qubits=4, grid_size=2)
        assert geo.mux_size == 2
        assert geo.qubit_positions == {}

    def test_custom_positions(self):
        positions = {0: (0, 0), 1: (0, 1)}
        geo = ChipGeometry(n_qubits=2, grid_size=2, qubit_positions=positions)
        assert geo.qubit_positions == positions


class TestBuildChipGeometry:
    """Tests for build_chip_geometry."""

    def test_basic_build(self):
        geo = build_chip_geometry(16, 4)
        assert geo.n_qubits == 16
        assert geo.grid_size == 4
        assert geo.mux_size == 2

    def test_custom_mux_size(self):
        geo = build_chip_geometry(64, 8, mux_size=4)
        assert geo.mux_size == 4


class TestGetQubitPosition:
    """Tests for get_qubit_position with explicit positions and MUX calculation."""

    def test_explicit_position_lookup(self):
        geo = ChipGeometry(
            n_qubits=4,
            grid_size=4,
            qubit_positions={0: (3, 1), 1: (0, 2)},
        )
        assert get_qubit_position(geo, 0) == (3, 1)
        assert get_qubit_position(geo, 1) == (0, 2)

    def test_mux_calculation_2x2(self):
        """4 qubits on a 2x2 grid, mux_size=2."""
        geo = ChipGeometry(n_qubits=4, grid_size=2, mux_size=2)
        # MUX index 0, local positions within the 2x2 MUX
        assert get_qubit_position(geo, 0) == (0, 0)
        assert get_qubit_position(geo, 1) == (0, 1)
        assert get_qubit_position(geo, 2) == (1, 0)
        assert get_qubit_position(geo, 3) == (1, 1)

    def test_mux_calculation_4x4_grid(self):
        """16 qubits on a 4x4 grid with mux_size=2."""
        geo = ChipGeometry(n_qubits=16, grid_size=4, mux_size=2)
        # First MUX (top-left): qubits 0-3
        assert get_qubit_position(geo, 0) == (0, 0)
        assert get_qubit_position(geo, 3) == (1, 1)
        # Second MUX (top-right): qubits 4-7
        assert get_qubit_position(geo, 4) == (0, 2)
        # Third MUX (bottom-left): qubits 8-11
        assert get_qubit_position(geo, 8) == (2, 0)

    def test_explicit_position_overrides_mux(self):
        """Explicit positions should override MUX calculation."""
        geo = ChipGeometry(
            n_qubits=4,
            grid_size=2,
            mux_size=2,
            qubit_positions={0: (1, 1)},  # override default (0,0)
        )
        assert get_qubit_position(geo, 0) == (1, 1)
        # qid=1 has no explicit position, falls back to MUX
        assert get_qubit_position(geo, 1) == (0, 1)


class TestCreateDataMatrix:
    """Tests for create_data_matrix."""

    def test_basic_matrix(self):
        geo = ChipGeometry(n_qubits=4, grid_size=2, mux_size=2)
        values = [10, 20, 30, 40]
        matrix = create_data_matrix(geo, values)
        assert matrix == [[10, 20], [30, 40]]

    def test_default_fill_value(self):
        """Unfilled cells should use the default value (NaN)."""
        geo = ChipGeometry(n_qubits=2, grid_size=2, mux_size=2)
        values = [10, 20]
        matrix = create_data_matrix(geo, values)
        assert matrix[0][0] == 10
        assert matrix[0][1] == 20
        assert math.isnan(matrix[1][0])
        assert math.isnan(matrix[1][1])

    def test_custom_default(self):
        geo = ChipGeometry(n_qubits=2, grid_size=2, mux_size=2)
        matrix = create_data_matrix(geo, [1, 2], default="N/A")
        assert matrix[1][0] == "N/A"

    def test_excess_values_ignored(self):
        """Values beyond n_qubits should be ignored."""
        geo = ChipGeometry(n_qubits=2, grid_size=2, mux_size=2)
        values = [10, 20, 99, 99]  # more values than qubits
        matrix = create_data_matrix(geo, values)
        assert matrix[0][0] == 10
        assert matrix[0][1] == 20

    def test_out_of_bounds_positions_skipped(self):
        """Qubit positions outside the grid should not cause errors."""
        geo = ChipGeometry(
            n_qubits=2,
            grid_size=2,
            qubit_positions={0: (0, 0), 1: (5, 5)},  # out of bounds
        )
        matrix = create_data_matrix(geo, [10, 20])
        assert matrix[0][0] == 10
        # (5,5) is out of 2x2 grid, value should not be placed


class TestFormatQubitText:
    """Tests for _format_qubit_text helper."""

    def test_fidelity_format(self):
        result = _format_qubit_text(0, 99.5, "X90 Gate Fidelity", "%")
        assert "99.50%" in result
        assert "Q000" in result

    def test_ghz_format(self):
        result = _format_qubit_text(5, 5.123456, "Qubit Frequency", "GHz")
        assert "5.123" in result
        assert "GHz" in result
        assert "Q005" in result

    def test_us_format(self):
        result = _format_qubit_text(10, 45.67, "T1", "\u00b5s")
        assert "45.67" in result
        assert "\u00b5s" in result

    def test_ns_format(self):
        result = _format_qubit_text(1, 123.456, "Gate Time", "ns")
        assert "123.46" in result
        assert "ns" in result

    def test_default_format(self):
        result = _format_qubit_text(0, 1.23456, "Custom Metric", "arb")
        assert "1.235" in result
        assert "arb" in result


class TestCreateQubitHeatmap:
    """Tests for create_qubit_heatmap."""

    def _make_metric_value(self, value):
        mv = MagicMock()
        mv.value = value
        return mv

    def test_basic_heatmap(self):
        geo = ChipGeometry(n_qubits=4, grid_size=2, mux_size=2)
        data = {
            "0": self._make_metric_value(10.0),
            "1": self._make_metric_value(20.0),
            "2": self._make_metric_value(30.0),
            "3": self._make_metric_value(40.0),
        }
        fig = create_qubit_heatmap(data, geo, 1.0, "Test", "arb")
        fig_dict = fig.to_dict()
        assert len(fig_dict["data"]) == 1
        assert fig_dict["data"][0]["type"] == "heatmap"

    def test_missing_data_produces_nan(self):
        """Qubits without data should have NaN values in the z matrix."""
        geo = ChipGeometry(n_qubits=4, grid_size=2, mux_size=2)
        data = {"0": self._make_metric_value(10.0)}  # only Q0
        fig = create_qubit_heatmap(data, geo, 1.0, "Test", "arb")
        z = fig.to_dict()["data"][0]["z"]
        # Q0=(0,0) should be 10.0, others should be NaN
        assert z[0][0] == 10.0
        assert math.isnan(z[0][1])

    def test_none_value_treated_as_missing(self):
        geo = ChipGeometry(n_qubits=2, grid_size=2, mux_size=2)
        data = {
            "0": self._make_metric_value(5.0),
            "1": self._make_metric_value(None),
        }
        fig = create_qubit_heatmap(data, geo, 1.0, "Test", "arb")
        z = fig.to_dict()["data"][0]["z"]
        assert z[0][0] == 5.0
        assert math.isnan(z[0][1])

    def test_metric_scale_applied(self):
        geo = ChipGeometry(n_qubits=1, grid_size=1, mux_size=1)
        data = {"0": self._make_metric_value(5.0)}
        fig = create_qubit_heatmap(data, geo, 1e6, "Frequency", "MHz")
        z = fig.to_dict()["data"][0]["z"]
        assert z[0][0] == 5.0e6

    def test_compact_mode_uses_smaller_sizing(self):
        geo = ChipGeometry(n_qubits=4, grid_size=2, mux_size=2)
        data = {"0": self._make_metric_value(1.0)}
        fig = create_qubit_heatmap(data, geo, 1.0, "Test", "arb", compact=True)
        layout = fig.to_dict()["layout"]
        # Compact mode should have a title and showscale=True
        assert layout["title"]["text"] == "Test"
        assert fig.to_dict()["data"][0]["showscale"] is True

    def test_default_mode_no_title(self):
        geo = ChipGeometry(n_qubits=4, grid_size=2, mux_size=2)
        data = {"0": self._make_metric_value(1.0)}
        fig = create_qubit_heatmap(data, geo, 1.0, "Test", "arb", compact=False)
        layout = fig.to_dict()["layout"]
        # Plotly stores title=None as {} or omits text
        title = layout.get("title")
        assert title is None or title == {} or title.get("text") is None

    def test_empty_metric_data(self):
        """All qubits missing data should produce all-NaN matrix."""
        geo = ChipGeometry(n_qubits=4, grid_size=2, mux_size=2)
        fig = create_qubit_heatmap({}, geo, 1.0, "Test", "arb")
        z = fig.to_dict()["data"][0]["z"]
        for row in z:
            for val in row:
                assert math.isnan(val)
