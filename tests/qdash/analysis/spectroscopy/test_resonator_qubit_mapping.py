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
    score_mapping_grid,
    solve_resonator_qubit_mapping,
    withheld_mapped_qids,
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


def test_broad_response_covering_half_sweep_outscores_narrow_crosstalk_spike() -> None:
    # A broad power-broadened response covering ~45% of the sweep used to inflate
    # per-trace MAD and lose to a 3-point crosstalk spike on a quiet trace.
    broad = _noise(10, sigma=0.025).copy()
    broad[20:82] = (broad[20:82] + 3.0 + np.pi) % (2 * np.pi) - np.pi  # wraps near +/-pi

    crosstalk = _noise(11, sigma=0.025).copy()
    crosstalk[90:93] -= 2.8

    assert score_1d_spectroscopy_trace(FREQUENCIES, broad) > 5.0 * score_1d_spectroscopy_trace(
        FREQUENCIES, crosstalk
    )


@pytest.mark.parametrize("index", [0, 60, -1])
def test_despike_suppresses_isolated_single_point_spike(index: int) -> None:
    spike = _noise(12, sigma=0.02).copy()
    spike[index] += 3.0

    despiked = score_1d_spectroscopy_trace(FREQUENCIES, spike, despike=True)
    raw = score_1d_spectroscopy_trace(FREQUENCIES, spike, despike=False)

    assert despiked < DEFAULT_MIN_RESPONSE_SCORE
    assert raw > 100.0


def test_despike_preserves_multi_point_boundary_response() -> None:
    trace = np.zeros_like(FREQUENCIES)
    trace[:3] = 1.0

    assert score_1d_spectroscopy_trace(FREQUENCIES, trace, despike=True) > 100.0


def test_score_mapping_grid_uses_per_column_noise_floor() -> None:
    # Candidate 0 is quiet (sigma=0.02), candidate 1 is noisier (sigma=0.08).
    # Q0 has a broad wrapped response on C0; Q1 has a broad response on C1;
    # Q0 also sees a narrow 2-point crosstalk dip on C1.
    q0_c0 = _noise(20, sigma=0.02).copy()
    q0_c0[25:85] = (q0_c0[25:85] + 2.9 + np.pi) % (2 * np.pi) - np.pi
    q0_c1 = _noise(21, sigma=0.08).copy()
    q0_c1[70:72] -= 2.0

    q1_c0 = _noise(22, sigma=0.02).copy()
    q1_c0[80] -= 2.8  # single-point crosstalk spike
    q1_c1 = _noise(23, sigma=0.08).copy()
    q1_c1[40:80] -= 2.4

    scores = score_mapping_grid(FREQUENCIES, [[q0_c0, q0_c1], [q1_c0, q1_c1]])
    result = solve_resonator_qubit_mapping(scores, ["0", "1"], _candidates(2))

    assert result.mapped_qids == ("0", "1")
    assert result.outcomes["0"].candidate_position == 0
    assert result.outcomes["1"].candidate_position == 1
    assert scores[1, 0] < DEFAULT_MIN_RESPONSE_SCORE
    assert scores[0, 0] > 10.0 * scores[0, 1]
    assert scores[1, 1] > 5.0 * scores[0, 1]


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


def test_grid_figure_uses_qubex_figure_style() -> None:
    # Q00 maps to C0; Q01 prefers C1 over C2 by too small a margin.
    scores = np.array([[30.0, 0.0, 0.0], [0.0, 20.0, 15.0]])
    result = solve_resonator_qubit_mapping(scores, ["0", "1"], _candidates(3))
    assert result.outcomes["0"].status == "mapped"
    assert result.outcomes["1"].status == "ambiguous"
    traces: list[list[np.ndarray | None]] = [
        [_noise(row * 3 + column) for column in range(3)] for row in range(2)
    ]

    figure = create_mapping_grid_figure(FREQUENCIES, traces, result, ["Q00", "Q01"])

    layout = figure.layout
    assert layout.font.family == "Times New Roman, Times, serif"
    assert layout.paper_bgcolor == "white"
    assert layout.plot_bgcolor == "rgba(0,0,0,0)"
    assert layout.title.font.size == 18
    assert layout.title.subtitle.font.size == 13
    axes = [layout[name] for name in layout if name.startswith(("xaxis", "yaxis"))]
    assert len(axes) == 12
    for axis in axes:
        assert axis.showline is True
        assert axis.mirror is True
        assert axis.linecolor == "black"
        assert axis.ticks == "inside"
        assert axis.showgrid is False
        assert axis.zeroline is False
    colors = [trace.line.color for trace in figure.data]
    assert colors == ["#0C5DA5", "#9e9e9e", "#9e9e9e", "#9e9e9e", "#FF9500", "#9e9e9e"]
    assert all(trace.fill == "tozeroy" for trace in figure.data)
    y_axes = [layout[name] for name in layout if name.startswith("yaxis")]
    assert all(axis.range[0] == pytest.approx(-0.1) and axis.range[1] > math.pi for axis in y_axes)
    for trace in figure.data:
        y_vals = np.asarray(trace.y, dtype=float)
        assert np.all((y_vals >= 0.0) & (y_vals <= math.pi + 1e-9))


# ---------------------------------------------------------------------------
# withheld_mapped_qids
# ---------------------------------------------------------------------------

RETAINED = {qid: candidate.frequency for qid, candidate in zip(QIDS, _candidates(), strict=True)}


def test_partial_chain_onto_a_retained_resonator_is_withheld_transitively() -> None:
    # 0 -> C1 (held by 1), 1 -> C2 (held by 2), 2 is silent and keeps C2.
    scores = np.array(
        [
            [0.0, 40.0, 0.0, 0.0],
            [0.0, 0.0, 40.0, 0.0],
            [0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 40.0],
        ]
    )
    result = solve_resonator_qubit_mapping(scores, QIDS, _candidates())
    assert result.mapped_qids == ("0", "1", "3")

    withheld = withheld_mapped_qids(result, RETAINED, tolerance=0.0005)

    assert set(withheld) == {"0", "1"}
    assert "retained by unmapped qid=2" in withheld["1"]
    assert "retained by unmapped qid=1" in withheld["0"]


def test_complete_swap_is_not_withheld() -> None:
    scores = np.array(
        [
            [0.0, 40.0, 0.0, 0.0],
            [40.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 40.0, 0.0],
            [0.0, 0.0, 0.0, 0.0],  # silent, keeps C3 that nobody takes
        ]
    )
    result = solve_resonator_qubit_mapping(scores, QIDS, _candidates())

    assert withheld_mapped_qids(result, RETAINED, tolerance=0.0005) == {}


def test_retained_frequency_of_unmeasured_qubit_blocks_mapping() -> None:
    result = solve_resonator_qubit_mapping(np.array([[0.0, 40.0]]), ["0"], _candidates(2))

    withheld = withheld_mapped_qids(
        result, {"0": None, "7": _candidates(2)[1].frequency}, tolerance=0.0005
    )

    assert set(withheld) == {"0"}


def test_grid_figure_rejects_candidates_that_do_not_match_result() -> None:
    result = solve_resonator_qubit_mapping(np.eye(2) * 30, ["0", "1"], _candidates(2))
    traces: list[list[np.ndarray | None]] = [[_noise(1)] * 3, [_noise(2)] * 3]

    with pytest.raises(ValueError, match="Expected 2 candidates"):
        create_mapping_grid_figure(FREQUENCIES, traces, result, ["Q00", "Q01"], _candidates(3))


def test_grid_figure_marks_withheld_qubits() -> None:
    result = solve_resonator_qubit_mapping(np.eye(2) * 30, ["0", "1"], _candidates(2))
    traces: list[list[np.ndarray | None]] = [[_noise(1), _noise(2)], [_noise(3), _noise(4)]]

    figure = create_mapping_grid_figure(
        FREQUENCIES, traces, result, ["Q00", "Q01"], withheld={"1": "blocked"}
    )

    badges = [a.text for a in figure.layout.annotations if a.text in {"SELECTED", "WITHHELD"}]
    assert badges == ["SELECTED", "WITHHELD"]
    assert figure.layout.yaxis3.title.text == "Q01<br>withheld"
