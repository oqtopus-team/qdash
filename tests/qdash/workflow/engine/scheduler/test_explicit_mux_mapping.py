"""Schedulers follow the topology's explicit MUX groups and local slots."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import yaml

from qdash.common.mux_mapping import MuxMapping, MuxMappingError
from qdash.workflow.engine.scheduler.cr_utils import build_qubit_to_mux_map, split_fast_slow_pairs
from qdash.workflow.engine.scheduler.one_qubit_plugins import (
    CheckerboardOrderingStrategy,
    DefaultOrderingStrategy,
    OrderingContext,
)
from qdash.workflow.engine.scheduler.one_qubit_scheduler import OneQubitScheduler

if TYPE_CHECKING:
    from pathlib import Path

# Sparse MUX IDs with permuted, noncontiguous members (local slot order).
GROUPS = {
    9: ["0", "17", "5", "2"],
    4: ["12", "3", "30", "7"],
}


def _wiring(ctrl_ports: int = 4) -> list[dict[str, Any]]:
    return [
        {
            "mux": 9,
            "ctrl": [f"Q73A-{i}" for i in range(4)],
            "read_out": "Q73A-8",
            "read_in": "Q73A-7",
        },
        {
            "mux": 4,
            "ctrl": [f"S159A-{i}" for i in range(ctrl_ports)],
            "read_out": "S159A-8",
            "read_in": "S159A-7",
        },
    ]


def _scheduler(tmp_path: Path, ctrl_ports: int = 4) -> OneQubitScheduler:
    path = tmp_path / "wiring.yaml"
    path.write_text(yaml.safe_dump({"chip-x": _wiring(ctrl_ports)}))
    return OneQubitScheduler(
        chip_id="chip-x",
        wiring_config_path=path,
        mux_mapping=MuxMapping.from_groups(GROUPS),
    )


def test_mux_targets_resolve_to_topology_members_in_slot_order(tmp_path: Path) -> None:
    schedule = _scheduler(tmp_path).generate_from_mux(mux_ids=[9, 4])

    assert [stage.qids for stage in schedule.stages] == [
        ["0", "17", "5", "2", "12", "3", "30", "7"]
    ]
    # One parallel group per MUX, sorted by MUX ID, members in slot order.
    assert schedule.stages[0].parallel_groups == [["12", "3", "30", "7"], ["0", "17", "5", "2"]]
    assert schedule.qid_to_mux["17"] == 9
    assert schedule.qid_to_mux["3"] == 4


def test_undefined_mux_or_qubit_is_rejected(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path)

    # MUX 0 would be qubits 0-3 by qid // 4, but this topology has no MUX 0.
    with pytest.raises(MuxMappingError):
        scheduler.generate_from_mux(mux_ids=[0])
    with pytest.raises(MuxMappingError):
        scheduler.generate(qids=["1"])


def test_member_slot_without_control_port_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(MuxMappingError, match="MUX 4 qubit 7 uses slot 3"):
        _scheduler(tmp_path, ctrl_ports=3).generate_from_mux(mux_ids=[4])


def test_rounds_follow_local_slots(tmp_path: Path) -> None:
    schedule = _scheduler(tmp_path).generate_rounds_from_mux(mux_ids=[4, 9], use_checkerboard=False)

    assert [round_.parallel_qids for round_ in schedule.rounds] == [
        ["12", "0"],
        ["3", "17"],
        ["30", "5"],
        ["7", "2"],
    ]


def test_checkerboard_uses_slots_by_mux_parity(tmp_path: Path) -> None:
    schedule = _scheduler(tmp_path).generate_rounds_from_mux(mux_ids=[4, 9], use_checkerboard=True)

    # MUX 4 (even) runs slots 0,1,2,3; MUX 9 (odd) runs slots 2,3,0,1.
    assert [round_.parallel_qids for round_ in schedule.rounds] == [
        ["12", "5"],
        ["3", "2"],
        ["30", "0"],
        ["7", "17"],
    ]


def test_checkerboard_keeps_slot_rounds_aligned_for_partial_muxes() -> None:
    """A MUX without some slots leaves those rounds empty; its other slots keep their round."""
    context = OrderingContext(
        chip_id="chip-x",
        grid_size=8,
        mux_grid_size=4,
        # MUX 9 (odd) has slots 0-2 and MUX 15 (odd) slots 0-1; MUX 6 (even) has five slots.
        mux_mapping=MuxMapping.from_groups(
            {9: ["38", "36", "39"], 15: ["61", "60"], 6: ["24", "25", "26", "27", "28"]}
        ),
    )

    rounds = CheckerboardOrderingStrategy().generate_rounds(
        [6, 9, 15], ["24", "25", "26", "27", "28", "38", "36", "39", "61", "60"], context
    )

    # Odd MUXes run slot 2 first: MUX 15 has none, so its slot 0 waits for round 2.
    assert rounds == [
        ["24", "39"],
        ["25"],
        ["26", "38", "61"],
        ["27", "36", "60"],
        ["28"],
    ]


def test_simultaneous_spectroscopy_groups_by_local_slot(tmp_path: Path) -> None:
    schedule = _scheduler(tmp_path).generate_simultaneous_spectroscopy_batches_from_mux(
        mux_ids=[9, 4], exclude_qids=["30"]
    )

    assert [(step.step_index, step.parallel_batches) for step in schedule.steps] == [
        (0, [["0", "12"]]),
        (1, [["3", "17"]]),
        (2, [["5"]]),
        (3, [["2", "7"]]),
    ]


def test_mux_info_lists_members_in_slot_order(tmp_path: Path) -> None:
    info = _scheduler(tmp_path).get_mux_info()

    assert info[9]["qids"] == ["0", "17", "5", "2"]
    assert info[4]["qids"] == ["12", "3", "30", "7"]


def test_ordering_strategies_use_the_mapping_slots() -> None:
    context = OrderingContext(
        chip_id="chip-x",
        grid_size=8,
        mux_grid_size=4,
        mux_mapping=MuxMapping.from_groups(GROUPS),
    )

    assert DefaultOrderingStrategy().order_qids_in_mux(9, ["2", "0", "5"], context) == [
        "0",
        "5",
        "2",
    ]
    assert CheckerboardOrderingStrategy().order_qids_in_mux(9, ["0", "17", "5", "2"], context) == [
        "5",
        "2",
        "0",
        "17",
    ]


def test_ordering_context_without_mapping_keeps_legacy_offsets() -> None:
    context = OrderingContext(chip_id="64Qv3", grid_size=8, mux_grid_size=4)

    assert CheckerboardOrderingStrategy().order_qids_in_mux(1, ["4", "5", "6", "7"], context) == [
        "6",
        "7",
        "4",
        "5",
    ]


def test_cr_mux_map_and_fast_pairs_follow_the_topology() -> None:
    mapping = MuxMapping.from_groups(GROUPS)
    qid_to_mux = build_qubit_to_mux_map(_wiring(), mapping)

    assert qid_to_mux == {qid: mux for mux, qids in GROUPS.items() for qid in qids}
    # 0 and 17 share MUX 9 here; by qid // 4 they would be an inter-MUX pair.
    fast, slow = split_fast_slow_pairs(["0-17", "5-12"], qid_to_mux)
    assert fast == ["0-17"]
    assert slow == ["5-12"]


def test_cr_mux_map_without_mapping_keeps_legacy() -> None:
    qid_to_mux = build_qubit_to_mux_map([{"mux": 2, "ctrl": ["A-0"]}])

    assert qid_to_mux == {"8": 2, "9": 2, "10": 2, "11": 2}


def test_cr_scheduler_resolves_the_chip_topology(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from qdash.workflow.engine.scheduler import cr_scheduler as cr_module
    from qdash.workflow.engine.scheduler.cr_scheduler import CRScheduler

    calls: list[str | None] = []

    def resolve(topology_id: str | None) -> MuxMapping:
        calls.append(topology_id)
        return MuxMapping.from_groups(GROUPS)

    monkeypatch.setattr(cr_module, "resolve_topology_mux_mapping", resolve)
    scheduler = CRScheduler("alice", "chip-x", project_id="project-1")
    scheduler._chip = SimpleNamespace(topology_id="synthetic-sparse-layout")  # type: ignore[assignment]

    assert scheduler._resolve_mux_mapping().mux_of("17") == 9
    assert calls == ["synthetic-sparse-layout"]


def test_cr_scheduler_propagates_unusable_topology(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from qdash.workflow.engine.scheduler import cr_scheduler as cr_module
    from qdash.workflow.engine.scheduler.cr_scheduler import CRScheduler

    def resolve(topology_id: str | None) -> MuxMapping:
        raise MuxMappingError(f"Topology {topology_id!r} not found")

    monkeypatch.setattr(cr_module, "resolve_topology_mux_mapping", resolve)
    scheduler = CRScheduler("alice", "chip-x", project_id="project-1")
    scheduler._chip = SimpleNamespace(topology_id="gone")  # type: ignore[assignment]

    with pytest.raises(MuxMappingError):
        scheduler._resolve_mux_mapping()


def test_checkerboard_keeps_single_slot_neighbors_in_different_rounds() -> None:
    """Even MUX 0 = [1] and odd MUX 1 = [4] both use slot 0, which run in different rounds."""
    context = OrderingContext(
        chip_id="chip-x",
        grid_size=8,
        mux_grid_size=4,
        mux_mapping=MuxMapping.from_groups({0: ["1"], 1: ["4"]}),
    )

    rounds = CheckerboardOrderingStrategy().generate_rounds([0, 1], ["1", "4"], context)

    # Even MUXes run slot 0 in round 0; odd MUXes run it in round 2 (order [2, 3, 0, 1]).
    assert rounds == [["1"], ["4"]]
