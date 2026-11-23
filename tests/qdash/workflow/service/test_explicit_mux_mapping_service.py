"""Workflow services use the chip topology's MUX mapping, not qid // 4."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock, patch

import pytest

from qdash.common.execution_resources import ExecutionResourceScope
from qdash.common.mux_mapping import MuxMapping, MuxMappingError
from qdash.workflow.service._internal.scheduling_tasks import (
    _is_mux_representative,
    _should_skip_task_for_qid,
)
from qdash.workflow.service.targets import AllMuxTargets, MuxTargets, QubitTargets

if TYPE_CHECKING:
    from qdash.workflow.service._internal.session import CalibSession

GROUPS = {9: ["0", "17", "5", "2"], 4: ["12", "3", "30", "7"]}


def _mapping() -> MuxMapping:
    return MuxMapping.from_groups(GROUPS)


def test_representative_is_local_slot_zero() -> None:
    mapping = _mapping()

    assert _is_mux_representative("0", mapping)
    assert _is_mux_representative("12", mapping)
    # qid 4 is the legacy MUX 1 representative, but not in this topology.
    with pytest.raises(MuxMappingError):
        _is_mux_representative("4", mapping)
    assert not _is_mux_representative("3", mapping)
    # Legacy mapping keeps qid % 4 and tolerates non-numeric IDs.
    assert _is_mux_representative("8")
    assert not _is_mux_representative("9")
    assert _is_mux_representative("not-a-qid")


def test_mux_task_skip_uses_the_session_mapping() -> None:
    session = cast("CalibSession", SimpleNamespace(mux_mapping=_mapping()))

    with patch(
        "qdash.workflow.calibtasks.active_protocols.is_mux_task", return_value=True
    ) as is_mux_task:
        assert not _should_skip_task_for_qid("CheckResonatorSpectroscopy", "12", "qubex", session)
        assert _should_skip_task_for_qid("CheckResonatorSpectroscopy", "17", "qubex", session)
    assert is_mux_task.call_count == 2

    with patch("qdash.workflow.calibtasks.active_protocols.is_mux_task", return_value=False):
        # Non-MUX tasks never consult the mapping.
        broken = SimpleNamespace()
        assert not _should_skip_task_for_qid("CheckRabi", "17", "qubex", broken)  # type: ignore[arg-type]


def test_mux_targets_pass_the_mapping_to_the_scheduler() -> None:
    mapping = _mapping()
    scheduler = MagicMock()
    scheduler.generate_from_mux.return_value.stages = [SimpleNamespace(qids=["0", "17", "5", "2"])]

    with patch("qdash.workflow.engine.OneQubitScheduler", return_value=scheduler) as scheduler_cls:
        qids = MuxTargets([9]).to_qids("chip-x", mux_mapping=mapping)

    assert qids == ["0", "17", "2", "5"]
    assert scheduler_cls.call_args.kwargs["mux_mapping"] is mapping


def test_all_mux_targets_use_topology_mux_ids() -> None:
    captured: list[list[int]] = []

    def to_qids(self: MuxTargets, chip_id: str, *, mux_mapping: Any = None) -> list[str]:
        captured.append(list(self.mux_ids))
        return []

    with patch.object(MuxTargets, "to_qids", to_qids):
        AllMuxTargets().to_qids("chip-x", mux_mapping=_mapping())
        AllMuxTargets().to_qids("chip-x", mux_mapping=MuxMapping.legacy())
        AllMuxTargets().to_qids("chip-x")

    assert captured == [[4, 9], list(range(16)), list(range(16))]


def test_configure_all_derives_mux_ids_from_the_mapping() -> None:
    from qdash.workflow.service.steps.box_setup import ConfigureAll

    service = SimpleNamespace(chip_id="chip-x", mux_mapping=_mapping())

    mux_ids = ConfigureAll()._resolve_mux_ids(service, QubitTargets(["17", "3", "30"]))  # type: ignore[arg-type]

    assert mux_ids == [4, 9]


def test_qubit_targets_outside_the_topology_fail() -> None:
    from qdash.workflow.service.steps.box_setup import ConfigureAll

    service = SimpleNamespace(chip_id="chip-x", mux_mapping=_mapping())

    with pytest.raises(MuxMappingError):
        ConfigureAll()._resolve_mux_ids(service, QubitTargets(["1"]))  # type: ignore[arg-type]


def test_pipeline_plan_resolves_targets_with_the_mapping() -> None:
    from qdash.workflow.service.pipeline_resources import plan_pipeline_resources
    from qdash.workflow.service.steps import ConfigureAll

    mapping = _mapping()
    calls: list[tuple[dict[str, Any], Any]] = []

    def scope(chip_id: str, parameters: dict[str, Any], *, mux_mapping: Any = None):
        calls.append((parameters, mux_mapping))
        return ExecutionResourceScope(chip_id, (f"p{len(calls)}",))

    with patch("qdash.workflow.service.pipeline_resources.resolve_execution_resource_scope", scope):
        planned = plan_pipeline_resources(
            "chip-x",
            QubitTargets(["17"]),
            [ConfigureAll(mux_ids=[9])],
            mux_mapping=mapping,
        )

    assert [parameters for parameters, _ in calls] == [{"qids": ["17"]}, {"mux_ids": [9]}]
    assert all(used is mapping for _, used in calls)
    assert planned.resources == ("p1", "p2")


def test_pipeline_plan_reserves_the_chip_for_unresolvable_targets() -> None:
    from qdash.workflow.service.pipeline_resources import plan_pipeline_resources

    targets = MagicMock()
    targets.to_qids.side_effect = MuxMappingError("MUX 0 is not defined")

    planned = plan_pipeline_resources("chip-x", targets, [], mux_mapping=_mapping())

    assert planned.exclusive


def _session() -> CalibSession:
    from qdash.workflow.service._internal.session import CalibSession
    from qdash.workflow.service._internal.settings import GitHubPolicy, SessionSettings

    return CalibSession(
        SessionSettings(
            username="alice",
            chip_id="chip-x",
            project_id="project-1",
            backend_name="fake",
            github=GitHubPolicy.disabled(),
        )
    )


def test_calib_session_scope_claims_chip_when_topology_is_unusable() -> None:
    session = _session()

    with patch(
        "qdash.workflow.service._internal.session.resolve_chip_mux_mapping",
        side_effect=MuxMappingError("Topology 'gone' not found"),
    ):
        assert session.resource_scope({"qid": "0"}).exclusive
        with pytest.raises(MuxMappingError):
            _ = session.mux_mapping


def test_calib_session_scope_uses_the_resolved_mapping() -> None:
    session = _session()
    mapping = _mapping()

    with (
        patch(
            "qdash.workflow.service._internal.session.resolve_chip_mux_mapping",
            return_value=mapping,
        ) as resolve,
        patch(
            "qdash.workflow.service._internal.session.resolve_execution_resource_scope",
            return_value=ExecutionResourceScope("chip-x", ("mux:9",)),
        ) as scope,
    ):
        session.resource_scope({"qid": "17"})
        session.resource_scope({"qid": "0"})

    resolve.assert_called_once_with("project-1", "chip-x")
    assert scope.call_args.kwargs["mux_mapping"] is mapping
