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

        for i, x in enumerate(xs):
            if idx_min is None and x >= spike_range.x_min:
                idx_min = i
            if x <= spike_range.x_max:
                idx_max = i

        if idx_min is None or idx_max is None:
            continue

        if idx_min == 0 or idx_max == len(xs) - 1:
            continue

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
