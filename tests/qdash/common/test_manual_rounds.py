"""Manual execution rounds: shape, hardware model and candidate checks."""

from __future__ import annotations

import pickle
from typing import Any

import pytest

from qdash.common.manual_rounds import (
    ManualRoundsError,
    RoundIssue,
    format_issues,
    load_wiring_entries,
    mux_target_qids,
    pair_candidate_issues,
    pair_round_issues,
    pair_rounds_for_mode,
    parse_pair_rounds,
    parse_qubit_rounds,
    qubit_candidate_issues,
    qubit_round_issues,
    qubit_rounds_for_mode,
    round_qids,
)


def _mux(mux: int, box: str, *, readout: str | None = None) -> dict[str, Any]:
    return {
        "mux": mux,
        "ctrl": [f"{box}-{port}" for port in (2, 4)],
        "read_out": readout or f"{box}-1",
        "read_in": f"{box}-0",
    }


# MUX 0 and 2: their own Box A modules. MUX 1: Box B. MUX 3 and 4: MIXED, sharing
# Box B ctrl module S1B. MUX 5: Box A sharing readout module R0A with MUX 0.
WIRING = [
    _mux(0, "Q0A", readout="R0A-1"),
    _mux(1, "U1B"),
    _mux(2, "Q2A"),
    {"mux": 3, "ctrl": ["S1B-2", "Q3A-4"], "read_out": "Q3A-1", "read_in": "Q3A-0"},
    {"mux": 4, "ctrl": ["S1B-9", "Q4A-4"], "read_out": "Q4A-1", "read_in": "Q4A-0"},
    _mux(5, "Q5A", readout="R0A-5"),
]
COUPLINGS = {"0-1", "1-0", "4-5", "8-9", "0-4", "20-21", "12-13", "16-17"}


def _reasons(issues: list[RoundIssue]) -> list[str]:
    return [issue.describe() for issue in issues]


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_qubit_rounds_keep_the_written_order() -> None:
    assert parse_qubit_rounds([["8", "0"], ("1", "9")], step="s") == (("8", "0"), ("1", "9"))


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (None, "non-empty list of rounds"),
        ([], "non-empty list of rounds"),
        ("0,8", "non-empty list of rounds"),
        ([[]], "round 1: a round must be a non-empty list"),
        ([["0"], "1"], "round 2: a round must be a non-empty list"),
        ([[0, 8]], "qubit ID 0 must be a string"),
        ([["q0"]], "must be a non-negative integer string"),
        ([["0", "0"]], "round 1 (0): qubit 0 appears twice"),
        ([["0", "8"], ["8"]], "round 2 (8): qubit 8 already runs in round 1"),
    ],
)
def test_malformed_qubit_rounds_name_the_round(value: object, message: str) -> None:
    with pytest.raises(ManualRoundsError) as error:
        parse_qubit_rounds(value, step="rabi")
    assert "Manual rounds of step 'rabi' cannot run" in str(error.value)
    assert message in str(error.value)


def test_every_problem_is_reported_at_once() -> None:
    with pytest.raises(ManualRoundsError) as error:
        parse_qubit_rounds([["0", "x"], [], ["0"]], step="s")
    assert [issue.round_number for issue in error.value.issues] == [1, 2, 3]


def test_pair_rounds_keep_direction_and_order() -> None:
    rounds = parse_pair_rounds([[("1", "0"), ["4", "5"]], [("8", "9")]], step="s")
    assert rounds == ((("1", "0"), ("4", "5")), (("8", "9"),))
    assert round_qids(rounds) == ["1", "0", "4", "5", "8", "9"]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ([[("0",)]], "must be a (control, target) pair"),
        ([[("0", "1", "2")]], "must be a (control, target) pair"),
        ([[("0", 1)]], "qubit ID 1 must be a string"),
        ([[("3", "3")]], "round 1 (3-3): a pair needs two different qubits"),
        ([[("0", "1"), ("0", "1")]], "pair 0-1 appears twice"),
        ([[("0", "1")], [("0", "1")]], "round 2 (0-1): pair 0-1 already runs in round 1"),
        ([[("0", "1"), ("1", "5")]], "round 1 (0-1, 1-5): pairs 0-1 and 1-5 share qubit 1"),
    ],
)
def test_malformed_pair_rounds_name_the_round(value: object, message: str) -> None:
    with pytest.raises(ManualRoundsError, match="cannot run") as error:
        parse_pair_rounds(value, step="cr")
    assert message in str(error.value)


def test_reversed_pair_in_another_round_is_a_different_coupling() -> None:
    assert parse_pair_rounds([[("0", "1")], [("1", "0")]], step="s") == (
        (("0", "1"),),
        (("1", "0"),),
    )


def test_error_survives_pickling_with_its_issues() -> None:
    error = ManualRoundsError("s", [RoundIssue("bad", 2, ("0",))])
    copy = pickle.loads(pickle.dumps(error))  # noqa: S301 - round-trips a local object
    assert copy.issues == error.issues and str(copy) == str(error)
    assert (
        format_issues("s", error.issues) == "Manual rounds of step 's' cannot run: round 2 (0): bad"
    )


# ---------------------------------------------------------------------------
# Mode and rounds belong together
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["parallel_by_round", "parallel_by_mux", "sequential"])
def test_rounds_are_rejected_for_scheduled_one_qubit_modes(mode: str) -> None:
    with pytest.raises(ValueError, match="rounds is only accepted with execution_mode='manual'"):
        qubit_rounds_for_mode(mode, [["0"]], step="s")
    assert qubit_rounds_for_mode(mode, None, step="s") is None


def test_manual_requires_rounds() -> None:
    with pytest.raises(ManualRoundsError, match="requires rounds"):
        qubit_rounds_for_mode("manual", None, step="s")
    with pytest.raises(ManualRoundsError, match="requires rounds"):
        pair_rounds_for_mode("manual", None, None, step="s")


def test_max_parallel_ops_belongs_to_automatic_only() -> None:
    with pytest.raises(ValueError, match="max_parallel_ops only caps automatic CR groups"):
        pair_rounds_for_mode("manual", [[("0", "1")]], 10, step="s")
    # Unset is not a conflict, and automatic keeps its cap.
    assert pair_rounds_for_mode("manual", [[("0", "1")]], None, step="s") == ((("0", "1"),),)
    assert pair_rounds_for_mode("automatic", None, 4, step="s") is None
    with pytest.raises(ValueError, match="rounds is only accepted"):
        pair_rounds_for_mode("automatic", [[("0", "1")]], None, step="s")


# ---------------------------------------------------------------------------
# One-qubit hardware model
# ---------------------------------------------------------------------------


def test_qubits_of_different_box_a_muxes_may_share_a_round() -> None:
    # The automatic round schedule pairs MUX 0 and MUX 2 the same way.
    assert qubit_round_issues((("0", "8"), ("1", "9")), WIRING) == []


def test_qubits_of_one_mux_cannot_share_a_round() -> None:
    [issue] = qubit_round_issues((("0", "8"), ("1", "2")), WIRING)
    assert issue.describe() == (
        "round 2 (1, 2): qubits 1 and 2 share MUX 0; qubits of one MUX must run in different rounds"
    )


def test_unwired_qubits_are_rejected() -> None:
    [issue] = qubit_round_issues((("0", "99"),), WIRING)
    assert issue.round_number == 1 and issue.targets == ("99",)
    assert "no MUX entry" in issue.reason


def test_a_round_stays_within_one_box_stage() -> None:
    [issue] = qubit_round_issues((("0", "4"),), WIRING)
    assert "mixes box stages A (0), B (4)" in issue.reason


def test_mixed_muxes_sharing_a_box_b_ctrl_module_are_rejected() -> None:
    [issue] = qubit_round_issues((("12", "16"),), WIRING)
    assert "share Box B ctrl module S1B" in issue.reason


def test_mux_targets_resolve_to_wired_qubits_without_exclusions() -> None:
    assert mux_target_qids([0, 9], ["1"], WIRING) == ["0", "2", "3"]


# ---------------------------------------------------------------------------
# Two-qubit hardware model
# ---------------------------------------------------------------------------


def test_disjoint_couplings_on_unrelated_muxes_pass() -> None:
    rounds = parse_pair_rounds([[("0", "1"), ("8", "9")], [("4", "5")]], step="s")
    assert pair_round_issues(rounds, WIRING, COUPLINGS) == []


def test_pairs_are_directed_and_never_reversed() -> None:
    issues = pair_round_issues(((("5", "4"),), (("9", "10"),)), WIRING, COUPLINGS)
    assert _reasons(issues) == [
        "round 1 (5-4): 5-4 is not a coupling of the chip; 4-5 is, so swap control and target "
        "to run that direction",
        "round 2 (9-10): 9-10 is not a coupling of the chip",
    ]


def test_pairs_of_one_round_cannot_share_a_mux() -> None:
    [issue] = pair_round_issues(((("0", "1"), ("0", "4")),), WIRING, COUPLINGS | {"2-3"})
    assert issue.targets == ("0-1", "0-4")
    [issue] = pair_round_issues(((("0", "1"), ("2", "3")),), WIRING, COUPLINGS | {"2-3"})
    assert "both use MUX 0" in issue.reason


def test_pairs_on_muxes_sharing_a_module_conflict() -> None:
    # MUX 0 and MUX 5 share the readout module R0A.
    [issue] = pair_round_issues(((("0", "1"), ("20", "21")),), WIRING, COUPLINGS)
    assert "share a readout or control module" in issue.reason


def test_unwired_pair_qubits_are_rejected() -> None:
    [issue] = pair_round_issues(((("40", "41"),),), WIRING, COUPLINGS | {"40-41"})
    assert "has no MUX entry" in issue.reason


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------


def test_one_qubit_rounds_must_name_exactly_the_candidates() -> None:
    rounds = (("0", "8"), ("1", "9"))
    assert qubit_candidate_issues(rounds, ["9", "8", "1", "0"]) == []
    issues = qubit_candidate_issues(rounds, ["0", "1", "8", "2", "3"])
    assert _reasons(issues) == [
        "round 2 (9): qubit 9 is not among the step's current qubits (a target, not excluded, "
        "and kept by earlier filters)",
        "current qubits 2, 3 are in no round; add them to a round or remove them from the targets",
    ]


def test_pair_qubits_must_be_candidates() -> None:
    rounds = ((("0", "1"),), (("8", "9"),))
    assert pair_candidate_issues(rounds, ["0", "1", "8", "9", "12"]) == []
    [issue] = pair_candidate_issues(rounds, ["0", "1", "8"])
    assert issue.round_number == 2 and "qubit 9 of 8-9" in issue.reason


# ---------------------------------------------------------------------------
# Wiring files
# ---------------------------------------------------------------------------


def test_wiring_files_in_both_formats_load(tmp_path: Any) -> None:
    chip_keyed = tmp_path / "a.yaml"
    chip_keyed.write_text("chip: [{mux: 0, ctrl: [Q0A-2], read_out: Q0A-1}]\n")
    grouped = tmp_path / "b.yaml"
    grouped.write_text("A1: [{mux: 0, ctrl: [Q0A-2]}]\nA2: [{mux: 1, ctrl: [Q1A-2]}]\n")
    assert [entry["mux"] for entry in load_wiring_entries(chip_keyed, "chip")] == [0]
    assert [entry["mux"] for entry in load_wiring_entries(grouped, "chip")] == [0, 1]
    with pytest.raises(FileNotFoundError):
        load_wiring_entries(tmp_path / "missing.yaml", "chip")
    bad = tmp_path / "c.yaml"
    bad.write_text("chip: [{ctrl: []}]\n")
    with pytest.raises(ValueError, match="integer mux"):
        load_wiring_entries(bad, "chip")
