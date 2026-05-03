"""Bare-shift boundary estimation for resonator spectroscopy data.

Provides estimators that decide where the high-power (curved) and low-power
(straight) regions of a 2D power-frequency spectroscopy sweep should be
sampled when running resonator-frequency estimation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt
from scipy.fft import fft

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True)
class BareShiftBoundary:
    """Boundary describing the high/low-power regions for resonator analysis."""

    low_power: float
    high_power_min: float | None
    high_power_max: float | None


@dataclass(frozen=True)
class BareShiftDebugOptions:
    """Optional debug-output configuration for boundary estimators."""

    artifact_prefix: str | None = None


@dataclass(frozen=True)
class BareShiftBoundaryEstimator(ABC):
    """Abstract base class for bare-shift boundary estimators."""

    @abstractmethod
    def estimate_bare_shift_boundary(
        self,
        xs: Sequence[float],
        ys: Sequence[float],
        zs: Sequence[Sequence[float]],
        *,
        debug: BareShiftDebugOptions | None = None,
    ) -> BareShiftBoundary:
        """Return the bare-shift boundary for the given data."""


@dataclass(frozen=True)
class ConfigBareShiftBoundaryEstimator(BareShiftBoundaryEstimator):
    """Estimator that returns boundaries from explicit configuration."""

    low_power: float
    high_power_min: float
    high_power_max: float

    def estimate_bare_shift_boundary(
        self,
        xs: Sequence[float],
        ys: Sequence[float],
        zs: Sequence[Sequence[float]],
        *,
        debug: BareShiftDebugOptions | None = None,
    ) -> BareShiftBoundary:
        return BareShiftBoundary(
            low_power=self.low_power,
            high_power_min=self.high_power_min,
            high_power_max=self.high_power_max,
        )


@dataclass(frozen=True)
class HighFrequencyStrengthBareShiftBoundaryEstimator(BareShiftBoundaryEstimator):
    """Detects the bare-shift boundary by tracking the high-frequency FFT energy.

    The estimator computes the mean of the high-frequency FFT bins for each
    power row, then picks the first local minimum whose value sits below
    ``strength_limit``. Powers above this index are treated as the "high
    power" region (curved response); the picked row itself is used as the
    low-power sample.
    """

    strength_limit: float

    def estimate_bare_shift_boundary(
        self,
        xs: Sequence[float],
        ys: Sequence[float],
        zs: Sequence[Sequence[float]],
        *,
        debug: BareShiftDebugOptions | None = None,
    ) -> BareShiftBoundary:
        high_freq = np.asarray(
            [self.compute_high_frequency_strength(trace) for trace in zs],
            dtype=np.float64,
        )

        bare_shift_boundary = self.compute_first_local_minimum_index(high_freq)

        if debug and debug.artifact_prefix:
            self._plot_fft(debug.artifact_prefix, xs, zs)
            self._plot_high_frequency_strength(debug.artifact_prefix, high_freq)

        if bare_shift_boundary + 1 < len(ys):
            return BareShiftBoundary(
                low_power=float(ys[bare_shift_boundary]),
                high_power_min=float(ys[bare_shift_boundary + 1]),
                high_power_max=float(ys[-1]),
            )

        return BareShiftBoundary(
            low_power=float(ys[bare_shift_boundary]),
            high_power_min=None,
            high_power_max=None,
        )

    def compute_first_local_minimum_index(
        self,
        high_frequency_strength: npt.NDArray[np.float64],
    ) -> int:
        arr = np.concatenate(([float("inf")], high_frequency_strength, [float("inf")]))

        diffs = np.diff(arr)
        is_local_min = np.logical_and((diffs < 0)[:-1], (diffs > 0)[1:])

        is_strength_less_than_limit = high_frequency_strength < self.strength_limit
        candidates = np.logical_and(is_local_min, is_strength_less_than_limit)

        if np.any(candidates):
            return int(np.argmax(candidates))

        return len(high_frequency_strength) - 1

    @staticmethod
    def compute_high_frequency_strength(trace: Sequence[float]) -> float:
        N = len(trace)
        trace_fft = fft(np.asarray(trace, dtype=np.float64))
        trace_fft = np.abs(trace_fft[9 : N // 2])
        return float(np.mean(trace_fft))

    @staticmethod
    def _plot_fft(
        artifact_prefix: str,
        xs: Sequence[float],
        zs: Sequence[Sequence[float]],
    ) -> None:
        import matplotlib.pyplot as plt
        from scipy.fft import fftfreq

        plt.clf()
        N = len(zs[0])
        xs_fft = fftfreq(N, xs[1] - xs[0])[: N // 2]

        for i, trace in enumerate(zs):
            if i % 2 == 1:
                continue
            zs_fft = fft(np.asarray(trace, dtype=np.float64))
            plt.plot(xs_fft[1:], 2.0 / N * np.abs(zs_fft[1 : N // 2]), label=f"y={i}")

        plt.grid()
        plt.legend()
        plt.savefig(artifact_prefix + "0_fft.png")

    @staticmethod
    def _plot_high_frequency_strength(
        artifact_prefix: str,
        high_freq: npt.NDArray[np.float64],
    ) -> None:
        import matplotlib.pyplot as plt

        plt.clf()
        plt.plot(high_freq)
        plt.grid()
        plt.savefig(artifact_prefix + "1_high_frequency_strength.png")


_BARE_SHIFT_ESTIMATORS: dict[str, type[BareShiftBoundaryEstimator]] = {
    "config": ConfigBareShiftBoundaryEstimator,
    "high_frequency_strength": HighFrequencyStrengthBareShiftBoundaryEstimator,
}


def create_bare_shift_boundary_estimator(
    type: str,
    args: dict | None = None,
) -> BareShiftBoundaryEstimator:
    """Build a bare-shift boundary estimator from a type tag and kwargs.

    Mirrors the JSON config format used by the standalone scripts:
        {"type": "high_frequency_strength", "args": {"strength_limit": 4.0}}
    """
    cls = _BARE_SHIFT_ESTIMATORS[type]
    return cls(**(args or {}))
