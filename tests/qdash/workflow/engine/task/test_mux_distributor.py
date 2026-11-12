"""MUX results fan out to the topology's MUX members."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock, patch

import pytest

from qdash.common.mux_mapping import MuxMapping, MuxMappingError
from qdash.workflow.calibtasks.base import PostProcessResult, RunResult
from qdash.workflow.engine.task.executor import TaskExecutor
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


def test_unpinned_mapping_fails_before_fanout_without_a_chip_lookup() -> None:
    """No pinned mapping: fan-out raises and never reads the chip topology.

    The resolver would succeed now (the topology was repaired after planning),
    but the execution did not plan or reserve that membership.
    """
    distributor = _distributor()
    state_manager = cast("MagicMock", distributor._state_manager)

    with (
        patch(
            "qdash.common.mux_mapping.resolve_chip_mux_mapping",
            return_value=MuxMapping.from_groups({2: ["40", "41"]}),
        ) as resolve,
        patch.object(distributor, "_distribute_to_qid") as distribute_to_qid,
        pytest.raises(MuxMappingError, match="no pinned MUX mapping"),
    ):
        distributor.distribute(MagicMock(), MagicMock(), MagicMock(), MagicMock(), "40")

    resolve.assert_not_called()
    distribute_to_qid.assert_not_called()
    state_manager.ensure_task_exists.assert_not_called()
    assert distributor._mux_mapping is None


def test_pinned_mapping_ignores_a_changed_chip_topology() -> None:
    pinned = MuxMapping.from_groups({2: ["40", "41"]})
    distributor = _distributor(pinned)

    with patch(
        "qdash.common.mux_mapping.resolve_chip_mux_mapping",
        return_value=MuxMapping.from_groups({2: ["40", "41", "42", "43"]}),
    ) as resolve:
        assert _fanout(distributor, "40") == ["41"]

    resolve.assert_not_called()


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


@pytest.mark.parametrize("representative", ["Q12", "012"])
def test_prefixed_representative_gets_no_second_result(representative: str) -> None:
    mapping = MuxMapping.from_groups({9: ["12", "3"]})

    assert _fanout(_distributor(mapping), representative) == ["3"]


def test_execution_mapping_reaches_the_distributor_without_a_chip_lookup() -> None:
    """The orchestrator's mapping flows TaskContext -> TaskExecutor -> MuxDistributor."""
    from qdash.workflow.engine.task.context import TaskContext

    mapping = MuxMapping.from_groups({9: ["12", "3"]})
    context = TaskContext(
        username="alice",
        execution_id="exec-1",
        qids=["12"],
        calib_dir="/tmp/x",
        state_manager=MagicMock(),
        mux_mapping=mapping,
    )
    distributor = context.executor._mux_distributor

    with patch("qdash.common.mux_mapping.resolve_chip_mux_mapping") as resolve:
        assert _fanout(distributor, "12") == ["3"]

    resolve.assert_not_called()


# --------------------------------------------------------------------------- TaskExecutor


class _ProbeTask:
    """Minimal task whose lifecycle calls are recorded."""

    def __init__(self, name: str, task_type: str = "qubit", *, is_mux_level: bool) -> None:
        self.name = name
        self._task_type = task_type
        self.is_mux_level = is_mux_level
        self.r2_threshold = 0.7
        self.backend = "fake"
        self.input_parameters: dict[str, object] = {}
        self.input_parameters_from_snapshot = False
        self.input_overrides: dict[str, object] = {}
        self.run_overrides: dict[str, object] = {}
        self.run_parameters: dict[str, object] = {}
        self.calls: list[str] = []

    def get_name(self) -> str:
        return self.name

    def get_task_type(self) -> str:
        return self._task_type

    def is_qubit_task(self) -> bool:
        return self._task_type == "qubit"

    def is_coupling_task(self) -> bool:
        return self._task_type == "coupling"

    def resolve_run_parameters(self, _backend: object, _qid: str) -> None:
        self.calls.append("resolve_run_parameters")

    def preprocess(self, _backend: object, _qid: str) -> None:
        self.calls.append("preprocess")

    def prepare_run(self, _backend: object, _qid: str) -> None:
        self.calls.append("prepare_run")

    def run(self, _backend: object, _qid: str) -> RunResult:
        self.calls.append("run")
        return RunResult(raw_result={})

    def batch_run(self, _backend: object, qids: list[str]) -> RunResult:
        self.calls.append(f"batch_run:{','.join(qids)}")
        return RunResult(raw_result={})

    def extract_raw_data(self, _run_result: RunResult) -> list[object]:
        return []

    def postprocess(
        self, _backend: object, _execution_id: str, _run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.calls.append(f"postprocess:{qid}")
        return PostProcessResult(output_parameters={})

    def attach_task_id(self, _task_id: str) -> dict[str, object]:
        return {}


def _executor(mux_mapping: MuxMapping | None) -> TaskExecutor:
    executor = TaskExecutor(
        state_manager=MagicMock(),
        calib_dir="/tmp/calib",
        execution_id="exec-1",
        task_manager_id="tm-1",
        result_processor=MagicMock(),
        history_recorder=MagicMock(),
        data_saver=MagicMock(),
        mux_mapping=mux_mapping,
    )
    backend_saver = MagicMock()
    executor._backend_saver = backend_saver
    executor._mux_distributor._backend_saver = backend_saver
    return executor


def _execute(executor: TaskExecutor, task: _ProbeTask, qid: str) -> Any:
    # The probe implements only what execute() calls; the backend is never used.
    return executor.execute(
        cast("Any", task), cast("Any", SimpleNamespace()), qid, execution_service=MagicMock()
    )


def test_unpinned_mux_task_fails_before_running_without_a_chip_lookup() -> None:
    executor = _executor(None)
    task = _ProbeTask("CheckResonatorSpectroscopy", is_mux_level=True)
    state_manager = cast("MagicMock", executor.state_manager)

    with (
        patch(
            "qdash.common.mux_mapping.resolve_chip_mux_mapping",
            return_value=MuxMapping.legacy(),
        ) as resolve,
        pytest.raises(MuxMappingError, match="no pinned MUX mapping"),
    ):
        _execute(executor, task, "0")

    resolve.assert_not_called()
    # Rejected before any hardware work, postprocess or save; recorded once as failed.
    assert task.calls == []
    cast("MagicMock", executor._backend_saver).save.assert_not_called()
    state_manager.update_task_status_to_failed.assert_called_once()
    assert state_manager.update_task_status_to_failed.call_args.args[2:4] == ("qubit", "0")


@pytest.mark.parametrize("task_type", ["system", "global", "qubit"])
def test_unpinned_execution_still_runs_tasks_that_do_not_fan_out(task_type: str) -> None:
    executor = _executor(None)
    task = _ProbeTask("SystemProbe", task_type, is_mux_level=False)

    with patch("qdash.common.mux_mapping.resolve_chip_mux_mapping") as resolve:
        _, result = _execute(executor, task, "0")

    assert result.success
    assert task.calls[-2:] == ["run", "postprocess:0"]
    resolve.assert_not_called()


def test_legacy_pinned_mux_task_fans_out_through_the_executor() -> None:
    executor = _executor(MuxMapping.legacy())
    task = _ProbeTask("CheckResonatorSpectroscopy", is_mux_level=True)

    with patch("qdash.common.mux_mapping.resolve_chip_mux_mapping") as resolve:
        _, result = _execute(executor, task, "4")

    assert result.success
    assert [call for call in task.calls if call.startswith("postprocess")] == [
        "postprocess:4",
        "postprocess:5",
        "postprocess:6",
        "postprocess:7",
    ]
    resolve.assert_not_called()


def _execute_batch(executor: TaskExecutor, task: _ProbeTask, qids: list[str]) -> Any:
    # The probe implements only what execute_batch() calls; the backend is never used.
    return executor.execute_batch(
        cast("Any", task), cast("Any", SimpleNamespace()), qids, execution_service=MagicMock()
    )


def test_unpinned_mux_batch_fails_before_batch_run_without_a_chip_lookup() -> None:
    """execute_batch() holds the same invariant as execute() for MUX-level tasks."""
    executor = _executor(None)
    task = _ProbeTask("CheckResonatorSpectroscopy", is_mux_level=True)
    state_manager = cast("MagicMock", executor.state_manager)

    with (
        patch(
            "qdash.common.mux_mapping.resolve_chip_mux_mapping",
            return_value=MuxMapping.legacy(),
        ) as resolve,
        pytest.raises(MuxMappingError, match="no pinned MUX mapping"),
    ):
        _execute_batch(executor, task, ["4", "5"])

    resolve.assert_not_called()
    # Rejected before parameter resolution, batch_run, postprocess or any save.
    assert task.calls == []
    cast("MagicMock", executor._backend_saver).save.assert_not_called()
    cast("MagicMock", executor.data_saver).save_raw_data.assert_not_called()
    state_manager.put_output_parameters.assert_not_called()
    # Every qid of the batch is recorded as failed exactly once and its run ended.
    failed = [call.args[2:4] for call in state_manager.update_task_status_to_failed.call_args_list]
    assert failed == [("qubit", "4"), ("qubit", "5")]
    ended = [call.args[2] for call in state_manager.end_task.call_args_list]
    assert ended == ["4", "5"]


@pytest.mark.parametrize("task_type", ["system", "global", "qubit"])
def test_unpinned_execution_still_runs_batches_that_do_not_fan_out(task_type: str) -> None:
    executor = _executor(None)
    task = _ProbeTask("BatchProbe", task_type, is_mux_level=False)

    with patch("qdash.common.mux_mapping.resolve_chip_mux_mapping") as resolve:
        _, results = _execute_batch(executor, task, ["0", "4"])

    assert all(result.success for result in results.values())
    assert task.calls[-3:] == ["batch_run:0,4", "postprocess:0", "postprocess:4"]
    resolve.assert_not_called()


def test_pinned_mux_batch_runs_once_and_postprocesses_each_qid() -> None:
    mapping = MuxMapping.from_groups({9: ["12", "3"]})
    executor = _executor(mapping)
    task = _ProbeTask("CheckResonatorSpectroscopy", is_mux_level=True)

    with patch("qdash.common.mux_mapping.resolve_chip_mux_mapping") as resolve:
        _, results = _execute_batch(executor, task, ["12", "3"])

    assert all(result.success for result in results.values())
    assert [call for call in task.calls if not call.startswith("resolve")] == [
        "batch_run:12,3",
        "postprocess:12",
        "postprocess:3",
    ]
    cast("MagicMock", executor.state_manager).update_task_status_to_failed.assert_not_called()
    resolve.assert_not_called()
