"""Remove false spikes from spectroscopy data.

This module provides functions to remove measurement-instrument-derived
false spikes from 2D spectroscopy data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    import plotly.graph_objs as go


@dataclass
class RemoveFalseSpikeRange:
    """Defines a frequency range to remove false spikes."""

    x_min: float
    x_max: float

    def __post_init__(self) -> None:
        if self.x_min > self.x_max:
            raise ValueError(f"x_min ({self.x_min}) must be <= x_max ({self.x_max})")


def remove_false_spike(
    xs: Sequence[float],
    zs: list[list[float]],
    ranges: Sequence[RemoveFalseSpikeRange],
) -> list[list[float]]:
    """Remove false spikes from 2D data by interpolating specified ranges.

    Args:
        xs: Frequency values (x-axis).
        zs: 2D intensity data (power x frequency). Will be modified in place.
        ranges: List of frequency ranges to interpolate over.

    Returns:
        The modified zs data with false spikes removed.
    """
    for spike_range in ranges:
        idx_min = None
        idx_max = None
        x_min = f"{spike_range.x_min:.3f}"
        x_max = f"{spike_range.x_max:.3f}"

        for i, x in enumerate(xs):
            x_str = f"{x:.3f}"
            if x_str == x_min:
                idx_min = i
            if x_str == x_max:
                idx_max = i
            if idx_min and idx_max:
                break

        if idx_min is None or idx_max is None:
            raise ValueError(f"Spike range [{x_min}, {x_max}] not found in x-axis")

        if idx_min == 0:
            raise ValueError(f"Spike range [{x_min}, {x_max}] starts at x-axis boundary")

        if idx_max == len(xs) - 1:
            raise ValueError(f"Spike range [{x_min}, {x_max}] ends at x-axis boundary")

        for z_row in zs:
            mean = (z_row[idx_min - 1] + z_row[idx_max + 1]) / 2.0
            for idx in range(idx_min, idx_max + 1):
                z_row[idx] = mean

    return zs


def remove_false_spike_from_figure(
    fig: go.Figure,
    ranges: Sequence[RemoveFalseSpikeRange],
) -> go.Figure:
    """Remove false spikes from a plotly figure.

    Args:
        fig: Plotly figure containing the spectroscopy data.
        ranges: List of frequency ranges to interpolate over.

    Returns:
        The modified figure with false spikes removed.
    """
    trace = fig.data[0]
    xs = list(trace.x)
    zs = [list(row) for row in trace.z]

    remove_false_spike(xs, zs, ranges)

    # Update the figure's z data
    fig.data[0].z = zs

    return fig


def remove_known_false_spikes_from_figure(fig: go.Figure) -> go.Figure:
    """Return a copy of a resonator spectroscopy figure without known instrument spikes.

    The spike ranges depend on the readout band (low band below 7 GHz, high band
    above). A range is applied only when both of its edges are interior grid
    points of the sweep, so the interpolation always has neighbors.

    Args:
        fig: Raw resonator spectroscopy figure. It is not modified.

    Returns:
        A denoised copy of ``fig``.
    """
    import plotly.graph_objects as pgo

    analysis_fig = pgo.Figure(fig)
    trace = analysis_fig.data[0]
    xs = list(trace.x)
    if not xs:
        return analysis_fig

    spike_ranges = (
        [
            RemoveFalseSpikeRange(5.998, 6.000),
            RemoveFalseSpikeRange(6.498, 6.500),
        ]
        if max(xs) < 7.0
        else [
            RemoveFalseSpikeRange(9.998, 10.000),
            RemoveFalseSpikeRange(10.248, 10.250),
            RemoveFalseSpikeRange(10.498, 10.500),
        ]
    )
    rounded_xs = {f"{x:.3f}": index for index, x in enumerate(xs)}
    applicable_ranges = []
    for spike_range in spike_ranges:
        idx_min = rounded_xs.get(f"{spike_range.x_min:.3f}")
        idx_max = rounded_xs.get(f"{spike_range.x_max:.3f}")
        if idx_min not in (None, 0) and idx_max not in (None, len(xs) - 1):
            applicable_ranges.append(spike_range)
    return remove_false_spike_from_figure(analysis_fig, applicable_ranges)
