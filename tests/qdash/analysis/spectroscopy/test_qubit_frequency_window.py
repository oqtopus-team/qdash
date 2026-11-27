"""Tests for coarse qubit frequency window estimation."""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import pytest

from qdash.analysis.spectroscopy import (
    create_qubit_frequency_window_figure,
    estimate_qubit_frequency_window,
)

FREQUENCIES = np.arange(6.5, 9.75, 0.01)
POWERS = np.array([-25.0, -15.0, -5.0])


def _noise(seed: int, sigma: float = 0.02) -> np.ndarray:
    return np.random.default_rng(seed).normal(0.0, sigma, FREQUENCIES.size)


def _lorentzian(center: float, height: float, width: float) -> np.ndarray:
    return height / (1.0 + ((FREQUENCIES - center) / width) ** 2)


def test_prefers_lowest_responsive_power_and_enforces_min_window() -> None:
    # -25 dB is pure noise; -15 dB has a crisp f01 peak at 7.85 GHz;
    # -5 dB is heavily power-broadened. The estimator must select -15 dB.
    rows = np.vstack(
        [
            _noise(1),
            _noise(2) + _lorentzian(7.85, 1.4, 0.03),
            _noise(3) + _lorentzian(7.85, 2.8, 0.40),
        ]
    )

    result = estimate_qubit_frequency_window(
        FREQUENCIES, POWERS, rows, margin_ghz=0.25, min_window_ghz=0.6
    )

    assert result.succeeded
    assert result.selected_power == pytest.approx(-15.0)
    assert result.center_frequency == pytest.approx(7.85, abs=0.02)
    assert result.window_min is not None and result.window_max is not None
    assert result.window_max - result.window_min >= 0.6 - 1e-6
    assert result.window_min < 7.85 < result.window_max
    assert result.window_max - result.window_min < 1.0


def test_dominant_cluster_ignores_distant_weaker_crosstalk() -> None:
    # Real f01 peak at 7.90 GHz plus a weaker narrow crosstalk dip at 8.95 GHz.
    row_mid = _noise(4) - _lorentzian(7.90, 2.0, 0.04) - _lorentzian(8.95, 0.35, 0.015)
    rows = np.vstack([_noise(5), row_mid, _noise(6) - _lorentzian(7.90, 2.8, 0.30)])

    result = estimate_qubit_frequency_window(
        FREQUENCIES, POWERS, rows, margin_ghz=0.25, min_window_ghz=0.6
    )

    assert result.succeeded
    assert result.center_frequency == pytest.approx(7.90, abs=0.02)
    assert result.window_max is not None
    assert result.window_max < 8.5


def test_clamps_window_to_swept_band_while_preserving_width() -> None:
    rows = np.vstack(
        [
            _noise(7) + _lorentzian(6.55, 1.5, 0.03),
            _noise(8) + _lorentzian(6.55, 2.5, 0.20),
        ]
    )

    result = estimate_qubit_frequency_window(
        FREQUENCIES, np.array([-20.0, -10.0]), rows, margin_ghz=0.25, min_window_ghz=0.6
    )

    assert result.succeeded
    assert result.window_min is not None and result.window_max is not None
    assert result.window_min == pytest.approx(float(FREQUENCIES.min()), abs=1e-6)
    assert result.window_max - result.window_min >= 0.6 - 1e-6
    assert result.window_max < 7.3


def test_all_noise_rows_report_failure() -> None:
    rows = np.vstack([_noise(10), _noise(11), _noise(12)])

    result = estimate_qubit_frequency_window(FREQUENCIES, POWERS, rows)

    assert not result.succeeded
    assert result.window_min is None
    assert result.window_max is None
    assert result.selected_power is None
    assert "min_response_score" in result.reason


def test_window_figure_draws_all_power_rows_and_shades_selected_window() -> None:
    rows = np.vstack(
        [
            _noise(20),
            _noise(21) + _lorentzian(8.10, 1.6, 0.04),
            _noise(22) + _lorentzian(8.10, 2.8, 0.30),
        ]
    )
    result = estimate_qubit_frequency_window(FREQUENCIES, POWERS, rows)

    figure = create_qubit_frequency_window_figure(FREQUENCIES, POWERS, rows, result, "Q32")

    assert isinstance(figure, go.Figure)
    assert len(figure.data) == 3
    assert [trace.line.color for trace in figure.data] == ["#9e9e9e", "#0C5DA5", "#9e9e9e"]
    assert all(trace.fill == "tozeroy" for trace in figure.data)
    # 3 vrects + 3 vlines across the 3 power subplots
    assert len(figure.layout.shapes) == 6
