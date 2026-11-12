"""MUX results fan out to the topology's MUX members."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock, patch

import pytest

from qdash.common.mux_mapping import MuxMapping, MuxMappingError
from qdash.workflow.engine.task.mux_distributor import MuxDistributor

if TYPE_CHECKING:
    from qdash.workflow.engine.execution.service import ExecutionService


def _distributor(mux_mapping: MuxMapping | None = None) -> MuxDistributor:
    return MuxDistributor(
        state_manager=MagicMock(),
        execution_id="exec-1",
        result_processor=MagicMock(),
        data_saver=MagicMock(),
        history_recorder=MagicMock(),
        backend_saver=MagicMock(),
        mux_mapping=mux_mapping,
    )


def _fanout(distributor: MuxDistributor, representative_qid: str) -> list[str]:
    targets: list[str] = []
    execution_service = cast(
        "ExecutionService", SimpleNamespace(project_id="project-1", chip_id="chip-x")
    )
    with patch.object(
        distributor,
        "_distribute_to_qid",
        side_effect=lambda _task, _backend, _service, _result, qid, **_kwargs: targets.append(qid),
    ):
        distributor.distribute(
            MagicMock(), MagicMock(), execution_service, MagicMock(), representative_qid
        )
    return targets


def test_fans_out_to_explicit_noncontiguous_members() -> None:
    mapping = MuxMapping.from_groups({9: ["12", "3", "30", "7"]})

    assert _fanout(_distributor(mapping), "12") == ["3", "30", "7"]


def test_unknown_representative_raises_for_explicit_mapping() -> None:
    mapping = MuxMapping.from_groups({9: ["12", "3", "30", "7"]})

    with pytest.raises(MuxMappingError):
        _fanout(_distributor(mapping), "0")


def test_resolves_mapping_from_the_execution_chip() -> None:
    mapping = MuxMapping.from_groups({2: ["40", "41"]})
    distributor = _distributor()

    with patch(
        "qdash.workflow.engine.task.mux_distributor.resolve_chip_mux_mapping",
        return_value=mapping,
    ) as resolve:
        assert _fanout(distributor, "40") == ["41"]
        assert _fanout(distributor, "41") == ["40"]

    resolve.assert_called_once_with("project-1", "chip-x")


def test_legacy_mapping_keeps_four_qubit_blocks() -> None:
    assert _fanout(_distributor(MuxMapping.legacy()), "8") == ["9", "10", "11"]
    assert _fanout(_distributor(MuxMapping.legacy()), "not-a-qid") == []


def test_standalone_representative_never_fans_out() -> None:
    mapping = MuxMapping.from_groups({9: ["12", "3"]}, known_qids=["12", "3", "5"])

    # Qubit 5 is known but in no MUX: no MUX to fan out to, and no guessed one.
    with pytest.raises(MuxMappingError, match="standalone"):
        _fanout(_distributor(mapping), "5")
    # Partial MUXes fan out to their declared members only.
    assert _fanout(_distributor(mapping), "3") == ["12"]


def test_fanout_keeps_the_representative_invocation() -> None:
    mapping = MuxMapping.from_groups({9: ["12", "3"]})
    distributor = _distributor(mapping)
    invocation = object()
    state_manager = cast("MagicMock", distributor._state_manager)
    state_manager.get_task.return_value = SimpleNamespace(invocation=invocation)
    execution_service = cast(
        "ExecutionService", SimpleNamespace(project_id="project-1", chip_id="chip-x")
    )

    with patch.object(distributor, "_distribute_to_qid") as distribute_to_qid:
        distributor.distribute(MagicMock(), MagicMock(), execution_service, MagicMock(), "12")

    distribute_to_qid.assert_called_once()
    assert distribute_to_qid.call_args.args[4] == "3"
    assert distribute_to_qid.call_args.kwargs["invocation"] is invocation
