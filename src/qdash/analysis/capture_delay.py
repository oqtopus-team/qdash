"""Locate readout pulse edges and choose capture delays.

Ported from https://github.com/orangekame3/capture-delay-tools. The edge fit is
implemented here with SciPy instead of sqe-analysis, which requires Python 3.13.

Delays are handled as total nanoseconds on a backend-specific grid:

- QuEL-1 combines ``capture_delay`` in 128 ns blocks (``ndelay``) with
  ``capture_delay_word`` in 8 ns words, restricted to multiples of 4 words. The
  total ``128 * capture_delay + 8 * capture_delay_word`` ns has a 32 ns grid.
- QuEL-3 takes ``capture_delay`` in ns on its 0.8 ns readout sampling grid.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from scipy.optimize import least_squares

if TYPE_CHECKING:
    from collections.abc import Sequence

BLOCK_NS = 128.0
WORD_NS = 8.0
WORD_STEP = 4
QUEL1_RESOLUTION_NS = WORD_NS * WORD_STEP
WORDS_PER_BLOCK = int(BLOCK_NS / WORD_NS)
QUEL3_RESOLUTION_NS = 0.8
# Space kept between the pulse and each end of the capture window.
MARGIN_NS = 32.0
# Observations whose pulse midpoints lie within this distance belong together.
CLUSTER_TOLERANCE_NS = BLOCK_NS / 2


def total_delay_ns(delay: int, capture_delay_word: int) -> float:
    """Return the combined coarse and word offset in nanoseconds."""
    return delay * BLOCK_NS + capture_delay_word * WORD_NS


def split_total_delay(total_ns: float) -> tuple[int, int]:
    """Split a QuEL-1 total delay on the 32 ns grid into ``(capture_delay, word)``."""
    coarse, word = divmod(round(total_ns / WORD_NS), WORDS_PER_BLOCK)
    return int(coarse), int(word)


@dataclass(frozen=True)
class Waveform:
    """One averaged complex capture, with time measured in nanoseconds."""

    mux: int
    target: str
    total_delay_ns: float
    time_ns: np.ndarray
    iq: np.ndarray
    pulse_duration_ns: float = math.nan
    setting: str = ""

    def __post_init__(self) -> None:
        """Require matching, finite, evenly spaced samples."""
        time = np.asarray(self.time_ns, dtype=float)
        iq = np.asarray(self.iq, dtype=np.complex128)
        if time.ndim != 1 or iq.shape != time.shape or time.size < 2:
            raise ValueError(f"{self.target}: time and IQ must be matching 1D arrays.")
        if not np.all(np.isfinite(time)) or not np.all(np.isfinite(iq)):
            raise ValueError(f"{self.target}: waveform contains non-finite samples.")
        spacing = np.diff(time)
        if not np.all(spacing > 0) or not np.allclose(spacing, spacing[0]):
            raise ValueError(f"{self.target}: time_ns must be increasing and evenly spaced.")
        object.__setattr__(self, "time_ns", time)
        object.__setattr__(self, "iq", iq)

    @property
    def label(self) -> str:
        """Return the delay setting shown in figures."""
        return self.setting or f"{self.total_delay_ns:g} ns"

    @property
    def sampling_period_ns(self) -> float:
        """Return the sample spacing in nanoseconds."""
        return float(self.time_ns[1] - self.time_ns[0])

    @property
    def window_center_ns(self) -> float:
        """Return the center of the capture window."""
        return float(self.time_ns.size * self.sampling_period_ns / 2)


@dataclass(frozen=True)
class EdgeResult:
    """Detected edges of one waveform."""

    waveform: Waveform
    success: bool = False
    rise_ns: float | None = None
    fall_ns: float | None = None
    snr: float | None = None
    edge_kind: str = "none"
    reason: str = "low_contrast"

    @property
    def mux(self) -> int:
        """Return the measured MUX index."""
        return self.waveform.mux

    @property
    def target(self) -> str:
        """Return the captured target label."""
        return self.waveform.target

    @property
    def time_start_ns(self) -> float:
        """Return the first sample time."""
        return float(self.waveform.time_ns[0])

    @property
    def time_stop_ns(self) -> float:
        """Return the last sample time."""
        return float(self.waveform.time_ns[-1])


@dataclass(frozen=True)
class SelectionReport:
    """Delay candidate chosen from a sweep of one MUX."""

    mux: int
    reason: str
    center_ns: float
    selected_total_ns: float | None = None
    estimated_midpoint_ns: float | None = None
    supporting_targets: tuple[str, ...] = ()
    support_points: int = 0


@dataclass(frozen=True)
class FinalReport:
    """Delay derived from the verification capture of one MUX."""

    mux: int
    reason: str
    final_total_ns: float | None = None
    predicted_midpoint_ns: float | None = None
    predicted_pre_margin_ns: float | None = None
    predicted_post_margin_ns: float | None = None
    unverified_targets: tuple[str, ...] = field(default_factory=tuple)


def _logistic(x: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + np.tanh(0.5 * x))


def _fit_step(time: np.ndarray, iq: np.ndarray) -> tuple[bool, float, float]:
    """Fit one complex logistic step and return ``(ok, location_ns, snr)``.

    The two complex levels are solved linearly for each trial location and
    width, so only those two values are optimized nonlinearly.
    """
    dt = float(time[1] - time[0])
    head = max(2, time.size // 8)
    distance = np.abs(iq - iq[:head].mean())
    crossing = np.flatnonzero(distance >= (distance.min() + distance.max()) / 2)
    t0_init = float(time[crossing[0]]) if crossing.size else float(time.mean())

    def levels(params: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        step = _logistic((time - params[0]) / np.exp(params[1]))
        basis = np.column_stack([1.0 - step, step])
        coefficients, *_ = np.linalg.lstsq(basis, iq, rcond=None)
        return coefficients, basis @ coefficients

    def residuals(params: np.ndarray) -> np.ndarray:
        _, model = levels(params)
        delta = iq - model
        return np.concatenate([delta.real, delta.imag])

    try:
        fitted = least_squares(
            residuals,
            x0=np.array([t0_init, math.log(dt)]),
            bounds=(
                [float(time[0]), math.log(dt / 10)],
                [float(time[-1]), math.log(time[-1] - time[0])],
            ),
        )
    except (ValueError, np.linalg.LinAlgError):
        return False, math.nan, math.nan
    coefficients, model = levels(fitted.x)
    noise = math.sqrt(float(np.mean(np.abs(iq - model) ** 2)) / 2)
    contrast = float(abs(coefficients[1] - coefficients[0]))
    snr = contrast / max(noise, 1e-12)
    location = float(fitted.x[0])
    ok = bool(fitted.success) and math.isfinite(location) and math.isfinite(snr)
    return ok, location, snr


def analyze_waveform(waveform: Waveform, *, snr_threshold: float, smoothing: int) -> EdgeResult:
    """Separate the pulse plateau, then fit its rising and falling edges."""
    time, values = waveform.time_ns, waveform.iq
    if time.size < max(16, 2 * smoothing + 1):
        raise ValueError(f"{waveform.target}: insufficient samples for edge analysis.")
    guard = max(3, smoothing)
    envelope = np.abs(values)
    padded = np.pad(envelope, (smoothing // 2, smoothing - 1 - smoothing // 2), mode="edge")
    smooth = np.convolve(padded, np.ones(smoothing) / smoothing, mode="valid")
    # Adjacent differences estimate noise without treating the pulse height as noise.
    differences = np.diff(values)
    mad = [
        float(np.median(np.abs(part - np.median(part))))
        for part in (differences.real, differences.imag)
    ]
    noise = max(math.hypot(*mad) / math.sqrt(2), 1e-12)
    low, high = np.percentile(smooth, [10, 90])
    contrast = float(high - low)
    if contrast < snr_threshold * noise:
        return EdgeResult(waveform)

    mask = smooth > low + contrast / 2
    boundaries = np.diff(np.r_[False, mask, False].astype(int))
    runs = [
        (int(a), int(b))
        for a, b in zip(
            np.flatnonzero(boundaries == 1), np.flatnonzero(boundaries == -1), strict=True
        )
        if b - a >= guard
    ]
    if len(runs) != 1:
        reason = "multiple_pulses" if len(runs) > 1 else "no_pulse"
        return EdgeResult(waveform, reason=reason)

    start, stop = runs[0]
    rising, falling = start >= guard, stop <= time.size - guard
    edge_kind = (
        "both"
        if rising and falling
        else "rising_only"
        if rising
        else "falling_only"
        if falling
        else "clipped"
    )
    if not rising and not falling:
        return EdgeResult(waveform, edge_kind=edge_kind, reason="no_edges")

    midpoint = (start + stop) // 2
    # Finely sampled captures resolve the edge ramp, so allow a few ns of shape.
    tolerance = max(guard * waveform.sampling_period_ns, 8.0)
    rise = fall = snr = None
    if rising:
        end = midpoint if falling else time.size
        ok, edge, edge_snr = _fit_step(time[:end], values[:end])
        if ok and edge_snr >= snr_threshold and abs(edge - time[start]) <= tolerance:
            rise, snr = edge, edge_snr
    if falling:
        begin = midpoint if rising else 0
        ok, edge, edge_snr = _fit_step(time[begin:], values[begin:])
        if ok and edge_snr >= snr_threshold and abs(edge - time[stop]) <= tolerance:
            fall, snr = edge, edge_snr if snr is None else min(snr, edge_snr)
    success = rise is not None or fall is not None
    return EdgeResult(
        waveform,
        success=success,
        rise_ns=rise,
        fall_ns=fall,
        snr=snr,
        edge_kind=edge_kind,
        reason="ok" if success else "edge_fit_failed",
    )


def analyze_waveforms(
    waveforms: Sequence[Waveform], *, snr_threshold: float = 5.0, smoothing: int = 5
) -> list[EdgeResult]:
    """Locate pulse edges in every waveform."""
    if not waveforms:
        raise ValueError("Measure waveforms before analyzing them.")
    if smoothing < 1 or int(smoothing) != smoothing or snr_threshold <= 0:
        raise ValueError("Smoothing must be a positive integer and SNR must be positive.")
    return [
        analyze_waveform(waveform, snr_threshold=snr_threshold, smoothing=int(smoothing))
        for waveform in waveforms
    ]


def _centered_delay(
    rises: np.ndarray,
    falls: np.ndarray,
    starts: np.ndarray,
    stops: np.ndarray,
    center: float,
    resolution: float,
) -> tuple[float | None, str]:
    """Choose the closest feasible grid point to the envelope midpoint."""
    lower = max(0.0, float(np.max(falls - stops + MARGIN_NS)))
    upper = float(np.min(rises - starts - MARGIN_NS))
    lo = math.ceil(round(lower / resolution, 9)) * resolution
    hi = math.floor(round(upper / resolution, 9)) * resolution
    if hi < 0:
        return None, "insufficient_pre_margin"
    if lo > hi:
        return None, "pulse_does_not_fit"
    midpoint = (float(np.min(rises)) + float(np.max(falls))) / 2
    ideal = round((midpoint - center) / resolution) * resolution
    # Snap again so the float total stays an exact multiple of the grid.
    total = round(min(max(ideal, lo), hi) / resolution) * resolution
    return round(total, 6), "ready"


def _as_float(value: float | None) -> float:
    """Return a missing edge as NaN so numeric checks can treat both alike."""
    return math.nan if value is None else float(value)


def select_delay(
    results: Sequence[EdgeResult],
    *,
    mux: int,
    center: float,
    resolution_ns: float = QUEL1_RESOLUTION_NS,
) -> SelectionReport:
    """Center the pulse envelope using two consistent observations per target."""
    group = [result for result in results if result.mux == mux]
    targets = list(dict.fromkeys(result.target for result in group))
    estimates: list[dict[str, float | str]] = []
    for result in group:
        if not result.success:
            continue
        rise, fall = _as_float(result.rise_ns), _as_float(result.fall_ns)
        has_rise, has_fall = math.isfinite(rise), math.isfinite(fall)
        if not has_rise and not has_fall:
            continue
        margin = max(MARGIN_NS, 3 * result.waveform.sampling_period_ns)
        observed = [edge for edge in (rise, fall) if math.isfinite(edge)]
        if any(
            edge - result.time_start_ns < margin or result.time_stop_ns - edge < margin
            for edge in observed
        ):
            continue
        duration = result.waveform.pulse_duration_ns
        if not (has_rise and has_fall):
            # One clipped edge is inferred from the recorded readout duration.
            if not math.isfinite(duration) or duration <= 0:
                continue
            if has_rise:
                fall = rise + duration
            else:
                rise = fall - duration
        if fall <= rise:
            continue
        offset = result.waveform.total_delay_ns
        estimates.append(
            {
                "target": result.target,
                "offset": offset,
                "rise": offset + rise,
                "fall": offset + fall,
                "midpoint": offset + (rise + fall) / 2,
                "start": result.time_start_ns,
                "stop": result.time_stop_ns,
            }
        )

    supported: list[dict[str, float | str | int]] = []
    ambiguous = False
    for target in targets:
        rows = sorted(
            (row for row in estimates if row["target"] == target),
            key=lambda row: float(row["midpoint"]),
        )
        clusters: list[list[dict[str, float | str]]] = []
        for row in rows:
            if (
                not clusters
                or float(row["midpoint"]) - float(clusters[-1][0]["midpoint"])
                > CLUSTER_TOLERANCE_NS
            ):
                clusters.append([])
            clusters[-1].append(row)
        # A single capture can alias by whole windows; require two distinct delays.
        valid = [cluster for cluster in clusters if len({row["offset"] for row in cluster}) >= 2]
        if len(valid) > 1:
            ambiguous = True
        if len(valid) == 1:
            cluster = valid[0]
            supported.append(
                {
                    "target": target,
                    "points": len({row["offset"] for row in cluster}),
                    "rise": float(np.median([float(row["rise"]) for row in cluster])),
                    "fall": float(np.median([float(row["fall"]) for row in cluster])),
                    "start": max(float(row["start"]) for row in cluster),
                    "stop": min(float(row["stop"]) for row in cluster),
                }
            )

    supporting_targets = tuple(sorted(str(row["target"]) for row in supported))
    support_points = sum(int(row["points"]) for row in supported)
    if ambiguous:
        return SelectionReport(
            mux=mux,
            reason="conflicting_candidates",
            center_ns=center,
            supporting_targets=supporting_targets,
            support_points=support_points,
        )
    if not targets or len(supported) != len(targets):
        return SelectionReport(
            mux=mux,
            reason="insufficient_support",
            center_ns=center,
            supporting_targets=supporting_targets,
            support_points=support_points,
        )

    rises = np.array([float(row["rise"]) for row in supported])
    falls = np.array([float(row["fall"]) for row in supported])
    total, reason = _centered_delay(
        rises,
        falls,
        np.array([float(row["start"]) for row in supported]),
        np.array([float(row["stop"]) for row in supported]),
        center,
        resolution_ns,
    )
    estimated_midpoint = (float(rises.min()) + float(falls.max())) / 2
    if total is None:
        return SelectionReport(
            mux=mux,
            reason=reason,
            center_ns=center,
            estimated_midpoint_ns=estimated_midpoint,
            supporting_targets=supporting_targets,
            support_points=support_points,
        )
    return SelectionReport(
        mux=mux,
        reason="selected",
        center_ns=center,
        selected_total_ns=total,
        estimated_midpoint_ns=estimated_midpoint,
        supporting_targets=supporting_targets,
        support_points=support_points,
    )


def finalize_delay(
    results: Sequence[EdgeResult],
    selection: SelectionReport,
    *,
    center: float,
    resolution_ns: float = QUEL1_RESOLUTION_NS,
) -> FinalReport:
    """Choose a delay containing every verified pulse with 32 ns margins."""
    mux = selection.mux
    selected = _as_float(selection.selected_total_ns)
    group = [
        result
        for result in results
        if result.mux == mux and math.isclose(result.waveform.total_delay_ns, selected)
    ]
    good = [
        result for result in group if result.success and math.isfinite(_as_float(result.rise_ns))
    ]
    good_targets = {result.target for result in good}
    required = set(selection.supporting_targets) | {result.target for result in group}
    unverified = tuple(sorted({result.target for result in group} - good_targets))
    if not good or not required.issubset(good_targets):
        return FinalReport(mux=mux, reason="verification_failed", unverified_targets=unverified)
    rise = np.array([_as_float(result.rise_ns) for result in good])
    fall = np.array([_as_float(result.fall_ns) for result in good])
    if not np.all(np.isfinite(fall)):
        return FinalReport(mux=mux, reason="missing_falling_edge", unverified_targets=unverified)

    starts = np.array([result.time_start_ns for result in good])
    stops = np.array([result.time_stop_ns for result in good])
    if np.any(rise < starts) or np.any(fall <= rise) or np.any(fall > stops):
        return FinalReport(mux=mux, reason="invalid_pulse_bounds", unverified_targets=unverified)

    offsets = np.array([result.waveform.total_delay_ns for result in good])
    arrivals, departures = offsets + rise, offsets + fall
    total, reason = _centered_delay(arrivals, departures, starts, stops, center, resolution_ns)
    if total is None:
        return FinalReport(mux=mux, reason=reason, unverified_targets=unverified)

    predicted_rises, predicted_falls = arrivals - total, departures - total
    pre_margin = float((predicted_rises - starts).min())
    post_margin = float((stops - predicted_falls).min())
    # The grid bounds already keep MARGIN_NS; allow only floating-point error.
    tolerance = 1e-6
    if total < 0 or pre_margin < MARGIN_NS - tolerance:
        reason = "insufficient_pre_margin"
    elif post_margin < MARGIN_NS - tolerance:
        reason = "insufficient_post_margin"
    return FinalReport(
        mux=mux,
        reason=reason,
        final_total_ns=total if reason == "ready" else None,
        predicted_midpoint_ns=float((predicted_rises.min() + predicted_falls.max()) / 2),
        predicted_pre_margin_ns=pre_margin,
        predicted_post_margin_ns=post_margin,
        unverified_targets=unverified,
    )
