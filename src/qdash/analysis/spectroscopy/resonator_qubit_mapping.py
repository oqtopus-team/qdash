"""Resonator-to-qubit mapping from a grid of 1D high-power qubit spectroscopy traces.

Resonator spectroscopy finds the resonators of a MUX but cannot tell which qubit
each one reads. Driving qubit ``i`` at high power while reading out at resonator
candidate ``j`` produces a dispersive phase response only when candidate ``j`` is
coupled to qubit ``i``. Measuring every (qubit, candidate) pair gives a score
matrix whose best one-to-one assignment is the mapping.

This module is pure analysis: it scores traces, solves the assignment and draws
the review figure. It does not estimate qubit frequencies.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from numpy.typing import ArrayLike

MappingStatus = Literal["mapped", "no_response", "ambiguous"]

DEFAULT_NOISE_FLOOR_SIGMA = 3.0
"""Robust z-score below which a trace point counts as noise."""

DEFAULT_MIN_RESPONSE_SCORE = 5.0
"""Minimum score of a significant response (sigma-points above the noise floor)."""

DEFAULT_MIN_MARGIN_RATIO = 2.0
"""Minimum ratio between the selected cells and the strongest competing cells."""

MAX_MAPPING_SIZE = 6
"""Largest number of qubits or candidates solved by exact enumeration."""

_MAD_TO_SIGMA = 1.4826
_MIN_TRACE_POINTS = 5
PHASE_NOISE_FLOOR = 1e-3
"""Smallest noise scale in rad, used when the MAD is zero or below it."""

# Qubex figure style (qxvisualizer.style), restated here so this module does not
# import qubex. The selected cell also carries a text badge, so color never
# carries the outcome alone.
_FONT_FAMILY = "Times New Roman, Times, serif"
_TITLE_FONT_SIZE = 18
_SUBTITLE_FONT_SIZE = 13
_AXIS_TICKFONT_SIZE = 11
_AXIS_TITLEFONT_SIZE = 12
_SUBPLOT_TITLE_FONT_SIZE = 11
_SELECTED_COLOR = "#0C5DA5"  # Qubex blue
_AMBIGUOUS_COLOR = "#FF9500"  # Qubex orange
_IDLE_COLOR = "#9e9e9e"  # Qubex gray
_BADGE_TEXT_COLORS = {_SELECTED_COLOR: "white", _AMBIGUOUS_COLOR: "black"}


@dataclass(frozen=True)
class ResonatorCandidate:
    """A resonator found by resonator spectroscopy, with its provisional readout settings.

    Attributes:
        candidate_index: Position of the candidate in frequency order.
        source_qid: Qubit whose calibration currently stores these values.
        frequency: Resonator (readout) frequency in GHz.
        readout_amplitude: Readout amplitude in a.u. chosen for this resonator.
        optimal_power: Readout power in dB chosen for this resonator, if stored.
    """

    candidate_index: int
    source_qid: str
    frequency: float
    readout_amplitude: float
    optimal_power: float | None = None


@dataclass(frozen=True)
class QubitMappingOutcome:
    """Mapping decision for one qubit.

    Attributes:
        qid: Qubit ID.
        status: ``"mapped"`` when the qubit has a verified candidate,
            ``"no_response"`` when no candidate gives a significant response, and
            ``"ambiguous"`` when the response does not single out one candidate.
        candidate_position: Index into the result's candidates of the selected
            candidate, or ``None`` when none is selected.
        score: Score of the selected cell (or the qubit's best cell when none is
            selected).
        margin_ratio: Ratio between the selected cells and the strongest
            alternative that moves this qubit; ``inf`` without a competitor.
        reason: Human-readable explanation of the status.
    """

    qid: str
    status: MappingStatus
    candidate_position: int | None
    score: float
    margin_ratio: float
    reason: str


@dataclass(frozen=True)
class ResonatorQubitMappingResult:
    """Solved resonator-to-qubit mapping for one MUX.

    Attributes:
        qids: Qubit IDs in score-matrix row order.
        candidates: Candidates in score-matrix column order.
        score_matrix: Cleaned scores, shape ``(len(qids), len(candidates))``.
        outcomes: Per-qubit decision keyed by qid.
        best_total_score: Total significant score of the best assignment.
        runner_up_total_score: Total significant score of the best different
            assignment, or ``0.0`` when there is none.
        margin_ratio: Ratio of the cells the best and runner-up assignments
            disagree on; ``inf`` when there is no runner-up.
        min_response_score: Threshold used for significant responses.
        min_margin_ratio: Threshold used for unambiguous assignments.
    """

    qids: tuple[str, ...]
    candidates: tuple[ResonatorCandidate, ...]
    score_matrix: np.ndarray
    outcomes: dict[str, QubitMappingOutcome]
    best_total_score: float
    runner_up_total_score: float
    margin_ratio: float
    min_response_score: float
    min_margin_ratio: float

    def outcome(self, qid: str) -> QubitMappingOutcome | None:
        """Return the outcome for ``qid``, or ``None`` when it was not measured."""
        return self.outcomes.get(qid)

    def mapped_candidate(self, qid: str) -> ResonatorCandidate | None:
        """Return the verified candidate of ``qid``, or ``None`` unless it is mapped."""
        outcome = self.outcomes.get(qid)
        if outcome is None or outcome.status != "mapped" or outcome.candidate_position is None:
            return None
        return self.candidates[outcome.candidate_position]

    @property
    def mapped_qids(self) -> tuple[str, ...]:
        """Qubits with a verified candidate, in row order."""
        return tuple(qid for qid in self.qids if self.outcomes[qid].status == "mapped")

    def summary(self) -> dict[str, object]:
        """Return a JSON-friendly summary for logs and raw results."""
        return {
            "qids": list(self.qids),
            "candidates": [
                {
                    "candidate_index": candidate.candidate_index,
                    "source_qid": candidate.source_qid,
                    "frequency": candidate.frequency,
                    "readout_amplitude": candidate.readout_amplitude,
                    "optimal_power": candidate.optimal_power,
                }
                for candidate in self.candidates
            ],
            "score_matrix": self.score_matrix.tolist(),
            "outcomes": {
                qid: {
                    "status": outcome.status,
                    "candidate_position": outcome.candidate_position,
                    "score": outcome.score,
                    "margin_ratio": _finite_or_none(outcome.margin_ratio),
                    "reason": outcome.reason,
                }
                for qid, outcome in self.outcomes.items()
            },
            "best_total_score": self.best_total_score,
            "runner_up_total_score": self.runner_up_total_score,
            "margin_ratio": _finite_or_none(self.margin_ratio),
            "min_response_score": self.min_response_score,
            "min_margin_ratio": self.min_margin_ratio,
        }


def _finite_or_none(value: float) -> float | None:
    return value if math.isfinite(value) else None


# ---------------------------------------------------------------------------
# Trace scoring
# ---------------------------------------------------------------------------


def score_1d_spectroscopy_trace(
    frequencies: ArrayLike,
    phase_values: ArrayLike,
    *,
    noise_floor_sigma: float = DEFAULT_NOISE_FLOOR_SIGMA,
) -> float:
    """Score how strongly a 1D phase trace departs from its noise floor.

    The baseline is the circular median of the phase, so a response of either
    sign and phases wrapped near +/-pi are handled alike. The noise scale is the
    median absolute deviation (MAD), floored at ``PHASE_NOISE_FLOOR``: when more
    than half of the points sit exactly on the baseline the MAD is zero, and the
    floor keeps a noiseless response scoring higher the wider it is, instead of
    letting the response set its own noise scale. The score is the
    area of the robust z-score above ``noise_floor_sigma``: a single point at
    ``noise_floor_sigma + 5`` sigma scores 5, and a broad power-broadened line
    scores more than an isolated spike of the same height. Pure noise scores
    near zero.

    Args:
        frequencies: Drive frequencies in GHz, one per phase value.
        phase_values: Measured phases in rad.
        noise_floor_sigma: Robust z-score treated as the noise floor.

    Returns:
        A non-negative score; ``0.0`` for traces too short, flat or non-finite.

    Raises:
        ValueError: If the arrays differ in length or the floor is negative.
    """
    if not math.isfinite(noise_floor_sigma) or noise_floor_sigma < 0:
        raise ValueError("noise_floor_sigma must be finite and non-negative")
    x = np.asarray(frequencies, dtype=float).ravel()
    y = np.asarray(phase_values, dtype=float).ravel()
    if x.shape != y.shape:
        raise ValueError(
            f"frequencies and phase_values must have the same length, got {x.size} and {y.size}"
        )
    finite = np.isfinite(x) & np.isfinite(y)
    y = y[finite]
    if y.size < _MIN_TRACE_POINTS:
        return 0.0

    baseline = _circular_median(y)
    deviation = _wrap_phase(y - baseline)
    scale = _MAD_TO_SIGMA * float(np.median(np.abs(deviation - np.median(deviation))))
    if not math.isfinite(scale) or scale < PHASE_NOISE_FLOOR:
        scale = PHASE_NOISE_FLOOR

    z_scores = np.abs(deviation) / scale
    excess = np.clip(z_scores - noise_floor_sigma, 0.0, None)
    score = float(np.sum(excess))
    return score if math.isfinite(score) else 0.0


def _wrap_phase(values: np.ndarray) -> np.ndarray:
    return np.asarray((values + np.pi) % (2 * np.pi) - np.pi, dtype=float)


def _circular_median(values: np.ndarray) -> float:
    """Median of phases taken around their circular mean, robust to wrapping."""
    mean_angle = float(np.angle(np.mean(np.exp(1j * values))))
    return mean_angle + float(np.median(_wrap_phase(values - mean_angle)))


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------


def solve_resonator_qubit_mapping(
    score_matrix: ArrayLike,
    qids: Sequence[str],
    candidates: Sequence[ResonatorCandidate],
    *,
    min_response_score: float = DEFAULT_MIN_RESPONSE_SCORE,
    min_margin_ratio: float = DEFAULT_MIN_MARGIN_RATIO,
) -> ResonatorQubitMappingResult:
    """Assign each qubit at most one candidate and each candidate at most one qubit.

    Cells scoring below ``min_response_score`` are treated as no response and
    never support an assignment. Every one-to-one assignment over the remaining
    cells is enumerated exactly, and the one with the highest total score wins.

    A qubit whose cells are all below the threshold is ``"no_response"``. An
    assigned qubit is ``"mapped"`` only when every alternative assignment that
    moves it loses by at least ``min_margin_ratio``: on the chain of changes
    through that qubit, the selected scores must be that many times the
    alternative's scores. Independent changes elsewhere in the MUX do not count.
    Otherwise, or when its significant candidates are all taken by stronger
    qubits, it is ``"ambiguous"``. A qubit must also win strictly, so an exact
    tie is ambiguous even with ``min_margin_ratio=1.0``.

    Args:
        score_matrix: Scores with one row per qubit and one column per candidate.
            NaN, infinite and negative scores count as no response.
        qids: Qubit IDs in row order.
        candidates: Candidates in column order.
        min_response_score: Minimum score of a significant response.
        min_margin_ratio: Minimum winning ratio for a mapped qubit, at least 1;
            ties are rejected regardless.

    Returns:
        The solved mapping.

    Raises:
        ValueError: On a shape mismatch, duplicate qids, invalid thresholds, or a
            problem larger than ``MAX_MAPPING_SIZE``.
    """
    if not math.isfinite(min_response_score) or min_response_score <= 0:
        raise ValueError("min_response_score must be finite and positive")
    if not math.isfinite(min_margin_ratio) or min_margin_ratio < 1.0:
        raise ValueError("min_margin_ratio must be finite and at least 1.0")
    qid_tuple = tuple(str(qid) for qid in qids)
    if len(set(qid_tuple)) != len(qid_tuple):
        raise ValueError(f"qids must be unique, got {list(qid_tuple)}")
    candidate_tuple = tuple(candidates)
    raw = np.asarray(score_matrix, dtype=float)
    if raw.ndim != 2 or raw.shape != (len(qid_tuple), len(candidate_tuple)):
        raise ValueError(
            f"score_matrix must have shape ({len(qid_tuple)}, {len(candidate_tuple)}), "
            f"got {raw.shape}"
        )
    if len(qid_tuple) > MAX_MAPPING_SIZE or len(candidate_tuple) > MAX_MAPPING_SIZE:
        raise ValueError(
            f"Exact mapping supports at most {MAX_MAPPING_SIZE} qubits and candidates, "
            f"got {len(qid_tuple)} x {len(candidate_tuple)}"
        )

    scores = np.where(np.isfinite(raw), raw, 0.0)
    scores = np.clip(scores, 0.0, None)
    significant = np.where(scores >= min_response_score, scores, 0.0)

    assignments = list(_enumerate_assignments(significant))
    totals = [_total(significant, assignment) for assignment in assignments]
    best_index = max(range(len(assignments)), key=lambda index: totals[index])
    best = assignments[best_index]
    best_total = totals[best_index]

    runner_up_total = 0.0
    global_margin = math.inf
    others = [index for index in range(len(assignments)) if index != best_index]
    if others:
        runner_up_index = max(others, key=lambda index: totals[index])
        runner_up_total = totals[runner_up_index]
        global_margin = _change_ratio(significant, best, assignments[runner_up_index])

    outcomes: dict[str, QubitMappingOutcome] = {}
    for row, qid in enumerate(qid_tuple):
        best_column = int(np.argmax(scores[row])) if scores.shape[1] else None
        row_best = float(scores[row, best_column]) if best_column is not None else 0.0
        if not np.any(significant[row] > 0):
            outcomes[qid] = QubitMappingOutcome(
                qid=qid,
                status="no_response",
                candidate_position=None,
                score=row_best,
                margin_ratio=math.nan,
                reason=(
                    f"best candidate score {row_best:.2f} is below "
                    f"min_response_score={min_response_score:g}"
                ),
            )
            continue

        column = best[row]
        if column is None:
            outcomes[qid] = QubitMappingOutcome(
                qid=qid,
                status="ambiguous",
                candidate_position=None,
                score=row_best,
                margin_ratio=1.0,
                reason=(
                    "every candidate with a significant response is claimed by a stronger qubit"
                ),
            )
            continue

        margin = min(
            (
                _change_ratio(significant, best, alternative, around_row=row)
                for alternative in assignments
                if alternative[row] != column
            ),
            default=math.inf,
        )
        cell_score = float(scores[row, column])
        # An exact tie never maps, even with min_margin_ratio=1.0: the winner
        # would be an arbitrary pick among equally good assignments.
        strictly_wins = margin > 1.0 and not math.isclose(margin, 1.0)
        if strictly_wins and margin >= min_margin_ratio:
            status: MappingStatus = "mapped"
            reason = (
                f"candidate {column} wins with score {cell_score:.2f} and "
                f"margin_ratio {_format_ratio(margin)}"
            )
        else:
            status = "ambiguous"
            reason = (
                f"candidate {column} scores {cell_score:.2f}, but margin_ratio "
                f"{_format_ratio(margin)} is below min_margin_ratio={min_margin_ratio:g}"
                if strictly_wins
                else f"candidate {column} ties another assignment (margin_ratio "
                f"{_format_ratio(margin)})"
            )
        outcomes[qid] = QubitMappingOutcome(
            qid=qid,
            status=status,
            candidate_position=column,
            score=cell_score,
            margin_ratio=margin,
            reason=reason,
        )

    return ResonatorQubitMappingResult(
        qids=qid_tuple,
        candidates=candidate_tuple,
        score_matrix=scores,
        outcomes=outcomes,
        best_total_score=best_total,
        runner_up_total_score=runner_up_total,
        margin_ratio=global_margin,
        min_response_score=float(min_response_score),
        min_margin_ratio=float(min_margin_ratio),
    )


def _enumerate_assignments(significant: np.ndarray) -> Iterator[tuple[int | None, ...]]:
    """Yield every one-to-one partial assignment over significant cells.

    Rows map to a column index or ``None``; only cells with a positive score are
    used, so assignments that differ only on insignificant cells are not repeated.
    """
    n_rows, _ = significant.shape
    options = [
        [None, *(int(column) for column in np.flatnonzero(significant[row] > 0))]
        for row in range(n_rows)
    ]
    for assignment in itertools.product(*options):
        used = [column for column in assignment if column is not None]
        if len(used) == len(set(used)):
            yield assignment


def _total(significant: np.ndarray, assignment: tuple[int | None, ...]) -> float:
    return float(
        sum(significant[row, column] for row, column in enumerate(assignment) if column is not None)
    )


def _change_ratio(
    significant: np.ndarray,
    selected: tuple[int | None, ...],
    alternative: tuple[int | None, ...],
    *,
    around_row: int | None = None,
) -> float:
    """Selected scores over alternative scores on the rows the two disagree on.

    With ``around_row``, only the connected chain of changes through that row
    counts: rows are linked when one row's selected candidate is another's
    alternative candidate. Independent changes elsewhere, such as a tie between
    two other qubits, then do not dilute this row's margin.
    """
    changed = [
        row
        for row, (chosen, other) in enumerate(zip(selected, alternative, strict=True))
        if chosen != other
    ]
    rows = set(changed)
    if around_row is not None:
        rows = _change_component(selected, alternative, changed, around_row)
    selected_sum = 0.0
    alternative_sum = 0.0
    for row in rows:
        chosen = selected[row]
        other = alternative[row]
        if chosen is not None:
            selected_sum += float(significant[row, chosen])
        if other is not None:
            alternative_sum += float(significant[row, other])
    if alternative_sum <= 0:
        return math.inf if selected_sum > 0 else 1.0
    return selected_sum / alternative_sum


def _change_component(
    selected: tuple[int | None, ...],
    alternative: tuple[int | None, ...],
    changed: list[int],
    start: int,
) -> set[int]:
    """Changed rows reachable from ``start`` through shared candidates."""
    component = {start}
    frontier = [start]
    while frontier:
        row = frontier.pop()
        columns = {selected[row], alternative[row]} - {None}
        for other in changed:
            if other in component:
                continue
            if columns & ({selected[other], alternative[other]} - {None}):
                component.add(other)
                frontier.append(other)
    return component


def _format_ratio(value: float) -> str:
    return "inf" if math.isinf(value) else f"{value:.2f}"


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------


def withheld_mapped_qids(
    result: ResonatorQubitMappingResult,
    retained_frequencies: Mapping[str, float | None],
    *,
    tolerance: float,
) -> dict[str, str]:
    """Return the mapped qubits that must not publish, with the reason.

    A qubit that is not published keeps its stored resonator frequency. If a
    mapped qubit published the frequency that another, unpublished qubit keeps,
    both qubits would read the same resonator. Starting from the mapped qubits,
    any qubit whose candidate is still retained by an unpublished qubit is
    withheld, and this repeats until nothing changes, because a withheld qubit
    keeps its own frequency too. A complete swap among mapped qubits stays
    publishable; a partial chain that ends at an unpublished qubit is withheld.

    Args:
        result: Solved mapping.
        retained_frequencies: Stored resonator frequency of each MUX qubit in GHz,
            ``None`` when it has none. Qubits that were not measured belong here
            too.
        tolerance: Frequencies closer than this (GHz) are the same resonator.

    Returns:
        Withheld qid -> reason, in no particular order.
    """
    publishable = set(result.mapped_qids)
    withheld: dict[str, str] = {}
    changed = True
    while changed:
        changed = False
        for qid in sorted(publishable, key=result.qids.index):
            candidate = result.mapped_candidate(qid)
            if candidate is None:
                continue
            for other, frequency in retained_frequencies.items():
                if other == qid or other in publishable or frequency is None:
                    continue
                if abs(frequency - candidate.frequency) < tolerance:
                    publishable.discard(qid)
                    withheld[qid] = (
                        f"candidate C{candidate.candidate_index} "
                        f"({candidate.frequency:.6f} GHz) is still retained by unmapped "
                        f"qid={other}"
                    )
                    changed = True
                    break
    return withheld


# ---------------------------------------------------------------------------
# Figure
# ---------------------------------------------------------------------------


def create_mapping_grid_figure(
    frequencies: ArrayLike,
    traces_grid: Sequence[Sequence[ArrayLike | None]],
    result: ResonatorQubitMappingResult,
    qubit_labels: Sequence[str],
    candidates: Sequence[ResonatorCandidate] | None = None,
    withheld: Mapping[str, str] | None = None,
) -> go.Figure:
    """Draw every (qubit, candidate) phase trace in one grid for review.

    Rows are qubits and columns are candidates. Each subplot title carries the
    candidate frequency and score. The selected cell of each qubit is drawn in
    the status color with a ``SELECTED`` badge when mapped, or an ``AMBIGUOUS``
    badge when it is the unverified best guess; other cells stay gray. A mapped
    qubit listed in ``withheld`` gets a ``WITHHELD`` badge instead of
    ``SELECTED``. The row axis title states each qubit's status.

    Args:
        frequencies: Drive frequencies in GHz shared by every trace.
        traces_grid: Phase traces indexed ``[qubit_row][candidate_column]``;
            ``None`` marks a pair that was not measured.
        result: Solved mapping whose rows and columns match the grid.
        qubit_labels: Display label of each qubit row.
        candidates: Candidates in column order; defaults to ``result.candidates``.
            They must match the result's candidates one for one.
        withheld: Mapped qids whose result is not published, with the reason, as
            returned by :func:`withheld_mapped_qids`.

    Returns:
        The grid figure.

    Raises:
        ValueError: If the candidates, labels or grid do not match the result.
    """
    candidate_tuple = tuple(candidates) if candidates is not None else result.candidates
    withheld = withheld or {}
    n_rows = len(result.qids)
    n_cols = len(candidate_tuple)
    if n_cols != len(result.candidates):
        raise ValueError(
            f"Expected {len(result.candidates)} candidates to match the result, got {n_cols}"
        )
    if result.score_matrix.shape != (n_rows, n_cols):
        raise ValueError(
            f"result.score_matrix must have shape ({n_rows}, {n_cols}), "
            f"got {result.score_matrix.shape}"
        )
    if len(qubit_labels) != n_rows:
        raise ValueError(f"Expected {n_rows} qubit labels, got {len(qubit_labels)}")
    if len(traces_grid) != n_rows or any(len(row) != n_cols for row in traces_grid):
        raise ValueError(f"traces_grid must be {n_rows} x {n_cols}")
    if n_rows == 0 or n_cols == 0:
        raise ValueError("The mapping grid needs at least one qubit and one candidate")
    x = np.asarray(frequencies, dtype=float).ravel()

    titles = [
        f"C{candidate.candidate_index} {candidate.frequency:.4f} GHz | "
        f"score {float(result.score_matrix[row, column]):.1f}"
        for row in range(n_rows)
        for column, candidate in enumerate(candidate_tuple)
    ]
    figure = make_subplots(
        rows=n_rows,
        cols=n_cols,
        shared_xaxes=True,
        subplot_titles=titles,
        horizontal_spacing=0.05,
        vertical_spacing=0.08,
    )
    figure.update_annotations(font_size=_SUBPLOT_TITLE_FONT_SIZE)

    for row, qid in enumerate(result.qids):
        outcome = result.outcomes[qid]
        published = outcome.status == "mapped" and qid not in withheld
        status_label = (
            "withheld" if outcome.status == "mapped" and not published else outcome.status
        )
        badge = (
            "SELECTED" if published else ("WITHHELD" if status_label == "withheld" else "AMBIGUOUS")
        )
        for column in range(n_cols):
            trace = traces_grid[row][column]
            selected = outcome.candidate_position == column
            color = _IDLE_COLOR
            if selected:
                color = _SELECTED_COLOR if published else _AMBIGUOUS_COLOR
            if trace is not None:
                y = np.asarray(trace, dtype=float).ravel()
                figure.add_trace(
                    go.Scatter(
                        x=x[: y.size],
                        y=y,
                        mode="lines",
                        line={"color": color, "width": 2.5 if selected else 1.5},
                        name=f"{qubit_labels[row]} / C{candidate_tuple[column].candidate_index}",
                        showlegend=False,
                        hovertemplate=(
                            f"{qubit_labels[row]} @ C{candidate_tuple[column].candidate_index}"
                            "<br>%{x:.4f} GHz<br>%{y:.3f} rad<extra></extra>"
                        ),
                    ),
                    row=row + 1,
                    col=column + 1,
                )
            if selected:
                axis_suffix = _axis_suffix(row, column, n_cols)
                figure.add_shape(
                    type="rect",
                    xref=f"x{axis_suffix} domain",
                    yref=f"y{axis_suffix} domain",
                    x0=0,
                    x1=1,
                    y0=0,
                    y1=1,
                    line={"color": color, "width": 3},
                    layer="above",
                )
                figure.add_annotation(
                    xref=f"x{axis_suffix} domain",
                    yref=f"y{axis_suffix} domain",
                    x=0.98,
                    y=0.95,
                    xanchor="right",
                    yanchor="top",
                    text=badge,
                    showarrow=False,
                    font={"size": 10, "color": _BADGE_TEXT_COLORS[color]},
                    bgcolor=color,
                    borderpad=2,
                )
        figure.update_yaxes(
            title_text=f"{qubit_labels[row]}<br>{status_label}",
            row=row + 1,
            col=1,
        )

    for column in range(n_cols):
        figure.update_xaxes(title_text="Drive frequency (GHz)", row=n_rows, col=column + 1)
    figure.update_layout(
        title={
            "text": "Resonator-qubit mapping (1D high-power qubit spectroscopy)",
            "subtitle": {
                "text": (
                    f"best={result.best_total_score:.1f} "
                    f"runner-up={result.runner_up_total_score:.1f} "
                    f"margin={_format_ratio(result.margin_ratio)} | "
                    f"min_response_score={result.min_response_score:g} "
                    f"min_margin_ratio={result.min_margin_ratio:g}"
                ),
                "font": {"size": _SUBTITLE_FONT_SIZE, "family": "monospace"},
            },
            "font": {"size": _TITLE_FONT_SIZE},
        },
        font={"family": _FONT_FAMILY},
        paper_bgcolor="white",
        plot_bgcolor="rgba(0,0,0,0)",
        width=max(260 * n_cols, 600),
        height=max(180 * n_rows, 300) + 100,
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
    figure.update_yaxes(**axis_style)
    return figure


def _axis_suffix(row: int, column: int, n_cols: int) -> str:
    index = row * n_cols + column + 1
    return "" if index == 1 else str(index)
