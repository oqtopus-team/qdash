"""Schedulers keep standalone (non-multiplexed) qubits and run them conservatively.

A standalone qubit is a known qubit that the chip topology lists in no MUX.
``wiring.yaml`` maps only MUXes to hardware, so the schedulers never drop
such a qubit, never put it in a MUX, and never run it in parallel with other
work.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest
import yaml

from qdash.common.mux_mapping import MuxMapping, MuxMappingError
from qdash.workflow.engine.scheduler.cr_scheduler import CRScheduler
from qdash.workflow.engine.scheduler.cr_utils import (
    group_cr_pairs_by_conflict,
    split_fast_slow_pairs,
)
from qdash.workflow.engine.scheduler.one_qubit_scheduler import OneQubitScheduler
from qdash.workflow.engine.scheduler.one_qubit_types import BOX_STANDALONE

if TYPE_CHECKING:
    from pathlib import Path

# MUX 9 lists slots out of qubit order; 6, 1 and 20 are standalone.
GROUPS = {9: ["0", "17", "5", "2"], 4: ["12", "3"]}
KNOWN = ["0", "1", "2", "3", "5", "6", "12", "17", "20"]
STANDALONE = ["1", "6", "20"]


def _wiring() -> list[dict[str, Any]]:
    return [
        {"mux": 9, "ctrl": [f"Q73A-{i}" for i in range(4)], "read_out": "Q73A-8"},
        {"mux": 4, "ctrl": [f"S159A-{i}" for i in range(4)], "read_out": "S159A-8"},
    ]


def _mapping() -> MuxMapping:
    return MuxMapping.from_groups(GROUPS, known_qids=KNOWN)


def _scheduler(tmp_path: Path, mapping: MuxMapping | None = None) -> OneQubitScheduler:
    path = tmp_path / "wiring.yaml"
    path.write_text(yaml.safe_dump({"chip-x": _wiring()}))
    return OneQubitScheduler(
        chip_id="chip-x", wiring_config_path=path, mux_mapping=mapping or _mapping()
    )


# ------------------------------------------------------------------ 1-qubit


def test_mixed_targets_keep_standalone_qubits_in_a_final_sequential_stage(
    tmp_path: Path,
) -> None:
    schedule = _scheduler(tmp_path).generate(qids=["20", "17", "0", "6", "12"])

    assert [stage.box_type for stage in schedule.stages] == ["A", BOX_STANDALONE]
    mux_stage, standalone_stage = schedule.stages
    assert mux_stage.parallel_groups == [["12"], ["0", "17"]]
    # One group: the standalone qubits run one at a time, in qubit order.
    assert standalone_stage.qids == ["6", "20"]
    assert standalone_stage.parallel_groups == [["6", "20"]]
    assert standalone_stage.mux_ids == set()
    assert "6" not in schedule.qid_to_mux
    assert schedule.metadata["standalone_count"] == 2


def test_all_standalone_targets_need_no_wiring(tmp_path: Path) -> None:
    mapping = MuxMapping.from_groups({}, known_qids=["0", "1", "2"])
    scheduler = OneQubitScheduler(
        chip_id="chip-x",
        wiring_config_path=tmp_path / "missing-wiring.yaml",
        mux_mapping=mapping,
    )

    schedule = scheduler.generate(qids=["2", "0"])
    synchronized = scheduler.generate_synchronized(qids=["2", "0"])
    batches = scheduler.generate_simultaneous_spectroscopy_batches(qids=["2", "0"], mode="all")

    assert [(s.box_type, s.parallel_groups) for s in schedule.stages] == [
        (BOX_STANDALONE, [["0", "2"]])
    ]
    assert [(s.box_type, s.parallel_qids) for s in synchronized.steps] == [
        (BOX_STANDALONE, ["0"]),
        (BOX_STANDALONE, ["2"]),
    ]
    assert [s.parallel_batches for s in batches.steps] == [[["0"]], [["2"]]]


def test_from_mux_adds_standalone_qubits_and_rejects_multiplexed_ones(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path)

    schedule = scheduler.generate_from_mux(
        mux_ids=[4], exclude_qids=["20"], standalone_qids=["20", "1"]
    )

    assert [stage.qids for stage in schedule.stages] == [["12", "3"], ["1"]]
    with pytest.raises(MuxMappingError, match="not standalone"):
        scheduler.generate_from_mux(mux_ids=[4], standalone_qids=["17"])
    # Standalone qubits alone are a valid target without any MUX.
    only_standalone = scheduler.generate_from_mux(mux_ids=[], standalone_qids=STANDALONE)
    assert [stage.box_type for stage in only_standalone.stages] == [BOX_STANDALONE]


def test_unknown_qubits_are_rejected_not_treated_as_standalone(tmp_path: Path) -> None:
    with pytest.raises(MuxMappingError, match="not defined"):
        _scheduler(tmp_path).generate(qids=["0", "99"])


def test_synchronized_runs_one_standalone_qubit_per_step_after_mux_steps(
    tmp_path: Path,
) -> None:
    schedule = _scheduler(tmp_path).generate_synchronized_from_mux(
        mux_ids=[4, 9], use_checkerboard=False, standalone_qids=["6", "1"]
    )

    assert [(step.box_type, step.parallel_qids) for step in schedule.steps] == [
        ("A", ["12", "0"]),
        ("A", ["3", "17"]),
        ("A", ["5"]),
        ("A", ["2"]),
        (BOX_STANDALONE, ["1"]),
        (BOX_STANDALONE, ["6"]),
    ]
    assert [step.step_index for step in schedule.steps] == list(range(6))


@pytest.mark.parametrize("mode", ["local_index", "all"])
def test_spectroscopy_batches_isolate_standalone_qubits(tmp_path: Path, mode: str) -> None:
    schedule = _scheduler(tmp_path).generate_simultaneous_spectroscopy_batches(
        qids=["17", "6", "12", "20"], mode=mode
    )

    standalone_steps = [step for step in schedule.steps if step.box_type == BOX_STANDALONE]
    assert [step.parallel_batches for step in standalone_steps] == [[["6"]], [["20"]]]
    mux_qids = [
        qid
        for step in schedule.steps
        if step.box_type != BOX_STANDALONE
        for batch in step.parallel_batches
        for qid in batch
    ]
    assert sorted(mux_qids, key=int) == ["12", "17"]
    indices = [step.step_index for step in schedule.steps]
    assert len(set(indices)) == len(indices)


# ------------------------------------------------------------------- CR pairs


def test_two_standalone_qubits_are_not_the_same_mux() -> None:
    qid_to_mux = {"0": 9, "17": 9}

    fast, slow = split_fast_slow_pairs(["0-17", "1-6", "0-6"], qid_to_mux)

    # None == None must not make the standalone pair intra-MUX.
    assert fast == ["0-17"]
    assert slow == ["1-6", "0-6"]


def test_pairs_with_standalone_qubits_never_share_a_group() -> None:
    qid_to_mux = {"0": 9, "17": 9, "12": 4, "3": 4}

    groups = group_cr_pairs_by_conflict(["0-17", "12-3", "1-6", "20-5"], qid_to_mux, {})

    together = next(group for group in groups if "0-17" in group)
    assert "12-3" in together
    assert [group for group in groups if "1-6" in group] == [["1-6"]]
    assert [group for group in groups if "20-5" in group] == [["20-5"]]


def _cr_scheduler(
    tmp_path: Path, mapping: MuxMapping, couplings: list[str], *, wiring: bool = True
) -> CRScheduler:
    path = tmp_path / "wiring.yaml"
    if wiring:
        path.write_text(yaml.safe_dump({"chip-x": _wiring()}))
    scheduler = CRScheduler(
        username="alice",
        chip_id="chip-x",
        wiring_config_path=str(path),
        mux_mapping=mapping,
    )
    chip = MagicMock()
    chip.topology_id = None
    scheduler._chip = chip
    qids = sorted({qid for pair in couplings for qid in pair.split("-")}, key=int)
    # Increasing frequency with qubit ID: every listed control < target pair passes.
    scheduler._qubit_models = {
        qid: MagicMock(data={"qubit_frequency": {"value": 5.0 + int(qid) / 100}}) for qid in qids
    }
    scheduler._load_coupling_ids = lambda: couplings  # type: ignore[method-assign]
    return scheduler


def test_cr_schedule_keeps_standalone_pairs_one_per_group(tmp_path: Path) -> None:
    couplings = ["0-17", "3-12", "1-6", "5-20", "2-99"]
    mapping = _mapping()

    schedule = _cr_scheduler(tmp_path, mapping, couplings).generate()

    groups = [sorted(f"{c}-{t}" for c, t in group) for group in schedule.parallel_groups]
    assert ["1-6"] in groups
    assert ["5-20"] in groups
    scheduled = {pair for group in groups for pair in group}
    # 99 is not a known qubit, so its pair is filtered; the others are kept.
    assert scheduled == {"0-17", "3-12", "1-6", "5-20"}
    assert schedule.metadata["fast_pairs"] == 2


def test_cr_schedule_without_any_mux_needs_no_wiring(tmp_path: Path) -> None:
    mapping = MuxMapping.from_groups({}, known_qids=["0", "1", "2", "3"])

    schedule = _cr_scheduler(tmp_path, mapping, ["0-1", "2-3"], wiring=False).generate()

    assert sorted(schedule.parallel_groups) == [[("0", "1")], [("2", "3")]]
    assert schedule.metadata["fast_pairs"] == 0


def test_selected_pairs_use_the_topology_and_keep_standalone_pairs(tmp_path: Path) -> None:
    couplings = ["0-17", "3-12", "1-6", "5-20", "2-99"]
    scheduler = _cr_scheduler(tmp_path, _mapping(), couplings)

    schedule = scheduler.schedule_pairs([("0", "17"), ("3", "12"), ("1", "6"), ("5", "20")])

    groups = [sorted(f"{c}-{t}" for c, t in group) for group in schedule.parallel_groups]
    # Topology MUX members are intra-MUX (0 and 17 are both in MUX 9, not qid // 4).
    assert schedule.metadata["fast_pairs"] == 2
    assert ["1-6"] in groups
    assert ["5-20"] in groups
    with pytest.raises(ValueError, match="missing from the wiring"):
        scheduler.schedule_pairs([("2", "99")])


def test_selected_pairs_without_any_mux_need_no_wiring(tmp_path: Path) -> None:
    mapping = MuxMapping.from_groups({}, known_qids=["0", "1", "2", "3"])
    scheduler = _cr_scheduler(tmp_path, mapping, ["0-1", "2-3"], wiring=False)

    schedule = scheduler.schedule_pairs([("0", "1"), ("2", "3")])

    assert sorted(schedule.parallel_groups) == [[("0", "1")], [("2", "3")]]
