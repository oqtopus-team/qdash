"""Resonator frequency estimation from spectroscopy data.

This module provides functions to estimate resonator frequencies from
2D power-frequency spectroscopy data by detecting peaks in high-power
and low-power regions and scoring them to identify genuine resonances.
"""

from __future__ import annotations

import functools
import itertools
from dataclasses import dataclass, field
from operator import attrgetter, itemgetter
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Sequence

    import plotly.graph_objs as go
    from qdash.analysis.spectroscopy.bare_shift import BareShiftBoundary

import numpy as np
from scipy.ndimage import convolve1d
from scipy.signal import find_peaks as scipy_find_peaks


class Peak(NamedTuple):
    """Represents a detected peak with position and prominence."""

    x: int
    y: int
    prominence: float


class PeakGroup:
    """A group of related peaks in the high-power region."""

    def __init__(self, peaks: Sequence[Peak]):
        self.peaks = list(peaks)

    @functools.cached_property
    def bottom(self) -> Peak:
        """Get the peak with the lowest y (power) value."""
        return sorted(self.peaks, key=attrgetter("y"))[0]

    @property
    def x(self) -> int:
        """X position of the bottom peak."""
        return self.bottom.x

    @property
    def y(self) -> int:
        """Y position of the bottom peak."""
        return self.bottom.y


class Resonance:
    """Represents a detected resonance combining high and low power peaks."""

    def __init__(self, high_power_peaks: PeakGroup | None, low_power_peak: Peak | None):
        self.high_power_peaks = high_power_peaks
        self.low_power_peak = low_power_peak

    @property
    def x(self) -> int:
        """X position of the resonance."""
        if self.low_power_peak:
            return self.low_power_peak.x
        if self.high_power_peaks:
            return self.high_power_peaks.x
        return -1

    @functools.cached_property
    def score(self) -> tuple[bool, bool, float, float]:
        """Score tuple used to rank resonances.

        Order of preference (descending):
          1. has a high-power peak group
          2. has a low-power peak
          3. high_power_grad (more strongly downward-sloped is better)
          4. max_prominence across all peaks
        """
        return (
            self.has_high_power_peaks,
            self.has_low_power_peak,
            self.high_power_grad,
            self.max_prominence,
        )

    @functools.cached_property
    def has_high_power_peaks(self) -> bool:
        return bool(self.high_power_peaks)

    @functools.cached_property
    def has_low_power_peak(self) -> bool:
        return bool(self.low_power_peak)

    @functools.cached_property
    def high_power_grad(self) -> float:
        """Maximum (least-negative) downward gradient between high-power peaks."""
        if len(self.peaks) <= 1:
            return float("-inf")
        return max(self._compute_grad(p0, p1) for p0, p1 in itertools.combinations(self.peaks, 2))

    @functools.cached_property
    def peaks(self) -> list[Peak]:
        """All peaks associated with this resonance."""
        peaks: list[Peak] = []
        if self.high_power_peaks:
            peaks.extend(self.high_power_peaks.peaks)
        if self.low_power_peak:
            peaks.append(self.low_power_peak)
        return peaks

    @property
    def max_prominence(self) -> float:
        """Maximum prominence across all peaks of this resonance."""
        if not self.peaks:
            return 0.0
        return max(peak.prominence for peak in self.peaks)

    @staticmethod
    def _compute_grad(p0: Peak, p1: Peak) -> float:
        """Compute gradient between two peaks; -inf if not strictly downward."""
        if p0.x == p1.x:
            return float("-inf")
        grad = float((p1.y - p0.y) / (p1.x - p0.x))
        if grad > 0:
            return float("-inf")
        return grad


@dataclass
class FindPeaksConfig:
    """Configuration for peak detection."""

    smooth_sigma: float = 1.0
    distance: int = 10
    prominence: float = 0.35


@dataclass
class GroupPeaksConfig:
    """Configuration for high-power peak grouping."""

    x_backward_max: int = 2
    x_distance_max: int = 25


@dataclass
class ComposeResonancesConfig:
    """Configuration for high/low-power peak pairing into resonances."""

    x_distance_max: int = 25
    x_backward_max: int = 2


@dataclass
class GroupResonancesConfig:
    """Configuration for nearby-resonance grouping."""

    x_distance_max: int = 25


@dataclass
class EstimateResonatorFrequencyConfig:
    """Configuration for resonator frequency estimation."""

    num_resonators: int = 4
    high_power_min: float | None = -20.0
    high_power_max: float | None = 0.0
    low_power: float = -30.0
    find_peaks_conf_high: FindPeaksConfig = field(default_factory=FindPeaksConfig)
    find_peaks_conf_low: FindPeaksConfig = field(
        default_factory=lambda: FindPeaksConfig(distance=5, prominence=0.05)
    )
    group_peaks_conf: GroupPeaksConfig = field(default_factory=GroupPeaksConfig)
    compose_resonances_conf: ComposeResonancesConfig = field(
        default_factory=ComposeResonancesConfig
    )
    group_resonances_conf: GroupResonancesConfig = field(default_factory=GroupResonancesConfig)

    def with_boundary(self, boundary: BareShiftBoundary) -> EstimateResonatorFrequencyConfig:
        """Return a copy of this config with power bounds taken from a boundary."""
        return EstimateResonatorFrequencyConfig(
            num_resonators=self.num_resonators,
            high_power_min=boundary.high_power_min,
            high_power_max=boundary.high_power_max,
            low_power=boundary.low_power,
            find_peaks_conf_high=self.find_peaks_conf_high,
            find_peaks_conf_low=self.find_peaks_conf_low,
            group_peaks_conf=self.group_peaks_conf,
            compose_resonances_conf=self.compose_resonances_conf,
            group_resonances_conf=self.group_resonances_conf,
        )


def _detect_peaks(
    trace: Sequence[float],
    *,
    num_resonators: int,
    smooth_sigma: float,
    distance: int,
    prominence: float,
) -> tuple[list[int], list[float]]:
    """Find peaks in a 1D trace with smoothing and filtering."""
    _trace = np.asarray(trace)

    if smooth_sigma and smooth_sigma > 0:
        radius = int(3 * smooth_sigma)
        x = np.arange(-radius, radius + 1)
        kernel = np.exp(-0.5 * (x / smooth_sigma) ** 2)
        kernel /= kernel.sum()
        trace_smooth = convolve1d(_trace, kernel, mode="nearest")
    else:
        trace_smooth = _trace

    peaks, props = scipy_find_peaks(trace_smooth, distance=distance, prominence=prominence)

    if peaks.size == 0:
        return [], []

    sorted_peaks = sorted(zip(props["prominences"], peaks, strict=False), reverse=True)
    top_peaks = sorted(sorted_peaks[:num_resonators], key=itemgetter(1))
    prominences, peaks_indices = zip(*top_peaks, strict=False)

    return list(peaks_indices), list(prominences)


def _group_peaks(
    peaks: Sequence[Peak], x_backward_max: int, x_distance_max: int
) -> list[PeakGroup]:
    """Group peaks in the high-power region based on spatial proximity."""
    if not peaks:
        return []

    peaks = sorted(peaks, key=lambda p: (p.x, -p.y))

    groups: list[PeakGroup] = []
    group: list[Peak] = [peaks[0]]
    x_bottom = peaks[0].x
    y_bottom = peaks[0].y

    for peak in peaks[1:]:
        cond1 = peak.y >= y_bottom and peak.x > x_bottom + x_backward_max
        cond2 = peak.y < y_bottom and (peak.x - x_bottom) > (y_bottom - peak.y) * x_distance_max
        if cond1 or cond2:
            groups.append(PeakGroup(sorted(group, key=attrgetter("y"))))
            group = [peak]
            x_bottom = peak.x
            y_bottom = peak.y
        else:
            group.append(peak)
            if peak.y < y_bottom:
                x_bottom = peak.x
                y_bottom = peak.y

    if group:
        groups.append(PeakGroup(group))

    return groups


def _compose_resonances(
    peak_groups: Sequence[PeakGroup],
    low_power_peaks: Sequence[Peak],
    x_distance_max: int,
    x_backward_max: int,
) -> list[Resonance]:
    """Pair adjacent high-power groups and low-power peaks into resonances.

    Walks the merged-and-sorted sequence of peak groups and low-power peaks
    once. When a low/high pair is adjacent and the offset is within the
    geometric tolerances, the two are paired into a single Resonance and the
    second item is consumed (``skip``). Otherwise the leading item becomes a
    standalone resonance.
    """
    arr_high: list[tuple[PeakGroup | Peak, int]] = [(peak_group, 0) for peak_group in peak_groups]
    arr_low: list[tuple[PeakGroup | Peak, int]] = [(peak, 1) for peak in low_power_peaks]

    arr = sorted(arr_high + arr_low, key=lambda item: (item[0].x, item[1]))
    items: list[PeakGroup | Peak | None] = [item[0] for item in arr]
    items.append(None)

    resonances: list[Resonance] = []
    skip = False

    for p0, p1 in itertools.pairwise(items):
        if skip:
            skip = False
            continue

        match p0, p1:
            case Peak(), PeakGroup():
                if p1.x - p0.x <= x_backward_max:
                    resonances.append(Resonance(p1, p0))
                    skip = True
                else:
                    resonances.append(Resonance(None, p0))
            case PeakGroup(), Peak():
                if p1.x - p0.x < (p0.y - p1.y) * x_distance_max:
                    resonances.append(Resonance(p0, p1))
                    skip = True
                else:
                    resonances.append(Resonance(p0, None))
            case Peak(), (Peak() | None):
                resonances.append(Resonance(None, p0))
            case PeakGroup(), (PeakGroup() | None):
                resonances.append(Resonance(p0, None))

    return resonances


def _group_resonances(
    resonances: Sequence[Resonance], x_distance_max: int
) -> list[list[Resonance]]:
    """Group nearby resonances together."""
    groups: list[list[Resonance]] = []

    if not resonances:
        return groups

    sorted_resonances = sorted(resonances, key=attrgetter("x"))
    group = [sorted_resonances[0]]

    for resonance in sorted_resonances[1:]:
        if resonance.x - group[-1].x > x_distance_max:
            groups.append(group)
            group = [resonance]
        else:
            group.append(resonance)

    if group:
        groups.append(group)

    return groups


def _arg_closest(arr: Sequence[float], v: float) -> int:
    """Find the index of the value closest to v in arr."""
    return int(np.argmin([abs(x - v) for x in arr]))


def _detect_high_power_peak_groups(
    ys: Sequence[float],
    zs: Sequence[Sequence[float]],
    config: EstimateResonatorFrequencyConfig,
) -> list[PeakGroup]:
    """Detect and group peaks across the high-power rows of zs."""
    if config.high_power_min is None or config.high_power_max is None:
        return []

    y_idx_high_min = _arg_closest(ys, config.high_power_min)
    y_idx_high_max = _arg_closest(ys, config.high_power_max)

    if y_idx_high_min > y_idx_high_max:
        y_idx_high_min, y_idx_high_max = y_idx_high_max, y_idx_high_min

    high_power_peaks: list[Peak] = []
    for y_idx in range(y_idx_high_min, y_idx_high_max + 1):
        peak_xs, prominences = _detect_peaks(
            trace=zs[y_idx],
            num_resonators=config.num_resonators * 2,
            smooth_sigma=config.find_peaks_conf_high.smooth_sigma,
            distance=config.find_peaks_conf_high.distance,
            prominence=config.find_peaks_conf_high.prominence,
        )
        high_power_peaks.extend(
            Peak(peak_idx, y_idx, prominence)
            for peak_idx, prominence in zip(peak_xs, prominences, strict=False)
        )

    return _group_peaks(
        high_power_peaks,
        config.group_peaks_conf.x_backward_max,
        config.group_peaks_conf.x_distance_max,
    )


def _detect_low_power_peaks(
    ys: Sequence[float],
    zs: Sequence[Sequence[float]],
    config: EstimateResonatorFrequencyConfig,
) -> list[Peak]:
    """Detect peaks in the low-power row of zs."""
    y_idx_low = _arg_closest(ys, config.low_power)
    peak_xs, prominences = _detect_peaks(
        trace=zs[y_idx_low],
        num_resonators=config.num_resonators * 2,
        smooth_sigma=config.find_peaks_conf_low.smooth_sigma,
        distance=config.find_peaks_conf_low.distance,
        prominence=config.find_peaks_conf_low.prominence,
    )
    return [
        Peak(peak_idx, y_idx_low, prominence)
        for peak_idx, prominence in zip(peak_xs, prominences, strict=False)
    ]


def _select_resonances(
    peak_groups: Sequence[PeakGroup],
    low_power_peaks: Sequence[Peak],
    config: EstimateResonatorFrequencyConfig,
) -> tuple[list[Resonance], list[Resonance]]:
    """Compose, group and rank resonances; return (selected, rejected)."""
    composed = _compose_resonances(
        peak_groups,
        low_power_peaks,
        config.compose_resonances_conf.x_distance_max,
        config.compose_resonances_conf.x_backward_max,
    )
    grouped = _group_resonances(composed, config.group_resonances_conf.x_distance_max)

    selected: list[Resonance] = []
    rejected: list[Resonance] = []
    for res_group in grouped:
        sorted_group = sorted(res_group, key=attrgetter("score"), reverse=True)
        selected.append(sorted_group[0])
        rejected.extend(sorted_group[1:])

    selected = sorted(selected, key=attrgetter("score"), reverse=True)
    rejected.extend(selected[config.num_resonators :])
    selected = selected[: config.num_resonators]

    selected = sorted(selected, key=attrgetter("x"))
    rejected = sorted(rejected, key=attrgetter("x"))

    return selected, rejected


def estimate_resonator_frequency(
    xs: Sequence[float],
    ys: Sequence[float],
    zs: Sequence[Sequence[float]],
    config: EstimateResonatorFrequencyConfig | None = None,
) -> tuple[list[Resonance], list[Resonance], list[float]]:
    """Estimate resonator frequencies from 2D spectroscopy data.

    Args:
        xs: Frequency values (x-axis).
        ys: Power values (y-axis).
        zs: 2D intensity data (power x frequency).
        config: Configuration for the estimation algorithm.

    Returns:
        A tuple of (resonances, rejected, frequencies):
        - resonances: list of selected Resonance objects (top ``num_resonators``).
        - rejected: list of Resonance objects rejected by grouping/scoring.
        - frequencies: list of estimated resonator frequencies (same units as xs).
    """
    if config is None:
        config = EstimateResonatorFrequencyConfig()

    peak_groups = _detect_high_power_peak_groups(ys, zs, config)
    low_power_peaks = _detect_low_power_peaks(ys, zs, config)
    selected, rejected = _select_resonances(peak_groups, low_power_peaks, config)

    frequencies = [float(xs[r.x]) for r in selected]

    return selected, rejected, frequencies


def estimate_resonator_frequency_from_figure(
    fig: go.Figure,
    config: EstimateResonatorFrequencyConfig | None = None,
) -> tuple[list[Resonance], list[Resonance], list[float]]:
    """Estimate resonator frequencies from a plotly figure.

    Args:
        fig: Plotly figure containing the spectroscopy data.
             Expected to have a heatmap trace with x (frequency),
             y (power), and z (intensity) data.
        config: Configuration for the estimation algorithm.

    Returns:
        A tuple of (resonances, rejected, frequencies).
    """
    trace = fig.data[0]
    xs = list(trace.x)
    ys = list(trace.y)
    zs = list(trace.z)

    return estimate_resonator_frequency(xs, ys, zs, config)


# Default color palette for marking peaks
MARKER_COLORS = [
    "#636EFA",  # blue
    "#EF553B",  # red
    "#00CC96",  # green
    "#AB63FA",  # purple
    "#FFA15A",  # orange
    "#19D3F3",  # cyan
    "#FF6692",  # pink
    "#B6E880",  # lime
    "#FF97FF",  # magenta
    "#FECB52",  # yellow
]


def create_marked_figure(
    fig: go.Figure,
    resonances: list[Resonance],
    rejected_resonances: list[Resonance] | None = None,
    show_high_power_peaks: bool = True,
    selected_color: str = "red",
    rejected_color: str = "orange",
) -> go.Figure:
    """Create a copy of the figure with resonance markers added.

    Args:
        fig: Original plotly figure containing the spectroscopy data.
        resonances: List of detected resonances to mark as selected.
        rejected_resonances: List of rejected resonances to mark differently.
        show_high_power_peaks: Whether to show high-power peak markers.
        selected_color: Color for selected resonance vertical lines.
        rejected_color: Color for rejected resonance vertical lines.

    Returns:
        A new figure with markers added.
    """
    import plotly.graph_objects as pgo

    marked_fig = pgo.Figure(fig)

    trace = fig.data[0]
    xs = list(trace.x)
    ys = list(trace.y)

    all_resonances = list(resonances)
    if rejected_resonances:
        all_resonances.extend(rejected_resonances)

    if show_high_power_peaks:
        peak_groups = sorted(
            [res.high_power_peaks for res in all_resonances if res.high_power_peaks is not None],
            key=lambda pg: pg.x,
        )

        for i, peak_group in enumerate(peak_groups):
            marker_xs = []
            marker_ys = []

            for peak in peak_group.peaks:
                marker_xs.append(xs[peak.x])
                marker_ys.append(ys[peak.y])

            color = MARKER_COLORS[i % len(MARKER_COLORS)]
            marked_fig.add_trace(
                pgo.Scatter(
                    x=marker_xs,
                    y=marker_ys,
                    mode="markers",
                    marker={"color": color, "size": 8, "symbol": "x"},
                    showlegend=False,
                )
            )

    for resonance in resonances:
        marked_fig.add_vline(
            x=xs[resonance.x],
            line_width=1,
            line_color=selected_color,
            line_dash="dash",
        )

    if rejected_resonances:
        for resonance in rejected_resonances:
            marked_fig.add_vline(
                x=xs[resonance.x],
                line_width=1,
                line_color=rejected_color,
                line_dash="dash",
            )

    return marked_fig


def estimate_and_mark_figure(
    fig: go.Figure,
    config: EstimateResonatorFrequencyConfig | None = None,
    show_rejected: bool = True,
) -> tuple[go.Figure, list[Resonance], list[float]]:
    """Estimate resonator frequencies and create a marked figure.

    Args:
        fig: Plotly figure containing the spectroscopy data.
        config: Configuration for the estimation algorithm.
        show_rejected: Whether to show rejected resonances on the marked figure.

    Returns:
        A tuple of (marked_figure, resonances, frequencies).
    """
    resonances, rejected, frequencies = estimate_resonator_frequency_from_figure(fig, config)

    marked_fig = create_marked_figure(
        fig,
        resonances,
        rejected_resonances=rejected if show_rejected else None,
    )

    return marked_fig, resonances, frequencies
