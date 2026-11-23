"""Manual rounds take MUX membership from the chip topology, not from ``qid // 4``.

The topology here is synthetic: MUX IDs are sparse, MUX 9 owns qubit 41 (which
``qid // 4`` would put in MUX 10), qubit 20 is standalone and any other qubit
is unknown. The same checks run in the worker and in the API preview.
"""

from __future__ import annotations

from typing import Any

import pytest

from qdash.common.manual_rounds import (
    ManualRoundsError,
    mux_target_qids,
    needs_wiring,
    pair_round_issues,
    parse_pair_rounds,
    parse_qubit_rounds,
    qubit_mux_map,
    qubit_round_issues,
)
from qdash.common.mux_mapping import MuxMapping

MAPPING = MuxMapping.from_groups(
    {9: ["36", "41", "38"], 2: ["5"]},
    topology_id="synthetic-sparse",
    known_qids=["36", "41", "38", "5", "20"],
)
# Both MUXes are on Box A, so their qubits may share a round.
WIRING: list[dict[str, Any]] = [
    {"mux": 9, "ctrl": ["Q9A-0", "Q9A-1", "Q9A-2"], "read_out": "R9A-0"},
    {"mux": 2, "ctrl": ["Q2A-0"], "read_out": "R2A-0"},
    # Wired for the legacy layout only: the topology does not define MUX 10.
    {"mux": 10, "ctrl": ["Q10A-0", "Q10A-1", "Q10A-2", "Q10A-3"], "read_out": "R10A-0"},
]
COUPLINGS = {"36-41", "41-5", "38-36", "20-5"}


def _qubit_reasons(rounds: list[list[str]], mapping: MuxMapping | None = MAPPING) -> list[str]:
    parsed = parse_qubit_rounds(rounds, step="s")
    return [issue.describe() for issue in qubit_round_issues(parsed, WIRING, mapping)]


def _pair_reasons(
    rounds: list[list[tuple[str, str]]], mapping: MuxMapping | None = MAPPING
) -> list[str]:
    parsed = parse_pair_rounds(rounds, step="s")
    return [issue.describe() for issue in pair_round_issues(parsed, WIRING, COUPLINGS, mapping)]


def test_membership_comes_from_the_topology_mapping() -> None:
    assert qubit_mux_map(WIRING, MAPPING) == {"36": 9, "41": 9, "38": 9, "5": 2}
    # Without a mapping the legacy convention still applies to every wired MUX.
    assert qubit_mux_map(WIRING)["41"] == 10


def test_qubits_of_one_declared_mux_cannot_share_a_round() -> None:
    [reason] = _qubit_reasons([["36", "41"]])
    assert "share MUX 9" in reason
    # The legacy layout puts 41 in MUX 10 and would have accepted the round.
    assert _qubit_reasons([["36", "41"]], mapping=None) == []
    assert _qubit_reasons([["41", "5"], ["36"], ["38"]]) == []


def test_standalone_qubits_run_alone_and_unknown_qubits_are_rejected() -> None:
    [standalone] = _qubit_reasons([["38", "20"]])
    assert "round 1 (20)" in standalone and "must run alone" in standalone
    assert _qubit_reasons([["38"], ["20"]]) == []
    [unknown] = _qubit_reasons([["99"]])
    assert "qubit 99 is not defined by topology synthetic-sparse" in unknown


def test_member_slots_need_control_ports_in_the_wiring() -> None:
    narrow = [dict(WIRING[0], ctrl=["Q9A-0", "Q9A-1"]), *WIRING[1:]]
    parsed = parse_qubit_rounds([["38"]], step="s")
    [issue] = qubit_round_issues(parsed, narrow, MAPPING)
    assert "MUX 9 qubit 38 uses slot 2" in issue.reason
    # A round that touches no MUX with a bad slot is not blamed for it.
    assert qubit_round_issues(parse_qubit_rounds([["5"]], step="s"), narrow, MAPPING) == []


def test_qubit_ids_must_be_canonical() -> None:
    with pytest.raises(ManualRoundsError, match="without leading zeros"):
        parse_qubit_rounds([["05"]], step="s")
    with pytest.raises(ManualRoundsError, match="without leading zeros"):
        parse_pair_rounds([[("05", "41")]], step="s")


def test_pairs_use_the_declared_mux_and_standalone_pairs_run_alone() -> None:
    assert _pair_reasons([[("36", "41")], [("20", "5")]]) == []
    [shared] = _pair_reasons([[("41", "5"), ("38", "36")]])
    assert "both use MUX 9" in shared
    # With the legacy layout 41 is in MUX 10, so the two pairs would look independent.
    legacy = _pair_reasons([[("41", "5"), ("38", "36")]], mapping=None)
    assert not any("both use MUX" in reason for reason in legacy)
    [standalone] = _pair_reasons([[("20", "5"), ("38", "36")]])
    assert "20-5 uses standalone qubit 20" in standalone and "must run alone" in standalone


def test_mux_targets_follow_member_slots_and_alias_exclusions() -> None:
    assert mux_target_qids([9, 2], ["Q41"], WIRING, MAPPING) == ["36", "38", "5"]
    # A MUX the topology does not define is left to the target checks.
    assert mux_target_qids([10], [], WIRING, MAPPING) == []
    # A chip without a topology keeps skipping MUXes outside the wiring.
    assert mux_target_qids([2, 3], [], WIRING) == ["8", "9", "10", "11"]


def test_a_topology_without_muxes_needs_no_wiring() -> None:
    only_standalone = MuxMapping.from_groups({}, known_qids=["0", "1"])
    assert not needs_wiring(only_standalone)
    assert needs_wiring(MAPPING) and needs_wiring(None)
    parsed = parse_qubit_rounds([["0"], ["1"]], step="s")
    assert qubit_round_issues(parsed, [], only_standalone) == []
