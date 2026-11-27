"""Estimate a narrowed qubit spectroscopy frequency window from fast coarse sweeps.

After resonator-to-qubit mapping identifies each qubit's resonator, a fast
few-power coarse 1D sweep (for example ``[-25, -15, -5] dB`` at ``10 MHz`` step)
locates the qubit response at the lowest power that still shows a clear signal.
The resulting ``[window_min, window_max]`` range lets downstream 2D
``CheckQubitSpectroscopy`` skip empty frequencies while preserving enough
off-resonant background for ``estimate_qubit_frequency``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from qdash.analysis.spectroscopy.resonator_qubit_mapping import (
    DEFAULT_MIN_RESPONSE_SCORE,
    DEFAULT_NOISE_FLOOR_SIGMA,
    _abs_phase_deviation,
    _circular_median,
    _estimate_trace_noise_scale,
    _median3,
    _wrap_phase,
)

if TYPE_CHECKING:
    from numpy.typing import ArrayLike

DEFAULT_WINDOW_MARGIN_GHZ = 0.25
"""Padding in GHz added on each side of the detected response cluster."""

DEFAULT_MIN_WINDOW_GHZ = 0.60
"""Minimum width in GHz of the returned search window."""

_FONT_FAMILY = "Times New Roman, Times, serif"
_TITLE_FONT_SIZE = 18
_SUBTITLE_FONT_SIZE = 13
_AXIS_TICKFONT_SIZE = 11
_AXIS_TITLEFONT_SIZE = 12
_SUBPLOT_TITLE_FONT_SIZE = 11
_SELECTED_COLOR = "#0C5DA5"  # Qubex blue
_IDLE_COLOR = "#9e9e9e"  # Qubex gray
_FILL_COLORS = {
    _SELECTED_COLOR: "rgba(12, 93, 165, 0.22)",
    _IDLE_COLOR: "rgba(158, 158, 158, 0.20)",
}
_WINDOW_SHADE_COLOR = "rgba(12, 93, 165, 0.12)"
_PHASE_YAXIS_RANGE = (-0.1, math.pi + 0.15)
_MIN_TRACE_POINTS = 5


@dataclass(frozen=True)
class QubitFrequencyWindowResult:
    """Narrowed drive-frequency window estimated from a coarse few-power sweep.

    Attributes:
        window_min: Lower bound of the search window in GHz, or ``None`` on failure.
        window_max: Upper bound of the search window in GHz, or ``None`` on failure.
        center_frequency: Peak frequency of the dominant response cluster in GHz.
        selected_power: Lowest drive power in dB that showed a significant response.
        selected_score: Trace score of ``selected_power`` (or best score on failure).
        row_scores: Per-power trace scores keyed by drive power in dB.
        reason: Human-readable explanation of the result.
    """

    window_min: float | None
    window_max: float | None
    center_frequency: float | None
    selected_power: float | None
    selected_score: float
    row_scores: dict[float, float]
    reason: str

    @property
    def succeeded(self) -> bool:
        """Whether a valid frequency window was found."""
        return (
            self.window_min is not None
            and self.window_max is not None
            and self.window_max > self.window_min
        )


def estimate_qubit_frequency_window(
    frequencies: ArrayLike,
    powers: ArrayLike,
    phase_rows: ArrayLike,
    *,
    margin_ghz: float = DEFAULT_WINDOW_MARGIN_GHZ,
    min_window_ghz: float = DEFAULT_MIN_WINDOW_GHZ,
    noise_floor_sigma: float = DEFAULT_NOISE_FLOOR_SIGMA,
    min_response_score: float = DEFAULT_MIN_RESPONSE_SCORE,
    despike: bool = True,
) -> QubitFrequencyWindowResult:
    """Locate a qubit's response and return a narrowed 2D spectroscopy window.

    Powers are inspected from lowest to highest so the narrowest, least
    power-broadened response is preferred. On the first power row whose score
    reaches ``min_response_score``, the contiguous frequency cluster with the
    largest integrated excess z-score is selected (ignoring weaker distant
    crosstalk spikes). The window is padded by ``margin_ghz`` on each side,
    expanded to at least ``min_window_ghz``, and clamped to the swept band.

    Args:
        frequencies: 1D drive frequencies in GHz.
        powers: 1D drive powers in dB, one per row of ``phase_rows``.
        phase_rows: 2D array of measured phases in rad, shape ``(n_powers, n_freqs)``.
        margin_ghz: Padding in GHz added to each side of the detected cluster.
        min_window_ghz: Minimum total window width in GHz.
        noise_floor_sigma: Robust z-score treated as the noise floor.
        min_response_score: Minimum row score required to accept a response.
        despike: Whether to apply a 3-point median filter to ``|Δφ|``.

    Returns:
        The estimated window and per-power diagnostics.

    Raises:
        ValueError: On shape mismatches or invalid threshold/width arguments.
    """
    if not math.isfinite(margin_ghz) or margin_ghz < 0:
        raise ValueError("margin_ghz must be finite and non-negative")
    if not math.isfinite(min_window_ghz) or min_window_ghz <= 0:
        raise ValueError("min_window_ghz must be finite and positive")
    if not math.isfinite(noise_floor_sigma) or noise_floor_sigma < 0:
        raise ValueError("noise_floor_sigma must be finite and non-negative")
    if not math.isfinite(min_response_score) or min_response_score <= 0:
        raise ValueError("min_response_score must be finite and positive")

    x = np.asarray(frequencies, dtype=float).ravel()
    p = np.asarray(powers, dtype=float).ravel()
    grid = np.atleast_2d(np.asarray(phase_rows, dtype=float))
    if grid.shape != (p.size, x.size):
        raise ValueError(f"phase_rows must have shape ({p.size}, {x.size}), got {grid.shape}")
    if x.size < _MIN_TRACE_POINTS or p.size == 0:
        return QubitFrequencyWindowResult(
            window_min=None,
            window_max=None,
            center_frequency=None,
            selected_power=None,
            selected_score=0.0,
            row_scores={},
            reason="insufficient frequency or power points",
        )

    order = np.argsort(p)
    row_scores: dict[float, float] = {}
    selected_idx: int | None = None
    selected_signal: np.ndarray | None = None
    selected_excess: np.ndarray | None = None
    selected_freqs: np.ndarray | None = None

    for idx in order:
        power_db = float(p[idx])
        y_raw = grid[idx]
        finite = np.isfinite(x) & np.isfinite(y_raw)
        if int(np.sum(finite)) < _MIN_TRACE_POINTS:
            row_scores[power_db] = 0.0
            continue
        xf = x[finite]
        yf = y_raw[finite]
        baseline = _circular_median(yf)
        abs_dev = np.abs(_wrap_phase(yf - baseline))
        scale = _estimate_trace_noise_scale(yf, baseline=baseline)
        signal = _median3(abs_dev) if despike else abs_dev
        excess = np.clip(signal / scale - noise_floor_sigma, 0.0, None)
        score = float(np.sum(excess))
        if not math.isfinite(score):
            score = 0.0
        row_scores[power_db] = score
        if selected_idx is None and score >= min_response_score:
            selected_idx = int(idx)
            selected_signal = signal
            selected_excess = excess
            selected_freqs = xf

    if (
        selected_idx is None
        or selected_signal is None
        or selected_excess is None
        or selected_freqs is None
    ):
        best_score = max(row_scores.values(), default=0.0)
        return QubitFrequencyWindowResult(
            window_min=None,
            window_max=None,
            center_frequency=None,
            selected_power=None,
            selected_score=best_score,
            row_scores=row_scores,
            reason=(
                f"no power row reached min_response_score={min_response_score:g} "
                f"(best score {best_score:.1f})"
            ),
        )

    selected_power = float(p[selected_idx])
    selected_score = row_scores[selected_power]
    cluster_low, cluster_high, peak_freq = _dominant_cluster(
        selected_freqs, selected_signal, selected_excess
    )

    band_min = float(np.nanmin(x))
    band_max = float(np.nanmax(x))
    win_min, win_max = _padded_window(
        cluster_low,
        cluster_high,
        band_min=band_min,
        band_max=band_max,
        margin_ghz=margin_ghz,
        min_window_ghz=min_window_ghz,
    )
    return QubitFrequencyWindowResult(
        window_min=round(win_min, 6),
        window_max=round(win_max, 6),
        center_frequency=round(peak_freq, 6),
        selected_power=selected_power,
        selected_score=selected_score,
        row_scores=row_scores,
        reason=(
            f"selected {selected_power:g} dB (score {selected_score:.1f}): "
            f"peak {peak_freq:.4f} GHz -> [{win_min:.4f}, {win_max:.4f}] GHz"
        ),
    )


def _dominant_cluster(
    frequencies: np.ndarray,
    signal: np.ndarray,
    excess: np.ndarray,
) -> tuple[float, float, float]:
    """Return ``(low_ghz, high_ghz, peak_ghz)`` of the highest-area active cluster."""
    active = excess > 0.0
    boundaries = np.diff(np.r_[False, active, False].astype(int))
    starts = np.flatnonzero(boundaries == 1)
    stops = np.flatnonzero(boundaries == -1)

    best_area = -1.0
    best_slice = (0, frequencies.size)
    for start, stop in zip(starts, stops, strict=True):
        area = float(np.sum(excess[start:stop]))
        if area > best_area:
            best_area = area
            best_slice = (int(start), int(stop))

    best_start, best_stop = best_slice
    cluster_freqs = frequencies[best_start:best_stop]
    cluster_signal = signal[best_start:best_stop]
    peak_offset = int(np.argmax(cluster_signal))
    return (
        float(cluster_freqs.min()),
        float(cluster_freqs.max()),
        float(cluster_freqs[peak_offset]),
    )


def _padded_window(
    cluster_low: float,
    cluster_high: float,
    *,
    band_min: float,
    band_max: float,
    margin_ghz: float,
    min_window_ghz: float,
) -> tuple[float, float]:
    """Pad a cluster by ``margin_ghz``, enforce ``min_window_ghz``, and clamp to band."""
    win_min = cluster_low - margin_ghz
    win_max = cluster_high + margin_ghz
    if win_max - win_min < min_window_ghz:
        midpoint = 0.5 * (cluster_low + cluster_high)
        win_min = midpoint - 0.5 * min_window_ghz
        win_max = midpoint + 0.5 * min_window_ghz

    target_width = min(max(win_max - win_min, min_window_ghz), band_max - band_min)
    if win_min < band_min:
        win_min = band_min
        win_max = min(band_max, band_min + target_width)
    if win_max > band_max:
        win_max = band_max
        win_min = max(band_min, band_max - target_width)
    return win_min, win_max


def create_qubit_frequency_window_figure(
    frequencies: ArrayLike,
    powers: ArrayLike,
    phase_rows: ArrayLike,
    result: QubitFrequencyWindowResult,
    qubit_label: str,
) -> go.Figure:
    """Draw the stacked 1D coarse power sweeps with the selected search window."""
    x = np.asarray(frequencies, dtype=float).ravel()
    p = np.asarray(powers, dtype=float).ravel()
    grid = np.atleast_2d(np.asarray(phase_rows, dtype=float))
    if grid.shape != (p.size, x.size):
        raise ValueError(f"phase_rows must have shape ({p.size}, {x.size}), got {grid.shape}")
    if p.size == 0:
        raise ValueError("At least one power row is required to draw the figure")

    order = np.argsort(p)
    n_rows = int(p.size)
    titles = [
        f"{float(p[idx]):g} dB | score {result.row_scores.get(float(p[idx]), 0.0):.1f}"
        + (
            " (selected)"
            if result.selected_power is not None
            and math.isclose(float(p[idx]), result.selected_power)
            else ""
        )
        for idx in order
    ]
    figure = make_subplots(
        rows=n_rows,
        cols=1,
        shared_xaxes=True,
        subplot_titles=titles,
        vertical_spacing=min(0.14, 0.35 / max(n_rows, 1)),
    )
    figure.update_annotations(font_size=_SUBPLOT_TITLE_FONT_SIZE)

    for row_idx, power_idx in enumerate(order, start=1):
        power_db = float(p[power_idx])
        selected = result.selected_power is not None and math.isclose(
            power_db, result.selected_power
        )
        color = _SELECTED_COLOR if selected else _IDLE_COLOR
        y = _abs_phase_deviation(grid[power_idx])
        figure.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="lines",
                fill="tozeroy",
                fillcolor=_FILL_COLORS[color],
                line={"color": color, "width": 2.2 if selected else 1.4},
                name=f"{power_db:g} dB",
                showlegend=False,
                hovertemplate=(
                    f"{qubit_label} @ {power_db:g} dB"
                    "<br>%{x:.4f} GHz<br>|Δφ| = %{y:.3f} rad<extra></extra>"
                ),
            ),
            row=row_idx,
            col=1,
        )
        if result.succeeded and result.window_min is not None and result.window_max is not None:
            figure.add_vrect(
                x0=result.window_min,
                x1=result.window_max,
                fillcolor=_WINDOW_SHADE_COLOR,
                line_width=1,
                line_dash="dot",
                line_color=_SELECTED_COLOR,
                row=row_idx,
                col=1,
            )
            if result.center_frequency is not None:
                figure.add_vline(
                    x=result.center_frequency,
                    line_width=1.5,
                    line_dash="dash",
                    line_color=_SELECTED_COLOR,
                    row=row_idx,
                    col=1,
                )
        figure.update_yaxes(title_text="|Δφ| (rad)", row=row_idx, col=1)

    figure.update_xaxes(title_text="Drive frequency (GHz)", row=n_rows, col=1)
    figure.update_layout(
        title={
            "text": f"Qubit frequency window ({qubit_label})",
            "subtitle": {
                "text": result.reason,
                "font": {"size": _SUBTITLE_FONT_SIZE, "family": "monospace"},
            },
            "font": {"size": _TITLE_FONT_SIZE},
        },
        font={"family": _FONT_FAMILY},
        paper_bgcolor="white",
        plot_bgcolor="rgba(0,0,0,0)",
        width=760,
        height=max(200 * n_rows, 300) + 110,
        margin={"l": 70, "r": 30, "b": 60, "t": 100},
    )
    axis_style: dict[str, Any] = {
        "showline": True,
        "mirror": True,
        "linecolor": "black",
        "linewidth": 1,
        "ticks": "inside",
        "showgrid": False,
        "zeroline": False,
        "tickfont": {"size": _AXIS_TICKFONT_SIZE},
        "title_font": {"size": _AXIS_TITLEFONT_SIZE},
    }
    figure.update_xaxes(**axis_style)
    figure.update_yaxes(**axis_style, range=list(_PHASE_YAXIS_RANGE), tickvals=[0, 1, 2, 3])
    return figure
