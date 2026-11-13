from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from qdash.datamodel.task_call import TaskCall
from qdash.workflow.service.steps.one_qubit import CustomOneQubit

if TYPE_CHECKING:
    from qdash.workflow.service._internal.session import CalibSession


def test_custom_one_qubit_direct_targets_reuse_step_execution(monkeypatch) -> None:
    from unittest.mock import MagicMock

    run = MagicMock(return_value={"1": {"status": "success"}})
    spec = object()
    monkeypatch.setattr(
        "qdash.workflow.service._internal.scheduling_tasks.run_qubit_calibrations_parallel",
        run,
    )
    session = SimpleNamespace(
        chip_id="64Qv3",
        worker_spec=MagicMock(return_value=spec),
        record_stage_result=MagicMock(),
        finish_calibration=MagicMock(side_effect=AssertionError("pipeline owns completion")),
    )
    step = CustomOneQubit(step_name="simple_tasks", tasks=[TaskCall(name="CheckRabi")])
    result = step._execute_direct(cast("CalibSession", session), ["1"])

    assert result == {"direct": {"1": {"status": "success"}}}
    # Workers receive the step session's spec and borrow its Execution.
    assert run.call_args.kwargs["worker"] is spec
    assert run.call_args.kwargs["plan"].step_id == "simple_tasks"
    session.record_stage_result.assert_called_once_with("simple_tasks", result)
    session.finish_calibration.assert_not_called()


def test_custom_one_qubit_qubit_targets_use_scheduled_strategy(monkeypatch) -> None:
    from qdash.workflow.service.steps.pipeline import StepContext
    from qdash.workflow.service.targets import QubitTargets

    calls = []

    class FakeStrategy:
        def execute(self, session, config):
            calls.append(config)
            return {"scheduled": {"1": {"status": "success"}, "4": {"status": "success"}}}

    monkeypatch.setattr(
        "qdash.workflow.service.strategy.get_one_qubit_strategy",
        lambda mode: FakeStrategy(),
    )

    session = SimpleNamespace(
        username="alice",
        chip_id="64Qv3",
        backend_name="qubex",
        project_id="project-1",
        default_run_parameters={},
        task_parameters={},
        tags=[],
        flow_name="simple_calibration",
        note={},
    )
    step = CustomOneQubit(
        step_name="simple_tasks",
        tasks=[TaskCall(name="Configure", on_failure="stop"), TaskCall(name="CheckRabi")],
        mode="scheduled",
        continue_on_failure=True,
    )

    step.execute(cast("CalibSession", session), QubitTargets(["1", "4"]), StepContext())

    assert len(calls) == 1
    assert calls[0].mux_ids == [0, 1]
    assert calls[0].qids == ["1", "4"]
    assert calls[0].tasks == ["Configure", "CheckRabi"]
    assert calls[0].plan.continue_on_failure is True
    assert [call.on_failure for call in calls[0].plan.calls] == ["stop", None]


def test_one_qubit_check_qubit_targets_use_scheduled_strategy(monkeypatch) -> None:
    from qdash.workflow.service.steps.one_qubit import OneQubitCheck
    from qdash.workflow.service.steps.pipeline import StepContext
    from qdash.workflow.service.targets import QubitTargets

    calls = []

    class FakeStrategy:
        def execute(self, session, config):
            calls.append(config)
            return {"scheduled": {"2": {"status": "success"}, "5": {"status": "success"}}}

    monkeypatch.setattr(
        "qdash.workflow.service.strategy.get_one_qubit_strategy",
        lambda mode: FakeStrategy(),
    )

    session = SimpleNamespace(
        username="alice",
        chip_id="64Qv3",
        backend_name="qubex",
        project_id="project-1",
        default_run_parameters={},
        task_parameters={},
        tags=[],
        flow_name="one_qubit",
        note={},
    )
    step = OneQubitCheck(mode="synchronized", tasks=[TaskCall(name="CheckRabi")])

    step.execute(cast("CalibSession", session), QubitTargets(["2", "5"]), StepContext())

    assert len(calls) == 1
    assert calls[0].mux_ids == [0, 1]
    assert calls[0].qids == ["2", "5"]
    assert calls[0].tasks == ["CheckRabi"]


@pytest.mark.parametrize("successful_qids", [[], ["1"]])
def test_fine_tune_respects_coarse_status_filter(monkeypatch, successful_qids) -> None:
    from unittest.mock import MagicMock

    from qdash.workflow.service.results import OneQubitResult, QubitCalibData
    from qdash.workflow.service.steps import FilterByStatus, OneQubitFineTune, StepContext
    from qdash.workflow.service.targets import QubitTargets

    coarse_result = OneQubitResult()
    for qid in ["0", "1"]:
        coarse_result.add_qubit(
            qid, QubitCalibData(status="success" if qid in successful_qids else "failed")
        )
    ctx = StepContext(candidate_qids=["0", "1"], one_qubit_check=coarse_result)
    session = cast("CalibSession", SimpleNamespace(chip_id="64Q"))
    targets = QubitTargets(["0", "1"])
    ctx = FilterByStatus().execute(session, targets, ctx)
    execute = MagicMock(return_value={})
    step = OneQubitFineTune()
    monkeypatch.setattr(step, "_execute_with_qids", execute)

    step.execute(session, targets, ctx)

    if successful_qids:
        assert execute.call_args.args[1] == successful_qids
    else:
        execute.assert_not_called()
        assert ctx.one_qubit_fine_tune is not None
        assert ctx.one_qubit_fine_tune.qubits == {}


def test_qubit_targets_of_a_backend_without_wiring_run_directly(monkeypatch) -> None:
    """The Qibocal emulator has no MUXes or boxes; its qubits skip the wiring scheduler."""
    from unittest.mock import MagicMock

    from qdash.workflow.service.steps.pipeline import StepContext
    from qdash.workflow.service.targets import QubitTargets

    monkeypatch.setattr(
        "qdash.workflow.service.strategy.get_one_qubit_strategy",
        MagicMock(side_effect=AssertionError("no wiring scheduler for qibocal")),
    )
    run = MagicMock(return_value={"0": {"status": "success"}})
    monkeypatch.setattr(
        "qdash.workflow.service._internal.scheduling_tasks.run_qubit_calibrations_parallel",
        run,
    )
    session = SimpleNamespace(
        chip_id="QIBOCAL",
        backend_name="qibocal",
        worker_spec=MagicMock(return_value=object()),
        record_stage_result=MagicMock(),
    )
    step = CustomOneQubit(
        step_name="qibocal", tasks=[TaskCall(name="QibocalRabiAmplitude")], mode="serial"
    )

    step.execute(cast("CalibSession", session), QubitTargets(["0"]), StepContext())

    assert run.call_args.kwargs["qids"] == ["0"]
    session.record_stage_result.assert_called_once_with(
        "qibocal", {"direct": {"0": {"status": "success"}}}
    )


def test_mux_targets_are_rejected_on_a_backend_without_wiring() -> None:
    from qdash.workflow.service.steps.pipeline import StepContext
    from qdash.workflow.service.targets import MuxTargets

    session = SimpleNamespace(chip_id="QIBOCAL", backend_name="qibocal")
    step = CustomOneQubit(step_name="qibocal", tasks=[TaskCall(name="QibocalRabiAmplitude")])

    with pytest.raises(ValueError, match="no MUX wiring; target qubits with qids"):
        step.execute(cast("CalibSession", session), MuxTargets(mux_ids=[0]), StepContext())
