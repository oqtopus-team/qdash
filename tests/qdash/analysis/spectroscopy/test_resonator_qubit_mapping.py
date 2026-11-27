"""Tests for resonator-to-qubit mapping analysis."""

import math

import numpy as np
import plotly.graph_objects as go
import pytest

from qdash.analysis.spectroscopy import (
    DEFAULT_MIN_RESPONSE_SCORE,
    ResonatorCandidate,
    create_mapping_grid_figure,
    score_1d_spectroscopy_trace,
    solve_resonator_qubit_mapping,
)

FREQUENCIES = np.arange(3.0, 5.75, 0.02)
QIDS = ["0", "1", "2", "3"]


def _candidates(count: int = 4) -> list[ResonatorCandidate]:
    return [
        ResonatorCandidate(
            candidate_index=index,
            source_qid=str(index),
            frequency=10.0 + 0.05 * index,
            readout_amplitude=0.1 + 0.01 * index,
            optimal_power=-20.0 - index,
        )
        for index in range(count)
    ]


def _noise(seed: int, sigma: float = 0.02) -> np.ndarray:
    return np.random.default_rng(seed).normal(0.0, sigma, FREQUENCIES.size)


def _line(center: float, height: float, width: float = 0.05) -> np.ndarray:
    return height / (1.0 + ((FREQUENCIES - center) / width) ** 2)


# ---------------------------------------------------------------------------
# score_1d_spectroscopy_trace
# ---------------------------------------------------------------------------


def test_noise_trace_scores_near_zero() -> None:
    score = score_1d_spectroscopy_trace(FREQUENCIES, _noise(1))

    assert 0.0 <= score < 2.0


@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_response_scores_high_for_peaks_and_dips(sign: float) -> None:
    trace = _noise(2) + sign * _line(4.2, 0.5)

    assert score_1d_spectroscopy_trace(FREQUENCIES, trace) > 50.0


def test_score_is_independent_of_phase_wrapping() -> None:
    trace = _noise(3) + _line(4.2, 0.5)
    wrapped = (trace + np.pi + np.pi) % (2 * np.pi) - np.pi  # shift baseline to +/-pi

    assert score_1d_spectroscopy_trace(FREQUENCIES, wrapped) == pytest.approx(
        score_1d_spectroscopy_trace(FREQUENCIES, trace), rel=1e-6
    )


def test_broad_response_outscores_single_spike_of_same_height() -> None:
    spike = _noise(4).copy()
    spike[50] += 0.5

    assert score_1d_spectroscopy_trace(
        FREQUENCIES, _noise(4) + _line(4.0, 0.5)
    ) > score_1d_spectroscopy_trace(FREQUENCIES, spike)


def test_score_ignores_non_finite_points() -> None:
    trace = _noise(5) + _line(4.2, 0.5)
    corrupted = trace.copy()
    corrupted[::10] = np.nan
    corrupted[5] = np.inf

    score = score_1d_spectroscopy_trace(FREQUENCIES, corrupted)

    assert math.isfinite(score)
    assert score > 30.0


def test_flat_short_and_all_nan_traces_score_zero() -> None:
    assert score_1d_spectroscopy_trace(FREQUENCIES, np.zeros_like(FREQUENCIES)) == 0.0
    assert score_1d_spectroscopy_trace([1.0, 2.0], [0.0, 1.0]) == 0.0
    assert score_1d_spectroscopy_trace(FREQUENCIES, np.full_like(FREQUENCIES, np.nan)) == 0.0


def test_zero_mad_uses_fixed_noise_floor_so_broad_responses_win() -> None:
    def plateau(width: int) -> np.ndarray:
        trace = np.zeros(138)
        trace[40 : 40 + width] = 1.0
        return trace

    x = np.linspace(3.0, 5.74, 138)
    scores = [score_1d_spectroscopy_trace(x, plateau(width)) for width in (3, 14, 28)]

    assert scores[0] < scores[1] < scores[2]
    assert min(scores) > 100 * DEFAULT_MIN_RESPONSE_SCORE
    assert score_1d_spectroscopy_trace(x, np.zeros(138)) == 0.0


def test_deviation_below_noise_floor_scores_zero() -> None:
    trace = np.zeros_like(FREQUENCIES)
    trace[40:43] = 1e-4  # far below PHASE_NOISE_FLOOR

    assert score_1d_spectroscopy_trace(FREQUENCIES, trace) == 0.0


def test_score_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        score_1d_spectroscopy_trace([1.0, 2.0, 3.0], [0.0, 1.0])


# ---------------------------------------------------------------------------
# solve_resonator_qubit_mapping
# ---------------------------------------------------------------------------


def test_recovers_permuted_mapping() -> None:
    permutation = [2, 0, 3, 1]
    scores = np.full((4, 4), 0.5)
    for row, column in enumerate(permutation):
        scores[row, column] = 40.0 + row

    result = solve_resonator_qubit_mapping(scores, QIDS, _candidates())

    assert [result.outcomes[qid].candidate_position for qid in QIDS] == permutation
    assert all(result.outcomes[qid].status == "mapped" for qid in QIDS)
    assert result.mapped_candidate("0") == _candidates()[2]
    assert result.best_total_score == pytest.approx(sum(40.0 + row for row in range(4)))
    assert result.mapped_qids == tuple(QIDS)


def test_crosstalk_is_resolved_by_one_to_one_assignment() -> None:
    # Qubit 1 responds at candidate 0 through crosstalk, but candidate 0 clearly
    # belongs to qubit 0, so qubit 1 keeps candidate 1.
    scores = np.array(
        [
            [60.0, 0.0, 0.0, 0.0],
            [12.0, 10.0, 0.0, 0.0],
            [0.0, 0.0, 30.0, 0.0],
            [0.0, 0.0, 0.0, 30.0],
        ]
    )

    result = solve_resonator_qubit_mapping(scores, QIDS, _candidates())

    assert result.outcomes["1"].candidate_position == 1
    assert result.outcomes["1"].status == "mapped"
    assert result.outcomes["1"].margin_ratio == pytest.approx(70.0 / 12.0)


def test_tied_candidates_are_ambiguous() -> None:
    scores = np.array(
        [
            [20.0, 20.0, 0.0, 0.0],
            [20.0, 20.0, 0.0, 0.0],
            [0.0, 0.0, 30.0, 0.0],
            [0.0, 0.0, 0.0, 30.0],
        ]
    )

    result = solve_resonator_qubit_mapping(scores, QIDS, _candidates())

    assert result.outcomes["0"].status == "ambiguous"
    assert result.outcomes["1"].status == "ambiguous"
    assert result.outcomes["0"].margin_ratio == pytest.approx(1.0)
    assert result.mapped_candidate("0") is None
    assert result.outcomes["2"].status == "mapped"
    assert result.outcomes["3"].status == "mapped"
    assert result.margin_ratio == pytest.approx(1.0)
    assert result.runner_up_total_score == pytest.approx(result.best_total_score)


def test_exact_tie_is_ambiguous_even_at_unit_margin_ratio() -> None:
    result = solve_resonator_qubit_mapping(
        np.array([[20.0, 20.0], [20.0, 20.0]]), ["0", "1"], _candidates(2), min_margin_ratio=1.0
    )

    assert result.outcomes["0"].status == "ambiguous"
    assert result.outcomes["1"].status == "ambiguous"
    assert "ties" in result.outcomes["0"].reason
    assert result.mapped_qids == ()


def test_unit_margin_ratio_still_maps_a_strict_winner() -> None:
    result = solve_resonator_qubit_mapping(
        np.array([[20.0, 19.0], [19.0, 20.0]]), ["0", "1"], _candidates(2), min_margin_ratio=1.0
    )

    assert result.mapped_qids == ("0", "1")


def test_low_margin_is_ambiguous() -> None:
    scores = np.array([[20.0, 15.0], [0.0, 0.0]])

    result = solve_resonator_qubit_mapping(scores, ["0", "1"], _candidates(2), min_margin_ratio=2.0)

    assert result.outcomes["0"].status == "ambiguous"
    assert result.outcomes["0"].candidate_position == 0
    assert result.outcomes["0"].margin_ratio == pytest.approx(20.0 / 15.0)
    assert "below min_margin_ratio" in result.outcomes["0"].reason


def test_silent_qubit_is_no_response_and_frees_its_candidate() -> None:
    scores = np.array(
        [
            [40.0, 0.2, 0.1, 0.3],
            [0.4, 1.0, 0.2, 0.1],  # dead qubit
            [0.0, 0.0, 35.0, 0.0],
            [0.0, 0.0, 0.0, 25.0],
        ]
    )

    result = solve_resonator_qubit_mapping(scores, QIDS, _candidates())

    assert result.outcomes["1"].status == "no_response"
    assert result.outcomes["1"].candidate_position is None
    assert math.isnan(result.outcomes["1"].margin_ratio)
    assert [result.outcomes[qid].status for qid in ("0", "2", "3")] == ["mapped"] * 3


def test_qubit_whose_candidates_are_taken_is_ambiguous() -> None:
    scores = np.array([[50.0, 0.0], [8.0, 0.0], [0.0, 40.0]])

    result = solve_resonator_qubit_mapping(scores, ["0", "1", "2"], _candidates(2))

    assert result.outcomes["0"].status == "mapped"
    assert result.outcomes["1"].status == "ambiguous"
    assert result.outcomes["1"].candidate_position is None
    assert result.outcomes["2"].status == "mapped"


def test_fewer_qubits_than_candidates() -> None:
    scores = np.array([[0.0, 0.0, 30.0, 0.0], [0.0, 25.0, 0.0, 0.0]])

    result = solve_resonator_qubit_mapping(scores, ["4", "5"], _candidates())

    assert result.outcomes["4"].candidate_position == 2
    assert result.outcomes["5"].candidate_position == 1
    assert result.margin_ratio == math.inf


def test_non_finite_and_negative_scores_are_no_response() -> None:
    scores = np.array([[np.nan, -5.0], [np.inf, 20.0]])

    result = solve_resonator_qubit_mapping(scores, ["0", "1"], _candidates(2))

    assert result.outcomes["0"].status == "no_response"
    assert result.outcomes["1"].candidate_position == 1
    assert result.score_matrix[1, 0] == 0.0


def test_all_silent_mux_has_no_mapping() -> None:
    result = solve_resonator_qubit_mapping(np.ones((4, 4)), QIDS, _candidates())

    assert all(outcome.status == "no_response" for outcome in result.outcomes.values())
    assert result.best_total_score == 0.0
    assert result.mapped_qids == ()


def test_summary_is_json_friendly() -> None:
    scores = np.diag([30.0, 30.0])
    summary = solve_resonator_qubit_mapping(scores, ["0", "1"], _candidates(2)).summary()

    assert summary["margin_ratio"] is None  # inf is reported as None
    assert summary["outcomes"]["0"]["status"] == "mapped"  # type: ignore[index]


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"min_response_score": 0.0}, "min_response_score"),
        ({"min_margin_ratio": 0.5}, "min_margin_ratio"),
    ],
)
def test_rejects_invalid_thresholds(kwargs: dict[str, float], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        solve_resonator_qubit_mapping(np.eye(2), ["0", "1"], _candidates(2), **kwargs)


def test_rejects_shape_mismatch_and_duplicate_qids() -> None:
    with pytest.raises(ValueError, match="shape"):
        solve_resonator_qubit_mapping(np.eye(3), ["0", "1"], _candidates(2))
    with pytest.raises(ValueError, match="unique"):
        solve_resonator_qubit_mapping(np.eye(2), ["0", "0"], _candidates(2))


# ---------------------------------------------------------------------------
# create_mapping_grid_figure
# ---------------------------------------------------------------------------


def test_grid_figure_draws_all_traces_and_marks_selection() -> None:
    permutation = [1, 0, 3, 2]
    scores = np.zeros((4, 4))
    traces: list[list[np.ndarray | None]] = []
    for row, column_selected in enumerate(permutation):
        scores[row, column_selected] = 50.0
        traces.append(
            [
                _noise(row * 4 + column) + (_line(4.0, 0.5) if column == column_selected else 0.0)
                for column in range(4)
            ]
        )
    result = solve_resonator_qubit_mapping(scores, QIDS, _candidates())

    figure = create_mapping_grid_figure(
        FREQUENCIES, traces, result, ["Q00", "Q01", "Q02", "Q03"], _candidates()
    )

    assert isinstance(figure, go.Figure)
    assert len(figure.data) == 16
    badges = [a for a in figure.layout.annotations if a.text == "SELECTED"]
    assert len(badges) == 4
    assert len(figure.layout.shapes) == 4
    titles = [a.text for a in figure.layout.annotations if a.text and "score" in a.text]
    assert len(titles) == 16
    assert "score 50.0" in titles[1]  # row 0 selects candidate 1
    assert figure.layout.yaxis.title.text == "Q00<br>mapped"


def test_grid_figure_marks_ambiguous_selection_and_missing_traces() -> None:
    scores = np.array([[20.0, 15.0], [0.0, 0.0]])
    result = solve_resonator_qubit_mapping(scores, ["0", "1"], _candidates(2))
    traces: list[list[np.ndarray | None]] = [[_noise(1), _noise(2)], [None, _noise(3)]]

    figure = create_mapping_grid_figure(FREQUENCIES, traces, result, ["Q00", "Q01"])

    assert len(figure.data) == 3
    assert [a.text for a in figure.layout.annotations if a.text == "AMBIGUOUS"] == ["AMBIGUOUS"]


def test_grid_figure_rejects_mismatched_grid() -> None:
    result = solve_resonator_qubit_mapping(np.eye(2) * 30, ["0", "1"], _candidates(2))

    with pytest.raises(ValueError, match="traces_grid"):
        create_mapping_grid_figure(FREQUENCIES, [[_noise(1)]], result, ["Q00", "Q01"])
