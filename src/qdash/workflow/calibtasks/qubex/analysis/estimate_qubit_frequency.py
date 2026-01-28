"""Qubit frequency estimation from spectroscopy data.

This module provides functions to estimate qubit frequencies (f01, f12) from
2D power-frequency spectroscopy data by detecting peaks using image binarization
and labeling techniques.
"""

from __future__ import annotations

import functools
import itertools
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple, cast

import numpy as np
import numpy.typing as npt
import scipy.ndimage

if TYPE_CHECKING:
    from collections.abc import Sequence

    import plotly.graph_objs as go


@dataclass
class EstimateQubitFrequencyConfig:
    """Configuration for qubit frequency estimation."""

    binarize_threshold_sigma_plus: float = 3.0
    binarize_threshold_sigma_minus: float = -2.0
    top_power: float = 0.0
    f01_height_min: float = 14.9
    f01_moment_thresholds: tuple[float, ...] = (0.1, 1750.0, 3600.0, 5000.0, 15000.0)
    f12_distance_min: float = 0.125
    f12_distance_max: float = 0.5
    f12_height_min: float = 14.9

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if self.binarize_threshold_sigma_plus <= 0:
            raise ValueError("binarize_thresholds_sigma_plus must be positive")

        if self.binarize_threshold_sigma_minus >= 0:
            raise ValueError("binarize_thresholds_sigma_minus must be negative")

        if self.f01_height_min <= 0:
            raise ValueError("f01_height_min must be > 0")

        if len(self.f01_moment_thresholds) == 0 or any(
            b <= a for a, b in itertools.pairwise(self.f01_moment_thresholds)
        ):
            raise ValueError("f01_moment_thresholds must be strictly increasing")

        if self.f12_distance_min < 0 or self.f12_distance_min > self.f12_distance_max:
            raise ValueError("bad f12 distance range")

        if self.f12_height_min <= 0:
            raise ValueError("f12_height_min must be > 0")


class F01Result(NamedTuple):
    """Result of f01 (qubit) frequency detection."""

    idx_x: int
    idx_y: int
    frequency: float
    label: int
    moment: float
    quality_level: int


class F12Result(NamedTuple):
    """Result of f12 frequency detection."""

    idx_x: int
    idx_y: int
    frequency: float


class Peak(NamedTuple):
    """Represents a detected peak region."""

    x_start: int
    x_end: int
    height: int
    height_db: float
    frequency_right: float


@dataclass
class QubitFrequencyResult:
    """Result of qubit frequency estimation."""

    f01: F01Result | None = None
    f12: F12Result | None = None

    @property
    def anharmonicity(self) -> float | None:
        """Calculate anharmonicity alpha = f12 - f01 = (f02 - f01) - f01.

        The anharmonicity is defined as:
            alpha = f02 - 2*f01
        Since f12 = f02 - f01, we have:
            alpha = (f01 + f12) - 2*f01 = f12 - f01

        Returns:
            Anharmonicity in GHz, or None if f01 or f12 is not detected.
            Typically negative for transmon qubits (around -200 to -300 MHz).
        """
        if self.f01 is None or self.f12 is None:
            return None
        return self.f12.frequency - self.f01.frequency


class QubitResponse:
    """Analyzes qubit spectroscopy data to extract frequency information.

    This class processes 2D power-frequency spectroscopy data to identify
    the qubit transition frequencies (f01 and f12) by:
    1. Standardizing and binarizing the data
    2. Labeling connected regions
    3. Finding peaks that extend from the bottom (high power)
    4. Identifying f01 as the tallest peak
    5. Identifying f12 based on distance constraints from f01
    """

    def __init__(
        self,
        xs: Sequence[float],
        ys: Sequence[float],
        zs: Sequence[Sequence[float]],
        config: EstimateQubitFrequencyConfig,
    ):
        self.xs = np.asarray(xs, dtype=np.float64)
        self.ys = np.asarray(ys, dtype=np.float64)
        self.zs = np.asarray(zs, dtype=np.float64)
        self.config = config

        self._validate_input()

    @functools.cached_property
    def zs_labeled(self) -> npt.NDArray[np.int32]:
        """Get the labeled and binarized data."""
        zs_standardized = self.standardize(self.zs)
        zs_binarized = self.binarize(
            zs_standardized,
            self.config.binarize_threshold_sigma_plus,
            self.config.binarize_threshold_sigma_minus,
        )
        return self.remove_noise(zs_binarized)

    @functools.cached_property
    def f01(self) -> F01Result | None:
        """Detect the f01 (qubit) frequency."""
        idx_max_height = np.argmax(self.heights)
        max_height = self.heights[idx_max_height]
        max_height_db = self.heights_db[idx_max_height]

        if max_height_db < self.config.f01_height_min:
            return None

        idx_y = len(self.zs) - max_height

        candidates = np.where(np.asarray(self.heights) == max_height)[0]
        idx_max = np.argmax(np.abs(self.zs[idx_y, candidates]))
        idx_x = candidates[idx_max]

        frequency = cast(float, self.xs[idx_x])
        label = cast(int, self.zs_labeled[idx_y, idx_x])
        moment = self.compute_moment(self.zs, self.zs_labeled, self.levers, self.y_diffs, label)
        quality_level_idx = np.searchsorted(self.config.f01_moment_thresholds, moment, side="left")
        return F01Result(
            idx_x=int(idx_x),
            idx_y=idx_y,
            frequency=frequency,
            label=label,
            moment=moment,
            quality_level=int(quality_level_idx),
        )

    @functools.cached_property
    def f12(self) -> F12Result | None:
        """Detect the f12 frequency."""
        if self.f01 is None:
            return None

        peaks = [
            peak
            for peak in self.peaks
            if self.config.f12_distance_min
            <= self.f01.frequency - peak.frequency_right
            <= self.config.f12_distance_max
            and peak.height_db >= self.config.f12_height_min
        ]

        if not peaks:
            return None

        max_height = max(peak.height for peak in peaks)
        peaks = [peak for peak in peaks if peak.height == max_height]
        peak = max(peaks, key=lambda p: p.x_end)

        idx_y = self.zs.shape[0] - peak.height
        idx_x = np.argmax(abs(self.zs[idx_y][peak.x_start : peak.x_end])) + peak.x_start
        frequency = cast(float, self.xs[idx_x])

        return F12Result(
            idx_x=int(idx_x),
            idx_y=idx_y,
            frequency=frequency,
        )

    @functools.cached_property
    def peaks(self) -> list[Peak]:
        """Detect all peaks in the data."""
        _peaks: list[Peak] = []
        x_start: int | None = None

        heights_zipped = zip(self.heights, self.heights_db, strict=False)
        heights_chained = itertools.chain([(0, 0.0)], heights_zipped, [(0, 0.0)])
        for x, ((height_prev, height_db_prev), (height, _)) in enumerate(
            itertools.pairwise(heights_chained)
        ):
            if height > height_prev:
                x_start = x

            elif height < height_prev and x_start is not None:
                _peaks.append(
                    Peak(
                        x_start=x_start,
                        x_end=x,
                        height=height_prev,
                        height_db=height_db_prev,
                        frequency_right=self.xs[x - 1],
                    )
                )
                x_start = None

        return _peaks

    @functools.cached_property
    def heights(self) -> npt.NDArray[np.int64]:
        """Compute heights of peaks at each x position (in index units)."""
        m = self.zs_labeled != 0
        first = np.argmax(m, axis=0)
        all_false = ~m.any(axis=0)
        first[all_false] = self.zs_labeled.shape[0]
        result: npt.NDArray[np.int64] = self.zs_labeled.shape[0] - first
        return result

    @functools.cached_property
    def heights_db(self) -> npt.NDArray[np.float64]:
        """Compute heights of peaks at each x position (in dB units)."""
        h_map = np.append(0.0, self.config.top_power - self.ys[::-1])
        return h_map[self.heights]

    @functools.cached_property
    def levers(self) -> npt.NDArray[np.float64]:
        """Compute lever arms for moment calculation."""
        return self.config.top_power - self.ys

    @functools.cached_property
    def y_diffs(self) -> npt.NDArray[np.float64]:
        """Compute y-axis differences for moment calculation."""
        return np.diff(np.append(self.ys, self.config.top_power))

    def _validate_input(self) -> None:
        if self.zs.ndim != 2:
            raise ValueError(f"zs must be 2D, got {self.zs.ndim}D")
        if self.zs.shape != (len(self.ys), len(self.xs)):
            raise ValueError(
                f"shape mismatch: zs{self.zs.shape} vs (len(ys),len(xs))={(len(self.ys),len(self.xs))}"
            )
        if not np.all(np.isfinite(self.zs)):
            raise ValueError("zs contains NaN/Inf")
        if len(self.xs) < 2 or len(self.ys) < 2:
            raise ValueError("xs/ys too short")
        if np.any(np.diff(self.xs) <= 0):
            raise ValueError("xs must be strictly increasing")
        if np.any(np.diff(self.ys) <= 0):
            raise ValueError("ys must be strictly increasing")
        if self.config.top_power <= np.max(self.ys):
            raise ValueError("`top_power` must be greater than the maximum value of ys.")

    @staticmethod
    def compute_moment(
        zs: npt.NDArray[np.float64],
        zs_labeled: npt.NDArray[np.int32],
        levers: npt.NDArray[np.float64],
        y_diffs: npt.NDArray[np.float64],
        label: int,
    ) -> float:
        """Compute the moment of a labeled region.

        The moment is calculated as the sum of (weight * lever * y_diff) for each
        pixel in the labeled region, where:
        - weight: absolute value of the z (phase shift) at that pixel
        - lever: distance from top_power to the y position (in dB)
        - y_diff: the y-axis step size at that position (in dB)
        """
        indices_y, indices_x = np.where(zs_labeled == label)
        weights = np.abs(zs[indices_y, indices_x])
        return float(np.sum(weights * levers[indices_y] * y_diffs[indices_y]))

    @staticmethod
    def standardize(zs: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        """Standardize the data to zero mean and unit variance."""
        std = zs.std()
        if std < 1e-12:
            raise ValueError("degenerate std")
        result: npt.NDArray[np.float64] = (zs - zs.mean()) / std
        return result

    @staticmethod
    def binarize(
        zs: npt.NDArray[np.float64],
        threshold_plus: float,
        threshold_minus: float,
    ) -> npt.NDArray[np.int32]:
        """Binarize the data based on thresholds."""
        return np.where((zs > threshold_plus) | (zs < threshold_minus), 1, 0).astype(
            np.int32, copy=False
        )

    @staticmethod
    def remove_noise(zs: npt.NDArray[np.int32]) -> npt.NDArray[np.int32]:
        """Remove noise by keeping only regions connected to the bottom."""
        result = scipy.ndimage.label(zs)
        labeled, _ = cast(tuple[npt.NDArray[np.int32], int], result)
        objects = scipy.ndimage.find_objects(labeled)
        valid_labels = [
            i + 1 for i, obj in enumerate(objects) if obj is not None and obj[0].stop == zs.shape[0]
        ]
        return labeled * np.isin(labeled, valid_labels).astype(np.int32)


def estimate_qubit_frequency(
    xs: Sequence[float],
    ys: Sequence[float],
    zs: Sequence[Sequence[float]],
    config: EstimateQubitFrequencyConfig | None = None,
) -> QubitFrequencyResult:
    """Estimate qubit frequencies from 2D spectroscopy data.

    Args:
        xs: Frequency values (x-axis, in GHz).
        ys: Power values (y-axis, in dB).
        zs: 2D intensity data (power x frequency).
        config: Configuration for the estimation algorithm.

    Returns:
        QubitFrequencyResult containing f01 and f12 frequency information.
    """
    if config is None:
        config = EstimateQubitFrequencyConfig()

    qubit_response = QubitResponse(xs, ys, zs, config)

    return QubitFrequencyResult(
        f01=qubit_response.f01,
        f12=qubit_response.f12,
    )


def estimate_qubit_frequency_from_figure(
    fig: go.Figure,
    config: EstimateQubitFrequencyConfig | None = None,
) -> QubitFrequencyResult:
    """Estimate qubit frequencies from a plotly figure.

    Args:
        fig: Plotly figure containing the spectroscopy data.
             Expected to have a heatmap trace with x (frequency),
             y (power), and z (intensity) data.
        config: Configuration for the estimation algorithm.

    Returns:
        QubitFrequencyResult containing f01 and f12 frequency information.
    """
    trace = fig.data[0]
    xs = list(trace.x)
    ys = list(trace.y)
    zs = list(trace.z)

    return estimate_qubit_frequency(xs, ys, zs, config)


def create_marked_figure(
    fig: go.Figure,
    result: QubitFrequencyResult,
    f01_color: str = "red",
    f12_color: str = "purple",
) -> go.Figure:
    """Create a copy of the figure with frequency markers added.

    Args:
        fig: Original plotly figure containing the spectroscopy data.
        result: QubitFrequencyResult containing detected frequencies.
        f01_color: Color for the f01 vertical line.
        f12_color: Color for the f12 vertical line.

    Returns:
        A new figure with markers added.
    """
    import plotly.graph_objects as pgo

    marked_fig = pgo.Figure(fig)

    if result.f01 is not None:
        marked_fig.add_vline(
            x=result.f01.frequency,
            line_width=1,
            line_color=f01_color,
            line_dash="dash",
        )

    if result.f12 is not None:
        marked_fig.add_vline(
            x=result.f12.frequency,
            line_width=1,
            line_color=f12_color,
            line_dash="dash",
        )

    return marked_fig


def estimate_and_mark_figure(
    fig: go.Figure,
    config: EstimateQubitFrequencyConfig | None = None,
) -> tuple[go.Figure, QubitFrequencyResult]:
    """Estimate qubit frequencies and create a marked figure.

    Args:
        fig: Plotly figure containing the spectroscopy data.
        config: Configuration for the estimation algorithm.

    Returns:
        A tuple of (marked_figure, result).
    """
    result = estimate_qubit_frequency_from_figure(fig, config)
    marked_fig = create_marked_figure(fig, result)

    return marked_fig, result
